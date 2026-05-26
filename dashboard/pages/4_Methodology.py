"""
Methodology — technical deep-dives into xShot, RAPM/xRAPM, validation,
and a honest discussion of model limitations.

This page communicates the statistical reasoning behind the models
to someone who understands data science but may not know basketball analytics.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from dashboard.utils.model_queries import (
    load_calibration_data, load_feature_importance, load_model_metadata,
    get_stability_data,
)
from dashboard.utils.viz import (
    calibration_curve_fig, feature_importance_fig, stability_scatter_fig,
)
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    SURFACE, BORDER, section_label, MODEBAR,
)

st.set_page_config(
    page_title="Methodology · NBA xShot + RAPM",
    page_icon="📖",
    layout="wide",
)

st.title("📖 Methodology")
st.caption(
    "Technical documentation for the xShot and RAPM/xRAPM models. "
    "Each section explains the approach, the statistical reasoning, and what the outputs mean."
)

# Load cached artifacts
cal_data  = load_calibration_data()
fi_data   = load_feature_importance()
meta      = load_model_metadata()
eval_m    = meta.get("evaluation", {})

tab_xshot, tab_rapm, tab_xrapm_why, tab_validation, tab_limits = st.tabs([
    "🎯  xShot",
    "📊  RAPM / xRAPM",
    "🔁  Why xRAPM?",
    "✅  Validation",
    "⚠️  Limitations",
])


# ===========================================================================
# TAB 1 — xSHOT
# ===========================================================================

with tab_xshot:
    st.markdown(section_label("What xShot Measures"), unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(
            "**xShot** is the predicted probability that a field goal attempt is made, "
            "given only pre-shot observable context. It is trained on historical outcomes "
            "and applied to every shot in the dataset.\n\n"
            "The key constraint — by design — is that **xShot does not know who is shooting**. "
            "This means xShot measures *shot difficulty*, not *shooter quality*. "
            "The gap between a player's actual FG% and their xShot is where shooter skill lives.\n\n"
            "This is the same framing as **expected goals (xG)** in soccer: the model evaluates "
            "the opportunity, not the player taking it."
        )
        st.markdown("#### Feature engineering")
        st.markdown(
            "**Spatial features** (strongest signal): `x_legacy`, `y_legacy` (raw court coordinates), "
            "`shot_distance`, `shot_angle`, `shot_zone` (categorical: at_rim / short_mid / mid_range / "
            "long_mid / three), `is_corner_three`, `is_paint`.\n\n"
            "**Shot-type flags**: 16 boolean features derived from the NBA API's `sub_type` field — "
            "`is_dunk`, `is_layup`, `is_pullup`, `is_fadeaway`, `is_cutting`, `is_putback`, "
            "`is_finger_roll`, `is_hook`, `is_floating`, `is_stepback`, `is_turnaround`, etc.\n\n"
            "**Context features**: `period`, `clock_seconds`, `is_overtime`, `is_playoffs`, "
            "`shot_value` (2 or 3 points).\n\n"
            f"Total: **{meta.get('feature_count', 30)} features**."
        )
        st.markdown("#### Model training")
        st.markdown(
            f"**Algorithm:** XGBoost binary classifier.\n\n"
            f"**Training data:** {meta.get('train_seasons', '2014-15 → 2022-23')} "
            f"(temporal split — no future data leaks into training).\n\n"
            f"**Holdout:** {meta.get('test_seasons', '2023-24 → 2024-25')} "
            f"({eval_m.get('test_n_shots', 0):,} shots — held out entirely during training).\n\n"
            "**Hyperparameters:** `max_depth=6`, `learning_rate=0.05`, `subsample=0.8`, "
            "`colsample_bytree=0.8`, `min_child_weight=10`. Early stopping at 20 rounds "
            f"on holdout log-loss. Best iteration: {meta.get('best_iteration', 127)}.\n\n"
            "**No Platt scaling** applied — XGBoost's probability outputs are used directly. "
            "The calibration curve (below) confirms reasonable calibration without post-processing."
        )
    with c2:
        st.markdown("#### Downstream metrics")
        st.markdown(
            f"""
