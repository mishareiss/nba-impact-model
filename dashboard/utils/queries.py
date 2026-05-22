"""Pre-written SQL query helpers for each dashboard page."""
import pandas as pd
from .db import query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PER_GAME = """
    ROUND(CASE WHEN gp > 0 THEN pts::numeric / gp ELSE NULL END, 1) AS ppg,
    ROUND(CASE WHEN gp > 0 THEN min::numeric / gp ELSE NULL END, 1) AS mpg,
    ROUND(CASE WHEN gp > 0 THEN reb::numeric / gp ELSE NULL END, 1) AS rpg,
    ROUND(CASE WHEN gp > 0 THEN ast::numeric / gp ELSE NULL END, 1) AS apg,
    ROUND(CASE WHEN gp > 0 THEN stl::numeric / gp ELSE NULL END, 1) AS spg,
    ROUND(CASE WHEN gp > 0 THEN blk::numeric / gp ELSE NULL END, 1) AS bpg
"""


# ---------------------------------------------------------------------------
# Leaderboard queries
# ---------------------------------------------------------------------------

def get_single_season_leaderboard(
    season: str, season_type: str, min_poss: int = 500
) -> pd.DataFrame:
    return query(
        f"""
        SELECT person_id, full_name, team, season,
               shots_attempted, actual_fg_pct, mean_xshot,
               fg_pct_above_expected, shot_pts_above_expected,
               xrapm, rapm,
               ROUND((rapm - xrapm)::numeric, 3) AS rapm_vs_xrapm,
               possessions, gp,
               {_PER_GAME},
               season_plus_minus
        FROM player_career_stats
        WHERE season = :season
          AND season_type = :season_type
          AND possessions >= :min_poss
        ORDER BY rapm DESC NULLS LAST
        """,
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


def get_pooled_leaderboard(min_poss: int = 1500) -> pd.DataFrame:
    return query(
        """
        SELECT full_name, team,
               season AS window_label,
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
    return query(
        f"""
        SELECT person_id, season, team,
               shots_attempted, actual_fg_pct, mean_xshot,
               fg_pct_above_expected, shot_pts_above_expected,
               xrapm, rapm,
               ROUND((rapm - xrapm)::numeric, 3) AS rapm_vs_xrapm,
               possessions,
               gp,
               {_PER_GAME},
               season_plus_minus
        FROM player_career_stats
        WHERE full_name = :name AND season_type = :season_type
        ORDER BY season
        """,
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


def get_league_distribution(season: str, season_type: str, min_poss: int = 500) -> pd.DataFrame:
    """Full distribution of key metrics for percentile calculation."""
    return query(
        """
        SELECT rapm, xrapm, fg_pct_above_expected,
               shot_pts_above_expected, mean_xshot, ppg, mpg
        FROM (
            SELECT rapm, xrapm, fg_pct_above_expected,
                   shot_pts_above_expected, mean_xshot,
                   ROUND(CASE WHEN gp > 0 THEN pts::numeric / gp ELSE NULL END, 1) AS ppg,
                   ROUND(CASE WHEN gp > 0 THEN min::numeric / gp ELSE NULL END, 1) AS mpg
            FROM player_career_stats
            WHERE season = :season
              AND season_type = :season_type
              AND possessions >= :min_poss
        ) t
        """,
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
