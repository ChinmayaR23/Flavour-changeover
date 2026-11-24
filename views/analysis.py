from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import planning, ui
from core.analysis import fmt_min, pareto
from core.rules import run_rules, save_and_load, set_status

con = ui.con()
line_id = st.session_state.get("line_id", 1)
ctx = planning.context(con, line_id)

st.title("Analysis")
st.caption("Where line-stop time goes, and what to change.")

c1, c2 = st.columns(2)
period = c1.selectbox("Period", ["Last 30 days", "Last 7 days", "Last 90 days", "All time"])
pairs = c2.selectbox("Flavour pairs", ["All pairs", "Light → dark only", "Dark → light only"])
days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(period)
summary, logs = ctx.summary, ctx.logs
if days and len(summary):
    since = pd.Timestamp(date.today() - timedelta(days=days))
    summary, logs = summary[summary["date"] >= since], logs[logs["date"] >= since]
if pairs != "All pairs" and len(summary):
    keep = summary["colour_drop"] >= 2 if pairs.startswith("Dark") else summary["colour_drop"] < 2
    summary = summary[keep]
    logs = logs[logs["changeover_id"].isin(summary["id"])]

if logs.empty:
    st.info("No logged changeovers match these filters yet.")
    st.stop()

# ---- Pareto -------------------------------------------------------------------
par = pareto(logs)
with st.container(border=True):
    st.markdown("**Bottlenecks: Pareto ranking**")
    nb = int(par["bottleneck"].sum())
    st.caption(f"{nb} of {len(par)} steps cause {par[par['bottleneck']]['share'].sum():.0%} of line-stop time. "
               "Fix these first.")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=par["activity"], y=par["total_min"] / 60, name="Hours of line-stop",
                         marker_color=["#B45309" if b else "#9AA3B2" for b in par["bottleneck"]]))
    fig.add_trace(go.Scatter(x=par["activity"], y=par["cum_share"] * 100, name="Cumulative %", yaxis="y2",
                             mode="lines+markers", line=dict(color="#1D4ED8", width=2.5)))
    fig.add_hline(y=80, line_dash="dot", line_color="#1D4ED8", yref="y2")
    fig.update_layout(yaxis=dict(title="hours"), yaxis2=dict(title="cumulative", overlaying="y", side="right",
                                                             range=[0, 105], tickvals=[0, 20, 40, 60, 80, 100],
                                                             ticksuffix=" %", showgrid=False))
    st.plotly_chart(ui.plotly_layout(fig, 320), width="stretch")
    st.dataframe(pd.DataFrame({
        "Step": par["activity"], "Total": par["total_min"].map(fmt_min),
        "Share": par["share"], "Cumulative": par["cum_share"], "Bottleneck": par["bottleneck"]}),
        hide_index=True, width="stretch",
        column_config={"Share": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=float(par["share"].max())),
                       "Cumulative": st.column_config.NumberColumn(format="percent")})

# ---- Recommendations -------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Recommendations**")
    recs = save_and_load(con, run_rules(logs, summary, ctx.base, ctx.settings))
    show_all = st.toggle("Show ignored tips", False)
    if recs.empty:
        st.success("No issues found for these filters.")
    for r in recs.itertuples():
        if r.status == "ignored" and not show_all:
            continue
        a, b = st.columns([5, 2])
        badge = f'<span class="pill {r.severity}">{r.severity.title()}</span>'
        done = " · <b style='color:#0F766E'>accepted</b>" if r.status == "accepted" else (
            " · <i>ignored</i>" if r.status == "ignored" else "")
        a.markdown(f'<div class="rec">{badge} <small style="color:#5A6372">{r.rule_code} · {r.kind} · at stake '
                   f'{fmt_min(r.minutes_at_stake)}{done}</small><br>{r.message}</div>', unsafe_allow_html=True)
        x, y = b.columns(2)
        if x.button("Accept", key=f"acc{r.rec_key}", type="primary", disabled=r.status == "accepted"):
            set_status(con, r.rec_key, "accepted")
            st.rerun()
        if y.button("Ignore", key=f"ign{r.rec_key}", disabled=r.status == "ignored"):
            set_status(con, r.rec_key, "ignored")
            st.rerun()

# ---- Step variation ---------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Step times and variation**")
    st.caption("Usual = median of the last 20 logs. Variation (CV) above "
               f"{ctx.settings.get('cv_limit', 0.3):.2f} means the step is done differently each time.")
    b = ctx.base.copy()
    st.dataframe(pd.DataFrame({
        "Step": b["activity"], "Usual": b["usual_min"].map(fmt_min), "Slow day (P75)": b["p75_min"].map(fmt_min),
        "Variation (CV)": b["cv"], "Logs": b["n"], "Based on": b["source"]}),
        hide_index=True, width="stretch")

with st.container(border=True):
    st.markdown("**Changeovers**")
    st.caption("Overlap above 1.0 means some steps already run at the same time.")
    s = summary.sort_values("line_stop_ts", ascending=False)
    st.dataframe(pd.DataFrame({
        "Date": s["date"].dt.strftime("%d %b %Y"), "Flavours": s["pair"], "Shift": s["shift"],
        "Line-stop": s["stop_min"].map(fmt_min), "Work done": s["work_min"].map(fmt_min),
        "Overlap": s["parallel_ratio"], "Sample": s["is_sample"].astype(bool)}),
        hide_index=True, width="stretch")
