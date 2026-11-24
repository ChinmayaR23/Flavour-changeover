import pandas as pd
import streamlit as st

from core import db, planning, ui
from core.analysis import changeover_summary
from core.predict import train

con = ui.con()
line_id = st.session_state.get("line_id", 1)
st.title("Data and settings")

t_rules, t_flav, t_steps, t_lines, t_data, t_ai = st.tabs(
    ["Rule settings", "Flavours", "Steps", "Lines", "Import / export", "AI predictor"])

with t_rules:
    s = db.df(con, "SELECT key, value, description FROM settings ORDER BY key")
    e = st.data_editor(s, hide_index=True, width="stretch", disabled=["key", "description"], key="set_ed")
    if st.button("Save settings", type="primary"):
        con.executemany("UPDATE settings SET value = ? WHERE key = ?", [(float(r.value), r.key) for r in e.itertuples()])
        con.commit()
        st.success("Saved.")

with t_flav:
    st.caption("Colour intensity: 1 = lightest, 5 = darkest. It drives the flavour-order rule.")
    f = db.df(con, "SELECT id, name, colour_intensity, has_allergen, base FROM flavours ORDER BY colour_intensity")
    f["has_allergen"] = f["has_allergen"].astype(bool)
    e = st.data_editor(f, hide_index=True, width="stretch", num_rows="dynamic", disabled=["id"], key="fl_ed",
                       column_config={"colour_intensity": st.column_config.NumberColumn(min_value=1, max_value=5, step=1)})
    if st.button("Save flavours", type="primary"):
        for r in e.dropna(subset=["name"]).itertuples():
            vals = (r.name, int(r.colour_intensity or 1), int(bool(r.has_allergen)), r.base or "soda")
            if pd.isna(r.id):
                con.execute("INSERT INTO flavours(name, colour_intensity, has_allergen, base) VALUES (?,?,?,?)", vals)
            else:
                con.execute("UPDATE flavours SET name=?, colour_intensity=?, has_allergen=?, base=? WHERE id=?",
                            (*vals, int(r.id)))
        con.commit()
        st.success("Saved.")

with t_steps:
    st.caption("depends_on: ids of steps that must finish first, separated by commas. "
               "can_be_external: the step could be done while the line still runs.")
    a = db.df(con, "SELECT id, name, category, can_be_external, std_min, depends_on, sop_link, sort_order "
                   "FROM activity_types ORDER BY sort_order, id")
    a["can_be_external"] = a["can_be_external"].astype(bool)
    e = st.data_editor(a, hide_index=True, width="stretch", num_rows="dynamic", disabled=["id"], key="st_ed")
    if st.button("Save steps", type="primary"):
        for r in e.dropna(subset=["name"]).itertuples():
            vals = (r.name, r.category or "setup", int(bool(r.can_be_external)), int(r.std_min or 10),
                    str(r.depends_on or ""), r.sop_link or "", int(r.sort_order or 0))
            if pd.isna(r.id):
                con.execute("INSERT INTO activity_types(name, category, can_be_external, std_min, depends_on, sop_link, sort_order)"
                            " VALUES (?,?,?,?,?,?,?)", vals)
            else:
                con.execute("UPDATE activity_types SET name=?, category=?, can_be_external=?, std_min=?, depends_on=?, "
                            "sop_link=?, sort_order=? WHERE id=?", (*vals, int(r.id)))
        con.commit()
        st.success("Saved.")

with t_lines:
    l = db.df(con, "SELECT id, name, crew_size, cases_per_hour FROM lines ORDER BY id")
    e = st.data_editor(l, hide_index=True, width="stretch", num_rows="dynamic", disabled=["id"], key="ln_ed")
    if st.button("Save lines", type="primary"):
        for r in e.dropna(subset=["name"]).itertuples():
            vals = (r.name, int(r.crew_size or 3), int(r.cases_per_hour or 1200))
            if pd.isna(r.id):
                con.execute("INSERT INTO lines(name, crew_size, cases_per_hour) VALUES (?,?,?)", vals)
            else:
                con.execute("UPDATE lines SET name=?, crew_size=?, cases_per_hour=? WHERE id=?", (*vals, int(r.id)))
        con.commit()
        st.success("Saved.")

