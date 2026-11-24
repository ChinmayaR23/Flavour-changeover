from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from core import db, planning, ui
from core.analysis import fmt_min

con = ui.con()
line_id = st.session_state.get("line_id", 1)
FMT = "%Y-%m-%d %H:%M:%S"


def now_s() -> str:
    return datetime.now().strftime(FMT)


flavours = db.df(con, "SELECT id, name FROM flavours ORDER BY colour_intensity, name")
fl = dict(zip(flavours["name"], flavours["id"]))
acts = db.df(con, "SELECT * FROM activity_types ORDER BY sort_order, id")
line = con.execute("SELECT * FROM lines WHERE id = ?", (line_id,)).fetchone()

st.title("Log changeover")
open_co = con.execute(
    """SELECT c.*, ff.name AS from_name, tf.name AS to_name FROM changeovers c
       JOIN flavours ff ON ff.id = c.from_flavour_id JOIN flavours tf ON tf.id = c.to_flavour_id
       WHERE c.line_id = ? AND c.line_restart_ts IS NULL ORDER BY c.id DESC LIMIT 1""", (line_id,)).fetchone()

live_tab, past_tab = st.tabs(["Live changeover", "Enter a past changeover"])

# ============================================================================ live
with live_tab:
    if open_co is None:
        st.caption(f"{line['name']} is running. Start here the moment the line stops.")
        cur = planning.current_flavour(con, line_id)
        names = list(fl)
        with st.form("start"):
            c1, c2, c3, c4 = st.columns(4)
            frm = c1.selectbox("From flavour", names, index=names.index(cur[1]) if cur else 0)
            to = c2.selectbox("To flavour", names, index=min(len(names) - 1, (names.index(cur[1]) + 1) if cur else 1))
            shift = c3.selectbox("Shift", ["A", "B", "C"])
            crew = c4.number_input("Crew", 1, 20, int(line["crew_size"]))
            if st.form_submit_button("Line stopped: start timing", type="primary"):
                if frm == to:
                    st.error("Pick two different flavours.")
                else:
                    con.execute(
                        "INSERT INTO changeovers(line_id, from_flavour_id, to_flavour_id, date, shift, line_stop_ts, crew_count)"
                        " VALUES (?,?,?,?,?,?,?)", (line_id, fl[frm], fl[to], date.today().isoformat(), shift, now_s(), crew))
                    con.commit()
                    st.rerun()
    else:
        cid = open_co["id"]
        ctx = planning.context(con, line_id)
        usual = ctx.cost.get((open_co["from_flavour_id"], open_co["to_flavour_id"]), 0.0)
        st.markdown(f"{ui.chip(open_co['from_name'])} <span class='arrow'>→</span> {ui.chip(open_co['to_name'])} "
                    f"&nbsp; Shift {open_co['shift']} · crew {open_co['crew_count']}", unsafe_allow_html=True)

        @st.fragment(run_every="1s")
        def timer():
            stop = datetime.strptime(open_co["line_stop_ts"], FMT)
            el = (datetime.now() - stop).total_seconds()
            h, r = divmod(int(el), 3600)
            m, s = divmod(r, 60)
            with st.container(border=True):
                a, b = st.columns([2, 1])
                a.markdown(f"<div style='font-size:13px;color:#4B5563;font-weight:600'>Line stopped for</div>"
                           f"<div style='font-family:JetBrains Mono,monospace;font-size:46px;font-weight:600'>"
                           f"{h:02d}:{m:02d}:{s:02d}</div>", unsafe_allow_html=True)
                b.metric("Usual for this pair", fmt_min(usual))
                st.progress(min(1.0, el / 60 / usual) if usual else 0.0)
        timer()

        logs = db.df(con, "SELECT * FROM activity_logs WHERE changeover_id = ? ORDER BY id", (cid,))
        base = ctx.base.set_index("activity_type_id")["usual_min"].to_dict()
        with st.container(border=True):
            st.markdown("**Steps** · tap Start and Stop as each one happens")
            for a in acts.itertuples():
                mine = logs[logs["activity_type_id"] == a.id]
                running = mine[mine["end_ts"].isna()]
                done = mine[mine["end_ts"].notna()]
                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                c1.markdown(f"**{a.name}**" + (" <span class='pill low'>can be done before the stop</span>"
                                               if a.can_be_external else ""), unsafe_allow_html=True)
                if len(running):
                    start = datetime.strptime(running.iloc[0]["start_ts"], FMT)
                    c2.markdown(f"<span class='pill medium'>Running</span> since {start:%H:%M}", unsafe_allow_html=True)
                    if c4.button("Stop", key=f"stop{a.id}", type="primary", width="stretch"):
                        con.execute("UPDATE activity_logs SET end_ts = ? WHERE id = ?", (now_s(), int(running.iloc[0]["id"])))
                        con.commit()
                        st.rerun()
                elif len(done):
                    d = done.iloc[-1]
                    mins = (datetime.strptime(d["end_ts"], FMT) - datetime.strptime(d["start_ts"], FMT)).total_seconds() / 60
                    c2.markdown(f"<span class='pill' style='background:#DDF2EE;color:#0F5F58'>Done</span> {fmt_min(mins)}",
                                unsafe_allow_html=True)
                    if c4.button("Restart", key=f"again{a.id}", width="stretch"):
                        con.execute("INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, line_stopped) VALUES (?,?,?,1)",
                                    (cid, int(a.id), now_s()))
                        con.commit()
                        st.rerun()
                else:
                    c2.markdown("<span class='pill low'>To do</span>", unsafe_allow_html=True)
                    if c4.button("Start", key=f"start{a.id}", width="stretch"):
                        con.execute("INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, line_stopped) VALUES (?,?,?,1)",
                                    (cid, int(a.id), now_s()))
                        con.commit()
                        st.rerun()
                c3.caption(f"usual {fmt_min(base.get(a.id, a.std_min))}")

        with st.container(border=True):
            st.markdown("**Record a delay**")
            with st.form("delay", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                step = c1.selectbox("Step", list(acts["name"]))
                reason = c2.selectbox("Reason", ["Waiting for syrup", "Waiting for parts", "Waiting for QC",
                                                 "Machine fault", "Other"])
                mins = c3.number_input("Minutes lost", 0, 600, 10)
                note = st.text_input("Note")
                if st.form_submit_button("Save delay"):
                    aid = int(acts.loc[acts["name"] == step, "id"].iloc[0])
                    row = con.execute("SELECT id FROM activity_logs WHERE changeover_id = ? AND activity_type_id = ? "
                                      "ORDER BY id DESC LIMIT 1", (cid, aid)).fetchone()
                    if row is None:
                        st.error("Start that step first, then record its delay.")
                    else:
                        con.execute("UPDATE activity_logs SET delay_reason = ?, delay_min = delay_min + ?, "
                                    "notes = TRIM(notes || ' ' || ?) WHERE id = ?", (reason, mins, note, row["id"]))
                        con.commit()
                        st.success("Delay saved.")

        c1, c2 = st.columns([1, 3])
        running_any = logs["end_ts"].isna().any() if len(logs) else False
        if c1.button("Line restarted", type="primary", width="stretch", disabled=bool(running_any),
                     help="Stop every running step first." if running_any else None):
            con.execute("UPDATE changeovers SET line_restart_ts = ? WHERE id = ?", (now_s(), cid))
            con.commit()
            st.success("Changeover saved.")
            st.rerun()
        with c2.expander("Discard this changeover"):
            if st.checkbox("Yes, delete this changeover and its steps"):
                if st.button("Delete"):
                    con.execute("DELETE FROM changeovers WHERE id = ?", (cid,))
                    con.commit()
                    st.rerun()

# ============================================================================ past
with past_tab:
    st.caption("For changeovers timed on paper. Enter the clock times of each step.")
    names = list(fl)
    c1, c2, c3, c4 = st.columns(4)
    frm = c1.selectbox("From flavour", names, key="p_from")
    to = c2.selectbox("To flavour", names, index=1 if len(names) > 1 else 0, key="p_to")
    day = c3.date_input("Date", date.today(), key="p_day")
    shift = c4.selectbox("Shift", ["A", "B", "C"], key="p_shift")
    template = pd.DataFrame({
        "Step": acts["name"], "Start": [None] * len(acts), "End": [None] * len(acts),
        "Line stopped": [True] * len(acts), "Delay reason": [""] * len(acts),
        "Delay min": [0] * len(acts), "Notes": [""] * len(acts)})
    edited = st.data_editor(template, hide_index=True, width="stretch", key="p_grid", column_config={
        "Step": st.column_config.TextColumn(disabled=True),
        "Start": st.column_config.TimeColumn(format="HH:mm"), "End": st.column_config.TimeColumn(format="HH:mm"),
        "Delay min": st.column_config.NumberColumn(min_value=0, max_value=600)})
    if st.button("Save changeover", type="primary"):
        rows = edited.dropna(subset=["Start", "End"])
        bad = rows[[datetime.combine(day, e) <= datetime.combine(day, s) for s, e in zip(rows["Start"], rows["End"])]]
        if frm == to:
            st.error("Pick two different flavours.")
        elif rows.empty:
            st.error("Enter start and end times for at least one step.")
        elif len(bad):
            st.error("End must be after start for: " + ", ".join(bad["Step"]))
        else:
            stopped = rows[rows["Line stopped"]]
            first = min(stopped["Start"]) if len(stopped) else min(rows["Start"])
            last = max(stopped["End"]) if len(stopped) else max(rows["End"])
            cur = con.execute(
                "INSERT INTO changeovers(line_id, from_flavour_id, to_flavour_id, date, shift, line_stop_ts, line_restart_ts, crew_count)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (line_id, fl[frm], fl[to], day.isoformat(), shift, datetime.combine(day, first).strftime(FMT),
                 datetime.combine(day, last).strftime(FMT), int(line["crew_size"])))
            aid = dict(zip(acts["name"], acts["id"]))
            for r in rows.itertuples():
                con.execute(
                    "INSERT INTO activity_logs(changeover_id, activity_type_id, start_ts, end_ts, line_stopped, delay_reason, delay_min, notes)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (cur.lastrowid, int(aid[r.Step]), datetime.combine(day, r.Start).strftime(FMT),
                     datetime.combine(day, r.End).strftime(FMT), int(bool(r._4)), r._5 or "", float(r._6 or 0), r.Notes or ""))
            con.commit()
            st.success(f"Saved {len(rows)} steps.")
