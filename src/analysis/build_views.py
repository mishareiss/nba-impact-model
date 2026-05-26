from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)


def build_team_shot_quality():
    """
    Creates (or replaces) the team_shot_quality materialized view.

    Offensive stats: from shot_predictions grouped by shooting team.
    Defensive stats: from shot_predictions, joining games to identify
    the defending team (opponent of the shooting team).

    Key metrics per team per season:
      Offense — FGA, FGM, FG%, mean xShot quality generated,
                actual pts, expected pts, pts above expected
      Defense — FGA allowed, FGM allowed, FG% allowed,
                mean xShot quality allowed, pts above expected defensively
    """
    sql = """
    DROP MATERIALIZED VIEW IF EXISTS team_shot_quality;

    CREATE MATERIALIZED VIEW team_shot_quality AS
    WITH off_stats AS (
        SELECT
            sp.team_id,
            sp.season,
            sp.season_type,
            COUNT(*)                                  AS fga,
            SUM(sp.shot_made::int)                    AS fgm,
            AVG(sp.xshot)                             AS mean_xshot_off,
            SUM(sp.xshot_points)                      AS xshot_pts_off,
            SUM(sp.shot_made::int * sp.shot_value)    AS actual_pts_off
        FROM shot_predictions sp
        GROUP BY sp.team_id, sp.season, sp.season_type
    ),
    def_stats AS (
        SELECT
            CASE
                WHEN g.home_team_id = sp.team_id THEN g.away_team_id
                ELSE g.home_team_id
            END                                       AS team_id,
            sp.season,
            sp.season_type,
            COUNT(*)                                  AS fga_allowed,
            SUM(sp.shot_made::int)                    AS fgm_allowed,
            AVG(sp.xshot)                             AS mean_xshot_def,
            SUM(sp.xshot_points)                      AS xshot_pts_allowed,
            SUM(sp.shot_made::int * sp.shot_value)    AS actual_pts_allowed
        FROM shot_predictions sp
        JOIN games g ON g.game_id = sp.game_id
        GROUP BY 1, sp.season, sp.season_type
    )
    SELECT
        t.tricode                                                         AS team,
        t.full_name                                                       AS team_name,
        o.team_id,
        o.season,
        o.season_type,
        -- Offense
        o.fga,
        o.fgm,
        ROUND(o.fgm::numeric / NULLIF(o.fga, 0), 4)                     AS fg_pct,
        ROUND(o.mean_xshot_off::numeric, 4)                              AS mean_xshot_off,
        o.actual_pts_off,
        ROUND(o.xshot_pts_off::numeric, 1)                               AS expected_pts_off,
        ROUND((o.actual_pts_off - o.xshot_pts_off)::numeric, 1)         AS pts_above_expected_off,
        -- Defense
        d.fga_allowed,
        d.fgm_allowed,
        ROUND(d.fgm_allowed::numeric / NULLIF(d.fga_allowed, 0), 4)     AS fg_pct_allowed,
        ROUND(d.mean_xshot_def::numeric, 4)                              AS mean_xshot_def,
        d.actual_pts_allowed,
        ROUND(d.xshot_pts_allowed::numeric, 1)                           AS expected_pts_allowed,
        ROUND((d.actual_pts_allowed - d.xshot_pts_allowed)::numeric, 1) AS pts_above_expected_def
    FROM off_stats o
    JOIN def_stats d
        ON  d.team_id     = o.team_id
        AND d.season      = o.season
        AND d.season_type = o.season_type
    JOIN teams t ON t.team_id = o.team_id;

    CREATE INDEX idx_tsq_season ON team_shot_quality (season, season_type);
    CREATE INDEX idx_tsq_team   ON team_shot_quality (team);
    """

    with engine.begin() as conn:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))

    logger.info("team_shot_quality materialized view created")