EXPORT_SQL = """
SELECT c.date, ln.name AS line, ff.name AS from_flavour, tf.name AS to_flavour, c.shift, c.crew_count,
       c.line_stop_ts, c.line_restart_ts, a.name AS step, l.start_ts, l.end_ts, l.line_stopped,
       l.operator, l.delay_reason, l.delay_min, l.notes, c.is_sample
FROM activity_logs l JOIN changeovers c ON c.id = l.changeover_id
JOIN lines ln ON ln.id = c.line_id JOIN activity_types a ON a.id = l.activity_type_id
JOIN flavours ff ON ff.id = c.from_flavour_id JOIN flavours tf ON tf.id = c.to_flavour_id
ORDER BY l.start_ts
"""
NEEDED = ["date", "line", "from_flavour", "to_flavour", "shift", "crew_count", "line_stop_ts", "line_restart_ts",
          "step", "start_ts", "end_ts", "line_stopped"]

with t_data:
    out = db.df(con, EXPORT_SQL)
    st.download_button("Export all logs (CSV)", out.to_csv(index=False).encode(), "changeover_logs.csv", "text/csv",
                       type="primary")
    st.markdown("**Import logs**")
    st.caption("Same columns as the export. Lines, flavours and steps must already exist with the same names.")
    up = st.file_uploader("CSV file", type="csv")
    if up is not None and st.button("Import"):
        d = pd.read_csv(up).fillna("")
        missing = [c for c in NEEDED if c not in d.columns]
        if missing:
            st.error("Missing columns: " + ", ".join(missing))
        else:
            ids = {t: dict(con.execute(f"SELECT name, id FROM {t}").fetchall()) for t in ("lines", "flavours", "activity_types")}
            n_co = n_log = 0
            errors = []
            for key, g in d.groupby(["date", "line", "from_flavour", "to_flavour", "line_stop_ts"]):
                r0 = g.iloc[0]
                try:
                    cur = con.execute(
                        "INSERT INTO changeovers(line_id, from_flavour_id, to_flavour_id, date, shift, line_stop_ts, line_restart_ts, crew_count, notes)"
                        " VALUES (?,?,?,?,?,?,?,?,?)",
                        (ids["lines"][r0["line"]], ids["flavours"][r0["from_flavour"]], ids["flavours"][r0["to_flavour"]],
                         r0["date"], r0["shift"] or "A", r0["line_stop_ts"], r0["line_restart_ts"] or None,
                         int(r0["crew_count"] or 3), "Imported"))
                    n_co += 1
                    for r in g.itertuples():
                        con.execute(
                            "INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, end_ts, line_stopped, operator, delay_reason, delay_min, notes)"
                            " VALUES (?,?,?,?,?,?,?,?,?)",
                            (cur.lastrowid, ids["activity_types"][r.step], r.start_ts, r.end_ts or None, int(r.line_stopped or 1),
                             getattr(r, "operator", ""), getattr(r, "delay_reason", ""), float(getattr(r, "delay_min", 0) or 0),
                             getattr(r, "notes", "")))
                        n_log += 1
                except KeyError as ex:
                    errors.append(f"{key}: unknown name {ex}")
            con.commit()
            st.success(f"Imported {n_co} changeovers and {n_log} steps.")
            for e in errors[:10]:
                st.warning(e)

    st.divider()
    st.markdown("**Sample data**")
    n = con.execute("SELECT COUNT(*) FROM changeovers WHERE is_sample = 1").fetchone()[0]
    st.caption(f"{n} illustrative changeovers are loaded." if n else "No sample changeovers are loaded.")
    c1, c2 = st.columns(2)
    if n and c1.button("Remove sample changeovers"):
        con.execute("DELETE FROM changeovers WHERE is_sample = 1")
        con.commit()
        st.rerun()
    with c2.expander("Start over with fresh sample data"):
        st.caption("Deletes everything in the database, including your own logs.")
        if st.checkbox("I understand, delete everything") and st.button("Reset database"):
            for t in ["recommendations", "plans", "changeover_matrix", "production_orders", "activity_logs",
                      "changeovers", "activity_types", "flavours", "lines"]:
                con.execute(f"DELETE FROM {t}")
            con.commit()
            from data.seed_sample import seed
            seed(con)
            st.rerun()

with t_ai:
    s = db.settings(con)
    summary = changeover_summary(con)
    status = train(summary[summary["line_id"] == line_id] if len(summary) else summary, int(s.get("ai_min_changeovers", 30)))
    (st.success if status.ready else st.info)(status.message)
    st.caption("Features: colour of both flavours, colour drop, allergen, crew, line, shift. "
               "Model: random forest, checked with 5-fold cross-validation against the median.")