| Metric | Derivation |
|--------|-----------|
| `xshot` | P(make) per shot |
| `mean_xshot` | Player avg xShot |
| `fg_pct_above_expected` | Actual FG% − avg xShot |
| `shot_pts_above_expected` | Σ(made − xshot) × shot_value |
| `xshot_pts` | xshot × shot_value (expected pts) |
"""
        )
        st.markdown("#### What xShot captures")
        st.markdown(
            f"- ✅ Shot location and distance\n"
            f"- ✅ Shot type (dunk vs pull-up etc.)\n"
            f"- ✅ Game context (late-game, playoffs)\n"
            f"- ❌ Defender proximity (no tracking data)\n"
            f"- ❌ Shooter identity (intentional)\n"
            f"- ❌ Free throws or assists"
        )

    st.markdown("#### Calibration Curve")
    st.caption(
        "If the model is well-calibrated, shots predicted at 40% should be made ~40% of the time. "
        "The curve should hug the diagonal. Deviations reveal systematic over/under-confidence."
    )
    fig_cal = calibration_curve_fig(cal_data)
    col_cal, _ = st.columns([2, 1])
    with col_cal:
        st.plotly_chart(fig_cal, use_container_width=True, config=MODEBAR)

    st.markdown("#### Feature Importance")
    st.caption(
        "XGBoost gain importance — how much each feature reduces prediction error across all tree splits. "
        "Dunk classification dominates because it is nearly deterministic (~98% FG%). "
        "Shot zone captures the bulk of location signal."
    )
    fig_fi = feature_importance_fig(fi_data, top_n=15)
    col_fi, _ = st.columns([2, 1])
    with col_fi:
        st.plotly_chart(fig_fi, use_container_width=True, config=MODEBAR)


# ===========================================================================
# TAB 2 — RAPM / xRAPM
# ===========================================================================

with tab_rapm:
    st.markdown(section_label("Ridge Regression on Lineup Stints"), unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### What RAPM solves")
        st.markdown(
            "Simple plus/minus is useless for comparing players: a backup who only plays "
            "with a team's starters will look great, while a star who plays with poor lineups "
            "looks bad. **RAPM** controls for this by modelling all lineup combinations "
            "simultaneously.\n\n"
            "Every 5v5 possession segment where both rosters are stable is a **lineup stint**. "
            "Each stint contributes a row to the design matrix. The regression estimates how "
            "much each individual player adds *independent of everyone else on the court*."
        )
        st.markdown("#### Design matrix construction")
        st.markdown(
            "For each stint, create a row vector of length = all players in the dataset.\n\n"
            "- **Home players:** `+1`\n"
            "- **Away players:** `-1`\n"
            "- **Everyone else:** `0`\n\n"
            "The target variable is the net scoring margin (home points − away points) "
            "per 100 possessions, with each row weighted by stint possession count.\n\n"
            "For **xRAPM**, replace actual points with xShot-derived expected points "
            "(`home_xshot_pts − away_xshot_pts`). Same regression, process-based target."
        )
        st.markdown("#### Ridge regularisation")
        st.markdown(
            "The design matrix is extremely large (~421k rows, ~600 columns) and highly "
            "collinear — teammates always appear together. Ridge regression (L2 penalty) "
            "prevents overfitting by shrinking coefficient magnitudes toward zero.\n\n"
            "- **λ = 30,000** for net RAPM / xRAPM (strong shrinkage, stable estimates)\n"
            "- **λ = 15,000** for offensive/defensive decomposition\n\n"
            "Higher λ → more shrinkage → estimates approach zero for low-minute players. "
            "This is conservative but appropriate: we'd rather say 'uncertain' than 'terrible'."
        )
        st.markdown("#### Offensive / defensive decomposition")
        st.markdown(
            "To split O-RAPM and D-RAPM, the stint matrix is doubled:\n\n"
            "- **Row 1 (offense):** home players `+1`, away players `0`\n"
            "- **Row 2 (defense):** home players `0`, away players `+1` (negated)\n\n"
            "Running ridge on this doubled matrix yields separate offensive and defensive "
            "coefficients. D-RAPM is stored as negated defensive regression coefficient "
            "(positive = better defense)."
        )
    with c2:
        st.markdown("#### v2: Pooled + Box-Score Prior")
        st.markdown(
            "**Problem with single-season RAPM:** a player with 800 stint possessions "
            "(~18 games as a starter) has too little data for the ridge penalty to "
            "separate their contribution from noise.\n\n"
            "**Solution: pool 3 consecutive seasons.** More data per player reduces "
            "collinearity. The trade-off is less sensitivity to within-career improvement.\n\n"
            "**Box-score prior:** each player gets a prior estimate based on their per-minute "
            "plus/minus scaled to per-100-possession units (γ = `(pm/min) × 48 × 0.12`). "
            "The prior is centred across the league.\n\n"
            "The regression runs on `y − Xγ` (residuals after prior), then recovers "
            "`β* = γ + β_residual`.\n\n"
            "**Effect:** players with large, consistent datasets are barely changed. "
            "Players with sparse data are pulled toward their historical plus/minus baseline — "
            "a more informative prior than zero."
        )
        st.markdown("#### Minimum possession thresholds")
        st.markdown(
            "| Version | Min possessions |\n"
            "|---------|----------------|\n"
            "| Single-season v1 | 1,000 |\n"
            "| Pooled v2 | 2,000 |\n\n"
            "Below these thresholds, the ridge bias dominates and ratings are "
            "not published (left null in the database)."
        )
        st.markdown("#### Output interpretation")
        st.markdown(
            "All RAPM values are in **pts per 100 lineup-stint possessions vs a league-average player**.\n\n"
            "- `+2.0` = the lineup is 2 points per 100 possessions better with this player than average\n"
            "- `0.0` = exactly league average contribution\n"
            "- `-1.5` = the lineup is 1.5 pts/100 worse with this player than average\n\n"
            "Top players typically range from +1.5 to +3.0. The scale is intentionally "
            "conservative due to ridge shrinkage."
        )


# ===========================================================================
# TAB 3 — WHY xRAPM?
# ===========================================================================

with tab_xrapm_why:
    st.markdown(section_label("Process vs Outcomes"), unsafe_allow_html=True)

    st.markdown(
        "RAPM measures what *actually happened*. xRAPM measures the *quality of the process* "
        "that generated those outcomes. The distinction matters because basketball has "
        "substantial shot-to-shot variance:\n\n"
        "- A player who takes a 38% shot and makes it produced positive RAPM but did not "
        "  produce a positive xRAPM outcome — they performed at their process level.\n"
        "- A player who takes a 62% shot and misses produced negative RAPM but no negative "
        "  xRAPM — they were unlucky, not bad.\n\n"
        "Over a full season, this variance partly cancels out — but not completely. "
        "A player shooting 2-for-20 on difficult pull-up 3s will have hurt their team's "
        "RAPM without hurting (much) their xRAPM, and vice versa."
    )

    st.markdown("#### RAPM − xRAPM: the process gap")
    col_gap1, col_gap2, col_gap3 = st.columns(3)
    with col_gap1:
        st.markdown(
            f'<div style="background:{SURFACE};border:1px solid {BORDER};'
            f'border-top:2px solid {ACCENT_GREEN};border-radius:9px;padding:16px">'
            f'<div style="font-weight:700;margin-bottom:8px;color:rgba(220,225,232,0.9)">'
            f'Large Positive Gap (+)</div>'
            f'<div style="font-size:0.82rem;color:{MUTED};line-height:1.5">'
            f'RAPM is much better than xRAPM.<br><br>'
            f'Possible causes: elite shot-making (real skill), '
            f'or positive shooting variance (luck). '
            f'Tends to regress toward xRAPM in future seasons.'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with col_gap2:
        st.markdown(
            f'<div style="background:{SURFACE};border:1px solid {BORDER};'
            f'border-top:2px solid rgba(160,165,175,0.5);border-radius:9px;padding:16px">'
            f'<div style="font-weight:700;margin-bottom:8px;color:rgba(220,225,232,0.9)">'
            f'Near Zero</div>'
            f'<div style="font-size:0.82rem;color:{MUTED};line-height:1.5">'
            f'RAPM and xRAPM agree.<br><br>'
            f'Player is converting approximately what the shot distribution predicts. '
            f'Most stable long-run profile.'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with col_gap3:
        st.markdown(
            f'<div style="background:{SURFACE};border:1px solid {BORDER};'
            f'border-top:2px solid {ACCENT_BLUE};border-radius:9px;padding:16px">'
            f'<div style="font-weight:700;margin-bottom:8px;color:rgba(220,225,232,0.9)">'
            f'Large Negative Gap (−)</div>'
            f'<div style="font-size:0.82rem;color:{MUTED};line-height:1.5">'
            f'xRAPM is better than RAPM.<br><br>'
            f"Player's process is better than outcomes suggest. "
            f'Positive regression candidate — likely to "look better" next season '
            f'as variance normalises.'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Year-to-year stability (preview)")
    st.caption(
        "The strongest evidence that xRAPM captures more signal than RAPM: "
        "it correlates more strongly with itself year-over-year. "
        "A higher R² means past xRAPM is a better predictor of future xRAPM "
        "than past RAPM is of future RAPM."
    )
    with st.spinner("Loading stability data…"):
        df_pairs = get_stability_data(min_poss=300)

    if not df_pairs.empty:
        sc1, sc2 = st.columns(2)
        with sc1:
            fig_r = stability_scatter_fig(df_pairs, metric="rapm",  label="RAPM",  color=ACCENT)
            if fig_r:
                st.markdown("**RAPM — Year-over-Year**")
                st.plotly_chart(fig_r, use_container_width=True, config=MODEBAR)
        with sc2:
            fig_x = stability_scatter_fig(df_pairs, metric="xrapm", label="xRAPM", color=ACCENT_BLUE)
            if fig_x:
                st.markdown("**xRAPM — Year-over-Year**")
                st.plotly_chart(fig_x, use_container_width=True, config=MODEBAR)


# ===========================================================================
# TAB 4 — VALIDATION
# ===========================================================================

with tab_validation:
    st.markdown(section_label("Model Validation"), unsafe_allow_html=True)

    st.markdown("#### xShot holdout evaluation")
    st.markdown(
        "The model was trained on 2014-15 through 2022-23 data and evaluated on "
        f"{meta.get('test_seasons', '2023-24 → 2024-25')} "
        f"({eval_m.get('test_n_shots', 0):,} shots never seen during training)."
    )

    cols = st.columns(4)
    metrics = [
        ("Log Loss", f"{eval_m.get('log_loss', '—')}", f"vs baseline: {eval_m.get('baseline_log_loss', '—')}"),
        ("Reduction", f"{eval_m.get('log_loss_reduction_pct', '—')}%", "over mean-FG% baseline"),
        ("Brier Score", f"{eval_m.get('brier_score', '—')}", "mean squared probability error"),
        ("Best iteration", str(meta.get("best_iteration", 127)), "early-stopped at 20 rounds"),
    ]
    for col, (label, val, sub) in zip(cols, metrics):
        with col:
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.04);border-radius:8px;'
                f'padding:12px 14px;text-align:center">'
                f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};'
                f'text-transform:uppercase">{label}</div>'
                f'<div style="font-size:1.4rem;font-weight:700;margin-top:4px">{val}</div>'
                f'<div style="font-size:0.72rem;color:{MUTED};margin-top:3px">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Interpreting the calibration curve")
    st.caption(
        "A well-calibrated model predicts probabilities that match empirical frequencies. "
        "Calibration is tested by binning shots by predicted probability and checking "
        "whether the actual make rate in each bin matches the prediction."
    )
    col_cal, col_note = st.columns([2, 1])
    with col_cal:
        fig_cal = calibration_curve_fig(cal_data)
        st.plotly_chart(fig_cal, use_container_width=True, config=MODEBAR)
    with col_note:
        st.markdown(
            "**Reading the chart:**\n\n"
            "- Each dot = a bin of shots with similar predicted xShot\n"
            "- Perfect calibration = diagonal line\n"
            "- Points above diagonal = model under-confident (predicts lower than actual)\n"
            "- Points below diagonal = model over-confident\n\n"
            "The low-probability end (0–0.10) tends to deviate slightly, as these bins "
            "are mostly rare/unusual shot types with limited training data.\n\n"
            f"The overall fit is strong across the 0.25–0.85 range where "
            f"the majority of shots fall."
        )

    st.markdown("#### RAPM stability validation")
    st.markdown(
        "Year-to-year correlation is the standard validation approach for impact metrics. "
        "A metric with zero predictive validity would have R² ≈ 0 year-over-year; "
        "a perfect metric would have R² = 1.0.\n\n"
        "The comparison between RAPM and xRAPM R² values directly tests whether "
        "removing shot-making variance (process vs outcomes) improves signal stability."
    )


# ===========================================================================
# TAB 5 — LIMITATIONS
# ===========================================================================

with tab_limits:
    st.markdown(section_label("Model Limitations"), unsafe_allow_html=True)
    st.caption(
        "Documenting limitations builds credibility. These are not excuses — "
        "they are honest statements about where the model should be trusted "
        "and where additional evidence is needed."
    )

    limitations = [
        ("No defender proximity",
         "xShot",
         f"<span style='color:{ACCENT_GOLD}'>Severity: High</span>",
         "The model cannot distinguish a wide-open corner 3 from a closely-guarded one. "
         "Defender proximity is the single most important missing variable. "
         "Second Spectrum tracking data would address this but is not publicly available. "
         "As a result, xShot likely over-values high-usage three-point shooters who draw "
         "heavy contest attention and under-values players who frequently find open looks."),
        ("No shooter identity",
         "xShot",
         f"<span style='color:{ACCENT_GOLD}'>Severity: Medium (by design)</span>",
         "Excluding shooter identity is a design choice, not a limitation per se. "
         "It ensures xShot measures shot difficulty, not shooter reputation. "
         "However, it means a Stephen Curry pull-up and a bench player pull-up get the same "
         "xShot, even though Curry converts at a dramatically higher rate. "
         "This is intentional: Curry's skill shows up in FG% above expected, not xShot."),
        ("RAPM collinearity",
         "RAPM / xRAPM",
         f"<span style='color:{ACCENT_GOLD}'>Severity: High for team-concentrated players</span>",
         "Players who almost never play without their best teammates have nearly identical "
         "rows in the design matrix. Ridge regression handles this by shrinking toward zero "
         "rather than producing extreme estimates, but it cannot assign credit correctly "
         "between, e.g., two stars who share 95% of their minutes. "
         "The pooled v2 model helps marginally by introducing more lineup diversity across seasons."),
        ("Small-sample instability",
         "RAPM / xRAPM",
         f"<span style='color:{ACCENT_GREEN}'>Severity: Mitigated by thresholds + pooling</span>",
         "Below 1,000 stint possessions (~18–20 games at starter minutes), ridge bias "
         "dominates and estimates are not published. The 3-year pooled model raises the "
         "effective floor to 2,000 possessions. "
         "Injury-shortened seasons and part-time players remain poorly estimated even with pooling."),
        ("Era effects",
         "Both models",
         f"<span style='color:{ACCENT_GOLD}'>Severity: Medium for cross-era comparisons</span>",
         "The NBA in 2014-15 and 2025-26 are substantially different games. "
         "3-point rates, pace, and lineup construction have all shifted. "
         "The xShot model was trained across all eras, which means a 2014-15 mid-range shot "
         "gets the same treatment as a 2025-26 mid-range shot — this is appropriate for "
         "within-season analysis but imperfect for comparing eras."),
        ("No free throws or turnovers",
         "xRAPM",
         f"<span style='color:{ACCENT_GOLD}'>Severity: Medium</span>",
         "xRAPM's target variable (xShot-derived expected points) captures only field goals. "
         "Free throw generation, fouling propensity, and turnovers all affect scoring margin "
         "but do not appear in xRAPM. RAPM (actual outcomes) subsumes these effects naturally. "
         "Players who generate substantial free throws or draw charges may be undervalued by "
         "xRAPM relative to RAPM."),
    ]

    for title, scope, severity, body in limitations:
        with st.expander(f"**{title}** — {scope}  ·  {severity}", expanded=False):
            st.markdown(body, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Glossary of metric terms")

    glossary = {
        "xShot": "Model-predicted make probability for each FGA given pre-shot context only.",
        "mean_xshot": "Player-season average of xShot across all field goal attempts.",
        "FG% above expected (SMOE)": "Actual FG% minus average xShot. Positive = shoots above expectation.",
        "Points above expected": "Total season points scored above xShot expectation = Σ(made − xshot) × shot_value.",
        "RAPM": "Regularised adjusted plus-minus. Marginal net scoring (actual) per 100 poss vs avg.",
        "xRAPM": "Same regression with xShot-derived expected points as the target. Process-based impact.",
        "RAPM − xRAPM": "Process gap. Positive = outscoring shot quality. Negative = regression candidate.",
        "O-RAPM": "Offensive component of RAPM — pts/100 poss added on offense.",
        "D-RAPM": "Defensive component. Positive = better than average defense.",
        "RAPM+Prior": "Pooled RAPM shrunk toward a box-score prior. Recommended for cross-player comparison.",
        "Stint possessions": "Total possessions in 5v5 lineup stints this player participated in.",
        "Lineup stint": "Any period during a game where both 5-player lineups are stable.",
    }

    for term, defn in glossary.items():
        st.markdown(f"**{term}** — {defn}")
