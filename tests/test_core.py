"""Each core function checked on a tiny example worked out by hand."""
from datetime import date

import pandas as pd
import pytest

from core import db
from core.analysis import baselines, changeover_summary, fmt_min, load_logs, pareto
from core.matrix import as_lookup, build_matrix, rule_estimate
from core.optimizer import Order, evaluate, optimise
from core.rules import run_rules
from core.scheduler import Task, schedule, sequential_minutes
from data.seed_sample import seed


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    seed(c, today=date(2026, 11, 24))
    yield c
    c.close()


def test_fmt_min():
    assert fmt_min(272) == "4 h 32 m"
    assert fmt_min(45) == "45 m"
    assert fmt_min(-25) == "−25 m"


def test_pareto_hand_example():
    logs = pd.DataFrame({"activity": ["A", "A", "B", "C"], "duration_min": [50, 30, 15, 5], "line_stopped": [1, 1, 1, 1]})
    p = pareto(logs)
    assert list(p["activity"]) == ["A", "B", "C"]
    assert p["share"].round(2).tolist() == [0.8, 0.15, 0.05]
    # A alone reaches 80 %, so only A is a bottleneck
    assert p["bottleneck"].tolist() == [True, False, False]


def test_rule_matrix():
    s = {"matrix_base_min": 220, "matrix_k_min": 35, "matrix_allergen_min": 60}
    assert rule_estimate(1, 5, False, s) == 220          # light -> dark
    assert rule_estimate(5, 2, False, s) == 220 + 105    # dark -> light, drop 3
    assert rule_estimate(2, 3, True, s) == 280           # allergen penalty


def test_optimizer_prefers_light_to_dark():
    cost = {}
    inten = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    for a in inten:
        for b in inten:
            if a != b:
                cost[(a, b)] = 220 + 35 * max(0, inten[a] - inten[b])
    orders = [Order(5, "Cola", 100), Order(2, "Orange", 100), Order(4, "Jeera", 100), Order(3, "Mango", 100)]
    best = optimise(1, orders, cost, 1200, "Lemon")
    assert [o.name for o in best.sequence] == ["Orange", "Mango", "Jeera", "Cola"]
    assert best.changeover_min == 880
    assert evaluate(1, orders, cost, 1200).changeover_min == 220 + 325 + 220 + 255


def test_optimizer_respects_priority_and_due():
    cost = {(a, b): 10 * abs(a - b) for a in range(4) for b in range(4) if a != b}
    orders = [Order(1, "x", 60), Order(3, "z", 60, priority=1), Order(2, "y", 60)]
    best = optimise(0, orders, cost, 60)
    assert best.sequence[0].name == "z"
    late = optimise(0, [Order(1, "x", 600, due_min=5)], cost, 60)
    assert late.feasible is False


def test_two_opt_matches_brute_force_on_nine():
    import core.optimizer as opt
    cost = {(a, b): (a * 7 + b * 3) % 11 + abs(a - b) for a in range(10) for b in range(10) if a != b}
    orders = [Order(i, str(i), 10) for i in range(1, 10)]
    heuristic = optimise(0, orders, cost, 60)
    old = opt.BRUTE_FORCE_LIMIT
    opt.BRUTE_FORCE_LIMIT = 9
    try:
        exact = optimise(0, orders, cost, 60)
    finally:
        opt.BRUTE_FORCE_LIMIT = old
    assert heuristic.changeover_min <= exact.changeover_min * 1.15


def test_scheduler_keeps_dependencies():
    tasks = [Task(1, "Drain", 24), Task(2, "Syrup", 48, external=True), Task(3, "CIP", 72, depends_on=(1,)),
             Task(4, "Rinse", 40, depends_on=(3,)), Task(5, "Nozzles", 30), Task(6, "QC", 22, depends_on=(4, 2))]
    slots, stop = schedule(tasks, crew=3)
    at = {s.task: s for s in slots}
    assert at["Syrup"].end <= 0                     # done before the stop
    assert at["CIP"].start >= at["Drain"].end
    assert at["Rinse"].start >= at["CIP"].end
    assert at["QC"].start >= at["Rinse"].end
    assert stop == pytest.approx(24 + 72 + 40 + 22)
    assert at["Drain"].critical and at["QC"].critical and not at["Nozzles"].critical
    assert sequential_minutes(tasks) == 24 + 72 + 40 + 30 + 22
    assert tasks[5].depends_on == (4, 2)             # caller's tasks unchanged


def test_one_person_does_everything_in_order():
    tasks = [Task(1, "a", 10), Task(2, "b", 5, depends_on=(1,)), Task(3, "c", 7)]
    _, stop = schedule(tasks, crew=1)
    assert stop == 22


def test_sample_data_pipeline(con):
    logs = load_logs(con)
    summary = changeover_summary(con, logs)
    assert len(summary) == 12
    assert (summary["stop_min"] > 0).all()
    at = db.df(con, "SELECT * FROM activity_types")
    base = baselines(logs, at)
    assert set(base["source"]) == {"history"}
    recs = run_rules(logs, summary, base, db.settings(con))
    codes = {r["rule_code"] for r in recs}
    assert {"R2", "R5"} <= codes
    m = build_matrix(db.df(con, "SELECT * FROM flavours"), summary, db.settings(con))
    assert len(m) == 20 and set(m["source"]) <= {"rule", "history"}
    assert len(as_lookup(m)) == 20


def test_bad_rows_are_dropped(con):
    con.execute("INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, end_ts) VALUES "
                "(1, 1, '2026-11-01 10:00:00', '2026-11-01 09:00:00')")
    logs = load_logs(con)
    assert (logs["duration_min"] > 0).all()
