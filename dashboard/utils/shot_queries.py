"""
Shot chart query helpers.

These queries join shot_predictions (xShot scores) with the shots materialized
view (spatial coordinates) and are deliberately separated from queries.py because:
  - They target large tables and need longer cache TTLs (shot data is immutable)
  - They're only needed on shot-chart-bearing pages (Player Profile, Compare)
  - The JOIN pattern differs from the player_career_stats CTE pattern

All functions are decorated with @st.cache_data(ttl=3600) — 1-hour cache is safe
because shot_predictions is only rebuilt when predict.py is re-run.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .db import engine


@st.cache_data(ttl=3600, show_spinner=False)
def get_player_shots(
    person_id: int,
    season: str,
    season_type: str,
) -> pd.DataFrame:
    """
    Individual shot-level records for a player/season with coordinates and xShot.

    Joins shot_predictions with the shots materialized view.
    Returned columns: x_legacy, y_legacy, xshot, shot_made, shot_value,
                      shot_zone, shot_distance, sub_type, shot_angle.
    """
    sql = """
    SELECT
        sp.xshot,
        sp.shot_made,
        sp.shot_value,
        s.x_legacy,
        s.y_legacy,
        s.shot_zone,
        s.shot_distance,
        s.sub_type,
        s.shot_angle
    FROM shot_predictions sp
    JOIN shots s
        ON  s.game_id   = sp.game_id
        AND s.action_id = sp.action_id
    WHERE sp.person_id   = %(person_id)s
      AND sp.season      = %(season)s
      AND sp.season_type = %(season_type)s
    ORDER BY sp.game_id, sp.action_id
    """
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={"person_id": person_id, "season": season, "season_type": season_type},
        )


@st.cache_data(ttl=3600, show_spinner=False)
def get_player_shot_zones(
    person_id: int,
    season: str,
    season_type: str,
) -> pd.DataFrame:
    """
    Pre-aggregated shot zone stats from the player_shot_zones materialized view.

    Returned columns: shot_zone, shot_value, attempts, makes, mean_xshot,
                      fg_pct, fg_pct_vs_expected, actual_pts, expected_pts,
                      pts_above_expected.
    """
    sql = """
    SELECT shot_zone, shot_value, attempts, makes,
           mean_xshot, fg_pct, fg_pct_vs_expected,
           actual_pts, expected_pts, pts_above_expected
    FROM player_shot_zones
    WHERE person_id   = %(person_id)s
      AND season      = %(season)s
      AND season_type = %(season_type)s
    ORDER BY shot_zone
    """
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={"person_id": person_id, "season": season, "season_type": season_type},
        )


@st.cache_data(ttl=3600, show_spinner=False)
def get_league_zone_averages(season: str, season_type: str) -> pd.DataFrame:
    """
    League-wide shot zone averages for the given season/type.

    Used to show context lines on zone efficiency charts ("league avg at rim = X%").
    Weighted by attempts so high-volume zones don't get averaged away by small samples.
    """
    sql = """
    SELECT
        shot_zone,
        shot_value,
        SUM(attempts)                                                       AS attempts,
        ROUND(SUM(makes)::numeric / NULLIF(SUM(attempts), 0), 4)           AS fg_pct,
        ROUND(SUM(attempts * mean_xshot) / NULLIF(SUM(attempts), 0), 4)    AS mean_xshot,
        ROUND(SUM(attempts * fg_pct_vs_expected)
              / NULLIF(SUM(attempts), 0), 4)                               AS fg_pct_vs_expected
    FROM player_shot_zones
    WHERE season      = %(season)s
      AND season_type = %(season_type)s
    GROUP BY shot_zone, shot_value
    ORDER BY shot_zone
    """
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"season": season, "season_type": season_type})


@st.cache_data(ttl=3600, show_spinner=False)
def get_player_id(full_name: str) -> int | None:
    """Look up person_id from player name — used on Compare page."""
    sql = "SELECT DISTINCT person_id FROM player_career_stats WHERE full_name = %(name)s LIMIT 1"
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"name": full_name})
    if df.empty:
        return None
    return int(df.iloc[0]["person_id"])


@st.cache_data(ttl=3600, show_spinner=False)
def get_player_zone_history(person_id: int, season_type: str) -> pd.DataFrame:
    """All seasons of zone data for a player — used for shot evolution trend."""
    sql = """
    SELECT season, shot_zone, attempts, fg_pct, mean_xshot, fg_pct_vs_expected
    FROM player_shot_zones
    WHERE person_id   = %(person_id)s
      AND season_type = %(season_type)s
    ORDER BY season, shot_zone
    """
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"person_id": person_id, "season_type": season_type})
