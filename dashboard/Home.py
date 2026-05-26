"""
NBA xShot + RAPM Impact Model — Project Overview
Landing page: project context, pipeline diagram, dataset summary,
model overview, key findings, and navigation.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from dashboard.utils.model_queries import (
    load_model_metadata, get_dataset_summary,
)
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    SURFACE, SURFACE_MED, BORDER, section_label, metric_card, metric_row,
    insight_card, nav_tile,
)

st.set_page_config(
    page_title="NBA xShot + RAPM Model",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.badge {
    display:inline-block;
    background:rgba(255,255,255,0.07);
    border:1px solid rgba(255,255,255,0.13);
    border-radius:5px;
    padding:3px 10px;
    font-size:0.75rem;
    font-weight:600;
    color:rgba(200,210,220,0.85);
    margin:2px 4px 2px 0;
    letter-spacing:0.03em;
}
.pipeline-node {
    flex:1; min-width:105px;
    background:rgba(255,255,255,0.05);
    border:1px solid rgba(255,255,255,0.10);
    border-radius:9px;
    padding:12px 10px;
    text-align:center;
}
.pipeline-node .pn-icon { font-size:1.3rem; margin-bottom:4px; }
.pipeline-node .pn-title {
    font-size:0.78rem; font-weight:700;
    color:rgba(220,225,232,0.92); margin-bottom:3px;
}
.pipeline-node .pn-sub {
    font-size:0.66rem; color:rgba(160,165,175,0.72); line-height:1.35;
}
.pipeline-arrow {
    display:flex; align-items:center; justify-content:center;
    font-size:1.1rem; color:rgba(160,165,175,0.45);
    padding:0 2px; flex-shrink:0;
}
.flex-row { display:flex; gap:8px; flex-wrap:wrap; align-items:stretch; }
.insight-row { display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; }
</style>
""", unsafe_allow_html=True)


# ── Load data (cached) ──────────────────────────────────────────────────────

meta = load_model_metadata()
try:
    summary = get_dataset_summary()
except Exception:
    summary = {}

eval_m = meta.get("evaluation", {})


# ── SECTION 1 — HERO ────────────────────────────────────────────────────────

st.markdown(
    f"<h1 style='margin-bottom:6px;font-size:2.1rem'>🏀 NBA xShot + RAPM Impact Model</h1>"
    f"<p style='font-size:1.0rem;color:{MUTED};max-width:800px;line-height:1.6;margin-top:0'>"
    "An end-to-end machine learning system for measuring NBA shot quality and player impact. "
    "An XGBoost model predicts the probability of every field goal attempt; "
    "those predictions feed a Ridge regression lineup model that isolates each player's "
    "marginal contribution to team scoring, controlling for teammates and opponents."
    "</p>",
    unsafe_allow_html=True,
)

# Tech stack badges
badges = [
    "XGBoost", "Ridge Regression", "Python 3.11",
    "PostgreSQL", "SQLAlchemy", "Streamlit", "Plotly",
]
st.markdown(
    "".join(f'<span class="badge">{b}</span>' for b in badges),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Scale numbers as inline cards
n_shots  = summary.get("shots",   2_680_000)
n_stints = summary.get("stints",    421_000)
n_seas   = summary.get("seasons",        12)
n_plyr   = summary.get("players",       500)

cards_html = metric_row(
    metric_card("Field Goal Attempts", f"{n_shots/1e6:.2f}M", "2014-15 → 2025-26", ACCENT),
    metric_card("Lineup Stints", f"{n_stints/1e3:.0f}k", "5v5 possession segments", ACCENT_BLUE),
    metric_card("Seasons", str(n_seas), "Regular season + playoffs", ACCENT_GREEN),
    metric_card("Log-Loss Reduction", f"{eval_m.get('log_loss_reduction_pct', 7.7):.1f}%",
                "xShot vs naive baseline", ACCENT_GOLD),
)
st.markdown(cards_html, unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)


# ── SECTION 2 — PIPELINE DIAGRAM ───────────────────────────────────────────

st.markdown(section_label("System Architecture"), unsafe_allow_html=True)
st.caption("End-to-end data pipeline from raw API data to dashboard-ready impact ratings.")

pipeline_nodes = [
    ("🌐", "NBA Stats API",      "play-by-play · box scores · shot logs"),
    ("🗄️", "PostgreSQL",         "raw PBP + shots\nstored & indexed"),
    ("⚙️", "Feature Engineering","spatial zones · shot types\nclock · context flags"),
    ("🎯", "xShot Model",        "XGBoost classifier\nP(make | shot context)"),
    ("📐", "Stint Construction", "5v5 lineup segments\nxShot pts aggregated"),
    ("📊", "RAPM / xRAPM",       "Ridge regression\nper-100 poss impact"),
    ("📱", "Dashboard",          "interactive explorer\nleaderboards · profiles"),
]

arrow = '<div class="pipeline-arrow">→</div>'
nodes_html = arrow.join(
    f'<div class="pipeline-node">'
    f'<div class="pn-icon">{icon}</div>'
    f'<div class="pn-title">{title}</div>'
    f'<div class="pn-sub">{sub.replace(chr(10), "<br>")}</div>'
    f'</div>'
    for icon, title, sub in pipeline_nodes
)
st.markdown(
    f'<div class="flex-row" style="align-items:center">{nodes_html}</div>',
    unsafe_allow_html=True,
)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)


