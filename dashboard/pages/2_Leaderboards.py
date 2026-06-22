"""
Impact Leaderboards — xRAPM, RAPM, O/D splits, xShot overperformance.

Rank + Percentile surfaced by default. Distribution context with KDE.
Single-season and 3-year pooled views.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.stats import percentileofscore, gaussian_kde

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_single_season_leaderboard, get_pooled_leaderboard
from dashboard.utils.nba_static import player_headshot_url, team_color
from dashboard.utils.theme import (
    inject_global_css, page_header, section_label, art_section,
    finding, chart_caption, tier_color,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, ACCENT_PURPLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SURFACE, BORDER, GRID, ZERO_LINE, MODEBAR,
)

st.set_page_config(
    page_title="Leaderboards · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()

st.markdown(
    page_header(
        "Impact Leaderboards",
        "All metrics derived from xShot and RAPM/xRAPM models — not raw box-score stats. "
        "Values represent pts per 100 lineup-stint possessions above a league-average player.",
    ),
    unsafe_allow_html=True,
)

# ── Metric definitions ────────────────────────────────────────────────────────
METRICS = {
    "xRAPM":               ("xrapm",                  ACCENT,        "+.2f",
                            "Net expected pts/100 poss. Process quality — removes shot-making variance."),
    "O-RAPM":              ("o_rapm",                 ACCENT_BLUE,   "+.2f",
                            "Offensive pts/100 added above average on the offensive end."),
    "D-RAPM":              ("d_rapm",                 ACCENT_PURPLE, "+.2f",
                            "Defensive pts/100 saved above average (positive = better defense)."),
    "RAPM":                ("rapm",                   ACCENT_GOLD,   "+.2f",
                            "Net actual pts/100 poss. Includes shot-making variance."),
    "RAPM − xRAPM":        ("rapm_vs_xrapm",          "#71717A",     "+.2f",
                            "Positive = outscoring process (great finishing or luck). Negative = regression candidate."),
    "xShot Overperformance":("fg_pct_above_expected", ACCENT_GREEN,  "+.3f",
                             "Actual FG% minus model-predicted FG%. Isolates shot-making skill."),
    "Avg Shot Difficulty": ("mean_xshot",             "#A78BFA",     ".3f",
                            "Average xShot across all FGA — how hard are this player's shots?"),
}

METRIC_TOOLTIPS = {k: v[3] for k, v in METRICS.items()}


def _fmt(v, spec: str) -> str:
    try:
        return f"{float(v):{spec}}"
    except (TypeError, ValueError):
        return "—"


def _pct_badge(pct: float) -> str:
    col = tier_color(pct)
    return (
        f'<span style="font-size:0.72rem;font-weight:700;color:{col};'
        f'background:rgba(255,255,255,0.05);border-radius:4px;padding:1px 5px">'
        f'{pct:.0f}th</span>'
    )


# ── Tab structure ─────────────────────────────────────────────────────────────
tab_single, tab_pooled = st.tabs(["Single Season  (v1)", "3-Year Pooled + Prior  (v2)"])

# ═════════════════════════════════════════════════════════════════════════════
# SINGLE SEASON
# ═════════════════════════════════════════════════════════════════════════════
_POS_GROUPS = {
    "Guard":          {"G", "G-F", "F-G"},
    "Forward":        {"F", "F-G", "G-F", "F-C", "C-F"},
    "Center":         {"C", "C-F", "F-C"},
}

def _primary_pos(raw: str | None) -> str:
    """Map raw NBA position string → Guard / Forward / Center / Unknown."""
    if not raw or str(raw).strip() == "":
        return "Unknown"
    raw = str(raw).strip()
    if raw in ("G",):
        return "Guard"
    if raw in ("F",):
        return "Forward"
    if raw in ("C",):
        return "Center"
    if "G" in raw and "F" not in raw:
        return "Guard"
    if "C" in raw and "F" not in raw:
        return "Center"
    if "G" in raw and "F" in raw:
        return "Guard"   # G-F leans guard
    if "F" in raw and "C" in raw:
        return "Forward" # F-C leans forward
    if raw == "F":
        return "Forward"
    return "Unknown"


with tab_single:

    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    seasons     = get_seasons()
    def_s       = "2025-26" if "2025-26" in seasons else seasons[0]
    season      = f1.selectbox("Season", seasons, index=seasons.index(def_s), key="ss_season")
    season_type = f2.selectbox("Season Type", get_season_types(), key="ss_stype")
    min_poss    = f3.number_input("Min Possessions", min_value=100, max_value=5000,
                                  value=500, step=100, key="ss_minposs")
    top_n       = f4.number_input("Show top N", min_value=5, max_value=50,
                                  value=25, step=5, key="ss_topn")

    df = get_single_season_leaderboard(season, season_type, int(min_poss))

    if df.empty:
        st.markdown(
            f'<div style="text-align:center;padding:48px;color:{TEXT_SECONDARY}">'
            f'No data for this selection.</div>',
            unsafe_allow_html=True,
        )
    else:
        # Add primary position group column for filtering
        if "position" in df.columns:
            df["pos_group"] = df["position"].apply(_primary_pos)

        # ── Filters row ───────────────────────────────────────────────────────
        fc1, fc2 = st.columns([3, 2])
        all_teams   = sorted(df["team"].dropna().unique())
        sel_teams   = fc1.multiselect("Filter by team  (blank = all)", all_teams, key="ss_teams")
        all_pos_groups = ["Guard", "Forward", "Center"]
        sel_pos     = fc2.multiselect("Filter by position  (blank = all)", all_pos_groups, key="ss_pos")

        if sel_teams:
            df = df[df["team"].isin(sel_teams)]
        if sel_pos and "pos_group" in df.columns:
            df = df[df["pos_group"].isin(sel_pos)]

        # Metric selector
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(section_label("Choose a Metric"), unsafe_allow_html=True)

        metric_label = st.radio(
            "Rank by", list(METRICS.keys()), horizontal=True, index=0, key="ss_metric",
        )
        col_key, _, fmt_spec, color = (
            METRICS[metric_label][0], METRICS[metric_label][1],
            METRICS[metric_label][2], METRICS[metric_label][1],
        )
        metric_desc = METRICS[metric_label][3]

        st.markdown(
            f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};margin:4px 0 16px 0">'
            f'<strong style="color:{color}">{metric_label}</strong> — {metric_desc}</div>',
            unsafe_allow_html=True,
        )

        df_sorted  = df.sort_values(col_key, ascending=False, na_position="last").reset_index(drop=True)
        chart_df   = df_sorted.head(int(top_n)).copy()

        # Compute percentiles against full (unfiltered) season distribution
        all_vals = df_sorted[col_key].dropna().values.astype(float)

        if not chart_df[col_key].dropna().empty:
            # ── Leaderboard table ──────────────────────────────────────────────
            st.markdown(art_section("", f"Top {int(top_n)} — {metric_label}"), unsafe_allow_html=True)

            # Build display rows as HTML cards
            for rank_idx, (_, row) in enumerate(chart_df.iterrows(), start=1):
                val = row.get(col_key)
                if val is None or str(val) == "nan":
                    continue
                fval    = float(val)
                fmt_val = _fmt(val, fmt_spec)
                pct     = percentileofscore(all_vals, fval, kind="rank") if len(all_vals) >= 2 else 50.0
                tcolor  = team_color(str(row["team"]))
                poss_v  = f'{int(row["possessions"]):,}' if str(row.get("possessions","")) not in ("","nan") else "—"
                val_color = ACCENT_GREEN if fval > 0 else ("#EF4444" if fval < 0 else TEXT_SECONDARY)
                if col_key in ("mean_xshot", "fg_pct_above_expected", "rapm_vs_xrapm"):
                    val_color = color  # neutral for these metrics

                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:12px;'
                    f'background:{SURFACE};border:1px solid {BORDER};border-radius:7px;'
                    f'padding:9px 14px;margin-bottom:5px">'
                    f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
                    f'min-width:26px;text-align:center">#{rank_idx}</div>'
                    f'<div style="flex:1">'
                    f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">'
                    f'{row["full_name"]}</div>'
                    f'<div style="font-size:0.72rem;font-weight:600;color:{tcolor}">'
                    f'{row["team"]}</div>'
                    f'</div>'
                    f'<div style="font-size:0.72rem;color:{TEXT_MUTED};min-width:60px;'
                    f'text-align:right">{poss_v}<br>poss</div>'
                    f'<div style="min-width:70px;text-align:right">'
                    f'<div style="font-size:1.05rem;font-weight:700;color:{val_color}">'
                    f'{fmt_val}</div>'
                    f'<div>{_pct_badge(pct)}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        # ── Distribution context ───────────────────────────────────────────────
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown(art_section("", "League Distribution"), unsafe_allow_html=True)
        st.caption(
            "Select up to 3 players to see where they fall. "
            "Most RAPM/xRAPM values cluster between −2 and +2 — elite players sit past ±3."
        )

        dist_pick, dist_chart = st.columns([1, 3])
        with dist_pick:
            dist_metric = st.selectbox("Metric", list(METRICS.keys()), key="ss_dist_metric")
            sel_players = st.multiselect(
                "Highlight players",
                df_sorted["full_name"].tolist(),
                max_selections=3,
                key="ss_dist_players",
            )

        dist_col  = METRICS[dist_metric][0]
        dist_clr  = METRICS[dist_metric][1]
        dist_fmt  = METRICS[dist_metric][2]

        with dist_chart:
            dist_vals = df[dist_col].dropna().values.astype(float)
            if len(dist_vals) >= 3:
                fig_dist = go.Figure()
                fig_dist.add_trace(go.Histogram(
                    x=dist_vals, nbinsx=30,
                    marker_color="rgba(96,165,250,0.20)", marker_line_width=0,
                    name="All players",
                    hovertemplate=f"{dist_metric}: %{{x:.2f}}<br>Players: %{{y}}<extra></extra>",
                ))
                if len(dist_vals) >= 5:
                    kde = gaussian_kde(dist_vals, bw_method=0.4)
                    xr  = np.linspace(dist_vals.min() - 0.5, dist_vals.max() + 0.5, 200)
                    bw  = (dist_vals.max() - dist_vals.min()) / 30
                    fig_dist.add_trace(go.Scatter(
                        x=xr, y=kde(xr) * len(dist_vals) * bw,
                        mode="lines", line=dict(color=ACCENT, width=2),
                        showlegend=False, hoverinfo="skip",
                    ))
                fig_dist.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)

                pal = [ACCENT_GOLD, ACCENT_GREEN, ACCENT_BLUE]
                for i, name in enumerate(sel_players[:3]):
                    row = df[df["full_name"] == name]
                    if row.empty or row.iloc[0][dist_col] is None:
                        continue
                    pv  = float(row.iloc[0][dist_col])
                    pct = percentileofscore(dist_vals, pv, kind="rank")
                    c   = pal[i % len(pal)]
                    fig_dist.add_vline(
                        x=pv, line_dash="solid", line_color=c, line_width=2,
                        annotation_text=f"{name.split()[-1]}  {_fmt(pv, dist_fmt)} ({pct:.0f}th)",
                        annotation_font_color=c, annotation_font_size=11,
                        annotation_position="top left" if i % 2 == 0 else "top right",
                    )

                fig_dist.update_layout(
                    barmode="overlay",
                    xaxis=dict(title=dist_metric, showgrid=True, gridcolor=GRID, zeroline=False),
                    yaxis=dict(title="Players", showgrid=True, gridcolor=GRID, zeroline=False),
                    height=300,
                    margin=dict(l=20, r=20, t=16, b=30),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    hovermode="closest",
                    showlegend=False,
                    font=dict(color=TEXT_SECONDARY, size=11),
                    hoverlabel=dict(bgcolor="#111114", font_color=TEXT_PRIMARY),
                )
                st.plotly_chart(fig_dist, use_container_width=True, config=MODEBAR, key="ss_dist")
                st.markdown(
                    chart_caption(
                        "Distribution of all qualifying players this season. "
                        "Coloured lines show where selected players fall and their percentile rank."
                    ),
                    unsafe_allow_html=True,
                )

        # ── Full table ─────────────────────────────────────────────────────────
        with st.expander("Full rankings table", expanded=False):
            df_display = df.sort_values(col_key, ascending=False, na_position="last").reset_index(drop=True)
            df_display.insert(0, "Rank", range(1, len(df_display) + 1))
            df_display["headshot"] = df_display["person_id"].apply(player_headshot_url)

            # Add percentile columns
            for m_label, (m_col, *_) in METRICS.items():
                if m_col in df_display.columns:
                    vals = df_display[m_col].dropna().values.astype(float)
                    df_display[f"{m_col}_pct"] = df_display[m_col].apply(
                        lambda x: round(percentileofscore(vals, float(x), kind="rank"), 0)
                        if str(x) not in ("", "nan", "None") else None
                    )

            st.dataframe(
                df_display[[
                    "headshot", "Rank", "full_name", "team",
                    "rapm", "xrapm", "rapm_vs_xrapm", "o_rapm", "d_rapm",
                    "fg_pct_above_expected", "mean_xshot", "possessions",
                ]],
                use_container_width=True,
                height=520,
                hide_index=True,
                column_config={
                    "headshot":   st.column_config.ImageColumn(" ", width="small"),
                    "Rank":       st.column_config.NumberColumn("#", width="small"),
                    "full_name":  st.column_config.TextColumn("Player", width="medium"),
                    "team":       st.column_config.TextColumn("Team", width="small"),
                    "xrapm":      st.column_config.NumberColumn("xRAPM",        format="%+.2f", width="small"),
                    "rapm":       st.column_config.NumberColumn("RAPM",          format="%+.2f", width="small"),
                    "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%+.2f", width="small"),
                    "o_rapm":     st.column_config.NumberColumn("O-RAPM",        format="%+.2f", width="small"),
                    "d_rapm":     st.column_config.NumberColumn("D-RAPM",        format="%+.2f", width="small"),
                    "fg_pct_above_expected": st.column_config.NumberColumn("FG% vs Exp", format="%+.3f", width="small"),
                    "mean_xshot": st.column_config.NumberColumn("Avg xShot",     format="%.3f",  width="small"),
                    "possessions":st.column_config.NumberColumn("Poss",          format="%.0f",  width="small"),
                },
            )


# ═════════════════════════════════════════════════════════════════════════════
# POOLED (v2)
# ═════════════════════════════════════════════════════════════════════════════
with tab_pooled:
    st.markdown(
        f'<p style="color:{TEXT_SECONDARY};font-size:0.875rem;max-width:720px;'
        f'line-height:1.6;margin-top:8px">'
        "The pooled model combines 3 consecutive seasons and anchors estimates toward a "
        "box-score prior (per-minute +/− scaled to per-100 possessions). "
        "<strong>RAPM+Prior</strong> is the recommended cross-player comparison metric.</p>",
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns([2, 2, 2, 1])
    pooled_stype = p1.selectbox("Season Type", get_season_types(), key="v2_stype")
    min_poss_v2  = p2.number_input("Min Pooled Possessions", min_value=500, max_value=10000,
                                   value=1500, step=500, key="v2_minposs")
    top_n_v2     = p4.number_input("Top N", min_value=5, max_value=50,
                                   value=25, step=5, key="v2_topn")

    df_v2 = get_pooled_leaderboard(int(min_poss_v2))
    if not df_v2.empty:
        df_v2 = df_v2[df_v2["season_type"] == pooled_stype]

    if df_v2.empty:
        st.markdown(
            f'<div style="text-align:center;padding:48px;color:{TEXT_MUTED}">'
            f'No pooled data available.</div>',
            unsafe_allow_html=True,
        )
    else:
        windows = sorted(df_v2["window_label"].unique(), reverse=True)
        selected_window = p3.selectbox("3-Year Window", windows, key="v2_window")
        df_w = (
            df_v2[df_v2["window_label"] == selected_window]
            .sort_values("rapm_prior", ascending=False)
            .reset_index(drop=True)
        )

        sel_teams_v2 = st.multiselect("Filter by team", sorted(df_w["team"].dropna().unique()), key="v2_teams")
        if sel_teams_v2:
            df_w = df_w[df_w["team"].isin(sel_teams_v2)]

        chart_v2   = df_w.head(int(top_n_v2)).copy()
        all_v2     = df_w["rapm_prior"].dropna().values.astype(float)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(art_section("", f"Top {int(top_n_v2)} — RAPM+Prior ({selected_window})"), unsafe_allow_html=True)

        for rank_idx, (_, row) in enumerate(chart_v2.iterrows(), start=1):
            val = row.get("rapm_prior")
            if val is None or str(val) == "nan":
                continue
            fval   = float(val)
            tcolor = team_color(str(row["team"]))
            pct    = percentileofscore(all_v2, fval, kind="rank") if len(all_v2) >= 2 else 50.0
            poss_v = f'{int(row["possessions"]):,}' if str(row.get("possessions","")) not in ("","nan") else "—"
            val_color = ACCENT_GREEN if fval > 0 else ("#EF4444" if fval < 0 else TEXT_SECONDARY)

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;'
                f'background:{SURFACE};border:1px solid {BORDER};border-radius:7px;'
                f'padding:9px 14px;margin-bottom:5px">'
                f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
                f'min-width:26px;text-align:center">#{rank_idx}</div>'
                f'<div style="flex:1">'
                f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">'
                f'{row["full_name"]}</div>'
                f'<div style="font-size:0.72rem;font-weight:600;color:{tcolor}">'
                f'{row["team"]}</div>'
                f'</div>'
                f'<div style="font-size:0.72rem;color:{TEXT_MUTED};min-width:60px;'
                f'text-align:right">{poss_v}<br>poss</div>'
                f'<div style="min-width:70px;text-align:right">'
                f'<div style="font-size:1.05rem;font-weight:700;color:{val_color}">'
                f'{_fmt(fval, "+.2f")}</div>'
                f'<div>{_pct_badge(pct)}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        with st.expander("Full pooled rankings table", expanded=False):
            st.dataframe(
                df_w[[
                    "full_name", "team", "rapm_prior", "xrapm",
                    "rapm", "rapm_vs_xrapm", "possessions",
                ]],
                use_container_width=True, height=480, hide_index=True,
                column_config={
                    "full_name":     st.column_config.TextColumn("Player", width="medium"),
                    "team":          st.column_config.TextColumn("Team", width="small"),
                    "rapm_prior":    st.column_config.NumberColumn("RAPM+Prior", format="%+.2f", width="small"),
                    "xrapm":         st.column_config.NumberColumn("xRAPM",      format="%+.2f", width="small"),
                    "rapm":          st.column_config.NumberColumn("RAPM (raw)", format="%+.2f", width="small"),
                    "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%+.2f", width="small"),
                    "possessions":   st.column_config.NumberColumn("Pooled Poss", format="%.0f", width="small"),
                },
            )
