"""
NBA Impact Dashboard — Home Page

Hero section, KPI cards, product value props, key findings, navigation.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from dashboard.utils.model_queries import load_model_metadata, get_dataset_summary
from dashboard.utils.theme import (
    inject_global_css,
    page_header, section_label,
    metric_card, metric_row, insight_card,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, ACCENT_PURPLE,
    TEXT_SECONDARY, TEXT_MUTED, SURFACE, BORDER, BG,
)

st.set_page_config(
    page_title="NBA Impact Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()

# ── Load cached data ─────────────────────────────────────────────────────────
meta   = load_model_metadata()
try:
    summary = get_dataset_summary()
except Exception:
    summary = {}

eval_m = meta.get("evaluation", {})

n_shots  = summary.get("shots",   2_680_000)
n_stints = summary.get("stints",    421_000)
n_seas   = summary.get("seasons",        12)
n_plyr   = summary.get("players",       500)
n_games  = summary.get("games",      15_000)

# ── HERO ─────────────────────────────────────────────────────────────────────
st.markdown(
    page_header(
        "NBA Impact Dashboard",
        "An end-to-end basketball analytics platform measuring shot quality and player impact "
        "across 12 seasons of NBA data. Built for basketball operations decision support."
    ),
    unsafe_allow_html=True,
)

badges = [
    "XGBoost", "Ridge Regression", "Python 3.11",
    "PostgreSQL", "SQLAlchemy", "Streamlit", "Plotly",
]
st.markdown(
    "".join(f'<span class="nb-badge">{b}</span>' for b in badges),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ── KPI CARDS ────────────────────────────────────────────────────────────────
ll_red = eval_m.get("log_loss_reduction_pct", 7.7)
st.markdown(
    metric_row(
        metric_card("Field Goal Attempts",   f"{n_shots/1e6:.2f}M",    "2014-15 → 2025-26",         ACCENT),
        metric_card("Lineup Stints",         f"{n_stints/1e3:.0f}k",   "5v5 possession segments",    ACCENT_BLUE),
        metric_card("Seasons Covered",       str(n_seas),              "Regular Season + Playoffs",  ACCENT_GREEN),
        metric_card("Players Rated",         f"{n_plyr:,}" if n_plyr else "~500",
                    "RAPM-qualified (≥1k poss)",  ACCENT_GOLD),
        metric_card("Model Improvement",     f"{ll_red:.1f}%",         "log-loss vs naive baseline", ACCENT_PURPLE),
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

# ── SYSTEM ARCHITECTURE ───────────────────────────────────────────────────────
st.markdown(section_label("System Architecture"), unsafe_allow_html=True)
st.caption("End-to-end pipeline from raw NBA API data to dashboard-ready impact ratings.")

pipeline_nodes = [
    ("NBA Stats API",      "play-by-play\nshot logs · box scores"),
    ("PostgreSQL",         "raw events stored\n& indexed"),
    ("Feature Engineering","spatial zones · shot types\nclock · context"),
    ("xShot Model",        "XGBoost · P(make)\nper shot context"),
    ("Stint Construction", "5v5 lineup segments\nxShot aggregated"),
    ("RAPM / xRAPM",       "Ridge regression\nper-100 poss impact"),
    ("Dashboard",          "Leaderboards\nProfiles · Lineups"),
]

arrow = (
    f'<div style="display:flex;align-items:center;justify-content:center;'
    f'color:{TEXT_SECONDARY};font-size:0.85rem;padding:0 2px;flex-shrink:0">→</div>'
)
nodes_html = arrow.join(
    f'<div style="flex:1;min-width:90px;background:{SURFACE};border:1px solid {BORDER};'
    f'border-radius:8px;padding:10px 10px;text-align:center">'
    f'<div style="font-size:0.75rem;font-weight:700;color:#E4E4E7;margin-bottom:3px">{title}</div>'
    f'<div style="font-size:0.65rem;color:{TEXT_MUTED};line-height:1.4">'
    f'{sub.replace(chr(10), "<br>")}</div>'
    f'</div>'
    for title, sub in pipeline_nodes
)
st.markdown(
    f'<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">{nodes_html}</div>',
    unsafe_allow_html=True,
)

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

# ── WHAT THIS ANSWERS ────────────────────────────────────────────────────────
st.markdown(section_label("Questions This Dashboard Answers"), unsafe_allow_html=True)

questions = [
    ("Who drives winning?",
     "RAPM and xRAPM isolate each player's marginal impact on team scoring margin, "
     "controlling for every teammate and opponent they share the court with."),
    ("Who creates quality shots?",
     "xShot scores every field goal attempt by location, shot type, and context — "
     "identifying players who generate high-value offensive opportunities."),
    ("Who outperforms expectation?",
     "RAPM − xRAPM separates shot-making skill from process quality, flagging "
     "players likely to regress or improve as variance normalizes."),
    ("Which players are undervalued?",
     "Decision Support surfaces players whose process (xRAPM) significantly "
     "exceeds their observed outcomes (RAPM) — buy-low candidates."),
    ("Which lineups work?",
     "Lineup Evaluation compares 5-player units' actual net rating against "
     "their xShot-expected net rating, revealing sustainable vs lucky combinations."),
    ("How do we test basketball knowledge?",
     "The Daily Stat Challenge generates a new season-stat leaderboard puzzle each day, "
     "built entirely from the project database."),
]

cols = st.columns(3)
for i, (q, a) in enumerate(questions):
    with cols[i % 3]:
        st.markdown(
            f'<div style="background:{SURFACE};border:1px solid {BORDER};'
            f'border-radius:8px;padding:14px 16px;margin-bottom:10px;height:100%">'
            f'<div style="font-size:0.85rem;font-weight:700;color:#E4E4E7;'
            f'margin-bottom:6px">{q}</div>'
            f'<div style="font-size:0.78rem;color:{TEXT_SECONDARY};line-height:1.5">{a}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

# ── KEY FINDINGS ──────────────────────────────────────────────────────────────
st.markdown(section_label("Key Findings"), unsafe_allow_html=True)

findings = [
    (ACCENT,        f"{ll_red:.1f}% Log-Loss Reduction",
     "xShot outperforms a naive mean-FG% baseline on a 466k-shot holdout. "
     "Shot location and type dominate; dunk classification alone accounts for ~35% of feature gain."),
    (ACCENT_BLUE,   "xRAPM More Stable Year-to-Year",
     "Year-over-year R² for xRAPM consistently exceeds RAPM. Removing shot-making "
     "variance isolates the process signal, making xRAPM more predictive of future performance."),
    (ACCENT_GREEN,  "RAPM − xRAPM Identifies Variance",
     "Players with large positive gaps tend to regress; large negative gaps often "
     "precede improvement. The process gap is a leading indicator, not a quality verdict."),
    (ACCENT_GOLD,   "Pooling Reduces Noise by ~40%",
     "The standard deviation of 3-year pooled estimates is materially tighter than "
     "single-season estimates, confirming that sample size is the primary RAPM noise source."),
]

st.markdown(
    f'<div style="display:flex;gap:10px;flex-wrap:wrap">'
    + "".join(insight_card("", h, b, a) for a, h, b in findings)
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

# ── NAVIGATION ────────────────────────────────────────────────────────────────
st.markdown(section_label("Explore"), unsafe_allow_html=True)

pages = [
    ("pages/2_Leaderboards.py",        "Leaderboards",
     "xRAPM, RAPM, O/D splits, xShot overperformance — ranked with percentiles and distribution context."),
    ("pages/3_Player_Profile.py",       "Player Profile",
     "Shot charts, percentile profile, season trends, shot quality landscape, and analyst interpretation."),
    ("pages/4_Lineup_Evaluation.py",    "Lineup Evaluation",
     "Expected vs actual net rating for 5-player lineups. Identifies sustainable vs lucky combinations."),
    ("pages/5_Decision_Support.py",     "Decision Support",
     "Undervalued players, hidden contributors, breakout candidates, and team fit concepts."),
    ("pages/6_Daily_Stat_Challenge.py", "Daily Stat Challenge",
     "Guess the Top 5 for today's season stat category. New challenge every day."),
    ("pages/7_Methodology.py",          "Methodology",
     "Technical deep-dive: xShot model, RAPM/xRAPM design, validation, and limitations."),
    ("pages/8_Glossary.py",             "Glossary",
     "Definitions for xShot, RAPM, xRAPM, possession, net rating, regularization, and more."),
]

nav_cols = st.columns(4)
for i, (page, title, desc) in enumerate(pages):
    with nav_cols[i % 4]:
        st.page_link(page, label=f"**{title}**", use_container_width=True)
        st.caption(desc)

st.markdown(
    f'<div class="nb-divider" style="margin-top:32px"></div>'
    f'<div style="font-size:0.72rem;color:{TEXT_MUTED}">'
    f'Data: NBA Stats API · Seasons 2014-15 through 2025-26 · '
    f'Regular Season + Playoffs · Models retrained seasonally</div>',
    unsafe_allow_html=True,
)