def build_player_career_stats():
    """
    Creates (or replaces) the player_career_stats materialized view.

    Joins per-season data from three sources into a single queryable table:
      - player_shot_quality  → shot quality metrics (xShot, SMOE, FG%)
      - player_impact_ratings → RAPM and xRAPM (single-season)
      - player_season_stats  → traditional box score totals

    Enables single-query season-over-season trend analysis per player.
    One row per (person_id, team_id, season, season_type).
    """
    sql = """
    DROP MATERIALIZED VIEW IF EXISTS player_career_stats;

    CREATE MATERIALIZED VIEW player_career_stats AS
    WITH primary_stats AS (
        SELECT DISTINCT ON (person_id, season, season_type)
            person_id, team_id, season, season_type,
            gp, min, pts, reb, ast, stl, blk, tov, plus_minus
        FROM player_season_stats
        WHERE min > 0
        ORDER BY person_id, season, season_type, min DESC
    )
    SELECT
        psq.person_id,
        psq.player_name                                AS full_name,
        psq.team_id,
        psq.team_tricode                               AS team,
        psq.season,
        psq.season_type,
        -- Shot quality
        psq.shots_attempted,
        ROUND(psq.actual_fg_pct::numeric, 4)           AS actual_fg_pct,
        ROUND(psq.mean_xshot::numeric, 4)              AS mean_xshot,
        ROUND(psq.fg_pct_above_expected::numeric, 4)   AS fg_pct_above_expected,
        psq.actual_points                              AS shot_actual_pts,
        ROUND(psq.expected_points::numeric, 1)         AS shot_expected_pts,
        ROUND(psq.points_above_expected::numeric, 1)   AS shot_pts_above_expected,
        -- Impact ratings
        pir.xrapm,
        pir.rapm,
        pir.o_rapm,
        pir.d_rapm,
        ROUND((pir.rapm - pir.xrapm)::numeric, 4)     AS rapm_minus_xrapm,
        pir.possessions,
        -- Box score
        ps.gp,
        ps.min,
        ps.pts,
        ps.reb,
        ps.ast,
        ps.stl,
        ps.blk,
        ps.tov,
        ps.plus_minus                                  AS season_plus_minus
    FROM player_shot_quality psq
    LEFT JOIN player_impact_ratings pir
        ON  pir.person_id   = psq.person_id
        AND pir.season      = psq.season
        AND pir.season_type = psq.season_type
    LEFT JOIN primary_stats ps
        ON  ps.person_id    = psq.person_id
        AND ps.season       = psq.season
        AND ps.season_type  = psq.season_type;

    CREATE INDEX idx_pcs_player  ON player_career_stats (person_id, season_type);
    CREATE INDEX idx_pcs_name    ON player_career_stats (full_name);
    CREATE INDEX idx_pcs_season  ON player_career_stats (season, season_type);
    """

    with engine.begin() as conn:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))

    logger.info("player_career_stats materialized view created")


def build_player_shot_zones():
    """
    Creates (or replaces) the player_shot_zones materialized view.

    Pre-aggregates shot quality metrics by (player, season, season_type, shot_zone)
    so zone-efficiency bar charts and shot profile comparisons can be served from a
    fast index scan rather than a 2.68M-row join every page load.

    Each row = one player's shot zone stats for one season / season type.
    """
    sql = """
    DROP MATERIALIZED VIEW IF EXISTS player_shot_zones;

    CREATE MATERIALIZED VIEW player_shot_zones AS
    SELECT
        sp.person_id,
        pl.full_name                                                        AS player_name,
        sp.season,
        sp.season_type,
        s.shot_zone,
        s.shot_value,
        COUNT(*)                                                            AS attempts,
        SUM(sp.shot_made)                                                   AS makes,
        ROUND(AVG(sp.xshot)::numeric, 4)                                    AS mean_xshot,
        ROUND(AVG(sp.shot_made::float)::numeric, 4)                         AS fg_pct,
        ROUND((AVG(sp.shot_made::float) - AVG(sp.xshot))::numeric, 4)      AS fg_pct_vs_expected,
        ROUND(SUM(sp.shot_made * sp.shot_value)::numeric, 1)               AS actual_pts,
        ROUND(SUM(sp.xshot * sp.shot_value)::numeric, 1)                   AS expected_pts,
        ROUND((SUM(sp.shot_made * sp.shot_value) - SUM(sp.xshot * sp.shot_value))::numeric, 1)
                                                                            AS pts_above_expected
    FROM shot_predictions sp
    JOIN shots s
        ON  s.game_id    = sp.game_id
        AND s.action_id  = sp.action_id
    LEFT JOIN players pl ON pl.person_id = sp.person_id
    GROUP BY sp.person_id, pl.full_name, sp.season, sp.season_type, s.shot_zone, s.shot_value;

    CREATE INDEX idx_psz_player  ON player_shot_zones (person_id, season, season_type);
    CREATE INDEX idx_psz_season  ON player_shot_zones (season, season_type);
    CREATE INDEX idx_psz_zone    ON player_shot_zones (shot_zone);
    """

    with engine.begin() as conn:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))

    logger.info("player_shot_zones materialized view created")


def refresh_analytics_views():
    """Refresh all analytics views after new data is ingested."""
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW team_shot_quality"))
        conn.execute(text("REFRESH MATERIALIZED VIEW player_career_stats"))
        conn.execute(text("REFRESH MATERIALIZED VIEW player_impact_leaderboard"))
        conn.execute(text("REFRESH MATERIALIZED VIEW player_shot_zones"))
    logger.info("Analytics views refreshed")


def main():
    logger.info("Building analytics materialized views...")
    build_team_shot_quality()
    build_player_career_stats()
    build_player_shot_zones()
    logger.info("Done")


if __name__ == "__main__":
    main()
