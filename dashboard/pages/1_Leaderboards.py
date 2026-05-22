"""
Leaderboards page: single-season and pooled impact ratings.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.express as px
from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_single_season_leaderboard, get_pooled_leaderboard

st.set_page_config(page_title="Leaderboards · NBA Impact", page_icon="📊", layout="wide")
st.title("📊 Impact Leaderboards")

tab_single, tab_pooled = st.tabs(["Single-Season (v1)", "Multi-Year Pooled (v2)"])

# ── Single-season ────────────────────────────────────────────────────────────
with tab_single:
    c1, c2, c3 = st.columns([2, 2, 1])
    seasons = get_seasons()
    default_season = "2024-25" if "2024-25" in seasons else seasons[0]
    season = c1.selectbox("Season", seasons, index=seasons.index(default_season), key="ss_season")
    season_type = c2.selectbox("Season Type", get_season_types(), key="ss_stype")
    min_poss = c3.number_input("Min possessions", min_value=100, max_value=5000,
                               value=500, step=100, key="ss_minposs")

    df = get_single_season_leaderboard(season, season_type, int(min_poss))

    if df.empty:
        st.warning("No data for this selection.")
    else:
        sort_col = st.radio(
            "Sort by",
            ["rapm", "xrapm", "fg_pct_above_expected", "shot_pts_above_expected"],
            horizontal=True,
            key="ss_sort",
        )
        df_sorted = df.sort_values(sort_col, ascending=False, na_position="last").reset_index(drop=True)
        df_sorted.index += 1

        # Bar chart — top / bottom 20
        n = min(20, len(df_sorted))
        chart_df = df_sorted.head(n)
        fig = px.bar(
            chart_df,
            x=sort_col,
            y="full_name",
            orientation="h",
            color=sort_col,
            color_continuous_scale="RdYlGn",
            labels={"full_name": "", sort_col: sort_col.upper()},
            title=f"Top {n} — {sort_col.upper()} ({season} {season_type})",
            height=520,
        )
        fig.update_layout(yaxis={"autorange": "reversed"}, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        display_cols = {
            "full_name": "Player", "team": "Team", "possessions": "Poss",
            "xrapm": "xRAPM", "rapm": "RAPM",
            "mean_xshot": "Mean xShot", "fg_pct_above_expected": "FG% Above Exp",
            "shot_pts_above_expected": "Pts Above Exp", "gp": "GP", "pts": "PPG",
        }
        st.dataframe(
            df_sorted[list(display_cols)].rename(columns=display_cols),
            use_container_width=True,
            height=500,
        )

# ── Pooled (v2) ──────────────────────────────────────────────────────────────
with tab_pooled:
    pc1, pc2, pc3 = st.columns([2, 2, 1])
    pooled_stype = pc1.selectbox("Season Type", get_season_types(), key="v2_stype")
    min_poss_v2 = pc2.number_input("Min pooled possessions", min_value=500, max_value=10000,
                                   value=1500, step=500, key="v2_minposs")
    df_v2 = get_pooled_leaderboard(int(min_poss_v2))
    if not df_v2.empty:
        df_v2 = df_v2[df_v2["season_type"] == pooled_stype]

    if df_v2.empty:
        st.warning("No pooled data available.")
    else:
        windows = sorted(df_v2["window_label"].unique(), reverse=True)
        selected_window = pc3.selectbox("End Season", windows, key="v2_window")
        df_w = df_v2[df_v2["window_label"] == selected_window].sort_values("rapm_prior", ascending=False)
        df_w = df_w.reset_index(drop=True)
        df_w.index += 1

        n = min(20, len(df_w))
        fig2 = px.bar(
            df_w.head(n),
            x="rapm_prior",
            y="full_name",
            orientation="h",
            color="rapm_prior",
            color_continuous_scale="RdYlGn",
            labels={"full_name": "", "rapm_prior": "RAPM+Prior"},
            title=f"Top {n} — RAPM + Box-Score Prior ({selected_window})",
            height=520,
        )
        fig2.update_layout(yaxis={"autorange": "reversed"}, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

        display_cols_v2 = {
            "full_name": "Player", "team": "Team",
            "rapm_prior": "RAPM+Prior", "xrapm": "xRAPM",
            "rapm": "RAPM (raw)", "possessions": "Poss",
        }
        st.dataframe(
            df_w[list(display_cols_v2)].rename(columns=display_cols_v2),
            use_container_width=True,
            height=500,
        )
