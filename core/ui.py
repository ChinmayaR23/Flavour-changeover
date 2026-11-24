"""Shared Streamlit helpers: connection, styling, small components."""
from __future__ import annotations

import streamlit as st

from core import db

FLAVOUR_COLOURS = {  # can colour, light stripe, label text, accent on dark
    "Lemon": ("#E6D53C", "#F7EF9E", "#2E3308", "#F6EE9A"),
    "Orange": ("#F2861E", "#FFC48C", "#3A1A00", "#FFC38A"),
    "Mango": ("#F6AE1A", "#FFDA8C", "#3D2400", "#FFD98A"),
    "Jeera": ("#8A6631", "#C9A36A", "#FFF4DE", "#D9B27A"),
    "Cola": ("#4A1A10", "#8C3A26", "#FFE3D6", "#EE9C80"),
}
FALLBACK_COLOURS = ("#3B82F6", "#93C5FD", "#FFFFFF", "#93C5FD")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, select, textarea { font-family: 'Inter', system-ui, sans-serif; }
h1, h2, h3 { font-family: 'Space Grotesk', 'Inter', sans-serif !important; letter-spacing: -0.01em; }
.block-container { padding-top: 2rem; max-width: 1180px; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #E6E9EF; border-radius: 18px; padding: 16px 18px;
  transition: transform .2s ease, box-shadow .2s ease; }
[data-testid="stMetric"]:hover { transform: translateY(-3px); box-shadow: 0 14px 30px rgba(15,23,42,.08); }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; }
.chip { display:inline-flex; align-items:center; gap:8px; height:34px; padding:0 12px; border-radius:10px;
  background:#FFFFFF; border:1px solid #D5DBE3; font-weight:600; font-size:14px; margin:2px 0; }
.dot { width:12px; height:12px; border-radius:50%; display:inline-block; }
.arrow { color:#475467; font-size:13px; font-weight:600; margin:0 6px; white-space:nowrap; }
.arrow.hot { color:#9A3412; }
.pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:700; }
.pill.high { background:#FCE8DA; color:#9A3412; } .pill.medium { background:#E3EAFB; color:#1E40AF; }
.pill.low { background:#EEF1F5; color:#3F4754; } .pill.sample { background:#FDF3E3; color:#7A3A05; }
.rec { padding:12px 14px; border-radius:12px; background:#F8FAFC; margin-bottom:8px; }
</style>
"""


@st.cache_resource
def _ready() -> bool:
    db.ensure_ready()
    return True


def con():
    _ready()
    if "con" not in st.session_state:
        st.session_state.con = db.connect()
    return st.session_state.con


def setup_page() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar() -> int:
    """Line picker plus the sample-data notice. Returns the chosen line id."""
    c = con()
    lines = db.df(c, "SELECT id, name FROM lines ORDER BY id")
    with st.sidebar:
        if lines.empty:
            st.warning("Add a production line in Data and settings.")
            return 0
        names = dict(zip(lines["name"], lines["id"]))
        choice = st.selectbox("Line", list(names), key="line_name")
        if db.has_sample_data(c):
            st.markdown(
                '<div style="padding:12px;border-radius:10px;background:#FDF3E3;border:1px solid #F0D3A8;'
                'color:#7A3A05;font-size:13px;line-height:19px"><b>Sample data</b><br>Numbers are illustrative '
                "until factory records are loaded. Remove them in Data and settings.</div>",
                unsafe_allow_html=True)
    return int(names[choice])


def colours(name: str):
    return FLAVOUR_COLOURS.get(name, FALLBACK_COLOURS)


def chip(name: str) -> str:
    return f'<span class="chip"><span class="dot" style="background:{colours(name)[0]}"></span>{name}</span>'


def plotly_layout(fig, height: int = 280):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=13, color="#1F2630"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor="#EEF1F5", zeroline=False)
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False)
    return fig
