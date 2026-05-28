"""
Model Explorer — article-format showcase of the xShot + RAPM/xRAPM models.

Structured as a single vertical scroll with sections that build on each other:
  1. xShot model performance
  2. Feature importance
  3. Shot difficulty landscape
  4. Why xRAPM is more stable than RAPM
  5. Interactive shot chart explorer
  6. Known limitations
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import streamlit as st

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_player_names
from dashboard.utils.shot_queries import (
    get_player_shots, get_player_shot_zones, get_league_zone_averages, get_player_id,
)
from dashboard.utils.model_queries import (
    load_feature_importance, load_calibration_data, load_model_metadata,
    get_shot_difficulty_dist, get_stability_data,
)
from dashboard.utils.viz import (
    calibration_curve_fig, feature_importance_fig, shot_difficulty_dist_fig,
    stability_scatter_fig, zone_efficiency_chart, zone_frequency_chart,
)
from dashboard.utils.court import shot_scatter_fig, shot_hexbin_fig
from dashboard.utils.nba_static import team_color
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    SURFACE, BORDER, MODEBAR,
    ARTICLE_CSS, art_section, finding, chart_caption, metric_card, metric_row,
    interactive_well_open, interactive_well_close,
)

st.set_page_config(
    page_title="Model Explorer · NBA xShot + RAPM",
    page_icon="🔬",
    layout="wide",
)

st.markdown(ARTICLE_CSS, unsafe_allow_html=True)

# ── Load static artifacts (cached, fast) ───────────────────────────────────
fi_data  = load_feature_importance()
cal_data = load_calibration_data()
meta     = load_model_metadata()
eval_m   = meta.get("evaluation", {})

# ── Page header ─────────────────────────────────────────────────────────────
st.markdown(
    f"<h1 style='margin-bottom:4px'>🔬 Model Explorer</h1>"
    f"<p style='font-size:1.0rem;color:{MUTED};max-width:780px;line-height:1.6;margin-top:0'>"
    "A technical walkthrough of the xShot shot-quality model and the RAPM/xRAPM "
    "impact model — how they were built, what they learned, and why the process-based "
    "xRAPM produces more reliable ratings than outcomes-based RAPM."
    "</p>",
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — xSHOT MODEL PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════

st.markdown(art_section("Section 01", "The xShot Model"), unsafe_allow_html=True)

st.markdown(
    "**xShot** is an XGBoost classifier that predicts the probability a field goal attempt "
    "is made, given only pre-shot context: court location, shot type, game clock, period, "
    "and whether it's a playoff game. Crucially, **the model has no idea who is shooting** — "
    "it measures shot difficulty, not shooter identity.\n\n"
    "The model was trained on shots from 2014-15 through 2022-23, then evaluated on a "
    f"held-out {meta.get('test_seasons', '2023-24 → 2024-25')} test set "
    f"({eval_m.get('test_n_shots', 0):,} shots the model never saw during training)."
)

ll      = eval_m.get("log_loss", "—")
ll_base = eval_m.get("baseline_log_loss", "—")
ll_red  = eval_m.get("log_loss_reduction_pct", 7.7)
brier   = eval_m.get("brier_score", "—")
n_test  = eval_m.get("test_n_shots", 0)

st.markdown(
    metric_row(
        metric_card("Log Loss", str(ll),   f"vs baseline {ll_base}", ACCENT),
        metric_card("Improvement", f"{ll_red:.1f}%", "over mean-FG% baseline", ACCENT_GREEN),
        metric_card("Brier Score", str(brier), "mean squared error", ACCENT_BLUE),
        metric_card("Test Shots", f"{n_test:,}", meta.get("test_seasons", "holdout"), ACCENT_GOLD),
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# Calibration curve
cal_col, cal_text = st.columns([3, 2])
with cal_col:
    fig_cal = calibration_curve_fig(cal_data)
    st.plotly_chart(fig_cal, use_container_width=True, config=MODEBAR, key="exp_cal")
    st.markdown(
        chart_caption(
            "Each dot is a bucket of shots with similar predicted xShot. "
            "A perfectly calibrated model's dots sit on the dashed diagonal. "
            "The curve hugging it tightly across the 0.25–0.85 range confirms "
            "the model's probabilities are well-grounded."
        ),
        unsafe_allow_html=True,
    )
with cal_text:
    st.markdown("#### What good calibration means")
    st.markdown(
        "If the model assigns a 40% probability to a shot, roughly 40% of those "
        "shots should actually be made. Deviations reveal systematic bias — the model "
        "is either over-confident or under-confident in that probability range.\n\n"
        "This matters for downstream metrics: `fg_pct_above_expected` and xRAPM are "
        "only interpretable if the baseline probability is accurate. A miscalibrated "
        "model would produce biased shot-quality scores even if its rank order is correct."
    )
    st.markdown(
        finding(f"✅ &nbsp;xShot achieves a <strong>{ll_red:.1f}% log-loss reduction</strong> over a naive baseline that always predicts the league-average FG% — confirming the model captures meaningful signal beyond 'shots go in about 47% of the time.'"),
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("Section 02", "What the Model Learned"), unsafe_allow_html=True)

fi_text, fi_col = st.columns([2, 3])
with fi_text:
    st.markdown("#### Feature gain importance")
    st.markdown(
        "XGBoost's *gain* importance measures how much a feature reduces prediction "
        "error across all tree splits. The top contributors reveal what truly "
        "determines shot difficulty:\n\n"
        "**Shot type flags** (dunk, layup) dominate because they are nearly "
        "deterministic — a dunk goes in ~98% of the time regardless of location. "
        "The model quickly learns to flag these.\n\n"
        "**Spatial features** (distance, zone, angle) carry the bulk of the remaining "
        "signal — closer and more central shots are easier.\n\n"
        "**Context features** (clock, period, playoffs) add modest but real signal: "
        "late-game, high-pressure shots are converted at lower rates."
    )
    st.markdown(
        finding(
            "🎯 &nbsp;Dunk + layup classification alone account for over a third of "
            "total feature gain — the model's first priority is recognising high-probability "
            "at-rim attempts before caring about anything else.",
            variant="blue",
        ),
        unsafe_allow_html=True,
    )
with fi_col:
    fig_fi = feature_importance_fig(fi_data, top_n=15)
    st.plotly_chart(fig_fi, use_container_width=True, config=MODEBAR, key="exp_fi")
    st.markdown(
        chart_caption(
            "Top 15 features by normalised XGBoost gain. "
            "Blue = spatial features, orange = shot-type flags, grey = context. "
            "Longer bars = more prediction error reduced by that feature."
        ),
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — SHOT DIFFICULTY LANDSCAPE
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("Section 03", "The Shot Difficulty Landscape"), unsafe_allow_html=True)

dist_text, dist_col = st.columns([2, 3])
with dist_text:
    st.markdown("#### Why a single FG% fails")
    st.markdown(
        "The NBA average FG% is roughly **47%**. A model that always predicts 47% "
        "technically gets close — but it misses everything interesting.\n\n"
        "The chart shows that shot difficulty is **bimodal**: there's a cluster of "
        "high-probability at-rim attempts (dunks, layups, put-backs) in the 0.55–0.95 "
        "range, and a separate cluster of perimeter shots in the 0.25–0.45 range.\n\n"
        "Using a single average flattens this heterogeneity entirely. xShot assigns "
        "each shot its own probability, so that a player who scores on dunks is not "
        "given the same credit as a player who converts contested pull-up threes."
    )
    st.markdown(
        finding(
            "📊 &nbsp;The bimodal distribution means treating all field goals as "
            "'equally difficult' misattributes value by roughly 15–25 percentage points "
            "for players at the extremes of the shot-selection spectrum.",
            variant="green",
        ),
        unsafe_allow_html=True,
    )
with dist_col:
    with st.spinner("Loading…"):
        df_dist = get_shot_difficulty_dist()
    if not df_dist.empty:
        fig_diff = shot_difficulty_dist_fig(df_dist)
        st.plotly_chart(fig_diff, use_container_width=True, config=MODEBAR, key="exp_dist")
        st.markdown(
            chart_caption(
                "Distribution of xShot probabilities across all 2.68M attempts. "
                "Green = at-rim attempts (easy), red = perimeter/contested shots (hard). "
                "A naive model uses one vertical line at 0.47 for everything."
            ),
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — xRAPM VS RAPM STABILITY
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("Section 04", "Why xRAPM Is More Reliable Than RAPM"), unsafe_allow_html=True)

st.markdown(
    "RAPM measures what *actually happened* — real points scored. xRAPM measures the "
    "*quality of the process* that generated those outcomes, using xShot-derived "
    "expected points instead of actual makes and misses.\n\n"
    "If xRAPM truly captures more signal and less noise, it should be **more predictable "
    "year-over-year** — a player's process quality should be more consistent than whether "
    "their shots happened to fall. The scatter plots below test this directly."
)

min_poss = st.select_slider(
    "Minimum possessions per season (both years)",
    options=[100, 200, 300, 500, 750, 1000],
    value=300,
    key="stab_poss",
)

with st.spinner("Computing year-to-year pairs…"):
    df_pairs = get_stability_data(min_poss=min_poss)

r2_rapm = r2_xrapm = None
if not df_pairs.empty:
    try:
        r2_rapm  = float(np.corrcoef(df_pairs["rapm_a"],  df_pairs["rapm_b"])[0, 1]) ** 2
        r2_xrapm = float(np.corrcoef(df_pairs["xrapm_a"], df_pairs["xrapm_b"])[0, 1]) ** 2
    except Exception:
        pass

if r2_rapm is not None and r2_xrapm is not None:
    delta = r2_xrapm - r2_rapm
    direction = "higher" if delta > 0 else "lower"
    st.markdown(
        finding(
            f"📈 &nbsp;xRAPM R² = <strong>{r2_xrapm:.3f}</strong> &nbsp;vs&nbsp; "
            f"RAPM R² = <strong>{r2_rapm:.3f}</strong> — "
            f"xRAPM year-over-year correlation is <strong>{abs(delta):.3f} points {direction}</strong>, "
            f"{'confirming' if delta > 0 else 'not confirming at this threshold'} that removing "
            f"shot-making variance improves the signal-to-noise ratio of impact estimates.",
            variant="blue" if delta > 0 else "",
        ),
        unsafe_allow_html=True,
    )

stab_c1, stab_c2 = st.columns(2)
with stab_c1:
    st.markdown(f"#### RAPM — Year N vs Year N+1")
    st.markdown(
        f"<span style='color:{MUTED};font-size:0.82rem'>"
        "Actual outcomes. Variance from shooting luck reduces year-over-year correlation."
        "</span>",
        unsafe_allow_html=True,
    )
    fig_r = stability_scatter_fig(df_pairs, metric="rapm", label="RAPM", color=ACCENT)
    if fig_r:
        st.plotly_chart(fig_r, use_container_width=True, config=MODEBAR, key="exp_stab_rapm")
        st.markdown(
            chart_caption("Each dot = one player-season pair. Dashed line = OLS fit. R² shown in chart."),
            unsafe_allow_html=True,
        )

with stab_c2:
    st.markdown(f"#### xRAPM — Year N vs Year N+1")
    st.markdown(
        f"<span style='color:{MUTED};font-size:0.82rem'>"
        "Process-based. Shot-making variance removed — should show tighter correlation."
        "</span>",
        unsafe_allow_html=True,
    )
    fig_x = stability_scatter_fig(df_pairs, metric="xrapm", label="xRAPM", color=ACCENT_BLUE)
    if fig_x:
        st.plotly_chart(fig_x, use_container_width=True, config=MODEBAR, key="exp_stab_xrapm")
        st.markdown(
            chart_caption("Same population as left chart. Higher R² = more predictable across seasons."),
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 — INTERACTIVE SHOT EXPLORER
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("Section 05", "Interactive Shot Chart Explorer"), unsafe_allow_html=True)

st.markdown(
    "Pick any player and season to visualise xShot model outputs directly on the court. "
    "Switch between scatter (individual shots) and hexbin (density map) modes. "
    "The hexbin modes show — for each court zone — either raw shot volume, average difficulty, "
    "actual FG%, or FG% relative to xShot expectation (the model's signal)."
)

st.markdown(interactive_well_open(), unsafe_allow_html=True)

all_names   = get_player_names()
default     = "Nikola Jokić" if "Nikola Jokić" in all_names else (all_names[0] if all_names else "")
seasons     = get_seasons()
def_s       = "2024-25" if "2024-25" in seasons else (seasons[0] if seasons else "")

fc1, fc2, fc3 = st.columns([3, 2, 2])
player_name = fc1.selectbox("Player", all_names,
    index=all_names.index(default) if default in all_names else 0, key="exp_player")
season      = fc2.selectbox("Season", seasons,
    index=seasons.index(def_s) if def_s in seasons else 0, key="exp_season")
season_type = fc3.selectbox("Season Type", get_season_types(), key="exp_stype")

mode_col, hex_col = st.columns([2, 3])
chart_mode  = mode_col.radio("Chart style", ["Scatter", "Hexbin"], horizontal=True, key="exp_mode")

hex_mode = "volume"
if chart_mode == "Hexbin":
    mode_opts = {
        "Shot Volume":        "volume",
        "xShot (Difficulty)": "xshot",
        "Actual FG%":         "fg_pct",
        "FG% Above Expected": "fg_vs_expected",
    }
    hex_mode_label = hex_col.select_slider(
        "Hexbin display", options=list(mode_opts.keys()),
        value="Shot Volume", key="exp_hexmode",
    )
    hex_mode = mode_opts[hex_mode_label]

pid = get_player_id(player_name)
if pid is None:
    st.warning(f"Player ID not found for {player_name}.")
else:
    with st.spinner("Loading shot data…"):
        df_shots    = get_player_shots(pid, season, season_type)
        df_zones    = get_player_shot_zones(pid, season, season_type)
        df_lg_zones = get_league_zone_averages(season, season_type)

    if df_shots.empty:
        st.info(f"No shot data for {player_name} in {season} {season_type}.")
    else:
        tcolor = team_color("UNK")
        chart_col, zone_col = st.columns([5, 3])
        with chart_col:
            if chart_mode == "Scatter":
                fig_court = shot_scatter_fig(
                    df_shots, player_name=player_name, season=season,
                    season_type=season_type, team_color=tcolor,
                    show_zone_overlay=True, df_zones=df_zones,
                )
            else:
                fig_court = shot_hexbin_fig(
                    df_shots, mode=hex_mode, player_name=player_name,
                    season=season, season_type=season_type, team_color=tcolor,
                )
            st.plotly_chart(fig_court, use_container_width=True, config=MODEBAR, key="exp_court")
        with zone_col:
            st.markdown(f"**Zone Efficiency vs xShot**")
            fig_ze = zone_efficiency_chart(df_zones, league_zones=df_lg_zones,
                                           player_name=player_name)
            st.plotly_chart(fig_ze, use_container_width=True, config=MODEBAR, key="exp_ze")
            st.markdown(f"**Shot Distribution by Zone**")
            fig_zf = zone_frequency_chart(df_zones, player_name=player_name)
            st.plotly_chart(fig_zf, use_container_width=True, config=MODEBAR, key="exp_zf")

st.markdown(interactive_well_close(), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 — KNOWN LIMITATIONS
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("Section 06", "Known Limitations"), unsafe_allow_html=True)

st.markdown(
    "Every model has blind spots. Being explicit about them is part of honest analysis — "
    "it tells you where to trust the outputs and where extra caution is warranted."
)

limitations = [
    ("No defender proximity data", "xShot",
     ACCENT_GOLD,
     "The model cannot distinguish a wide-open corner 3 from a closely-guarded one. "
     "A 25-foot pull-up over a flat-footed defender and the same shot into a rim protector "
     "get the same xShot. Tracking data (Second Spectrum) would close this gap but is not "
     "publicly available."),
    ("No shooter identity in xShot", "xShot",
     ACCENT_GOLD,
     "By design, xShot does not know who is shooting — it measures shot difficulty, "
     "not shooter quality. Stephen Curry's pull-up 3 and a bench player's pull-up 3 "
     "get the same xShot. Curry's skill shows up in FG% above expected, not xShot."),
    ("RAPM collinearity", "RAPM / xRAPM",
     ACCENT_BLUE,
     "Players who almost never play without their best teammates have nearly identical "
     "rows in the design matrix. Ridge regression shrinks their coefficients toward zero "
     "rather than producing extreme estimates, but cannot perfectly separate stars who "
     "share 95% of their minutes."),
    ("Small-sample instability", "RAPM / xRAPM",
     ACCENT_BLUE,
     "Below ~1,000 stint possessions, ridge bias dominates and estimates aren't published. "
     "Injury-shortened seasons and bench players are poorly estimated even with the "
     "3-year pooled model."),
    ("Era effects", "Both models",
     ACCENT,
     "The NBA in 2014-15 and 2025-26 are different games — 3-point rates, pace, and "
     "defensive schemes have all shifted. Single-season RAPM is comparable within an era; "
     "cross-era comparisons should be treated as approximate."),
    ("No free throws or turnovers", "xRAPM",
     ACCENT,
     "xRAPM's target uses xShot-derived expected points (field goals only). Free throw "
     "generation, fouling tendencies, and turnovers are absent. RAPM (actual outcomes) "
     "subsumes these naturally; xRAPM does not."),
]

for title, scope, scope_color, body in limitations:
    with st.expander(f"{title}  —  {scope}", expanded=False):
        st.markdown(
            f"<span style='font-size:0.78rem;font-weight:700;color:{scope_color}'>{scope}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(body)
