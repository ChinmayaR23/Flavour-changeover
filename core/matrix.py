"""Logic 5: estimated changeover minutes for every flavour -> flavour pair."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


def rule_estimate(i_from: int, i_to: int, allergen_from: bool, s: dict) -> float:
    base = s.get("matrix_base_min", 220)
    k = s.get("matrix_k_min", 35)
    allergen = s.get("matrix_allergen_min", 60) if allergen_from else 0
    return float(base + k * max(0, i_from - i_to) + allergen)


def build_matrix(flavours: pd.DataFrame, summary: pd.DataFrame, s: dict,
                 model=None) -> pd.DataFrame:
    """Long table: from_id, to_id, from, to, est_min, source, n_samples.

    History (median stop time of that pair) wins once a pair has enough logs;
    an accurate model fills the rest; the rule covers everything else.
    """
    min_logs = int(s.get("matrix_min_pair_logs", 3))
    hist = {}
    if not summary.empty:
        g = summary.groupby(["from_flavour_id", "to_flavour_id"])["stop_min"]
        hist = {k: (v.median(), len(v)) for k, v in g}
    rows = []
    for _, a in flavours.iterrows():
        for _, b in flavours.iterrows():
            if a["id"] == b["id"]:
                continue
            med, n = hist.get((a["id"], b["id"]), (None, 0))
            if n >= min_logs:
                est, src = med, "history"
            elif model is not None:
                est, src = model(a, b), "model"
            else:
                est, src = rule_estimate(a["colour_intensity"], b["colour_intensity"],
                                         bool(a["has_allergen"]), s), "rule"
            rows.append({"from_id": int(a["id"]), "to_id": int(b["id"]), "from": a["name"],
                         "to": b["name"], "est_min": round(float(est), 1), "source": src,
                         "n_samples": int(n)})
    return pd.DataFrame(rows)


def as_lookup(m: pd.DataFrame) -> dict[tuple[int, int], float]:
    return {(r.from_id, r.to_id): r.est_min for r in m.itertuples()}


def save_matrix(con, m: pd.DataFrame) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    con.execute("DELETE FROM changeover_matrix")
    con.executemany(
        "INSERT INTO changeover_matrix VALUES (?,?,?,?,?,?)",
        [(r.from_id, r.to_id, r.est_min, r.source, r.n_samples, now) for r in m.itertuples()])
    con.commit()
