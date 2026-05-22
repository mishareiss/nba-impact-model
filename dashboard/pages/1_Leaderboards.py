"""
Leaderboards page: single-season v1 and multi-year pooled v2 impact ratings.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_single_season_leaderboard, get_pooled_leaderboard
from dashboard.utils.nba_static import TEAM_COLORS, player_headshot_url, team_color

st.set_page_config(page_title="Leaderboards · NBA Impact", page_icon="📊", layout="wide")
st.title("📊 Impact Leaderboards")
st.caption(
    "RAPM = net actual scoring margin per 100 possessions, controlling for teammates and opponents. "
    "xRAPM = same but using expected shot value instead of actual outcomes — more process-based."
)

# ── Sort options (friendly label → column name) ──────────────────────────────
SORT_OPTIONS = {
    "RAPM (Actual outcomes)": "rapm",
    "xRAPM (Expected shot value)": "xrapm",
    "RAPM − xRAPM (Outscoring process)": "rapm_vs_xrapm",
    "FG% vs Expected (Shot-making)": "fg_pct_above_expected",
    "Pts Above Expected (Shot volume)": "shot_pts_above_expected",
    "Shot Quality Generated (Mean xShot)": "mean_xshot",
    "PPG": "ppg",
}

tab_single, tab_pooled = st.tabs(["Single-Season  (v1)", "3-Year Pooled + Prior  (v2)"])

# ── Single-season ─────────────────────────────────────────────────────────────
with tab_single:
    with st.expander("ℹ️ How to read this leaderboard", expanded=False):
        st.markdown(
            "Each row is one player for the selected season. **RAPM** and **xRAPM** are "
            "in units of *points per 100 possessions* relative to a league-average player. "
            "+2.0 = 2 extra points per 100 poss above average. "
            "Values require ≥ the selected possession threshold for stability. "
            "See the **Glossary** page for full definitions."
        )

    # Filters row
    f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 1, 1])
    seasons = get_seasons()
    default_season = "2024-25" if "2024-25" in seasons else seasons[0]
    season     = f1.selectbox("Season", seasons, index=seasons.index(default_season), key="ss_season")
    season_type = f2.selectbox("Season Type", get_season_types(), key="ss_stype")
    sort_label = f3.selectbox("Sort by", list(SORT_OPTIONS.keys()), key="ss_sort")
    sort_col   = SORT_OPTIONS[sort_label]
    min_poss   = f4.number_input("Min Poss", min_value=100, max_value=5000, value=500, step=100, key="ss_minposs")
    top_n      = f5.number_input("Show top", min_value=5, max_value=50, value=20, step=5, key="ss_topn")

    df = get_single_season_leaderboard(season, season_type, int(min_poss))

    if df.empty:
        st.warning("No data for this selection.")
    else:
        # Team filter (multi-select)
        all_teams = sorted(df["team"].dropna().unique().tolist())
        selected_teams = st.multiselect(
            "Filter by team  (leave blank = all teams)", all_teams, key="ss_teams"
        )
        if selected_teams:
            df = df[df["team"].isin(selected_teams)]

        df_sorted = df.sort_values(sort_col, ascending=False, na_position="last").reset_index(drop=True)
        chart_df = df_sorted.head(int(top_n))

        # Bar chart colored by team brand color
        bar_colors = [team_color(str(t)) for t in chart_df["team"]]
        hover_text = [
            f"<b>{name}</b>  ({team})<br>"
            f"RAPM: {rapm:.2f} | xRAPM: {xrapm:.2f}<br>"
            f"PPG: {ppg} | GP: {gp} | Poss: {poss:.0f}"
            for name, team, rapm, xrapm, ppg, gp, poss in zip(
                chart_df["full_name"], chart_df["team"],
                chart_df["rapm"].fillna(0), chart_df["xrapm"].fillna(0),
                chart_df["ppg"].fillna("—"), chart_df["gp"].fillna("—"),
                chart_df["possessions"].fillna(0),
            )
        ]

        fig = go.Figure(go.Bar(
            x=chart_df[sort_col],
            y=chart_df["full_name"],
            orientation="h",
            marker_color=bar_colors,
            marker_line_color="rgba(255,255,255,0.15)",
            marker_line_width=0.5,
            text=[f"{v:.3f}" for v in chart_df[sort_col]],
            textposition="outside",
            hovertext=hover_text,
            hoverinfo="text",
        ))
        fig.add_vline(x=0, line_dash="dot", line_color="gray", opacity=0.5)
        fig.update_layout(
            title=f"Top {int(top_n)} by {sort_label}  —  {season} {season_type}",
            yaxis={"autorange": "reversed"},
            xaxis_title=sort_label,
            height=max(400, int(top_n) * 26),
            margin=dict(l=0, r=80, t=50, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Full table
        st.markdown("#### Full Rankings")
        df_display = df_sorted.copy()
        df_display.insert(0, "Rank", range(1, len(df_display) + 1))
        df_display["headshot"] = df_display["person_id"].apply(player_headshot_url)

        col_cfg = {
            "headshot":              st.column_config.ImageColumn(" ", width="small"),
            "Rank":                  st.column_config.NumberColumn("#", width="small"),
            "full_name":             st.column_config.TextColumn("Player"),
            "team":                  st.column_config.TextColumn("Team"),
            "rapm":                  st.column_config.NumberColumn("RAPM", format="%.2f",
                                         help="Net actual pts/100 poss vs avg"),
            "xrapm":                 st.column_config.NumberColumn("xRAPM", format="%.2f",
                                         help="Net expected pts/100 poss vs avg"),
            "rapm_vs_xrapm":         st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f",
                                         help="Positive = outscores expected process"),
            "fg_pct_above_expected": st.column_config.NumberColumn("FG% vs Exp", format="%.3f",
                                         help="Actual FG% minus model-predicted FG%"),
            "shot_pts_above_expected": st.column_config.NumberColumn("Pts Above Exp", format="%.0f",
                                         help="Total points scored above xShot expectation"),
            "mean_xshot":            st.column_config.NumberColumn("Avg xShot", format="%.3f",
                                         help="Average shot difficulty of attempts taken"),
            "ppg":                   st.column_config.NumberColumn("PPG", format="%.1f"),
            "mpg":                   st.column_config.NumberColumn("MPG", format="%.1f"),
            "gp":                    st.column_config.NumberColumn("GP", format="%d"),
            "possessions":           st.column_config.NumberColumn("Poss (Stints)", format="%.0f"),
        }

        show_cols = ["headshot", "Rank", "full_name", "team",
                     "rapm", "xrapm", "rapm_vs_xrapm",
                     "fg_pct_above_expected", "shot_pts_above_expected", "mean_xshot",
                     "ppg", "mpg", "gp", "possessions"]
        available = [c for c in show_cols if c in df_display.columns or c == "Rank"]
        st.dataframe(
            df_display[[c for c in show_cols if c in df_display.columns]],
            use_container_width=True,
            height=520,
            hide_index=True,
            column_config={k: v for k, v in col_cfg.items() if k in show_cols},
        )

# ── Multi-year pooled (v2) ────────────────────────────────────────────────────
with tab_pooled:
    with st.expander("ℹ️ About the v2 pooled model", expanded=False):
        st.markdown(
            "**Why pool multiple seasons?** Single-season stints are often collinear — "
            "teammates share too much court time to fully disentangle. Three seasons of "
            "data helps separate individual contributions.\n\n"
            "**What is the box-score prior?** Each player's estimate is shrunk toward "
            "their historical plus/minus baseline, anchoring noisy estimates and correctly "
            "elevating stars whose box-score impact is measurable through traditional stats.\n\n"
            "**RAPM+Prior is the recommended metric** for cross-era player comparisons. "
            "See the Glossary for full details."
        )

    p1, p2, p3, p4 = st.columns([2, 2, 2, 1])
    pooled_stype = p1.selectbox("Season Type", get_season_types(), key="v2_stype")
    min_poss_v2  = p2.number_input("Min Pooled Poss", min_value=500, max_value=10000,
                                    value=1500, step=500, key="v2_minposs")
    top_n_v2     = p4.number_input("Show top", min_value=5, max_value=50, value=20, step=5, key="v2_topn")

    df_v2 = get_pooled_leaderboard(int(min_poss_v2))
    if not df_v2.empty:
        df_v2 = df_v2[df_v2["season_type"] == pooled_stype]

    if df_v2.empty:
        st.warning("No pooled data available.")
    else:
        windows = sorted(df_v2["window_label"].unique(), reverse=True)
        selected_window = p3.selectbox("3-Year Window (end season)", windows, key="v2_window")
        df_w = (
            df_v2[df_v2["window_label"] == selected_window]
            .sort_values("rapm_prior", ascending=False)
            .reset_index(drop=True)
        )

        # Team filter
        all_teams_v2 = sorted(df_w["team"].dropna().unique().tolist())
        sel_teams_v2 = st.multiselect("Filter by team", all_teams_v2, key="v2_teams")
        if sel_teams_v2:
            df_w = df_w[df_w["team"].isin(sel_teams_v2)]

        chart_v2 = df_w.head(int(top_n_v2))
        bar_colors_v2 = [team_color(str(t)) for t in chart_v2["team"]]

        hover_v2 = [
            f"<b>{name}</b>  ({team})<br>"
            f"RAPM+Prior: {rp:.2f} | RAPM raw: {r:.2f} | xRAPM: {x:.2f}<br>"
            f"Pooled Poss: {p:.0f}"
            for name, team, rp, r, x, p in zip(
                chart_v2["full_name"], chart_v2["team"],
                chart_v2["rapm_prior"].fillna(0), chart_v2["rapm"].fillna(0),
                chart_v2["xrapm"].fillna(0), chart_v2["possessions"].fillna(0),
            )
        ]

        fig2 = go.Figure(go.Bar(
            x=chart_v2["rapm_prior"],
            y=chart_v2["full_name"],
            orientation="h",
            marker_color=bar_colors_v2,
            marker_line_color="rgba(255,255,255,0.15)",
            marker_line_width=0.5,
            text=[f"{v:.2f}" for v in chart_v2["rapm_prior"]],
            textposition="outside",
            hovertext=hover_v2,
            hoverinfo="text",
        ))
        fig2.add_vline(x=0, line_dash="dot", line_color="gray", opacity=0.5)
        fig2.update_layout(
            title=f"Top {int(top_n_v2)} — RAPM + Box-Score Prior  ({selected_window}  {pooled_stype})",
            yaxis={"autorange": "reversed"},
            xaxis_title="RAPM + Prior (pts / 100 poss)",
            height=max(400, int(top_n_v2) * 26),
            margin=dict(l=0, r=80, t=50, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

        col_cfg_v2 = {
            "full_name":     st.column_config.TextColumn("Player"),
            "team":          st.column_config.TextColumn("Team"),
            "rapm_prior":    st.column_config.NumberColumn("RAPM+Prior", format="%.2f",
                                 help="Ridge RAPM shrunk toward box-score baseline (recommended)"),
            "xrapm":         st.column_config.NumberColumn("xRAPM", format="%.2f",
                                 help="Expected shot value based impact"),
            "rapm":          st.column_config.NumberColumn("RAPM (raw)", format="%.2f",
                                 help="Actual outcomes RAPM without prior"),
            "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f"),
            "possessions":   st.column_config.NumberColumn("Pooled Poss", format="%.0f"),
        }
        v2_show = ["full_name", "team", "rapm_prior", "xrapm", "rapm", "rapm_vs_xrapm", "possessions"]
        st.dataframe(
            df_w[[c for c in v2_show if c in df_w.columns]],
            use_container_width=True,
            height=520,
            hide_index=True,
            column_config={k: v for k, v in col_cfg_v2.items() if k in v2_show},
        )