# ── SECTION 3 — DATASET SUMMARY ────────────────────────────────────────────

st.markdown(section_label("Dataset Summary"), unsafe_allow_html=True)

n_games = summary.get("games", 0)
games_str = f"{n_games:,}" if n_games else "~15,000"

row2 = metric_row(
    metric_card("Games Ingested", games_str, "2014-15 through 2025-26", MUTED_LIGHT),
    metric_card("Shot Predictions", f"{n_shots/1e6:.2f}M", "xShot scored via predict.py", ACCENT),
    metric_card("Lineup Stints",    f"{n_stints/1e3:.0f}k", "weighted by possessions", ACCENT_BLUE),
    metric_card("Players Modeled",  str(n_plyr) if n_plyr else "~600",
                "≥300 stint possessions", ACCENT_GREEN),
    metric_card("Training cutoff",  meta.get("train_seasons", "2014-15 → 2022-23"),
                f"test: {meta.get('test_seasons', '2023-24 → 2024-25')}", ACCENT_GOLD),
)
st.markdown(row2, unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)


# ── SECTION 4 — MODEL OVERVIEW ─────────────────────────────────────────────

st.markdown(section_label("Model Overview"), unsafe_allow_html=True)

tab_xshot, tab_rapm = st.tabs(["🎯  xShot Model", "📊  RAPM / xRAPM"])

with tab_xshot:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### What is xShot?")
        st.markdown(
            "**xShot** is the predicted probability that a field goal attempt will be made, "
            "given only pre-shot information — location, shot type, shot value, clock, and game context. "
            "It answers: *how difficult was this shot to make, on average?*\n\n"
            "**Why not just use FG%?** FG% conflates shot selection with shot-making. A player "
            "averaging 55% may be hunting only layups; another averaging 47% may be taking "
            "contested pull-ups. xShot separates the two by establishing a per-shot difficulty baseline."
        )
        st.markdown("#### How it was built")
        st.markdown(
            f"- **Algorithm:** XGBoost binary classifier\n"
            f"- **Training data:** ~{(n_shots - 466446)/1e6:.1f}M shots, 2014-15 → "
            f"{meta.get('train_seasons', '2022-23').split('→')[-1].strip()}\n"
            f"- **Features:** {meta.get('feature_count', 30)} features — spatial coordinates, "
            f"shot zone, shot type flags, period, clock, playoffs\n"
            f"- **Temporal split:** trained on historical data, evaluated on 2023-25 holdout\n"
            f"- **No shooter identity** in the model — by design, to prevent circular reasoning\n"
            f"- **Holdout log-loss:** {eval_m.get('log_loss', '0.638')} "
            f"({eval_m.get('log_loss_reduction_pct', 7.7):.1f}% improvement over naive baseline)"
        )
    with c2:
        st.markdown("#### Key outputs")
        st.markdown(
            "| Output | Description |\n"
            "|--------|-------------|\n"
            "| `xshot` | P(make) for each FGA |\n"
            "| `mean_xshot` | Player avg shot difficulty |\n"
            "| `fg_pct_above_expected` | Actual − expected FG% |\n"
            "| `shot_pts_above_expected` | Total value added vs baseline |\n"
            "| `xshot_pts` | Expected points per attempt |\n"
        )
        st.markdown("#### Feature categories")
        st.markdown(
            f"**Spatial** (strongest signal): distance, zone, angle, x/y coordinates\n\n"
            f"**Shot type flags**: dunk, layup, pullup, fadeaway, cutting, putback…\n\n"
            f"**Context**: period, clock, playoff game indicator"
        )

