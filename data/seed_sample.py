"""Illustrative sample data, clearly tagged with is_sample = 1.

Nothing here is real factory data. It exists so the app can be demonstrated
before any records are collected. Run `python -m data.seed_sample` to rebuild.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

FLAVOURS = [  # name, colour intensity 1 (light) .. 5 (dark), allergen, base
    ("Lemon", 1, 0, "soda"),
    ("Orange", 2, 0, "soda"),
    ("Mango", 3, 0, "juice"),
    ("Jeera", 4, 0, "soda"),
    ("Cola", 5, 0, "soda"),
]

# name, category, mode today, can_be_external, std_min, depends_on (names), sort
ACTIVITIES = [
    ("Drain and flush line", "drain", "internal", 0, 24, [], 1),
    ("Syrup batch prep", "material", "internal", 1, 48, [], 2),
    ("Tank CIP", "clean", "internal", 0, 72, ["Drain and flush line"], 3),
    ("Rinse and sanitise", "rinse", "internal", 0, 40, ["Tank CIP"], 4),
    ("Filler nozzle change", "setup", "internal", 0, 30, [], 5),
    ("Label and cap change", "setup", "internal", 0, 16, ["Filler nozzle change"], 6),
    ("QC sample and taste", "QC", "internal", 0, 22, ["Rinse and sanitise", "Syrup batch prep"], 7),
    ("Paperwork and line clearance", "paperwork", "internal", 1, 13, ["QC sample and taste"], 8),
]

# (from, to) for the 12 sample changeovers, oldest first
PAIRS = [
    ("Cola", "Lemon"), ("Lemon", "Orange"), ("Jeera", "Orange"), ("Orange", "Mango"),
    ("Mango", "Jeera"), ("Cola", "Mango"), ("Lemon", "Mango"), ("Orange", "Lemon"),
    ("Lemon", "Jeera"), ("Orange", "Mango"), ("Mango", "Cola"), ("Lemon", "Orange"),
]
SYRUP_DONE_BEFORE_STOP = {2, 7, 11}   # indexes where syrup was prepared off-line
VARIATION = {"Filler nozzle change": 0.40, "QC sample and taste": 0.15}


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def seed(con, today: date | None = None, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    today = today or date.today()

    con.execute("INSERT INTO lines(id, name, crew_size, cases_per_hour) VALUES (1, 'Line 1', 3, 1200)")
    fid = {}
    for name, inten, allergen, base in FLAVOURS:
        cur = con.execute(
            "INSERT INTO flavours(name, colour_intensity, has_allergen, base, is_sample) VALUES (?,?,?,?,1)",
            (name, inten, allergen, base),
        )
        fid[name] = cur.lastrowid
    aid = {}
    for name, cat, mode, ext, std, _deps, order in ACTIVITIES:
        cur = con.execute(
            "INSERT INTO activity_types(name, category, mode, can_be_external, std_min, sort_order) VALUES (?,?,?,?,?,?)",
            (name, cat, mode, ext, std, order),
        )
        aid[name] = cur.lastrowid
    for name, *_rest, deps, _order in ACTIVITIES:
        con.execute(
            "UPDATE activity_types SET depends_on = ? WHERE id = ?",
            (",".join(str(aid[d]) for d in deps), aid[name]),
        )

    inten = {n: i for n, i, *_ in FLAVOURS}
    for k, (frm, to) in enumerate(PAIRS):
        day = today - timedelta(days=30 - k * 2 - rng.randint(0, 1))
        stop = datetime(day.year, day.month, day.day, 9, 0) + timedelta(minutes=rng.randint(0, 60))
        drop = max(0, inten[frm] - inten[to])
        dark_to_light = drop >= 2
        cur = con.execute(
            "INSERT INTO changeovers(line_id, from_flavour_id, to_flavour_id, date, shift, line_stop_ts, crew_count, notes, is_sample)"
            " VALUES (1, ?, ?, ?, ?, ?, 3, ?, 1)",
            (fid[frm], fid[to], day.isoformat(), rng.choice("AB"), _fmt(stop),
             "Sample data (illustrative)"),
        )
        cid = cur.lastrowid

        def minutes(name: str, std: int) -> float:
            sd = VARIATION.get(name, 0.10)
            m = max(std * 0.5, rng.gauss(std, std * sd))
            if dark_to_light:
                m += {"Tank CIP": 55, "Rinse and sanitise": 30, "QC sample and taste": 15}.get(name, 0)
            return round(m, 1)

        t = stop
        for name, _cat, _mode, _ext, std, _deps, _order in ACTIVITIES:
            dur = minutes(name, std)
            delay_reason, delay_min, line_stopped = "", 0.0, 1
            if name == "Syrup batch prep" and k in SYRUP_DONE_BEFORE_STOP:
                start = stop - timedelta(minutes=dur + 5)
                line_stopped = 0
            elif name == "Filler nozzle change" and k % 2 == 0:
                start = t - timedelta(minutes=40)   # done alongside the CIP
            else:
                start = t
            if name == "QC sample and taste" and k % 3 != 1:
                delay_min = float(rng.randint(12, 24))
                delay_reason = "Waiting for QC"
                dur += delay_min
            end = start + timedelta(minutes=dur)
            con.execute(
                "INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, end_ts, line_stopped, operator, delay_reason, delay_min, notes)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (cid, aid[name], _fmt(start), _fmt(end), line_stopped,
                 rng.choice(["Operator A", "Operator B", "Operator C"]), delay_reason, delay_min, ""),
            )
            if line_stopped:
                t = max(t, end)
        con.execute("UPDATE changeovers SET line_restart_ts = ? WHERE id = ?", (_fmt(t), cid))

    tomorrow = (today + timedelta(days=1)).isoformat()
    for name, qty, due, prio in [("Cola", 2000, "", 2), ("Orange", 1200, "12:00", 2),
                                 ("Jeera", 1500, "", 2), ("Mango", 800, "", 2)]:
        con.execute(
            "INSERT INTO production_orders(date, line_id, flavour_id, qty_cases, due_time, priority) VALUES (?,1,?,?,?,?)",
            (tomorrow, fid[name], qty, due, prio),
        )
    con.commit()


if __name__ == "__main__":
    from core.db import DB_PATH, connect, init_db

    if DB_PATH.exists():
        DB_PATH.unlink()
    con = connect()
    init_db(con)
    seed(con)
    print(f"Sample database written to {DB_PATH}")
