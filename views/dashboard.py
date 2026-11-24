from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, hero, planning, ui
from core.analysis import fmt_min, pareto
from core.rules import run_rules

con = ui.con()
line_id = st.session_state.get("line_id", 1)
ctx = planning.context(con, line_id)
line_name = ctx.line.get("name", "Line")
crew = int(ctx.line.get("crew_size", 3))

# ---- hero: what is running now and what comes next -------------------------
now = planning.current_flavour(con, line_id)
next_text, next_pair, planned, usual = "No production orders entered yet. Add them in the Planner.", "—", "—", ""
best_saving = None
if now:
    day = planning.next_order_date(con, line_id)
    orders = planning.orders_for(con, ctx, line_id, day) if day else []
    if orders:
        entered, best = planning.plans(ctx, now, orders)
        best_saving = entered.changeover_min - best.changeover_min
        fc = planning.first_changeover(best, now)
        frm, first = fc if fc else (now, best.sequence[0])
        est = ctx.cost.get((frm[0], first.flavour_id), 0.0)
        next_pair = f"{frm[1]} → {first.name}"
        next_text = (f"Next on the line is {first.name}, following the planner's order for "
                     f"{pd.Timestamp(day):%d %b}. Light to dark keeps cleaning short.")
        planned = fmt_min(planning.planned_for_pair(ctx, est, crew))
        usual = f"usual {fmt_min(est)}"
hero_html = (
    hero.render(now[1] if now else "—", ui.colours(now[1] if now else ""), line_name, next_text, next_pair,
                planned, usual, db.has_sample_data(con))
)
if hasattr(st, "iframe"):          # Streamlit 1.50+
    st.iframe(hero_html, height=420)
else:                              # older Streamlit
    import streamlit.components.v1 as components
    components.html(hero_html, height=420)
c1, c2, _ = st.columns([1, 1, 3])
c1.page_link("views/log_changeover.py", label="Log a changeover", icon=":material/timer:")
c2.page_link("views/planner.py", label="Open planner", icon=":material/route:")

# ---- KPIs over the last 30 days --------------------------------------------
summary, logs = ctx.summary, ctx.logs
since = pd.Timestamp(date.today() - timedelta(days=30))
recent = summary[summary["date"] >= since] if not summary.empty else summary
recent_logs = logs[logs["date"] >= since] if not logs.empty else logs
par = pareto(recent_logs)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Average line-stop", fmt_min(recent["stop_min"].mean()) if len(recent) else "—",
          help=f"{len(recent)} changeovers in the last 30 days")
k2.metric("Line-stop hours", f"{recent['stop_min'].sum() / 60:.0f} h" if len(recent) else "—",
          help="Lost to changeovers in the last 30 days")
if len(par):
    k3.metric(f"Biggest bottleneck · {par.iloc[0]['share']:.0%}", par.iloc[0]["activity"],
              help="Share of all line-stop time in the last 30 days")
else:
    k3.metric("Biggest bottleneck", "—")
k4.metric("Saving in next plan", fmt_min(best_saving) if best_saving is not None else "—",
          help="From a better flavour order (Planner)")

# ---- charts ------------------------------------------------------------------
left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**Line-stop per changeover**")
    if len(recent):
        avg = recent["stop_min"].mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=recent["line_stop_ts"], y=recent["stop_min"], mode="lines+markers",
                                 line=dict(color="#1D4ED8", width=2.5), fill="tozeroy",
                                 fillcolor="rgba(59,107,240,0.12)", name="Line-stop (min)",
                                 customdata=recent["pair"], hovertemplate="%{customdata}<br>%{y:.0f} min<extra></extra>"))
        fig.add_hline(y=avg, line_dash="dash", line_color="#B45309",
                      annotation_text=f"average {fmt_min(avg)}", annotation_position="bottom right")
        fig.update_yaxes(title="minutes", rangemode="tozero")
        st.plotly_chart(ui.plotly_layout(fig, 260), width="stretch")
    else:
        st.info("No finished changeovers in the last 30 days.")
with right.container(border=True):
    st.markdown("**Top 5 bottlenecks**")
    if len(par):
        top = par.head(5).iloc[::-1]
        fig = go.Figure(go.Bar(
            x=top["total_min"] / 60, y=top["activity"], orientation="h",
            marker_color=["#1D4ED8"] * (len(top) - 1) + ["#B45309"],
            text=[f"{s:.0%}" for s in top["share"]], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:.1f} h<extra></extra>"))
        fig.update_xaxes(title="hours of line-stop", range=[0, float(top["total_min"].max()) / 60 * 1.18])
        st.plotly_chart(ui.plotly_layout(fig, 260), width="stretch")
        st.page_link("views/analysis.py", label="Full analysis", icon=":material/arrow_forward:")
    else:
        st.info("Nothing logged yet.")

# ---- recommendations and recent changeovers ---------------------------------
left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**Latest recommendations**")
    recs = run_rules(recent_logs, recent, ctx.base, ctx.settings)[:3]
    for r in recs:
        st.markdown(f'<div class="rec"><span class="pill {r["severity"]}">{r["severity"].title()}</span> '
                    f'<small style="color:#5A6372">Rule {r["rule_code"]} · {r["kind"]}</small><br>{r["message"]}</div>',
                    unsafe_allow_html=True)
    if not recs:
        st.success("No issues found in the last 30 days.")
with right.container(border=True):
    st.markdown("**Recent changeovers**")
    if len(summary):
        avg_all = summary["stop_min"].mean()
        t = summary.sort_values("line_stop_ts", ascending=False).head(6)
        st.dataframe(pd.DataFrame({
            "Date": t["date"].dt.strftime("%d %b"), "Flavours": t["pair"],
            "Line-stop": t["stop_min"].map(fmt_min),
            "vs average": (t["stop_min"] - avg_all).map(lambda m: ("+" if m > 0 else "") + fmt_min(m)),
        }), hide_index=True, width="stretch")
