"""
Leaderboards — single-season and multi-year pooled impact ratings.
One visible chart at a time; metric chosen via radio buttons.
Distribution context shows where each value sits across the league.
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
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    GRID, ZERO_LINE, SURFACE, BORDER, MODEBAR, ARTICLE_CSS,
    art_section, finding, chart_caption,
)

st.set_page_config(
    page_title="Leaderboards · NBA xShot + RAPM",
    page_icon="📊",
    layout="wide",
)
st.markdown(ARTICLE_CSS, unsafe_allow_html=True)

st.markdown(
    f"<h1 style='margin-bottom:4px'>📊 Impact Leaderboards</h1>"
    f"<p style='color:{MUTED};font-size:0.95rem;max-width:720px;line-height:1.6;margin-top:0'>"
    "All metrics come from the xShot and RAPM/xRAPM models — not box-score stats. "
    "Values are in pts per 100 lineup-stint possessions above a league-average player. "
    "Pick a metric and season, then explore where individual players fall in the distribution."
    "</p>",
    unsafe_allow_html=True,
)

# ── Metric definitions ──────────────────────────────────────────────────────

METRICS = {
    "RAPM":                 ("rapm",                   ACCENT,       "+.2f", "Net actual pts/100 poss vs avg, controlling for teammates & opponents."),
    "xRAPM":                ("xrapm",                  ACCENT_BLUE,  "+.2f", "Net expected pts/100 poss (xShot-based). Process quality, less noise."),
    "RAPM − xRAPM":         ("rapm_vs_xrapm",          ACCENT_GOLD,  "+.2f", "Positive = outscoring process (great finishing or luck). Negative = regression candidate."),
    "O-RAPM":               ("o_rapm",                 ACCENT,       "+.2f", "Offensive pts/100 added above average."),
    "D-RAPM":               ("d_rapm",                 ACCENT_BLUE,  "+.2f", "Defensive pts/100 saved above average (positive = better defense)."),
    "FG% Above Expected":   ("fg_pct_above_expected",  ACCENT_GREEN, "+.3f", "Actual FG% minus model-predicted FG% — isolates shot-making skill."),
    "Avg Shot Difficulty":  ("mean_xshot",             ACCENT_GOLD,  ".3f",  "Average xShot across all FGA — how hard are the shots this player takes?"),
}

def _fmt(v, spec: str) -> str:
    try:
        return f"{float(v):{spec}}"
    except (TypeError, ValueError):
        return "—"

# ── Filters ─────────────────────────────────────────────────────────────────

tab_single, tab_pooled = st.tabs(["Single Season  (v1)", "3-Year Pooled + Prior  (v2)"])


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE SEASON
# ═══════════════════════════════════════════════════════════════════════════

with tab_single:

    # Filter row
    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    seasons      = get_seasons()
    def_s        = "2024-25" if "2024-25" in seasons else seasons[0]
    season       = f1.selectbox("Season", seasons, index=seasons.index(def_s), key="ss_season")
    season_type  = f2.selectbox("Season Type", get_season_types(), key="ss_stype")
    min_poss     = f3.number_input("Min Possessions", min_value=100, max_value=5000,
                                   value=500, step=100, key="ss_minposs")
    top_n        = f4.number_input("Show top N", min_value=5, max_value=50,
                                   value=20, step=5, key="ss_topn")

    df = get_single_season_leaderboard(season, season_type, int(min_poss))

    if df.empty:
        st.warning("No data for this selection.")
        st.stop()

    all_teams = sorted(df["team"].dropna().unique())
    sel_teams = st.multiselect("Filter by team  (blank = all teams)", all_teams, key="ss_teams")
    if sel_teams:
        df = df[df["team"].isin(sel_teams)]

    # ── Metric selector (prominent radio) ──────────────────────────────────
    st.markdown(art_section("", "Choose a Metric to Rank By"), unsafe_allow_html=True)

    metric_label = st.radio(
        "Rank players by",
        list(METRICS.keys()),
        horizontal=True,
        index=0,
        key="ss_metric",
    )
    col, fmt_spec, color = METRICS[metric_label][0], METRICS[metric_label][2], METRICS[metric_label][1]
    metric_desc = METRICS[metric_label][3]

    st.markdown(
        f'<div style="font-size:0.82rem;color:{MUTED};margin:4px 0 16px 0">'
        f'<strong style="color:{color}">{metric_label}</strong> — {metric_desc}</div>',
        unsafe_allow_html=True,
    )

    # ── Hero bar chart ───────────────────────────────────────────────────────
    df_sorted = df.sort_values(col, ascending=False, na_position="last").reset_index(drop=True)
    chart_df  = df_sorted.head(int(top_n))

    if chart_df[col].dropna().empty:
        st.info(f"No data for **{metric_label}** this season. The model may need to be re-run.")
    else:
        hover_text = [
            f"<b>{row['full_name']}</b>  ({row['team']})<br>"
            f"RAPM: {_fmt(row['rapm'], '+.2f')}  |  xRAPM: {_fmt(row['xrapm'], '+.2f')}<br>"
            f"FG% vs Exp: {_fmt(row['fg_pct_above_expected'], '+.3f')}  |  "
            f"Poss: {int(row['possessions']) if str(row['possessions']) not in ('', 'nan') else '—'}"
            for _, row in chart_df.iterrows()
        ]

        fig = go.Figure(go.Bar(
            x=chart_df[col],
            y=chart_df["full_name"],
            orientation="h",
            marker_color=[team_color(str(t)) for t in chart_df["team"]],
            marker_line_color="rgba(0,0,0,0)",
            text=[_fmt(v, fmt_spec) for v in chart_df[col]],
            textposition="outside",
            cliponaxis=False,
            hovertext=hover_text,
            hoverinfo="text",
        ))
        fig.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)
        fig.update_layout(
            yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
            xaxis=dict(title=metric_label, showgrid=True, gridcolor=GRID, zeroline=False),
            height=max(400, int(top_n) * 30),
            margin=dict(l=20, r=110, t=30, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            hovermode="closest",
        )
        st.plotly_chart(fig, use_container_width=True, config=MODEBAR, key="ss_chart")
        st.markdown(
            chart_caption(
                f"Top {int(top_n)} players by {metric_label} — {season} {season_type}. "
                "Bar colour = team colour. Hover for full profile."
            ),
            unsafe_allow_html=True,
        )

    # ── Distribution context ─────────────────────────────────────────────────
    st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
    st.markdown(art_section("", "Distribution Context"), unsafe_allow_html=True)

    st.markdown(
        f"<span style='color:{MUTED};font-size:0.86rem'>"
        "Select up to 3 players to see where they fall in the full league distribution. "
        "Most RAPM/xRAPM values cluster between −2 and +2 — truly elite players sit past ±3."
        "</span>",
        unsafe_allow_html=True,
    )

    dist_col_pick, dist_col_chart = st.columns([1, 3])
    with dist_col_pick:
        dist_metric_label = st.selectbox(
            "Metric", list(METRICS.keys()), key="ss_dist_metric"
        )
        selected_players = st.multiselect(
            "Highlight players",
            df["full_name"].tolist() if not df.empty else [],
            max_selections=3,
            key="ss_dist_players",
        )

    dist_col_def = METRICS[dist_metric_label][0]
    dist_color   = METRICS[dist_metric_label][1]
    dist_fmt     = METRICS[dist_metric_label][2]

    with dist_col_chart:
        if not df[dist_col_def].dropna().empty:
            vals = df[dist_col_def].dropna().values.astype(float)
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Histogram(
                x=vals, nbinsx=30,
                marker_color=f"rgba(76,155,232,0.40)", marker_line_width=0,
                name="All players",
                hovertemplate=f"{dist_metric_label}: %{{x:.2f}}<br>Players: %{{y}}<extra></extra>",
            ))
            if len(vals) >= 5:
                kde = gaussian_kde(vals, bw_method=0.4)
                xr  = np.linspace(vals.min() - 0.5, vals.max() + 0.5, 200)
                bw  = (vals.max() - vals.min()) / 30
                fig_dist.add_trace(go.Scatter(
                    x=xr, y=kde(xr) * len(vals) * bw,
                    mode="lines", line=dict(color=ACCENT_BLUE, width=2),
                    showlegend=False, hoverinfo="skip",
                ))
            fig_dist.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)

            pal = [ACCENT_GOLD, ACCENT_GREEN, ACCENT]
            for i, name in enumerate(selected_players[:3]):
                row = df[df["full_name"] == name]
                if row.empty or row.iloc[0][dist_col_def] is None:
                    continue
                pv  = float(row.iloc[0][dist_col_def])
                pct = percentileofscore(vals, pv, kind="rank")
                c   = pal[i % len(pal)]
                fig_dist.add_vline(
                    x=pv, line_dash="solid", line_color=c, line_width=2.5,
                    annotation_text=f"{name.split()[-1]}  {_fmt(pv, dist_fmt)}  ({pct:.0f}th)",
                    annotation_font_color=c, annotation_font_size=11,
                    annotation_position="top left" if i % 2 == 0 else "top right",
                )

            fig_dist.update_layout(
                barmode="overlay",
                xaxis=dict(title=dist_metric_label, showgrid=True, gridcolor=GRID, zeroline=False),
                yaxis=dict(title="Players", showgrid=True, gridcolor=GRID, zeroline=False),
                height=300,
                margin=dict(l=20, r=20, t=20, b=30),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="closest",
                showlegend=False,
            )
            st.plotly_chart(fig_dist, use_container_width=True, config=MODEBAR, key="ss_dist")
            st.markdown(
                chart_caption(
                    "Bell-curve distribution of all qualifying players this season. "
                    "Coloured lines show where selected players fall and their percentile rank."
                ),
                unsafe_allow_html=True,
            )

    # ── Full table (collapsed) ────────────────────────────────────────────────
    with st.expander("📋  Full rankings table", expanded=False):
        df_display = df.sort_values("rapm", ascending=False, na_position="last").reset_index(drop=True)
        df_display.insert(0, "Rank", range(1, len(df_display) + 1))
        df_display["headshot"] = df_display["person_id"].apply(player_headshot_url)

        st.dataframe(
            df_display[[
                "headshot", "Rank", "full_name", "team",
                "rapm", "xrapm", "rapm_vs_xrapm", "o_rapm", "d_rapm",
                "fg_pct_above_expected", "mean_xshot",
                "shot_pts_above_expected", "ppg", "possessions",
            ]],
            use_container_width=True,
            height=500,
            hide_index=True,
            column_config={
                "headshot":   st.column_config.ImageColumn(" ", width="small"),
                "Rank":       st.column_config.NumberColumn("#", width="small"),
                "full_name":  st.column_config.TextColumn("Player", width="medium"),
                "team":       st.column_config.TextColumn("Team", width="small"),
                "rapm":       st.column_config.NumberColumn("RAPM",         format="%.2f", width="small"),
                "xrapm":      st.column_config.NumberColumn("xRAPM",        format="%.2f", width="small"),
                "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f", width="small"),
                "o_rapm":     st.column_config.NumberColumn("O-RAPM",       format="%.2f", width="small"),
                "d_rapm":     st.column_config.NumberColumn("D-RAPM",       format="%.2f", width="small"),
                "fg_pct_above_expected": st.column_config.NumberColumn("FG% vs Exp", format="+.3f", width="small"),
                "mean_xshot": st.column_config.NumberColumn("Avg xShot",    format="%.3f", width="small"),
                "shot_pts_above_expected": st.column_config.NumberColumn("Pts vs Exp", format="%.0f", width="small"),
                "ppg":        st.column_config.NumberColumn("PPG",          format="%.1f", width="small"),
                "possessions":st.column_config.NumberColumn("Poss",         format="%.0f", width="small"),
            },
        )


# ═══════════════════════════════════════════════════════════════════════════
# POOLED (v2)
# ═══════════════════════════════════════════════════════════════════════════

with tab_pooled:
    st.markdown(
        f"<p style='color:{MUTED};font-size:0.86rem;max-width:700px;line-height:1.5;margin-top:8px'>"
        "The pooled model combines 3 consecutive seasons and anchors estimates toward a "
        "box-score prior (per-minute +/− scaled to per-100 possessions). More data per player "
        "reduces collinearity noise. <strong>RAPM+Prior</strong> is the recommended comparison metric."
        "</p>",
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns([2, 2, 2, 1])
    pooled_stype = p1.selectbox("Season Type", get_season_types(), key="v2_stype")
    min_poss_v2  = p2.number_input("Min Pooled Possessions", min_value=500, max_value=10000,
                                   value=1500, step=500, key="v2_minposs")
    top_n_v2     = p4.number_input("Top N", min_value=5, max_value=50,
                                   value=20, step=5, key="v2_topn")

    df_v2 = get_pooled_leaderboard(int(min_poss_v2))
    if not df_v2.empty:
        df_v2 = df_v2[df_v2["season_type"] == pooled_stype]

    if df_v2.empty:
        st.warning("No pooled data available.")
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

        chart_v2 = df_w.head(int(top_n_v2))

        hover_v2 = [
            f"<b>{row['full_name']}</b>  ({row['team']})<br>"
            f"RAPM+Prior: {_fmt(row['rapm_prior'], '+.2f')}  |  "
            f"xRAPM: {_fmt(row['xrapm'], '+.2f')}  |  RAPM raw: {_fmt(row['rapm'], '+.2f')}<br>"
            f"Pooled Poss: {int(row['possessions']) if str(row['possessions']) not in ('', 'nan') else '—'}"
            for _, row in chart_v2.iterrows()
        ]

        fig2 = go.Figure(go.Bar(
            x=chart_v2["rapm_prior"],
            y=chart_v2["full_name"],
            orientation="h",
            marker_color=[team_color(str(t)) for t in chart_v2["team"]],
            marker_line_color="rgba(0,0,0,0)",
            text=[_fmt(v, "+.2f") for v in chart_v2["rapm_prior"]],
            textposition="outside",
            cliponaxis=False,
            hovertext=hover_v2,
            hoverinfo="text",
        ))
        fig2.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)
        fig2.update_layout(
            yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
            xaxis=dict(title="RAPM + Box-Score Prior (pts/100 poss)",
                       showgrid=True, gridcolor=GRID, zeroline=False),
            height=max(400, int(top_n_v2) * 30),
            margin=dict(l=20, r=110, t=30, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True, config=MODEBAR, key="v2_chart")
        st.markdown(
            chart_caption(f"Top {int(top_n_v2)} by RAPM+Prior — {selected_window} {pooled_stype}."),
            unsafe_allow_html=True,
        )

        with st.expander("📋  Full pooled rankings table", expanded=False):
            st.dataframe(
                df_w[[
                    "full_name", "team", "rapm_prior", "xrapm",
                    "rapm", "rapm_vs_xrapm", "possessions",
                ]],
                use_container_width=True, height=460, hide_index=True,
                column_config={
                    "full_name":     st.column_config.TextColumn("Player", width="medium"),
                    "team":          st.column_config.TextColumn("Team", width="small"),
                    "rapm_prior":    st.column_config.NumberColumn("RAPM+Prior", format="%.2f", width="small"),
                    "xrapm":         st.column_config.NumberColumn("xRAPM",      format="%.2f", width="small"),
                    "rapm":          st.column_config.NumberColumn("RAPM (raw)", format="%.2f", width="small"),
                    "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f", width="small"),
                    "possessions":   st.column_config.NumberColumn("Pooled Poss", format="%.0f", width="small"),
                },
            )
