"""Logic 4: rule engine R1-R5 that turns logs into plain-language advice."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.analysis import fmt_min


def severity(minutes: float) -> str:
    if minutes >= 30:
        return "high"
    if minutes >= 10:
        return "medium"
    return "low"


def _rec(key, code, kind, message, stake, activity_type_id=None, changeover_id=None):
    return {"rec_key": key, "rule_code": code, "kind": kind, "message": message,
            "minutes_at_stake": round(float(stake), 1), "severity": severity(stake),
            "activity_type_id": activity_type_id, "changeover_id": changeover_id}


def run_rules(logs: pd.DataFrame, summary: pd.DataFrame, base: pd.DataFrame,
              settings: dict) -> list[dict]:
    recs: list[dict] = []
    if logs.empty:
        return recs
    usual = base.set_index("activity_type_id")["usual_min"].to_dict()
    min_hist = int(settings.get("min_history", 5))

    # R1 overrun: the worst overrun of each step
    over = logs.assign(usual=logs["activity_type_id"].map(usual))
    over = over[over["duration_min"] > settings.get("overrun_factor", 1.25) * over["usual"]]
    for aid, g in over.groupby("activity_type_id"):
        w = g.loc[(g["duration_min"] - g["usual"]).idxmax()]
        extra = w["duration_min"] - w["usual"]
        pct = 100 * extra / w["usual"]
        recs.append(_rec(
            f"R1-{w['id']}", "R1", "Overrun",
            f"{w['activity']} took {fmt_min(w['duration_min'])} on {w['date']:%d %b} "
            f"({w['from_flavour']} → {w['to_flavour']}), {pct:.0f} % over its usual {fmt_min(w['usual'])}.",
            extra, int(aid), int(w["changeover_id"])))

    # R2 move off-line: steps that could run while the line runs but did not
    ext = logs[(logs["can_be_external"] == 1)]
    for aid, g in ext.groupby("activity_type_id"):
        inside = g[g["line_stopped"] == 1]
        if inside.empty:
            continue
        n_co = g["changeover_id"].nunique()
        avg = inside["duration_min"].mean()
        recs.append(_rec(
            f"R2-{aid}", "R2", "Move off-line",
            f"{g['activity'].iloc[0]} was done with the line stopped in {inside['changeover_id'].nunique()} "
            f"of {n_co} changeovers (avg {fmt_min(avg)}). Do it before the line stops.",
            avg, int(aid)))

    # R3 unstable step
    for _, b in base.iterrows():
        if b["n"] >= min_hist and b["cv"] > settings.get("cv_limit", 0.30):
            spread = b["p75_min"] - b["usual_min"]
            recs.append(_rec(
                f"R3-{b['activity_type_id']}", "R3", "Unstable step",
                f"{b['activity']} varies a lot from one changeover to the next (CV {b['cv']:.2f}). "
                f"Add a step-by-step checklist so it is done the same way each time.",
                max(spread, 1), int(b["activity_type_id"])))

    # R4 waiting
    waited = logs[(logs["delay_min"] > 0) & (logs["delay_reason"] != "")]
    for (aid, reason), g in waited.groupby(["activity_type_id", "delay_reason"]):
        avg = g["delay_min"].mean()
        if avg > settings.get("wait_limit_min", 15):
            recs.append(_rec(
                f"R4-{aid}-{reason}", "R4", "Waiting",
                f"“{reason}” cost {fmt_min(avg)} on average during {g['activity'].iloc[0]} "
                f"({len(g)} times). Arrange it before the step is due.",
                avg, int(aid)))

    # R5 flavour order: dark → light changeovers
    if not summary.empty:
        hard = summary[summary["colour_drop"] >= 2]
        easy = summary[summary["colour_drop"] < 2]
        if len(hard) and len(easy):
            extra = hard["stop_min"].mean() - easy["stop_min"].mean()
            if extra > 0:
                example = hard.iloc[-1]["pair"]
                recs.append(_rec(
                    "R5", "R5", "Flavour order",
                    f"{len(hard)} of {len(summary)} changeovers went from a dark to a much lighter flavour "
                    f"(e.g. {example}), about {fmt_min(extra)} longer each. Run flavours light → dark using the Planner.",
                    extra))

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(recs, key=lambda r: (order[r["severity"]], -r["minutes_at_stake"]))


def save_and_load(con, recs: list[dict]) -> pd.DataFrame:
    """Store new tips once (by rec_key), refresh their text, and return them with their status."""
    now = datetime.now().isoformat(timespec="seconds")
    keys = []
    for r in recs:
        keys.append(r["rec_key"])
        con.execute(
            """INSERT INTO recommendations(rec_key, changeover_id, activity_type_id, rule_code, message,
                   severity, minutes_at_stake, created_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(rec_key) DO UPDATE SET message = excluded.message,
                   severity = excluded.severity, minutes_at_stake = excluded.minutes_at_stake""",
            (r["rec_key"], r["changeover_id"], r["activity_type_id"], r["rule_code"], r["message"],
             r["severity"], r["minutes_at_stake"], now))
    con.commit()
    if not keys:
        return pd.DataFrame()
    q = ",".join("?" * len(keys))
    stored = pd.read_sql_query(f"SELECT rec_key, status FROM recommendations WHERE rec_key IN ({q})", con,
                               params=keys)
    out = pd.DataFrame(recs).merge(stored, on="rec_key", how="left")
    return out


def set_status(con, rec_key: str, status: str) -> None:
    con.execute("UPDATE recommendations SET status = ? WHERE rec_key = ?", (status, rec_key))
    con.commit()
