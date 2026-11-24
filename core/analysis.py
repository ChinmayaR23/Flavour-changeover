"""Logic 1-3: durations, usual time per step, bottleneck ranking (Pareto)."""
from __future__ import annotations

import pandas as pd

LOGS_SQL = """
SELECT l.id, l.changeover_id, l.activity_type_id, a.name AS activity, a.category,
       a.can_be_external, a.std_min, l.start_ts, l.end_ts, l.line_stopped,
       l.operator, l.delay_reason, l.delay_min, l.notes,
       c.line_id, c.date, c.shift, c.crew_count, c.is_sample,
       ff.name AS from_flavour, tf.name AS to_flavour,
       ff.colour_intensity AS from_intensity, tf.colour_intensity AS to_intensity,
       ff.has_allergen AS from_allergen
FROM activity_logs l
JOIN activity_types a ON a.id = l.activity_type_id
JOIN changeovers c ON c.id = l.changeover_id
JOIN flavours ff ON ff.id = c.from_flavour_id
JOIN flavours tf ON tf.id = c.to_flavour_id
"""

CHANGEOVERS_SQL = """
SELECT c.*, ff.name AS from_flavour, tf.name AS to_flavour,
       ff.colour_intensity AS from_intensity, tf.colour_intensity AS to_intensity,
       ff.has_allergen AS from_allergen
FROM changeovers c
JOIN flavours ff ON ff.id = c.from_flavour_id
JOIN flavours tf ON tf.id = c.to_flavour_id
"""


def load_logs(con) -> pd.DataFrame:
    """Logic 1: every finished step with its duration in minutes."""
    d = pd.read_sql_query(LOGS_SQL, con)
    d["start_ts"] = pd.to_datetime(d["start_ts"])
    d["end_ts"] = pd.to_datetime(d["end_ts"])
    d = d.dropna(subset=["end_ts"])
    d["duration_min"] = (d["end_ts"] - d["start_ts"]).dt.total_seconds() / 60
    # reject impossible rows rather than let them skew the numbers
    d = d[(d["duration_min"] > 0) & (d["duration_min"] <= 600)].copy()
    d["date"] = pd.to_datetime(d["date"])
    return d


def changeover_summary(con, logs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Logic 1: stop time, work content and overlap for each finished changeover."""
    c = pd.read_sql_query(CHANGEOVERS_SQL, con)
    c = c.dropna(subset=["line_restart_ts"]).copy()
    if c.empty:
        return c.assign(stop_min=[], work_min=[], parallel_ratio=[], colour_drop=[])
    c["line_stop_ts"] = pd.to_datetime(c["line_stop_ts"])
    c["line_restart_ts"] = pd.to_datetime(c["line_restart_ts"])
    c["date"] = pd.to_datetime(c["date"])
    c["stop_min"] = (c["line_restart_ts"] - c["line_stop_ts"]).dt.total_seconds() / 60
    logs = load_logs(con) if logs is None else logs
    stopped = logs[logs["line_stopped"] == 1]
    work = stopped.groupby("changeover_id")["duration_min"].sum()
    c["work_min"] = c["id"].map(work).fillna(0)
    c["parallel_ratio"] = (c["work_min"] / c["stop_min"]).round(2)
    c["colour_drop"] = (c["from_intensity"] - c["to_intensity"]).clip(lower=0)
    c["pair"] = c["from_flavour"] + " → " + c["to_flavour"]
    return c.sort_values("line_stop_ts")


def baselines(logs: pd.DataFrame, activity_types: pd.DataFrame, min_history: int = 5,
              window: int = 20) -> pd.DataFrame:
    """Logic 2: usual time (median of the last `window` logs) for every step."""
    rows = []
    for _, at in activity_types.iterrows():
        last = (logs[logs["activity_type_id"] == at["id"]]
                .sort_values("start_ts").tail(window)["duration_min"])
        n = len(last)
        if n >= min_history:
            usual, p75, src = last.median(), last.quantile(0.75), "history"
        else:
            usual, p75, src = float(at["std_min"]), float(at["std_min"]), "planned"
        cv = float(last.std(ddof=0) / last.mean()) if n >= 2 and last.mean() > 0 else 0.0
        rows.append({"activity_type_id": at["id"], "activity": at["name"], "usual_min": round(usual, 1),
                     "p75_min": round(p75, 1), "cv": round(cv, 2), "n": n, "source": src})
    return pd.DataFrame(rows)


def pareto(logs: pd.DataFrame, line_stopped_only: bool = True) -> pd.DataFrame:
    """Logic 3: steps ranked by total minutes, with share and cumulative share."""
    d = logs[logs["line_stopped"] == 1] if line_stopped_only else logs
    if d.empty:
        return pd.DataFrame(columns=["activity", "total_min", "share", "cum_share", "bottleneck"])
    t = (d.groupby("activity")["duration_min"].sum().sort_values(ascending=False)
         .rename("total_min").reset_index())
    t["share"] = t["total_min"] / t["total_min"].sum()
    t["cum_share"] = t["share"].cumsum()
    # bottlenecks: every step up to and including the one that crosses 80 %
    prev = t["cum_share"].shift(fill_value=0)
    t["bottleneck"] = prev < 0.80
    return t


def fmt_min(m: float | None) -> str:
    """Minutes as '4 h 32 m'."""
    if m is None or pd.isna(m):
        return "—"
    m = int(round(m))
    h, r = divmod(abs(m), 60)
    sign = "−" if m < 0 else ""
    return f"{sign}{h} h {r:02d} m" if h else f"{sign}{r} m"
