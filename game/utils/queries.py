"""SQL queries for the Daily Stat Challenge game."""
import pandas as pd
from game.utils.db import query


def get_daily_challenge_stats(
    season: str,
    season_type: str = "Regular Season",
    min_gp: int = 50,
    min_mpg: float = 15.0,
) -> pd.DataFrame:
    """
    Return traditional per-game stats for all qualifying players.
    Requires ≥50 GP and ≥15 MPG to eliminate small-sample outliers.
    Percentage stats should be further filtered by the caller using the
    fga_pg / fg3a_pg / fta_pg columns.
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
            ROUND(pss.pts::numeric, 0)  AS pts_total,
            ROUND(pss.reb::numeric, 0)  AS reb_total,
            ROUND(pss.ast::numeric, 0)  AS ast_total,
            ROUND(pss.stl::numeric, 0)  AS stl_total,
            ROUND(pss.blk::numeric, 0)  AS blk_total,
            ROUND(pss.fg3m::numeric, 0) AS fg3m_total
        FROM player_season_stats pss
        JOIN players p ON pss.person_id = p.person_id
        WHERE pss.season      = :season
          AND pss.season_type = :season_type
          AND pss.gp         >= :min_gp
          AND (pss.min::float / NULLIF(pss.gp, 0)) >= :min_mpg
          AND p.full_name IS NOT NULL
        ORDER BY pss.person_id, pss.team_id
        """,
        {
            "season": season,
            "season_type": season_type,
            "min_gp": min_gp,
            "min_mpg": min_mpg,
        },
    )
