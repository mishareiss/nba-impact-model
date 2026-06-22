"""
Methodology — complete technical documentation for xShot and RAPM/xRAPM.

Merged from former Model Explorer + Methodology pages into a single
vertical-scroll article. Covers data pipeline, feature engineering,
model design, evaluation, interactive shot explorer, limitations,
and future improvements.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import streamlit as st
import plotly.graph_objects as go

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
    inject_global_css, page_header, section_label, art_section,
    metric_card, metric_row, finding, chart_caption,
    interactive_well_open, interactive_well_close,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SURFACE, BORDER, MODEBAR,
)

st.set_page_config(
    page_title="Methodology · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()

fi_data  = load_feature_importance()
cal_data = load_calibration_data()
meta     = load_model_metadata()
eval_m   = meta.get("evaluation", {})

st.markdown(
    page_header(
        "Methodology",
        "Technical documentation for the xShot shot-quality model and the RAPM/xRAPM "
        "player impact model — how they were built, what they measure, and where they fall short.",
    ),
    unsafe_allow_html=True,
)

st.markdown(
    f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin:16px 0">'
    f'<a href="#data-pipeline" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">Data Pipeline</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#xshot" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">xShot Model</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#rapm" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">RAPM / xRAPM</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#evaluation" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">Evaluation</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#shot-explorer" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">Shot Explorer</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#limitations" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">Limitations</a>'
    f'<span style="color:{TEXT_SECONDARY}">·</span>'
    f'<a href="#future" style="font-size:0.82rem;color:{ACCENT};text-decoration:none">Future Work</a>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── SECTION 1 — DATA PIPELINE ─────────────────────────────────────────────────
st.markdown(art_section("Section 01", "Data Pipeline"), unsafe_allow_html=True)
st.markdown(
    "All data originates from the **NBA Stats API** via the `nba_api` Python library. "
    "The ingestion pipeline is idempotent — each game can be re-fetched and re-inserted "
    "safely, with `ingestion_log` checkpointing skipping previously successful games."
)

pipeline = [
    ("NBA Stats API",      "PlayByPlayV3, LeagueDashPlayerStats, LeagueDashTeamStats",
     "7.5M PBP events, 12 seasons, regular season + playoffs"),
    ("PostgreSQL",         "play_by_play, games, players, teams, player_season_stats",
     "Raw events stored with UniqueConstraint (game_id, action_id) — no duplicates"),
    ("Feature Engineering","build_features.py: shot_angle, shot_zone, shot-type flags",
     "30 features, saved to shots_features.parquet + metadata JSON sidecar"),
    ("xShot Training",     "train_xshot.py: XGBoost binary classifier, temporal split",
     "Train: 2014-15→2022-23. Test: 2023-24→2024-25 (466k held-out shots)"),
    ("Inference",          "predict.py: xshot, xshot_points per FGA",
     "2.68M shot predictions → shot_predictions table"),
    ("Stint Construction", "build_stints.py: parse substitution events from PBP",
     "421,849 stints across 15,370 games with possession counts and xShot aggregates"),
    ("RAPM Training",      "train_xrapm.py (v1) + train_xrapm_v2.py (pooled)",
     "Ridge regression: λ=30k, min 1k poss (single-season), 2k poss (pooled)"),
    ("Analytics Views",    "build_views.py: materialized views for dashboard",
     "player_career_stats, player_shot_zones, team_shot_quality, player_impact_leaderboard"),
]

for title, detail, result in pipeline:
    st.markdown(
        f'<div style="display:flex;gap:0;align-items:stretch;margin-bottom:4px">'
        f'<div style="width:3px;background:{ACCENT};border-radius:2px;flex-shrink:0;margin-right:14px"></div>'
        f'<div style="flex:1;background:{SURFACE};border:1px solid {BORDER};'
        f'border-radius:7px;padding:10px 14px">'
        f'<div style="font-size:0.85rem;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:3px">{title}</div>'
        f'<div style="font-size:0.78rem;color:{TEXT_SECONDARY};margin-bottom:2px">{detail}</div>'
        f'<div style="font-size:0.72rem;color:{TEXT_MUTED}">{result}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 2 — xSHOT MODEL ───────────────────────────────────────────────────
st.markdown(art_section("Section 02", "The xShot Model"), unsafe_allow_html=True)

xshot_left, xshot_right = st.columns([3, 2])
with xshot_left:
    st.markdown("#### What xShot Measures")
    st.markdown(
        "**xShot** is the predicted probability that a field goal attempt is made, "
        "given only pre-shot observable context. Crucially, **xShot does not know who is shooting** — "
        "it measures *shot difficulty*, not shooter quality. "
        "This is the same framing as **expected goals (xG)** in soccer analytics.\n\n"
        "The gap between a player's actual FG% and their average xShot is where "
        "shooter skill lives (`fg_pct_above_expected`)."
    )
    st.markdown("#### Feature Engineering")
    feature_table = (
        "| Category | Features | Signal |\n"
        "|----------|---------|--------|\n"
        "| **Spatial** | `shot_distance`, `shot_angle`, `x_legacy`, `y_legacy`, `shot_zone`, `is_corner_three`, `is_paint` | Strongest |\n"
        "| **Shot type** | `is_dunk`, `is_layup`, `is_pullup`, `is_fadeaway`, `is_cutting`, `is_putback`, `is_alley_oop`, `is_finger_roll`, `is_driving`, `is_running`, `is_stepback`, `is_hook`, `is_floating`, `is_turnaround`, `is_reverse`, `is_bank` | Very strong |\n"
        "| **Context** | `period`, `clock_seconds`, `is_overtime`, `is_playoffs`, `shot_value` | Moderate |\n"
    )
    st.markdown(feature_table)
    st.markdown("#### Model Training")
    st.markdown(
        f"- **Algorithm:** XGBoost binary classifier\n"
        f"- **Training:** {meta.get('train_seasons', '2014-15 → 2022-23')} "
        f"(strictly chronological split — no future leakage)\n"
        f"- **Holdout:** {meta.get('test_seasons', '2023-24 → 2024-25')} "
        f"({eval_m.get('test_n_shots', 0):,} shots)\n"
        f"- **Hyperparameters:** `max_depth=6`, `learning_rate=0.05`, `subsample=0.8`, "
        f"`colsample_bytree=0.8`, `min_child_weight=10`\n"
        f"- **Early stopping:** 20 rounds on holdout log-loss. "
        f"Best iteration: {meta.get('best_iteration', 127)}\n"
        f"- **No Platt scaling** — XGBoost outputs used directly (calibration curve confirms this is safe)"
    )
with xshot_right:
    st.markdown("#### What xShot captures")
    st.markdown(
        "- ✅ Shot location and distance\n"
        "- ✅ Shot type (dunk vs pull-up etc.)\n"
        "- ✅ Game context (late-game, playoffs)\n"
        "- ❌ Defender proximity (no tracking data)\n"
        "- ❌ Shooter identity (intentional by design)\n"
        "- ❌ Free throws or assists"
    )
    st.markdown("#### Downstream Metrics")
    st.markdown(
        "| Metric | Derivation |\n"
        "|--------|------------|\n"
        "| `xshot` | P(make) per FGA |\n"
        "| `mean_xshot` | Player avg shot difficulty |\n"
        "| `fg_pct_above_expected` | Actual FG% − avg xShot |\n"
        "| `shot_pts_above_expected` | Σ(made − xshot) × shot_value |\n"
        "| `xshot_pts` | xshot × shot_value |\n"
    )

st.markdown("#### Calibration Curve")
st.caption(
    "If xShot = 0.40 for a bucket of shots, ~40% should be made. "
    "Calibration verifies the probabilities are well-grounded, not just rank-ordered."
)
cal_col, cal_text = st.columns([3, 2])
with cal_col:
    fig_cal = calibration_curve_fig(cal_data)
    st.plotly_chart(fig_cal, use_container_width=True, config=MODEBAR, key="meth_cal")
    st.markdown(chart_caption("Each dot = a bin of shots with similar predicted xShot. Perfect calibration = diagonal."), unsafe_allow_html=True)
with cal_text:
    ll_red = eval_m.get("log_loss_reduction_pct", 7.7)
    st.markdown(
        finding(
            f"✅ xShot achieves a <strong>{ll_red:.1f}% log-loss reduction</strong> over a naive baseline "
            f"that always predicts league-average FG%.",
            variant="green",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        "This confirms the model captures meaningful signal beyond "
        "'shots go in about 47% of the time.' Calibration holds across the "
        "0.25–0.85 probability range where most shots fall."
    )

st.markdown("#### Feature Importance")
st.caption("XGBoost gain: how much each feature reduces prediction error across all tree splits.")
fi_text, fi_col = st.columns([2, 3])
with fi_col:
    fig_fi = feature_importance_fig(fi_data, top_n=15)
    st.plotly_chart(fig_fi, use_container_width=True, config=MODEBAR, key="meth_fi")
    st.markdown(chart_caption("Top 15 features by normalised gain. Blue = spatial, orange = shot-type flags, grey = context."), unsafe_allow_html=True)
with fi_text:
    st.markdown(
        finding(
            "🎯 Dunk + layup classification alone accounts for over a third of "
            "total feature gain — the model's first priority is recognising high-probability "
            "at-rim attempts.",
            variant="blue",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Shot type flags** dominate because they are nearly deterministic — "
        "a dunk goes in ~98% of the time regardless of location. "
        "**Spatial features** carry the bulk of remaining signal. "
        "**Context** (clock, period, playoffs) adds modest but real signal."
    )

st.markdown("#### Shot Difficulty Distribution")
st.caption("The distribution is bimodal — showing that treating all shots as equally difficult is a significant error.")
with st.spinner("Loading distribution…"):
    df_dist = get_shot_difficulty_dist()
if not df_dist.empty:
    fig_diff = shot_difficulty_dist_fig(df_dist)
    st.plotly_chart(fig_diff, use_container_width=True, config=MODEBAR, key="meth_dist")

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 3 — RAPM / xRAPM ─────────────────────────────────────────────────
st.markdown(art_section("Section 03", "RAPM and xRAPM"), unsafe_allow_html=True)

rapm_left, rapm_right = st.columns([3, 2])
with rapm_left:
    st.markdown("#### What RAPM Solves")
    st.markdown(
        "Simple plus/minus is useless for comparing players: a backup who only plays "
        "with starters looks great, while a star on a poor team looks bad. "
        "**RAPM** controls for this by modelling all lineup combinations simultaneously.\n\n"
        "Every 5v5 possession segment where both rosters are stable is a **lineup stint**. "
        "Each stint contributes a row to the design matrix. The regression estimates how "
        "much each individual player adds *independent of everyone else on the court*."
    )
    st.markdown("#### Design Matrix Construction")
    st.markdown(
        "For each stint, create a row vector of length = all players in the dataset.\n\n"
        "- **Home players:** `+1`\n"
        "- **Away players:** `−1`\n"
        "- **Everyone else:** `0`\n\n"
        "Target = net scoring margin (home pts − away pts) per 100 possessions, "
        "weighted by stint possession count.\n\n"
        "For **xRAPM**, replace actual points with xShot-derived expected points "
        "(`home_xshot_pts − away_xshot_pts`). Same regression, process-based target."
    )
    st.markdown("#### Ridge Regularisation")
    st.markdown(
        "The design matrix is large (~421k rows, ~600 columns) and highly collinear — "
        "teammates always appear together. Ridge regression (L2 penalty) prevents "
        "overfitting by shrinking coefficients toward zero.\n\n"
        "- **λ = 30,000** for net RAPM / xRAPM\n"
        "- **λ = 15,000** for O/D decomposition\n\n"
        "Below ~1,000 stint possessions, ridge bias dominates and estimates are not published."
    )
    st.markdown("#### O-RAPM / D-RAPM Decomposition")
    st.markdown(
        "The stint matrix is doubled:\n\n"
        "- **Row 1 (offense):** home players `+1`, away players `0`\n"
        "- **Row 2 (defense):** home players `0`, away players `+1` (negated)\n\n"
        "Running ridge on this doubled matrix yields separate offensive and defensive coefficients."
    )
with rapm_right:
    st.markdown("#### v2: Pooled + Box-Score Prior")
    st.markdown(
        "**Problem:** A player with 800 stint possessions has too little data for the "
        "ridge penalty to separate their contribution from noise.\n\n"
        "**Solution:** Pool 3 consecutive seasons. More data reduces collinearity. "
        "The trade-off is less sensitivity to within-career improvement.\n\n"
        "**Box-score prior:** each player gets a prior estimate based on per-minute "
        "plus/minus scaled to per-100-possession units (γ = `(pm/min) × 48 × 0.12`). "
        "The prior is centred across the league.\n\n"
        "The regression runs on `y − Xγ` (residuals after prior), then recovers "
        "`β* = γ + β_residual`.\n\n"
        "**Effect:** data-rich players are barely changed. Data-sparse players are "
        "pulled toward their historical baseline — a more informative prior than zero."
    )
    st.markdown("#### Output Interpretation")
    st.markdown(
        "All values are **pts per 100 lineup-stint possessions vs league-average player**.\n\n"
        "| Value | Meaning |\n"
        "|-------|--------|\n"
        "| `+2.0` | Lineup is 2 pts/100 better with this player than average |\n"
        "| `0.0` | Exactly league-average contribution |\n"
        "| `−1.5` | Lineup is 1.5 pts/100 worse with this player |\n\n"
        "Top players typically range from +1.5 to +3.0. Scale is conservative due to ridge shrinkage."
    )

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 4 — EVALUATION ────────────────────────────────────────────────────
st.markdown(art_section("Section 04", "Model Evaluation"), unsafe_allow_html=True)

ll      = eval_m.get("log_loss", "—")
ll_base = eval_m.get("baseline_log_loss", "—")
ll_red  = eval_m.get("log_loss_reduction_pct", 7.7)
brier   = eval_m.get("brier_score", "—")
n_test  = eval_m.get("test_n_shots", 0)

st.markdown(
    metric_row(
        metric_card("Log Loss",    str(ll),            f"baseline: {ll_base}",    ACCENT),
        metric_card("Improvement", f"{ll_red:.1f}%",   "over mean-FG% baseline", ACCENT_GREEN),
        metric_card("Brier Score", str(brier),         "mean squared prob error", ACCENT_BLUE),
        metric_card("Test Shots",  f"{n_test:,}",      meta.get("test_seasons", "holdout"), ACCENT_GOLD),
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown("#### Year-to-Year Stability: RAPM vs xRAPM")
st.caption(
    "If xRAPM captures more signal than RAPM, it should be more predictable year-over-year. "
    "Higher R² = past values are better predictors of future values."
)

min_poss_stab = st.select_slider(
    "Minimum possessions per season (both years)",
    options=[100, 200, 300, 500, 750, 1000],
    value=300,
    key="stab_poss",
)
with st.spinner("Computing year-to-year pairs…"):
    df_pairs = get_stability_data(min_poss=min_poss_stab)

r2_rapm = r2_xrapm = None
if not df_pairs.empty:
    try:
        import numpy as np
        r2_rapm  = float(np.corrcoef(df_pairs["rapm_a"],  df_pairs["rapm_b"])[0, 1]) ** 2
        r2_xrapm = float(np.corrcoef(df_pairs["xrapm_a"], df_pairs["xrapm_b"])[0, 1]) ** 2
    except Exception:
        pass

if r2_rapm is not None and r2_xrapm is not None:
    delta = r2_xrapm - r2_rapm
    direction = "higher" if delta > 0 else "lower"
    st.markdown(
        finding(
            f"📈 xRAPM R² = <strong>{r2_xrapm:.3f}</strong> &nbsp;vs&nbsp; "
            f"RAPM R² = <strong>{r2_rapm:.3f}</strong> — "
            f"xRAPM year-over-year correlation is <strong>{abs(delta):.3f} points {direction}</strong>.",
            variant="blue" if delta > 0 else "",
        ),
        unsafe_allow_html=True,
    )

stab_c1, stab_c2 = st.columns(2)
with stab_c1:
    st.markdown("**RAPM — Year N vs Year N+1**")
    fig_r = stability_scatter_fig(df_pairs, metric="rapm", label="RAPM", color=ACCENT_GOLD)
    if fig_r:
        st.plotly_chart(fig_r, use_container_width=True, config=MODEBAR, key="meth_stab_rapm")
with stab_c2:
    st.markdown("**xRAPM — Year N vs Year N+1**")
    fig_x = stability_scatter_fig(df_pairs, metric="xrapm", label="xRAPM", color=ACCENT)
    if fig_x:
        st.plotly_chart(fig_x, use_container_width=True, config=MODEBAR, key="meth_stab_xrapm")

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 5 — INTERACTIVE SHOT EXPLORER ─────────────────────────────────────
st.markdown(art_section("Section 05", "Interactive Shot Explorer"), unsafe_allow_html=True)
st.markdown(
    "Pick any player and season to visualise xShot outputs on the court. "
    "Switch between scatter (individual shots) and hexbin (density/efficiency) modes."
)

st.markdown(interactive_well_open(), unsafe_allow_html=True)

all_names   = get_player_names()
default     = "Nikola Jokić" if "Nikola Jokić" in all_names else (all_names[0] if all_names else "")
seasons     = get_seasons()
def_s       = "2025-26" if "2025-26" in seasons else (seasons[0] if seasons else "")

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
        "Hexbin metric", options=list(mode_opts.keys()), value="Shot Volume", key="exp_hexmode",
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
            st.markdown("**Zone Efficiency vs xShot**")
            fig_ze = zone_efficiency_chart(df_zones, league_zones=df_lg_zones, player_name=player_name)
            st.plotly_chart(fig_ze, use_container_width=True, config=MODEBAR, key="exp_ze")
            st.markdown("**Shot Distribution by Zone**")
            fig_zf = zone_frequency_chart(df_zones, player_name=player_name)
            st.plotly_chart(fig_zf, use_container_width=True, config=MODEBAR, key="exp_zf")

st.markdown(interactive_well_close(), unsafe_allow_html=True)

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 6 — LIMITATIONS ──────────────────────────────────────────────────
st.markdown(art_section("Section 06", "Model Limitations"), unsafe_allow_html=True)
st.caption(
    "Documenting limitations builds credibility. These are honest statements about "
    "where the model should be trusted and where extra caution is warranted."
)

limitations = [
    ("No defender proximity", "xShot", "High",
     "The model cannot distinguish a wide-open corner 3 from a closely-guarded one. "
     "Defender proximity is the single most important missing variable. "
     "Second Spectrum tracking data would address this but is not publicly available."),
    ("No shooter identity in xShot", "xShot", "Medium (by design)",
     "xShot excludes shooter identity intentionally to measure shot difficulty, not shooter quality. "
     "Stephen Curry's pull-up and a bench player's pull-up get the same xShot. "
     "Curry's skill shows up in FG% above expected, not xShot."),
    ("RAPM collinearity", "RAPM / xRAPM", "High for team-concentrated players",
     "Players who almost never play without their best teammates have nearly identical "
     "rows in the design matrix. Ridge shrinks toward zero rather than producing extreme "
     "estimates, but cannot perfectly separate two stars sharing 95% of their minutes."),
    ("Small-sample instability", "RAPM / xRAPM", "Mitigated by thresholds + pooling",
     "Below ~1,000 stint possessions, ridge bias dominates and estimates are not published. "
     "Injury-shortened seasons and bench players remain poorly estimated even with pooling."),
    ("Era effects", "Both models", "Medium for cross-era comparisons",
     "The NBA in 2014-15 and 2025-26 are substantially different games. "
     "3-point rates, pace, and lineup construction have all shifted. "
     "Single-season RAPM is comparable within an era; cross-era comparisons are approximate."),
    ("No free throws or turnovers in xRAPM", "xRAPM", "Medium",
     "xRAPM's target uses xShot-derived expected points (field goals only). "
     "Free throw generation, fouling tendencies, and turnovers are absent. "
     "RAPM (actual outcomes) subsumes these naturally. "
     "Players who generate FTs or draw charges may be undervalued by xRAPM."),
]

for title, scope, severity, body in limitations:
    with st.expander(f"{title}  —  {scope}", expanded=False):
        sev_color = ACCENT_GREEN if "Mitigated" in severity else ACCENT_GOLD if "Medium" in severity else "#EF4444"
        st.markdown(
            f'<span style="font-size:0.75rem;font-weight:700;color:{sev_color}">'
            f'Severity: {severity}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(body)

st.markdown("<hr style='border-color:#27272A;margin:24px 0'>", unsafe_allow_html=True)

# ── SECTION 7 — FUTURE IMPROVEMENTS ──────────────────────────────────────────
st.markdown(art_section("Section 07", "Future Improvements"), unsafe_allow_html=True)

improvements = [
    ("Defender proximity via tracking data",
     "Incorporating Second Spectrum or similar player-tracking data to add defender distance "
     "as a feature would be the single largest improvement to xShot accuracy."),
    ("Era normalisation for RAPM",
     "Adjusting RAPM outputs for league-wide pace and efficiency changes across seasons "
     "would improve cross-era comparability."),
    ("Shooter identity model variant",
     "A separate xShot+Identity model that includes shooter fixed effects would enable "
     "decomposing shot quality vs. shooter skill at the prediction level."),
    ("Free throw and turnover integration in xRAPM",
     "Extending the xRAPM target variable to include xFT (expected free throws) and "
     "turnover costs would produce a more complete process-based metric."),
    ("Automated season refresh",
     "A pipeline trigger (cron job or NBA season-end webhook) to re-run ingestion, "
     "prediction, RAPM training, and view refresh when new data is available."),
]

for title, body in improvements:
    st.markdown(
        f'<div style="display:flex;gap:12px;margin-bottom:10px">'
        f'<div style="color:{ACCENT};font-size:1.0rem;flex-shrink:0;padding-top:2px">→</div>'
        f'<div><div style="font-size:0.875rem;font-weight:600;color:{TEXT_PRIMARY};'
        f'margin-bottom:3px">{title}</div>'
        f'<div style="font-size:0.8rem;color:{TEXT_SECONDARY};line-height:1.5">{body}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
