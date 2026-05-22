"""
NBA Impact Model — Dashboard
Home page: league-level overview and navigation.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from dashboard.utils.db import query

st.set_page_config(
    page_title="NBA Impact Model",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏀 NBA Impact Model")
st.caption("Play-by-play analytics: xShot quality, RAPM, and xRAPM — 2014-15 through 2025-26")

# ── League overview stats ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("League Overview")

@st.cache_data(ttl=600, show_spinner=False)
def load_overview():
    return query("""
        SELECT
            COUNT(DISTINCT game_id)   AS total_games,
            COUNT(*)                  AS total_shots,
            ROUND(AVG(xshot)::numeric, 4) AS league_avg_xshot,
            ROUND(AVG(shot_made::int)::numeric, 4) AS league_fg_pct
        FROM shot_predictions
    """)

@st.cache_data(ttl=600, show_spinner=False)
def load_season_counts():
    return query("""
        SELECT season, season_type, COUNT(DISTINCT game_id) AS games, COUNT(*) AS shots
        FROM shot_predictions
        GROUP BY season, season_type
        ORDER BY season DESC, season_type
    """)

overview = load_overview()
if not overview.empty:
    row = overview.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Games", f"{int(row['total_games']):,}")
    col2.metric("Total Shots", f"{int(row['total_shots']):,}")
    col3.metric("League Avg xShot", f"{float(row['league_avg_xshot']):.3f}")
    col4.metric("League FG%", f"{float(row['league_fg_pct']):.3f}")

st.markdown("---")
st.subheader("Seasons in Database")
season_df = load_season_counts()
if not season_df.empty:
    st.dataframe(
        season_df.rename(columns={"season": "Season", "season_type": "Type",
                                  "games": "Games", "shots": "FGA"}),
        use_container_width=True,
        hide_index=True,
    )

# ── Navigation guide ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Pages")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("### 📊 Leaderboards")
    st.markdown(
        "Single-season RAPM / xRAPM rankings and pooled multi-year leaderboard "
        "with box-score prior. Filter by season and minimum possessions."
    )
with c2:
    st.markdown("### 👤 Player Profile")
    st.markdown(
        "Search any player and view season-over-season trends in shot quality, "
        "impact ratings, and traditional box score stats."
    )
with c3:
    st.markdown("### 🏟 Team Analytics")
    st.markdown(
        "Offensive and defensive shot quality per team. Scatter plot of xShot "
        "generated vs allowed. Season-over-season trend lines per franchise."
    )
