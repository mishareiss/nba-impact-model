"""Pre-written SQL query helpers for each dashboard page."""
import pandas as pd
from .db import query


# ---------------------------------------------------------------------------
# Shared CTE: aggregates traded players into one row per (person, season)
#
# For traded players, player_career_stats has one row per team they played for.
# Shot quality stats differ by team; RAPM and box score stats are duplicated.
# This CTE aggregates shot quality by volume-weighted average and takes MAX
# for all other fields (since they're identical across rows for a given player-season).
# ---------------------------------------------------------------------------

_DEDUP_CTE = """
WITH deduped AS (
    SELECT
        MAX(person_id)    AS person_id,
        MAX(full_name)    AS full_name,
        CASE
            WHEN COUNT(DISTINCT team) > 1
            THEN COUNT(DISTINCT team)::text || 'TM'
            ELSE MAX(team)
        END               AS team,
        season,
        season_type,
        -- Shot quality: volume-weighted average for rates, SUM for totals
        SUM(shots_attempted)::int                                                   AS shots_attempted,
        ROUND(SUM(shots_attempted * actual_fg_pct)
              / NULLIF(SUM(shots_attempted), 0), 4)                                 AS actual_fg_pct,
        ROUND(SUM(shots_attempted * mean_xshot)
              / NULLIF(SUM(shots_attempted), 0), 4)                                 AS mean_xshot,
        ROUND(SUM(shots_attempted * fg_pct_above_expected)
              / NULLIF(SUM(shots_attempted), 0), 4)                                 AS fg_pct_above_expected,
        ROUND(SUM(shot_pts_above_expected)::numeric, 1)                             AS shot_pts_above_expected,
        -- RAPM: identical across rows, take any
        MAX(xrapm)        AS xrapm,
        MAX(rapm)         AS rapm,
        MAX(o_rapm)       AS o_rapm,
        MAX(d_rapm)       AS d_rapm,
        MAX(possessions)  AS possessions,
        -- Box score totals: identical across rows (from DISTINCT ON), take MAX
        MAX(gp)           AS gp,
        MAX(pts)          AS pts,
        MAX(min)          AS min,
        MAX(reb)          AS reb,
        MAX(ast)          AS ast,
        MAX(stl)          AS stl,
        MAX(blk)          AS blk,
        MAX(season_plus_minus) AS season_plus_minus
    FROM player_career_stats
    {where}
    GROUP BY person_id, season, season_type
)
"""

_SELECT_COLS = """
    person_id, full_name, team, season, season_type,
    shots_attempted, actual_fg_pct, mean_xshot,
    fg_pct_above_expected, shot_pts_above_expected,
    xrapm, rapm, o_rapm, d_rapm,
    ROUND((rapm - xrapm)::numeric, 3)                                          AS rapm_vs_xrapm,
    possessions,
    gp,
    ROUND(CASE WHEN gp > 0 THEN pts::numeric  / gp ELSE NULL END, 1)          AS ppg,
    ROUND(CASE WHEN gp > 0 THEN min::numeric  / gp ELSE NULL END, 1)          AS mpg,
    ROUND(CASE WHEN gp > 0 THEN reb::numeric  / gp ELSE NULL END, 1)          AS rpg,
    ROUND(CASE WHEN gp > 0 THEN ast::numeric  / gp ELSE NULL END, 1)          AS apg,
    ROUND(CASE WHEN gp > 0 THEN stl::numeric  / gp ELSE NULL END, 1)          AS spg,
    ROUND(CASE WHEN gp > 0 THEN blk::numeric  / gp ELSE NULL END, 1)          AS bpg,
    season_plus_minus
"""


# ---------------------------------------------------------------------------
# Leaderboard queries
# ---------------------------------------------------------------------------

