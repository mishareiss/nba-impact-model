"""
NBA Impact Model — Home
League overview and navigation guide.
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
st.markdown(
    "A play-by-play analytics system covering **2.68 million field goal attempts** "
    "across 12 NBA seasons (2014-15 → 2025-26). Quantifies shot quality and player "
    "impact independently of teammates and opponents."
)

# ── League overview ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("League Snapshot")


@st.cache_data(ttl=600, show_spinner=False)
def load_overview():
    return query("""
        SELECT
            COUNT(DISTINCT game_id)                          AS total_games,
            COUNT(*)                                         AS total_shots,
            ROUND(AVG(xshot)::numeric, 3)                    AS league_avg_xshot,
            ROUND(AVG(shot_made::int)::numeric, 3)           AS league_fg_pct,
            ROUND(AVG(CASE WHEN shot_value = 3 THEN 1 ELSE 0 END)::numeric, 3)
                                                             AS three_pt_rate
        FROM shot_predictions
    """)


@st.cache_data(ttl=600, show_spinner=False)
def load_season_counts():
    return query("""
        SELECT season, season_type,
               COUNT(DISTINCT game_id)  AS games,
               COUNT(*)                 AS fga,
               ROUND(AVG(xshot)::numeric, 3)        AS avg_xshot,
               ROUND(AVG(shot_made::int)::numeric, 3) AS fg_pct
        FROM shot_predictions
        GROUP BY season, season_type
        ORDER BY season DESC, season_type
    """)


overview = load_overview()
if not overview.empty:
    row = overview.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Games", f"{int(row['total_games']):,}")
    c2.metric("Total Shot Attempts", f"{int(row['total_shots']):,}")
    c3.metric("League Avg xShot", f"{float(row['league_avg_xshot']):.3f}",
              help="Average predicted make probability across all shot attempts")
    c4.metric("League FG%", f"{float(row['league_fg_pct']):.3f}",
              help="Actual field goal percentage across all seasons")
    c5.metric("3-Point Rate", f"{float(row['three_pt_rate']):.1%}",
              help="Share of field goal attempts that are 3-pointers")

st.markdown("---")
st.subheader("Seasons in Database")
season_df = load_season_counts()
if not season_df.empty:
    st.dataframe(
        season_df.rename(columns={
            "season": "Season", "season_type": "Type",
            "games": "Games", "fga": "FGA",
            "avg_xshot": "Avg xShot", "fg_pct": "FG%",
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Avg xShot": st.column_config.NumberColumn(format="%.3f"),
            "FG%": st.column_config.NumberColumn(format="%.3f"),
        },
    )

# ── Pages guide ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Pages")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown("### 📊 Leaderboards")
    st.markdown(
        "Single-season RAPM and xRAPM rankings (v1) plus a multi-year pooled "
        "leaderboard with box-score prior (v2). Filter by season, season type, "
        "team, and minimum possessions. Bars are colored by team."
    )

with c2:
    st.markdown("### 👤 Player Profile")
    st.markdown(
        "Search any player for season-over-season trend charts in impact ratings "
        "and shot quality. Shows headshot, league percentile context, PPG/MPG, "
        "and a full career stats table."
    )

with c3:
    st.markdown("### 🏟 Team Analytics")
    st.markdown(
        "Offensive and defensive shot quality per team. Team-colored scatter plot "
        "of xShot generated vs allowed with quadrant labels. Season-over-season "
        "trend lines per franchise."
    )

with c4:
    st.markdown("### 📖 Glossary")
    st.markdown(
        "Plain-English explanations of every metric: xShot, RAPM, xRAPM, RAPM+Prior, "
        "FG% Above Expected, Points Above Expected, and more. Start here if you "
        "are new to process-based basketball analytics."
    )

# ── Methodology note ─────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("How this system works"):
    st.markdown("""
**Step 1 — Shot Quality (xShot)**
Every field goal attempt is scored by an XGBoost model trained on shot location,
shot type, and game context. The output is a probability (0–1) that the shot is made.
A dunk from the restricted area might score 0.95; a contested mid-range fadeaway might score 0.35.

**Step 2 — Shot-Making Over Expected**
Comparing xShot predictions to actual outcomes reveals which players consistently
outperform or underperform the difficulty of their attempts. This separates
shot-making skill from shot selection and volume.

**Step 3 — Player Impact (RAPM / xRAPM)**
Every game is parsed into lineup stints — periods where both 5-player lineups
are unchanged. Ridge regression over all stints estimates each player's marginal
contribution to team scoring margin per 100 possessions, controlling for
teammates and opponents simultaneously.

**Step 4 — Multi-Year Pooling + Prior (v2)**
Rolling 3-season windows reduce single-season noise. A box-score prior anchors
estimates toward each player's historical plus/minus baseline, correctly elevating
stars whose impact is independently measurable from traditional stats.
    """)
