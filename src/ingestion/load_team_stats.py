import time
import pandas as pd
from nba_api.stats.endpoints import leaguedashteamstats
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Table, Column, Integer, Float, Text, MetaData
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

SEASONS = [
  "2014-15", "2015-16", "2016-17", "2017-18", "2018-19",
  "2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
  "2024-25", "2025-26",
]
SEASON_TYPES = ["Regular Season", "Playoffs"]

metadata = MetaData()
team_season_stats = Table(
  "team_season_stats", metadata,
  Column("team_id",     Integer, nullable=False),
  Column("season",      Text,    nullable=False),
  Column("season_type", Text,    nullable=False),
  Column("gp",          Integer),
  Column("min",         Float),
  Column("pts",         Float),
  Column("reb",         Float),
  Column("ast",         Float),
  Column("stl",         Float),
  Column("blk",         Float),
  Column("tov",         Float),
  Column("fgm",         Float),
  Column("fga",         Float),
  Column("fg_pct",      Float),
  Column("fg3m",        Float),
  Column("fg3a",        Float),
  Column("fg3_pct",     Float),
  Column("ftm",         Float),
  Column("fta",         Float),
  Column("ft_pct",      Float),
  Column("oreb",        Float),
  Column("dreb",        Float),
  Column("pf",          Float),
  Column("plus_minus",  Float),
)
COL_MAP = {
  "TEAM_ID":     "team_id",
  "GP":          "gp",
  "MIN":         "min",
  "PTS":         "pts",
  "REB":         "reb",
  "AST":         "ast",
  "STL":         "stl",
  "BLK":         "blk",
  "TOV":         "tov",
  "FGM":         "fgm",
  "FGA":         "fga",
  "FG_PCT":      "fg_pct",
  "FG3M":        "fg3m",
  "FG3A":        "fg3a",
  "FG3_PCT":     "fg3_pct",
  "FTM":         "ftm",
  "FTA":         "fta",
  "FT_PCT":      "ft_pct",
  "OREB":        "oreb",
  "DREB":        "dreb",
  "PF":          "pf",
  "PLUS_MINUS":  "plus_minus",
}

def fetch_season(season: str, season_type: str) -> pd.DataFrame:
    time.sleep(1)
    df = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        season_type_all_star=season_type,
        per_mode_detailed="Totals",
    ).get_data_frames()[0]
    return df

def upsert(rows: list):
    if not rows:
        return
    insert_stmt = pg_insert(team_season_stats).values(rows)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["team_id", "season", "season_type"],
        set_={
            k: insert_stmt.excluded[k] for k in COL_MAP.values() if k != "team_id"
        },
    )

    with engine.begin() as conn:
        conn.execute(stmt)

def main():
    total = 0
    for season in SEASONS:
        for season_type in SEASON_TYPES:
            try:
                df = fetch_season(season, season_type)
                if df.empty:
                    logger.warning(f"{season} {season_type} — empty response")
                    continue

                df = df.rename(columns=COL_MAP)
                df["season"] = season
                df["season_type"] = season_type

                keep = list(COL_MAP.values()) + ["season", "season_type"]
                keep = [c for c in keep if c in df.columns]
                rows = df[keep].to_dict(orient="records")

                upsert(rows)
                total += len(rows)
                logger.info(f"{season} {season_type} — {len(rows)} teams loaded")

            except Exception as e:
                logger.error(f"{season} {season_type} — failed: {e}")

        logger.info(f"Done — {total:,} total rows upserted")


if __name__ == "__main__":
    main()