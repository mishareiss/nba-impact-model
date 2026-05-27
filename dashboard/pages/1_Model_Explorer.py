"""
Model Explorer — xShot performance, interactive shot explorer,
RAPM/xRAPM stability analysis, and model limitations.

This is the primary showcase of the ML work: every section answers
"What does this tell us about how the models work?"
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_player_names, get_league_distribution
from dashboard.utils.shot_queries import (
    get_player_shots, get_player_shot_zones, get_league_zone_averages, get_player_id,
)
from dashboard.utils.model_queries import (
    load_feature_importance, load_calibration_data, load_model_metadata,
    get_shot_difficulty_dist, get_stability_data,
)
from dashboard.utils.viz import (
    calibration_curve_fig, feature_importance_fig, shot_difficulty_dist_fig,
    stability_scatter_fig, zone_efficiency_chart, zone_frequency_chart, TIER_LEGEND,
)
from dashboard.utils.court import shot_scatter_fig, shot_hexbin_fig
from dashboard.utils.nba_static import team_color
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    section_label, MODEBAR,
)

st.set_page_config(
    page_title="Model Explorer · NBA xShot + RAPM",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Model Explorer")
st.caption(
    "Evaluate model quality, explore interactive shot charts, and examine "
    "the statistical properties that make xRAPM a more reliable impact metric than RAPM."
)

# ── Load static artifacts once ─────────────────────────────────────────────

fi_data   = load_feature_importance()
cal_data  = load_calibration_data()
meta      = load_model_metadata()
eval_m    = meta.get("evaluation", {})

# ── Page sections ──────────────────────────────────────────────────────────

sec_xshot, sec_explorer, sec_stability, sec_limits = st.tabs([
    "🎯  xShot Performance",
    "🏀  Interactive Shot Explorer",
    "📈  Stability Analysis",
    "⚠️  Limitations",
])


# ===========================================================================
# TAB 1 — xSHOT PERFORMANCE
# ===========================================================================

with sec_xshot:

    st.markdown(section_label("Model Evaluation"), unsafe_allow_html=True)

    # Key metrics banner
    ll      = eval_m.get("log_loss", "—")
    ll_base = eval_m.get("baseline_log_loss", "—")
    ll_red  = eval_m.get("log_loss_reduction_pct", "—")
    brier   = eval_m.get("brier_score", "—")
    n_test  = eval_m.get("test_n_shots", 0)

    st.markdown(
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">'
        f'<div style="flex:1;min-width:140px;background:rgba(255,255,255,0.04);'
        f'border-left:3px solid {ACCENT};border-radius:8px;padding:12px 14px">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};text-transform:uppercase">Log Loss</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{ll}</div>'
        f'<div style="font-size:0.72rem;color:{MUTED}">xShot model (holdout)</div></div>'
        f'<div style="flex:1;min-width:140px;background:rgba(255,255,255,0.04);'
        f'border-left:3px solid rgba(160,165,175,0.4);border-radius:8px;padding:12px 14px">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};text-transform:uppercase">Baseline Log Loss</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{ll_base}</div>'
        f'<div style="font-size:0.72rem;color:{MUTED}">always predict mean FG%</div></div>'
        f'<div style="flex:1;min-width:140px;background:rgba(255,255,255,0.04);'
        f'border-left:3px solid {ACCENT_GREEN};border-radius:8px;padding:12px 14px">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};text-transform:uppercase">Reduction</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{ll_red}%</div>'
        f'<div style="font-size:0.72rem;color:{MUTED}">improvement over baseline</div></div>'
        f'<div style="flex:1;min-width:140px;background:rgba(255,255,255,0.04);'
        f'border-left:3px solid {ACCENT_BLUE};border-radius:8px;padding:12px 14px">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};text-transform:uppercase">Brier Score</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{brier}</div>'
        f'<div style="font-size:0.72rem;color:{MUTED}">mean squared prob error</div></div>'
        f'<div style="flex:1;min-width:140px;background:rgba(255,255,255,0.04);'
        f'border-left:3px solid {ACCENT_GOLD};border-radius:8px;padding:12px 14px">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};text-transform:uppercase">Test Shots</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{n_test:,}</div>'
        f'<div style="font-size:0.72rem;color:{MUTED}">{meta.get("test_seasons", "2023-24 → 2024-25")}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Calibration curve + feature importance side-by-side ──
    col_cal, col_fi = st.columns([1, 1])

    with col_cal:
        st.markdown("#### Calibration Curve")
        st.caption(
            "A well-calibrated model's predictions match actual outcomes. "
            "Each point = a bin of shots with similar predicted probability; "
            "y-axis = fraction that were actually made. "
            "Hugging the diagonal means the model's confidence is well-grounded."
        )
        fig_cal = calibration_curve_fig(cal_data)
        st.plotly_chart(fig_cal, use_container_width=True, config=MODEBAR)

    with col_fi:
        st.markdown("#### Feature Importance  (XGBoost gain)")
        st.caption(
            "Gain importance measures how much each feature reduces prediction error "
            "across all tree splits. Shot type (especially dunk) and shot zone "
            "dominate — spatial context is the core signal."
        )
        fig_fi = feature_importance_fig(fi_data, top_n=15)
        st.plotly_chart(fig_fi, use_container_width=True, config=MODEBAR)

    # ── Shot difficulty distribution ──
    st.markdown("#### Shot Difficulty Distribution")
    st.caption(
        "Distribution of xShot probabilities across all 2.68M attempts. "
        "The bimodal shape reflects the distinction between high-probability "
        "at-rim attempts (0.55–0.95) and lower-probability perimeter shots (0.25–0.45). "
        "A naive FG% model uses a single mean — xShot captures this heterogeneity."
    )
    with st.spinner("Loading shot difficulty distribution…"):
        df_dist = get_shot_difficulty_dist()

    if not df_dist.empty:
        fig_diff = shot_difficulty_dist_fig(df_dist)
        st.plotly_chart(fig_diff, use_container_width=True, config=MODEBAR)


# ===========================================================================
# TAB 2 — INTERACTIVE SHOT EXPLORER
# ===========================================================================

with sec_explorer:

    st.markdown(section_label("xShot Explorer"), unsafe_allow_html=True)
    st.caption(
        "Visualise the xShot model's output for any player and season. "
        "Switch between scatter (individual shots) and hexbin (density) modes. "
        "Use the mode selector to view volume, raw shot quality, shooting efficiency, "
        "or FG% above/below expected."
    )

    # ── Controls ──
    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
    all_names   = get_player_names()
    default     = "Nikola Jokić" if "Nikola Jokić" in all_names else all_names[0]
    player_name = fc1.selectbox("Player", all_names,
                                index=all_names.index(default) if default in all_names else 0,
                                key="exp_player")
    seasons     = get_seasons()
    def_s       = "2024-25" if "2024-25" in seasons else seasons[0]
    season      = fc2.selectbox("Season", seasons,
                                index=seasons.index(def_s) if def_s in seasons else 0,
                                key="exp_season")
    season_type = fc3.selectbox("Season Type", get_season_types(), key="exp_stype")
    chart_mode  = fc4.selectbox("Chart Mode", ["scatter", "hexbin"], key="exp_mode")

    if chart_mode == "hexbin":
        mode_opts = {
            "Shot Volume":       "volume",
            "xShot (Difficulty)":"xshot",
            "Actual FG%":        "fg_pct",
            "FG% Above Expected":"fg_vs_expected",
        }
        hex_mode_label = st.select_slider(
            "Hexbin Display", options=list(mode_opts.keys()),
            value="Shot Volume", key="exp_hexmode"
        )
        hex_mode = mode_opts[hex_mode_label]
    else:
        hex_mode = "volume"

    # ── Load data ──
    pid = get_player_id(player_name)
    if pid is None:
        st.warning(f"Player ID not found for {player_name}.")
        st.stop()

    with st.spinner("Loading shots…"):
        df_shots    = get_player_shots(pid, season, season_type)
        df_zones    = get_player_shot_zones(pid, season, season_type)
        df_lg_zones = get_league_zone_averages(season, season_type)

    if df_shots.empty:
        st.info(f"No shot data for {player_name} in {season} {season_type}.")
    else:
        tcolor = team_color("UNK")
        chart_col, zone_col = st.columns([3, 2])

        with chart_col:
            if chart_mode == "scatter":
                fig_court = shot_scatter_fig(
                    df_shots,
                    player_name=player_name,
                    season=season,
                    season_type=season_type,
                    team_color=tcolor,
                    show_zone_overlay=True,
                    df_zones=df_zones,
                )
            else:
                fig_court = shot_hexbin_fig(
                    df_shots,
                    mode=hex_mode,
                    player_name=player_name,
                    season=season,
                    season_type=season_type,
                    team_color=tcolor,
                )
            st.plotly_chart(fig_court, use_container_width=True, config=MODEBAR)

        with zone_col:
            st.markdown("**Zone Efficiency**")
            fig_ze = zone_efficiency_chart(df_zones, league_zones=df_lg_zones,
                                           player_name=player_name)
            st.plotly_chart(fig_ze, use_container_width=True, config=MODEBAR)

            st.markdown("**Shot Distribution**")
            fig_zf = zone_frequency_chart(df_zones, player_name=player_name)
            st.plotly_chart(fig_zf, use_container_width=True, config=MODEBAR)


# ===========================================================================
# TAB 3 — STABILITY ANALYSIS
# ===========================================================================

with sec_stability:

    st.markdown(section_label("Year-to-Year Stability"), unsafe_allow_html=True)
    st.caption(
        "If xRAPM is a better process metric than RAPM, it should show higher "
        "year-over-year correlation — future performance should be more predictable from "
        "xRAPM than from RAPM. The R² values below test this directly."
    )

    min_poss_stab = st.slider(
        "Minimum possessions (both seasons)", min_value=100, max_value=1000,
        value=300, step=50, key="stab_minposs"
    )

    with st.spinner("Computing year-to-year pairs…"):
        df_pairs = get_stability_data(min_poss=min_poss_stab)

    if df_pairs.empty:
        st.info("Not enough data for stability analysis at this possession threshold.")
    else:
        n_pairs = len(df_pairs)
        st.caption(f"**{n_pairs:,}** consecutive-season player pairs (Regular Season, ≥{min_poss_stab} poss each).")

        stab_c1, stab_c2 = st.columns(2)

        with stab_c1:
            st.markdown("#### RAPM — Year-over-Year")
            st.caption(
                "Actual outcomes. Noise from shooting variance, team context changes, "
                "and small samples reduces R². Lower R² = less predictive signal."
            )
            fig_rapm_stab = stability_scatter_fig(
                df_pairs, metric="rapm", label="RAPM", color=ACCENT,
            )
            if fig_rapm_stab:
                st.plotly_chart(fig_rapm_stab, use_container_width=True, config=MODEBAR)

        with stab_c2:
            st.markdown("#### xRAPM — Year-over-Year")
            st.caption(
                "Process-based outcomes (expected points, not actual). "
                "Removing shooting variance should yield a higher R² — "
                "demonstrating xRAPM isolates more stable underlying quality."
            )
            fig_xrapm_stab = stability_scatter_fig(
                df_pairs, metric="xrapm", label="xRAPM", color=ACCENT_BLUE,
            )
            if fig_xrapm_stab:
                st.plotly_chart(fig_xrapm_stab, use_container_width=True, config=MODEBAR)

        st.markdown("#### Interpretation")
        # Compute R² values for the summary
        import numpy as np
        r2_rapm = r2_xrapm = None
        try:
            x_r = df_pairs["rapm_a"].values.astype(float)
            y_r = df_pairs["rapm_b"].values.astype(float)
            r2_rapm = float(np.corrcoef(x_r, y_r)[0, 1]) ** 2

            x_x = df_pairs["xrapm_a"].values.astype(float)
            y_x = df_pairs["xrapm_b"].values.astype(float)
            r2_xrapm = float(np.corrcoef(x_x, y_x)[0, 1]) ** 2
        except Exception:
            pass

        if r2_rapm is not None and r2_xrapm is not None:
            delta = r2_xrapm - r2_rapm
            st.info(
                f"**RAPM R²: {r2_rapm:.3f}**  ·  "
                f"**xRAPM R²: {r2_xrapm:.3f}**  ·  "
                f"xRAPM {'↑' if delta > 0 else '↓'} {abs(delta):.3f} more stable — "
                f"{'confirming' if delta > 0 else 'not confirming'} that process-based impact "
                f"is a more reliable year-to-year signal than outcomes-based RAPM."
            )


# ===========================================================================
# TAB 4 — LIMITATIONS
# ===========================================================================

with sec_limits:

    st.markdown(section_label("Known Limitations"), unsafe_allow_html=True)
    st.caption(
        "Every model has constraints. Documenting them honestly is part of rigorous "
        "analysis — it tells you where to trust the outputs and where to be cautious."
    )

    # (title, scope_label, scope_color, body)
    limitations = [
        (
            "No defender proximity data",
            "xShot", ACCENT_GOLD,
            "The model has no information about how closely a shot is contested. "
            "A 25-foot pull-up over a flat-footed defender and a 25-foot pull-up "
            "into a perfectly positioned rim protector receive the same xShot. "
            "Tracking data (e.g. Second Spectrum) would close this gap but is not "
            "publicly available.",
        ),
        (
            "No shooter identity in xShot",
            "xShot", ACCENT_GOLD,
            "By design, xShot does not know who is shooting. This prevents the "
            "model from learning that Stephen Curry makes more pull-up threes than "
            "average — that signal is reserved for FG% above expected (SMOE) rather "
            "than baked into the difficulty estimate.",
        ),
        (
            "RAPM collinearity",
            "RAPM / xRAPM", ACCENT_BLUE,
            "Players who share nearly all their minutes with the same teammates "
            "have collinear rows in the design matrix. Ridge regularisation shrinks "
            "their coefficients toward zero rather than producing unreliable extreme "
            "estimates, but players on dominant teams may be systematically "
            "undervalued or overvalued relative to their true contribution.",
        ),
        (
            "Small-sample instability",
            "RAPM / xRAPM", ACCENT_BLUE,
            "Below ~1,000 stint possessions (roughly 20–25 games of starter-level "
            "minutes), the ridge penalty dominates and estimates shrink heavily "
            "toward zero. Injury-shortened seasons and bench players are particularly "
            "affected. The 3-year pooled model mitigates this but does not eliminate it.",
        ),
        (
            "Era effects",
            "Both models", ACCENT,
            "The NBA has changed dramatically from 2014-15 to 2025-26: 3-point rates, "
            "pace, and defensive schemes have all shifted. Single-season RAPM within "
            "an era is comparable; cross-era comparisons should treat the pooled "
            "model as approximate and be interpreted with caution.",
        ),
        (
            "No free throws or turnovers",
            "Both models", ACCENT,
            "xShot is a field goal model only. Free throw generation, defensive "
            "fouling tendencies, and turnovers all affect team scoring but are not "
            "captured in xRAPM's target variable. RAPM (actual outcomes) subsumes "
            "these, but xRAPM does not.",
        ),
    ]

    for title, scope, scope_color, body in limitations:
        with st.expander(f"{title}  —  {scope}", expanded=False):
            st.markdown(
                f"<span style='font-size:0.78rem;font-weight:700;"
                f"color:{scope_color}'>{scope}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(body)
