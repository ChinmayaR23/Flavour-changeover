-- Flavour Changeover Optimizer: SQLite schema (10 tables)
PRAGMA foreign_keys = ON;

-- Master data -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flavours (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    colour_intensity INTEGER NOT NULL CHECK (colour_intensity BETWEEN 1 AND 5),
    has_allergen     INTEGER NOT NULL DEFAULT 0,
    base             TEXT NOT NULL DEFAULT 'soda',
    is_sample        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lines (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    crew_size        INTEGER NOT NULL DEFAULT 3,
    cases_per_hour   INTEGER NOT NULL DEFAULT 1200
);

CREATE TABLE IF NOT EXISTS activity_types (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    category         TEXT NOT NULL,          -- drain, clean, rinse, setup, material, QC, paperwork
    mode             TEXT NOT NULL DEFAULT 'internal',  -- how it is done today
    can_be_external  INTEGER NOT NULL DEFAULT 0,        -- could be done while the line runs
    std_min          INTEGER NOT NULL,                  -- planned minutes
    depends_on       TEXT NOT NULL DEFAULT '',          -- comma-separated activity_type ids
    sop_link         TEXT NOT NULL DEFAULT '',
    sort_order       INTEGER NOT NULL DEFAULT 0
);

-- Logged during each changeover -------------------------------------------
CREATE TABLE IF NOT EXISTS changeovers (
    id               INTEGER PRIMARY KEY,
    line_id          INTEGER NOT NULL REFERENCES lines(id),
    from_flavour_id  INTEGER NOT NULL REFERENCES flavours(id),
    to_flavour_id    INTEGER NOT NULL REFERENCES flavours(id),
    date             TEXT NOT NULL,          -- YYYY-MM-DD
    shift            TEXT NOT NULL DEFAULT 'A',
    line_stop_ts     TEXT NOT NULL,          -- ISO datetime, IST
    line_restart_ts  TEXT,                   -- NULL while in progress
    crew_count       INTEGER NOT NULL DEFAULT 3,
    notes            TEXT NOT NULL DEFAULT '',
    is_sample        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id               INTEGER PRIMARY KEY,
    changeover_id    INTEGER NOT NULL REFERENCES changeovers(id) ON DELETE CASCADE,
    activity_type_id INTEGER NOT NULL REFERENCES activity_types(id),
    start_ts         TEXT NOT NULL,
    end_ts           TEXT,                   -- NULL while running
    line_stopped     INTEGER NOT NULL DEFAULT 1,
    operator         TEXT NOT NULL DEFAULT '',
    delay_reason     TEXT NOT NULL DEFAULT '',
    delay_min        REAL NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT ''
);

-- Planning ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS production_orders (
    id               INTEGER PRIMARY KEY,
    date             TEXT NOT NULL,
    line_id          INTEGER NOT NULL REFERENCES lines(id),
    flavour_id       INTEGER NOT NULL REFERENCES flavours(id),
    qty_cases        INTEGER NOT NULL,
    due_time         TEXT NOT NULL DEFAULT '',   -- HH:MM or empty
    priority         INTEGER NOT NULL DEFAULT 2  -- 1 = must run first
);

CREATE TABLE IF NOT EXISTS changeover_matrix (
    from_flavour_id  INTEGER NOT NULL REFERENCES flavours(id),
    to_flavour_id    INTEGER NOT NULL REFERENCES flavours(id),
    est_min          REAL NOT NULL,
    source           TEXT NOT NULL,          -- rule, history, model
    n_samples        INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (from_flavour_id, to_flavour_id)
);

CREATE TABLE IF NOT EXISTS plans (
    id               INTEGER PRIMARY KEY,
    date             TEXT NOT NULL,
    line_id          INTEGER NOT NULL REFERENCES lines(id),
    sequence         TEXT NOT NULL,          -- JSON list of flavour ids
    est_total_min    REAL NOT NULL,
    baseline_min     REAL NOT NULL,
    task_plan        TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL
);

-- Outputs and settings ------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    id               INTEGER PRIMARY KEY,
    rec_key          TEXT NOT NULL UNIQUE,   -- rule + subject, so a tip is stored once
    changeover_id    INTEGER,
    activity_type_id INTEGER,
    rule_code        TEXT NOT NULL,
    message          TEXT NOT NULL,
    severity         TEXT NOT NULL,          -- low, medium, high
    minutes_at_stake REAL NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'new',  -- new, accepted, ignored
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key              TEXT PRIMARY KEY,
    value            REAL NOT NULL,
    description      TEXT NOT NULL DEFAULT ''
);
