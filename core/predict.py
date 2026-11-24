"""Logic 8: AI predictor, switched on only when there is enough data.

It is used only if its cross-validated error beats the simple 'median of all
changeovers' baseline by at least 10 %. Until then the app keeps using rules.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FEATURES = ["from_intensity", "to_intensity", "colour_drop", "from_allergen", "crew_count", "line_id", "shift_b"]


@dataclass
class PredictorStatus:
    ready: bool
    message: str
    model_mae: float | None = None
    baseline_mae: float | None = None
    model: object | None = None


def _features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["colour_drop"] = (x["from_intensity"] - x["to_intensity"]).clip(lower=0)
    x["shift_b"] = (x["shift"] == "B").astype(int)
    return x[FEATURES].astype(float)


def train(summary: pd.DataFrame, min_changeovers: int = 30) -> PredictorStatus:
    n = len(summary)
    if n < min_changeovers:
        return PredictorStatus(False, f"{n} of {min_changeovers} changeovers logged. The predictor "
                                      "switches on once there is enough data; rules are used until then.")
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import KFold, cross_val_predict
    except ImportError:
        return PredictorStatus(False, "scikit-learn is not installed.")
    x, y = _features(summary), summary["stop_min"].to_numpy()
    model = RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=0)
    pred = cross_val_predict(model, x, y, cv=KFold(5, shuffle=True, random_state=0))
    mae = float(np.mean(np.abs(pred - y)))
    base = float(np.mean(np.abs(np.median(y) - y)))
    if mae > 0.9 * base:
        return PredictorStatus(False, f"Model error {mae:.0f} min is not 10 % better than the median "
                                      f"baseline ({base:.0f} min). Keeping the rules.", mae, base)
    model.fit(x, y)
    return PredictorStatus(True, f"Model error {mae:.0f} min vs baseline {base:.0f} min. In use.", mae, base, model)


def pair_predictor(status: PredictorStatus, crew: int = 3, line_id: int = 1):
    """A function (from_row, to_row) -> minutes, for build_matrix; None if not ready."""
    if not status.ready:
        return None

    def f(a, b):
        row = pd.DataFrame([{"from_intensity": a["colour_intensity"], "to_intensity": b["colour_intensity"],
                             "from_allergen": a["has_allergen"], "crew_count": crew, "line_id": line_id,
                             "shift": "A"}])
        return float(status.model.predict(_features(row))[0])

    return f
