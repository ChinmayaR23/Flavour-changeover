"""Flavour Changeover Optimizer: Streamlit entry point.

Run locally:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Changeover Optimizer", page_icon=":material/local_drink:", layout="wide")

from core import ui  # noqa: E402  (after set_page_config)

ui.setup_page()
pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
    st.Page("views/log_changeover.py", title="Log changeover", icon=":material/timer:"),
    st.Page("views/analysis.py", title="Analysis", icon=":material/bar_chart:"),
    st.Page("views/planner.py", title="Planner", icon=":material/route:"),
    st.Page("views/settings.py", title="Data and settings", icon=":material/tune:"),
]
nav = st.navigation(pages)
st.sidebar.markdown("### Changeover Optimizer")
st.session_state.line_id = ui.sidebar()
nav.run()
