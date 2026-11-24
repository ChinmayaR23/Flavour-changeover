import json
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import db, planning, ui
from core.analysis import fmt_min
from core.matrix import save_matrix

con = ui.con()
line_id = st.session_state.get("line_id", 1)
ctx = planning.context(con, line_id)
names = list(ctx.flavours["name"])
fid = dict(zip(ctx.flavours["name"], ctx.flavours["id"]))

st.title("Planner")
st.caption("Plan the day's flavour order and each changeover.")

# ---- inputs --------------------------------------------------------------------------
default_day = planning.next_order_date(con, line_id) or (date.today() + timedelta(days=1)).isoformat()
cur = planning.current_flavour(con, line_id)
c1, c2, c3 = st.columns(3)
day = c1.date_input("Date", date.fromisoformat(default_day)).isoformat()
start_name = c2.selectbox("Flavour on the line at the start", names, index=names.index(cur[1]) if cur else 0)
crew = c3.number_input("Crew per changeover", 1, 20, int(ctx.line.get("crew_size", 3)))

with st.container(border=True):
    st.markdown("**Orders**")
    rows = db.df(con, "SELECT flavour_id, qty_cases, due_time, priority FROM production_orders "
                      "WHERE line_id = ? AND date = ? ORDER BY id", (line_id, day))
    id_name = {v: k for k, v in fid.items()}
    table = pd.DataFrame({
        "Flavour": rows["flavour_id"].map(id_name), "Cases": rows["qty_cases"],
        "Due by (HH:MM)": rows["due_time"], "Priority": rows["priority"]})
    edited = st.data_editor(table, num_rows="dynamic", hide_index=True, width="stretch", key=f"orders{day}",
                            column_config={
                                "Flavour": st.column_config.SelectboxColumn(options=names, required=True),
                                "Cases": st.column_config.NumberColumn(min_value=1, required=True),
                                "Due by (HH:MM)": st.column_config.TextColumn(help="Leave empty if there is no deadline"),
                                "Priority": st.column_config.SelectboxColumn(options=[1, 2], help="1 = must run first")})
    if st.button("Save orders"):
        good = edited.dropna(subset=["Flavour", "Cases"])
        con.execute("DELETE FROM production_orders WHERE line_id = ? AND date = ?", (line_id, day))
        for r in good.itertuples():
            due = r._3.strip() if isinstance(r._3, str) else ""
            try:
                if due:
                    datetime.strptime(due, "%H:%M")
            except ValueError:
                st.error(f"“{due}” is not a time like 14:30. That order was saved without a due time.")
                due = ""
            con.execute("INSERT INTO production_orders(date, line_id, flavour_id, qty_cases, due_time, priority) "
                        "VALUES (?,?,?,?,?,?)", (day, line_id, fid[r.Flavour], int(r.Cases), due, int(r.Priority) if pd.notna(r.Priority) else 2))
        con.commit()
        st.rerun()

orders = planning.orders_for(con, ctx, line_id, day)
if not orders:
    st.info("Add the day's orders above and press Save orders.")
    st.stop()

start = (fid[start_name], start_name)
entered, best = planning.plans(ctx, start, orders)
day_start = datetime.combine(date.fromisoformat(day), datetime.min.time()) + timedelta(hours=ctx.settings.get("shift_start_hour", 6))


def sequence_html(plan, label, bg):
    parts = [ui.chip(start_name)]
    for (a, b, m) in plan.steps:
        if a == b:
            continue                      # already on the line: no changeover
        hot = "hot" if m > ctx.settings.get("matrix_base_min", 220) else ""
        parts.append(f"<span class='arrow {hot}'>→ {m:.0f} m →</span>{ui.chip(b)}")
    late = "" if plan.feasible else " <span class='pill high'>misses a due time</span>"
    return (f"<div style='padding:14px 16px;border-radius:12px;background:{bg};margin-bottom:10px'>"
            f"<div style='display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px'><b>{label}{late}</b>"
            f"<b>{fmt_min(plan.changeover_min)} of changeovers</b></div>"
            f"<div style='display:flex;flex-wrap:wrap;align-items:center;margin-top:8px'>{''.join(parts)}</div></div>")