with tab_rapm:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### What is RAPM / xRAPM?")
        st.markdown(
            "**RAPM** (Regularised Adjusted Plus-Minus) measures a player's marginal contribution "
            "to team scoring margin per 100 possessions, controlling simultaneously for all "
            "teammates and opponents on the court via Ridge regression over lineup stints.\n\n"
            "**xRAPM** is the same regression, but the target is *expected* scoring margin "
            "derived from xShot predictions instead of actual makes and misses. "
            "This removes shot-making variance and measures process quality.\n\n"
            "**RAPM − xRAPM** (the process gap) flags players whose actual outcomes "
            "diverge from their process: positive = outscoring shot quality (elite finishing "
            "or variance); negative = regression candidate."
        )
        st.markdown("#### Multi-year pooling (v2)")
        st.markdown(
            "Single-season RAPM is noisy for players with limited minutes. "
            "The v2 model pools 3 consecutive seasons, anchors estimates toward a "
            "box-score prior (per-minute plus/minus × 0.12), and shrinks small-sample "
            "outliers toward the historical baseline. **RAPM+Prior** is the recommended "
            "metric for cross-player comparisons."
        )
    with c2:
        st.markdown("#### Key design decisions")
        st.markdown(
            "**Ridge regularisation (λ):** prevents overfitting when players share "
            "many lineups. λ=30,000 for net RAPM; λ=15,000 for O/D split.\n\n"
            "**Possession weighting:** stints weighted by total possessions so "
            "high-minute players contribute proportionally more.\n\n"
            "**Minimum threshold:** 1,000 stint possessions for single-season; "
            "2,000 for pooled — below this, ridge bias dominates.\n\n"
            "**O-RAPM / D-RAPM:** separate offensive and defensive regressions "
            "using a doubled stint matrix with +1 encoding for on-court only."
        )

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)


# ── SECTION 5 — KEY FINDINGS ───────────────────────────────────────────────

st.markdown(section_label("Key Findings"), unsafe_allow_html=True)

ll_red = eval_m.get("log_loss_reduction_pct", 7.7)
findings = [
    ("🎯", f"{ll_red:.1f}% log-loss reduction",
     "xShot outperforms a naive mean-FG% baseline on a 466k-shot holdout. "
     "Shot location and type dominate; dunk classification alone accounts for ~35% of feature gain."),
    ("📈", "xRAPM more stable year-to-year",
     "Year-to-year R² for xRAPM consistently exceeds RAPM. Removing made/missed "
     "variance isolates the process signal, making xRAPM more predictive of future performance."),
    ("⚖️", "RAPM − xRAPM identifies variance",
     "Players with large positive gaps tend to regress; large negative gaps often "
     "precede improvement. The process gap is a leading indicator, not a quality verdict."),
    ("🔬", "Pooling reduces noise by ~40%",
     "The standard deviation of 3-year pooled estimates is materially tighter than "
     "single-season estimates, confirming that sample size is the primary source of RAPM noise."),
]

st.markdown(
    '<div class="insight-row">'
    + "".join(insight_card(icon, h, b) for icon, h, b in findings)
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)


# ── SECTION 6 — NAVIGATION ─────────────────────────────────────────────────

st.markdown(section_label("Explore the Model"), unsafe_allow_html=True)

pages = [
    ("pages/1_Model_Explorer.py", "🔬", "Model Explorer",
     "xShot calibration · feature importance · shot difficulty distribution · "
     "year-over-year stability analysis · methodology · limitations"),
    ("pages/2_Leaderboards.py",   "📊", "Leaderboards",
     "RAPM & xRAPM player rankings by season. Metric tabs for overall, "
     "offense, defense, and shooting. Distribution context for every value."),
    ("pages/3_Player_Profile.py", "👤", "Player Profile",
     "Per-player shot chart · hexbin density map · zone efficiency · "
     "RAPM/xRAPM career trend · process vs results scatter."),
    ("pages/4_Methodology.py",    "📖", "Methodology",
     "Technical deep-dives into xShot, RAPM/xRAPM, validation approach, "
     "and an honest discussion of model limitations."),
]

nav_cols = st.columns(len(pages))
for col, (page, icon, title, desc) in zip(nav_cols, pages):
    with col:
        st.page_link(page, label=f"{icon}  **{title}**", use_container_width=True)
        st.caption(desc)

st.markdown("---")
st.caption(
    "Data: NBA Stats API · Seasons 2014-15 through 2025-26 · "
    "Regular Season + Playoffs · Models retrained seasonally"
)
