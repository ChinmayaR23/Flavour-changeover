"""SQLite access: connection, schema setup and small query helpers."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "data" / "schema.sql"
DB_PATH = Path(os.environ.get("CHANGEOVER_DB", ROOT / "data" / "changeover.db"))

DEFAULT_SETTINGS = {
    "overrun_factor": (1.25, "R1: flag a step that takes this many times its usual time"),
    "cv_limit": (0.30, "R3: flag a step whose variation (CV) is above this"),
    "wait_limit_min": (15, "R4: flag waiting longer than this many minutes"),
    "min_history": (5, "Logs a step needs before its own median is used"),
    "matrix_min_pair_logs": (3, "Logs a flavour pair needs before history replaces the rule"),
    "matrix_base_min": (220, "Rule: minutes for a light-to-dark changeover"),
    "matrix_k_min": (35, "Rule: extra minutes per level of colour drop"),
    "matrix_allergen_min": (60, "Rule: extra minutes after an allergen flavour"),
    "ai_min_changeovers": (30, "Changeovers needed before the AI predictor is tried"),
    "shift_start_hour": (6, "Hour the planner's day starts"),
}


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def session(path: Path | str | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text())
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        con.execute(
            "INSERT OR IGNORE INTO settings(key, value, description) VALUES (?, ?, ?)",
            (key, value, desc),
        )
    con.commit()


def is_empty(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT COUNT(*) FROM flavours").fetchone()[0] == 0


def ensure_ready(path: Path | str | None = None) -> None:
    """Create tables and load sample data the first time the app runs."""
    from data.seed_sample import seed  # local import avoids a cycle

    with session(path) as con:
        init_db(con)
        if is_empty(con):
            seed(con)


def df(con: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)


def settings(con: sqlite3.Connection) -> dict[str, float]:
    return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM settings")}


def has_sample_data(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT COUNT(*) FROM changeovers WHERE is_sample = 1").fetchone()[0] > 0