def get_single_season_leaderboard(
    season: str, season_type: str, min_poss: int = 500
) -> pd.DataFrame:
    cte = _DEDUP_CTE.format(
        where="WHERE season = :season AND season_type = :season_type AND possessions >= :min_poss"
    )
    return query(
        cte + f"SELECT {_SELECT_COLS} FROM deduped ORDER BY rapm DESC NULLS LAST",
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


def get_pooled_leaderboard(min_poss: int = 1500) -> pd.DataFrame:
    return query(
        """
        SELECT full_name, team,
               season        AS window_label,
               season_type,
               rapm_prior, xrapm, rapm,
               ROUND((rapm - xrapm)::numeric, 3) AS rapm_vs_xrapm,
               possessions
        FROM player_impact_leaderboard
        WHERE rating_type = 'pooled_3yr'
          AND possessions >= :min_poss
        ORDER BY rapm_prior DESC NULLS LAST
        """,
        {"min_poss": min_poss},
    )


# ---------------------------------------------------------------------------
# Player profile queries
# ---------------------------------------------------------------------------

def get_player_names() -> list[str]:
    df = query(
        "SELECT DISTINCT full_name FROM player_career_stats ORDER BY full_name"
    )
    return df["full_name"].tolist()


def get_player_career(full_name: str, season_type: str) -> pd.DataFrame:
    cte = _DEDUP_CTE.format(
        where="WHERE full_name = :name AND season_type = :season_type"
    )
    return query(
        cte + f"SELECT {_SELECT_COLS} FROM deduped ORDER BY season",
        {"name": full_name, "season_type": season_type},
    )


def get_player_pooled(full_name: str) -> pd.DataFrame:
    return query(
        """
        SELECT season AS window_label, season_type,
               rapm_prior, xrapm, rapm, possessions
        FROM player_impact_leaderboard
        WHERE full_name = :name
          AND rating_type = 'pooled_3yr'
        ORDER BY season, season_type
        """,
        {"name": full_name},
    )


def get_league_distribution(
    season: str, season_type: str, min_poss: int = 500
) -> pd.DataFrame:
    """Full distribution of all metrics for percentile rank computation."""
    cte = _DEDUP_CTE.format(
        where="WHERE season = :season AND season_type = :season_type AND possessions >= :min_poss"
    )
    return query(
        cte + f"SELECT {_SELECT_COLS} FROM deduped",
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


# ---------------------------------------------------------------------------
# Team analytics queries
# ---------------------------------------------------------------------------

def get_team_shot_quality(season: str, season_type: str) -> pd.DataFrame:
    return query(
        """
        SELECT team, team_name, season, season_type,
               fga, fg_pct, mean_xshot_off,
               actual_pts_off, expected_pts_off, pts_above_expected_off,
               fga_allowed, fg_pct_allowed, mean_xshot_def,
               actual_pts_allowed, expected_pts_allowed, pts_above_expected_def,
               ROUND((pts_above_expected_off - pts_above_expected_def)::numeric, 1)
                   AS net_pts_above_expected
        FROM team_shot_quality
        WHERE season = :season AND season_type = :season_type
        ORDER BY net_pts_above_expected DESC
        """,
        {"season": season, "season_type": season_type},
    )


def get_team_trend(team: str, season_type: str) -> pd.DataFrame:
    return query(
        """
        SELECT season, fg_pct, mean_xshot_off, pts_above_expected_off,
               fg_pct_allowed, mean_xshot_def, pts_above_expected_def,
               ROUND((pts_above_expected_off - pts_above_expected_def)::numeric, 1)
                   AS net_pts_above_expected
        FROM team_shot_quality
        WHERE team = :team AND season_type = :season_type
        ORDER BY season
        """,
        {"team": team, "season_type": season_type},
    )


def get_all_teams() -> list[str]:
    df = query("SELECT DISTINCT team FROM team_shot_quality ORDER BY team")
    return df["team"].tolist()


def get_team_league_distribution(season: str, season_type: str) -> pd.DataFrame:
    """All teams' shot-quality stats for the selected season — used for percentile chart."""
    return query(
        """
        SELECT team, team_name,
               pts_above_expected_off,
               mean_xshot_off,
               fg_pct,
               ROUND((pts_above_expected_off - pts_above_expected_def)::numeric, 1)
                   AS net_pts_above_expected,
               -pts_above_expected_def        AS pts_saved_on_defense,
               -mean_xshot_def                AS xshot_suppression,
               -fg_pct_allowed                AS fg_pct_def_inverted
        FROM team_shot_quality
        WHERE season = :season AND season_type = :season_type
        """,
        {"season": season, "season_type": season_type},
    )