with st.container(border=True):
    st.markdown("**Best flavour order**")
    st.markdown(sequence_html(entered, "As entered", "#F3F5F8") + sequence_html(best, "Suggested", "#E8EFFC"),
                unsafe_allow_html=True)
    saving = entered.changeover_min - best.changeover_min
    st.markdown(f"Saves **{fmt_min(saving)}** of line-stop. Method: {best.method}.")
    finish = pd.DataFrame({"Flavour": [o.name for o in best.sequence],
                           "Cases": [o.qty_cases for o in best.sequence],
                           "Finishes": [(day_start + timedelta(minutes=t)).strftime("%d %b %H:%M") for t in best.finishes],
                           "Due by": [(day_start + timedelta(minutes=o.due_min)).strftime("%H:%M") if o.due_min is not None else ""
                                      for o in best.sequence]})
    st.dataframe(finish, hide_index=True, width="stretch")
    a, b = st.columns([1, 1])
    if a.button("Save plan", type="primary"):
        slots, stop, _ = planning.task_plan(ctx, crew)
        con.execute("INSERT INTO plans(date, line_id, sequence, est_total_min, baseline_min, task_plan, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (day, line_id, json.dumps([o.flavour_id for o in best.sequence]), best.changeover_min,
                     entered.changeover_min, json.dumps([s.__dict__ for s in slots]),
                     datetime.now().isoformat(timespec="seconds")))
        save_matrix(con, ctx.matrix)
        con.commit()
        st.success("Plan saved.")
    b.download_button("Download plan (CSV)", finish.to_csv(index=False).encode(), f"plan_{day}.csv", "text/csv")

# ---- task plan (SMED + crew) ---------------------------------------------------------
fc = planning.first_changeover(best, start)
frm, first = fc if fc else (start, best.sequence[0])
usual = ctx.cost.get((frm[0], first.flavour_id), 0.0)
slots, stop, seq = planning.task_plan(ctx, crew)
with st.container(border=True):
    st.markdown(f"**Task plan for the first changeover: {frm[1]} → {first.name}, crew of {crew}**")
    m1, m2, m3 = st.columns(3)
    planned = planning.planned_for_pair(ctx, usual, crew)
    m1.metric("Usual line-stop", fmt_min(usual))
    m2.metric("With this task plan", fmt_min(planned))
    m3.metric("Saved", fmt_min(usual - planned))
    colour = {("external", False): "#0F766E", ("internal", True): "#1D4ED8", ("internal", False): "#7FA0E8"}
    fig = go.Figure()
    for s in slots:
        fig.add_trace(go.Bar(
            y=[s.worker], x=[s.end - s.start], base=[s.start], orientation="h",
            marker=dict(color=colour[(s.kind, s.critical)], line=dict(color="#FFFFFF", width=1)),
            text=s.task, textposition="inside", insidetextanchor="middle", textangle=0, showlegend=False,
            hovertemplate=f"{s.task}<br>{s.start:.0f} → {s.end:.0f} min<extra></extra>"))
    fig.add_vline(x=0, line_color="#0B1220", line_width=2, annotation_text="line stops", annotation_position="top")
    fig.add_vline(x=stop, line_color="#0B1220", line_dash="dash", annotation_text="restart", annotation_position="top")
    workers = [f"Operator {chr(65 + i)}" for i in range(int(crew))]
    fig.update_xaxes(title="minutes from the line stopping")
    ui.plotly_layout(fig, 110 + 60 * int(crew))
    fig.update_layout(barmode="overlay", uniformtext_minsize=11, uniformtext_mode="hide", margin=dict(t=36))
    fig.update_yaxes(categoryorder="array", categoryarray=workers[::-1], range=[-0.5, len(workers) - 0.5])
    st.plotly_chart(fig, width="stretch")
    st.caption("Green: done before the line stops. Dark blue: the critical path that sets the restart time. "
               "Light blue: runs alongside. Step times are each step's usual time.")

# ---- matrix ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Changeover matrix (minutes)**")
    m = ctx.matrix
    grid = m.pivot(index="from", columns="to", values="est_min").reindex(index=names, columns=names)
    fig = px.imshow(grid, text_auto=".0f", color_continuous_scale=["#FDF6EC", "#F5C894", "#B45309"], aspect="auto")
    fig.update_xaxes(title="to", side="top")
    fig.update_yaxes(title="from")
    st.plotly_chart(ui.plotly_layout(fig, 340), width="stretch")
    src = m["source"].value_counts().to_dict()
    st.caption("Sources: " + ", ".join(f"{v} pairs from {k}" for k, v in src.items()) +
               ". A pair switches to its own history once it has "
               f"{int(ctx.settings.get('matrix_min_pair_logs', 3))} or more logs.")
