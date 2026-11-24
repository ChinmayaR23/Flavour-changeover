"""Glue between the database and the planning logic (matrix, optimizer, scheduler)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from core import db
from core.analysis import baselines, changeover_summary, load_logs
from core.matrix import as_lookup, build_matrix
from core.optimizer import Order, Plan, evaluate, optimise
from core.predict import pair_predictor, train
from core.scheduler import Task, schedule, sequential_minutes


@dataclass
class Context:
    flavours: pd.DataFrame
    activity_types: pd.DataFrame
    logs: pd.DataFrame
    summary: pd.DataFrame
    base: pd.DataFrame
    settings: dict
    matrix: pd.DataFrame
    cost: dict
    line: dict


def context(con, line_id: int) -> Context:
    s = db.settings(con)
    flavours = db.df(con, "SELECT * FROM flavours ORDER BY colour_intensity, name")
    at = db.df(con, "SELECT * FROM activity_types ORDER BY sort_order, id")
    logs = load_logs(con)
    logs = logs[logs["line_id"] == line_id] if not logs.empty else logs
    summary = changeover_summary(con, logs)
    if not summary.empty:
        summary = summary[summary["line_id"] == line_id]
    base = baselines(logs, at, int(s.get("min_history", 5)))
    status = train(summary, int(s.get("ai_min_changeovers", 30)))
    line = dict(con.execute("SELECT * FROM lines WHERE id = ?", (line_id,)).fetchone() or {})
    m = build_matrix(flavours, summary, s, pair_predictor(status, line.get("crew_size", 3), line_id))
    return Context(flavours, at, logs, summary, base, s, m, as_lookup(m), line)


def tasks(ctx: Context) -> list[Task]:
    usual = ctx.base.set_index("activity_type_id")["usual_min"].to_dict()
    out = []
    for r in ctx.activity_types.itertuples():
        deps = tuple(int(x) for x in str(r.depends_on).split(",") if x.strip())
        out.append(Task(int(r.id), r.name, float(usual.get(r.id, r.std_min)), bool(r.can_be_external), deps))
    return out


def task_plan(ctx: Context, crew: int):
    t = tasks(ctx)
    slots, stop = schedule(t, crew)
    today_style = sequential_minutes([Task(x.id, x.name, x.minutes) for x in t])  # all inside the stop
    return slots, stop, today_style


def planned_for_pair(ctx: Context, usual_min: float, crew: int) -> float:
    """Usual minutes for the pair, minus what the task plan saves."""
    _, stop, seq = task_plan(ctx, crew)
    return max(0.4 * usual_min, usual_min - (seq - stop))


def current_flavour(con, line_id: int) -> tuple[int, str] | None:
    r = con.execute(
        """SELECT f.id, f.name FROM changeovers c JOIN flavours f ON f.id = c.to_flavour_id
           WHERE c.line_id = ? ORDER BY c.line_stop_ts DESC LIMIT 1""", (line_id,)).fetchone()
    return (r["id"], r["name"]) if r else None


def _due_minutes(due: str, start_hour: float) -> float | None:
    due = (due or "").strip()
    if not due:
        return None
    h, m = (int(x) for x in due.split(":"))
    return (h - start_hour) * 60 + m


def orders_for(con, ctx: Context, line_id: int, day: str) -> list[Order]:
    names = dict(zip(ctx.flavours["id"], ctx.flavours["name"]))
    rows = db.df(con, "SELECT * FROM production_orders WHERE line_id = ? AND date = ? ORDER BY id", (line_id, day))
    start = ctx.settings.get("shift_start_hour", 6)
    return [Order(int(r.flavour_id), names[r.flavour_id], int(r.qty_cases), _due_minutes(r.due_time, start),
                  int(r.priority)) for r in rows.itertuples()]


def next_order_date(con, line_id: int) -> str | None:
    r = con.execute("SELECT MIN(date) FROM production_orders WHERE line_id = ? AND date >= ?",
                    (line_id, date.today().isoformat())).fetchone()
    return r[0] if r and r[0] else None


def plans(ctx: Context, start: tuple[int, str], orders: list[Order]) -> tuple[Plan, Plan]:
    rate = float(ctx.line.get("cases_per_hour", 1200))
    entered = evaluate(start[0], orders, ctx.cost, rate, start[1])
    best = optimise(start[0], orders, ctx.cost, rate, start[1])
    return entered, best


def first_changeover(plan: Plan, start: tuple[int, str]):
    """The first real flavour change in a plan: ((from_id, from_name), order), or None."""
    prev = start
    for o in plan.sequence:
        if o.flavour_id != prev[0]:
            return prev, o
        prev = (o.flavour_id, o.name)
    return None
