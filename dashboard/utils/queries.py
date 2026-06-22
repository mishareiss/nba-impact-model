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
    # Wrap the deduped result then LEFT JOIN position (picks row with most minutes for traded players)
    sql = cte + f"""
, pos_map AS (
    SELECT DISTINCT ON (person_id, season, season_type)
        person_id, season, season_type,
        NULLIF(TRIM(position), '') AS position
    FROM player_season_stats
    WHERE position IS NOT NULL AND TRIM(position) <> ''
    ORDER BY person_id, season, season_type, min DESC NULLS LAST
),
lb AS (SELECT {_SELECT_COLS} FROM deduped)
SELECT lb.*, pm.position
FROM lb
LEFT JOIN pos_map pm
    ON  pm.person_id   = lb.person_id
    AND pm.season      = lb.season
    AND pm.season_type = lb.season_type
ORDER BY lb.rapm DESC NULLS LAST
"""
    return query(sql, {"season": season, "season_type": season_type, "min_poss": min_poss})


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


# ---------------------------------------------------------------------------
# Lineup Evaluation queries
# ---------------------------------------------------------------------------

def get_lineup_leaderboard(
    season: str, season_type: str, min_poss: float = 250.0,
) -> pd.DataFrame:
    """
    Aggregate lineup_stints from both home and away perspectives.
    Returns one row per unique 5-player lineup with:
      - total_poss, n_stints
      - actual_net_rtg   (pts per 100 poss, actual)
      - expected_net_rtg (xShot-derived pts per 100 poss)
      - luck             (actual − expected)
      - player_ids       (array text for display lookup)

    min_poss=250 is the default floor — below ~200 possessions (~4-6 games of
    5v5 time) net ratings are too noisy to be meaningful.
    """
    return query(
        """
        WITH all_sides AS (
            SELECT home_players AS players,
                   home_points - away_points    AS margin,
                   home_xshot_pts - away_xshot_pts AS xshot_margin,
                   total_poss
            FROM lineup_stints
            WHERE season = :season AND season_type = :season_type
              AND total_poss > 0

            UNION ALL

            SELECT away_players AS players,
                   away_points - home_points    AS margin,
                   away_xshot_pts - home_xshot_pts AS xshot_margin,
                   total_poss
            FROM lineup_stints
            WHERE season = :season AND season_type = :season_type
              AND total_poss > 0
        ),
        agg AS (
            SELECT
                players,
                COUNT(*)                                                AS n_stints,
                SUM(total_poss)                                         AS total_poss,
                ROUND(SUM(margin)::numeric       / SUM(total_poss)::numeric * 100, 2)    AS actual_net_rtg,
                ROUND(SUM(xshot_margin)::numeric / SUM(total_poss)::numeric * 100, 2)    AS expected_net_rtg,
                ROUND((SUM(margin) - SUM(xshot_margin))::numeric
                      / SUM(total_poss)::numeric * 100, 2)                               AS luck
            FROM all_sides
            GROUP BY players
            HAVING SUM(total_poss) >= :min_poss
               AND COUNT(*) >= 5      -- at least 5 distinct stints; single-game blowout lineups excluded
        )
        SELECT * FROM agg
        ORDER BY actual_net_rtg DESC NULLS LAST
        """,
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


def get_player_id_name_map() -> dict[int, str]:
    """Return {person_id: full_name} for all players in the players table."""
    df = query("SELECT person_id, full_name FROM players WHERE full_name IS NOT NULL")
    if df.empty:
        return {}
    return dict(zip(df["person_id"].astype(int), df["full_name"]))


# ---------------------------------------------------------------------------
# Decision Support queries
# ---------------------------------------------------------------------------

def get_decision_support(
    season: str, season_type: str, min_poss: int = 500,
) -> pd.DataFrame:
    """
    Return all qualifying players with xRAPM, RAPM, and gap for categorisation.
    Called by the Decision Support page to derive player categories.
    """
    cte = _DEDUP_CTE.format(
        where=(
            "WHERE season = :season AND season_type = :season_type "
            "AND possessions >= :min_poss"
        )
    )
    return query(
        cte + f"SELECT {_SELECT_COLS} FROM deduped ORDER BY xrapm DESC NULLS LAST",
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


def get_player_trajectory(season_type: str, min_poss: int = 300) -> pd.DataFrame:
    """
    Two consecutive seasons for the same player — used to identify improving players.
    Returns pairs (season_a, season_b) where season_b = season_a + 1.
    """
    return query(
        """
        WITH base AS (
            SELECT
                person_id, full_name, team, season, season_type,
                xrapm, rapm, possessions
            FROM player_career_stats
            WHERE season_type = :season_type
              AND possessions >= :min_poss
              AND xrapm IS NOT NULL
        ),
        pairs AS (
            SELECT
                a.person_id, a.full_name,
                a.season   AS season_a, b.season   AS season_b,
                a.xrapm    AS xrapm_a,  b.xrapm    AS xrapm_b,
                a.rapm     AS rapm_a,   b.rapm     AS rapm_b,
                a.possessions AS poss_a, b.possessions AS poss_b,
                b.team
            FROM base a
            JOIN base b ON a.person_id = b.person_id
              AND b.season = CONCAT(
                  SPLIT_PART(a.season, '-', 1)::int + 1, '-',
                  LPAD((SPLIT_PART(a.season, '-', 2)::int + 1)::text, 2, '0')
              )
        )
        SELECT *,
               ROUND((xrapm_b - xrapm_a)::numeric, 3) AS xrapm_delta
        FROM pairs
        ORDER BY xrapm_delta DESC
        """,
        {"season_type": season_type, "min_poss": min_poss},
    )


# ---------------------------------------------------------------------------
# Daily Stat Challenge queries
# ---------------------------------------------------------------------------

def get_daily_challenge_stats(
    season: str, season_type: str = "Regular Season",
    min_gp: int = 50, min_mpg: float = 15.0,
) -> pd.DataFrame:
    """
    Return traditional per-game stats for all qualifying players.
    Used by the Daily Stat Challenge page to populate the leaderboards.

    Defaults require ≥50 GP and ≥15 MPG — enough games to rule out short-sample
    flukes while still including players who missed a few weeks.
    Percentage stats should be further filtered by the caller using the
    fga_pg / fg3a_pg / fta_pg columns returned here.
    """
    return query(
        """
        SELECT DISTINCT ON (pss.person_id)
            pss.person_id,
            p.full_name,
            pss.gp,
            ROUND(pss.pts::numeric  / NULLIF(pss.gp, 0), 1)  AS ppg,
            ROUND(pss.reb::numeric  / NULLIF(pss.gp, 0), 1)  AS rpg,
            ROUND(pss.ast::numeric  / NULLIF(pss.gp, 0), 1)  AS apg,
            ROUND(pss.stl::numeric  / NULLIF(pss.gp, 0), 1)  AS spg,
            ROUND(pss.blk::numeric  / NULLIF(pss.gp, 0), 1)  AS bpg,
            ROUND(pss.tov::numeric  / NULLIF(pss.gp, 0), 1)  AS tpg,
            ROUND(pss.fg3m::numeric / NULLIF(pss.gp, 0), 1)  AS fg3m_pg,
            ROUND(pss.fga::numeric  / NULLIF(pss.gp, 0), 1)  AS fga_pg,
            ROUND(pss.fg3a::numeric / NULLIF(pss.gp, 0), 1)  AS fg3a_pg,
            ROUND(pss.fta::numeric  / NULLIF(pss.gp, 0), 1)  AS fta_pg,
            CASE WHEN pss.fga > 0
                 THEN ROUND(pss.fgm::numeric / pss.fga::numeric, 3) END AS fg_pct,
            CASE WHEN pss.fg3a > 0
                 THEN ROUND(pss.fg3m::numeric / pss.fg3a::numeric, 3) END AS fg3_pct,
            CASE WHEN pss.fta > 0
                 THEN ROUND(pss.ftm::numeric / pss.fta::numeric, 3) END AS ft_pct,
            ROUND(pss.oreb::numeric / NULLIF(pss.gp, 0), 1)  AS orpg,
            ROUND(pss.dreb::numeric / NULLIF(pss.gp, 0), 1)  AS drpg,
            ROUND(pss.min::numeric  / NULLIF(pss.gp, 0), 1)  AS mpg,
            ROUND(pss.plus_minus::numeric / NULLIF(pss.gp, 0), 1) AS pm_pg,
            ROUND(pss.pts::numeric, 0) AS pts_total,
            ROUND(pss.reb::numeric, 0) AS reb_total,
            ROUND(pss.ast::numeric, 0) AS ast_total,
            ROUND(pss.stl::numeric, 0) AS stl_total,
            ROUND(pss.blk::numeric, 0) AS blk_total,
            ROUND(pss.fg3m::numeric, 0) AS fg3m_total
        FROM player_season_stats pss
        JOIN players p ON pss.person_id = p.person_id
        WHERE pss.season = :season
          AND pss.season_type = :season_type
          AND pss.gp >= :min_gp
          AND (pss.min::float / NULLIF(pss.gp, 0)) >= :min_mpg
          AND p.full_name IS NOT NULL
        ORDER BY pss.person_id, pss.team_id
        """,
        {
            "season": season, "season_type": season_type,
            "min_gp": min_gp, "min_mpg": min_mpg,
        },
    )


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
