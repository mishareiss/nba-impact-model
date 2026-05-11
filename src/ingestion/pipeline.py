import time
import argparse
from src.ingestion.fetch import get_game_ids, fetch_pbp
from src.ingestion.transform import normalize_columns, clean_columns
from src.ingestion.load import upsert_pbp, log_ingestion, is_already_ingested, refresh_shots_view
from src.utils.logging import get_logger

logger = get_logger(__name__)

SEASONS = [
    ("2025-26", "Regular Season"),
    ("2025-26", "Playoffs"),
    ("2024-25", "Regular Season"),
    ("2024-25", "Playoffs"),
    ("2023-24", "Regular Season"),
    ("2023-24", "Playoffs"),
    ("2022-23", "Regular Season"),
    ("2022-23", "Playoffs"),
    ("2021-22", "Regular Season"),
    ("2021-22", "Playoffs"),
    ("2020-21", "Regular Season"),
    ("2020-21", "Playoffs"),
    ("2019-20", "Regular Season"),
    ("2019-20", "Playoffs"),
    ("2018-19", "Regular Season"),
    ("2018-19", "Playoffs"),
    ("2017-18", "Regular Season"),
    ("2017-18", "Playoffs"),
    ("2016-17", "Regular Season"),
    ("2016-17", "Playoffs"),
    ("2015-16", "Regular Season"),
    ("2015-16", "Playoffs"),
    ("2014-15", "Regular Season"),
    ("2014-15", "Playoffs"),
]

RATE_LIMIT_SLEEP = 0.6 # seconds between API calls

def insert_season(season: str, season_type: str = "Regular Season",limit: int | None = None) -> dict:
    """
    Ingest one season of data. Returns a summary dict with inserted count and errors.
    """
    logger.info(f"=== Starting ingestion: {season} {season_type} ===")
    game_ids = get_game_ids(season=season, season_type=season_type)
    
    if limit:
        game_ids = game_ids[:limit]

    total_inserted = 0
    skipped = 0
    errors = []

    for i, gid in enumerate(game_ids, 1):
        if is_already_ingested(gid):
            logger.debug(f"[{i}/{len(game_ids)}] {gid} - skipped (already ingested)")
            skipped += 1
            time.sleep(0.05) # minimal sleep when skipping
            continue
        try:
            raw         = fetch_pbp(gid)

            if raw.empty:
                log_ingestion(gid, season, season_type, status="empty", row_count=0)
                logger.warning(f"[{i}/{len(game_ids)}] {gid} - empty response, skipped")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            df          = normalize_columns(raw)
            clean_df    = clean_columns(df, game_id=gid, season=season, season_type=season_type)
            n           = upsert_pbp(clean_df)

            log_ingestion(gid, season, season_type, status="success", row_count=n)
            total_inserted += n
            logger.info(f"[{i}/{len(game_ids)}] {gid} - inserted {n} rows")

        except Exception as e:
            log_ingestion(gid, season, season_type, status="error", error_msg=str(e))
            logger.error(f"[{i}/{len(game_ids)}] {gid} - FAILED: {e}")
            errors.append({"game_id": gid, "error": str(e)})

        time.sleep(RATE_LIMIT_SLEEP)

    logger.info(f"Done. {total_inserted} rows inserted, {skipped} skipped, {len(errors)} games failed.")
    return {"season": season, "inserted": total_inserted, "skipped": skipped, "errors": errors}

def insert_game(game_id: str, season: str, season_type: str) -> dict:
    """
    Ingest a single game by game_id. Userful for retrying specific failed games.
    """
    logger.info(f"=== Inserting single game: {game_id} ({season} {season_type}) ===")
    try:
        raw = fetch_pbp(game_id)
        if raw.empty:
            log_ingestion(game_id, season, season_type, status="empty", row_count=0)
            logger.warning(f"{game_id} - empty response")
            return {"game_id": game_id, "inserted": 0, "error": "empty response"}
        
        df = normalize_columns(raw)
        clean_df = clean_columns(df, game_id=game_id, season=season, season_type=season_type)
        n = upsert_pbp(clean_df)
        log_ingestion(game_id, season, season_type, status="success", row_count=n)
        logger.info(f"OK: {game_id} - inserted {n} rows")
        return {"game_id": game_id, "inserted": n, "error": None}
    except Exception as e:
        log_ingestion(game_id, season, season_type, status="error", error_msg=str(e))
        logger.error(f"FAILED: {game_id} - {e}")
        return {"game_id": game_id, "inserted": 0, "error": str(e)}

def insert_seasons(seasons: list[tuple[str, str]] = SEASONS, limit: int | None = None):
    """
    Ingest multiple seasons sequentially. Returns a list of summary dicts with series-level error tracking.
    """
    total_inserted = 0
    all_errors = []

    for season, season_type in seasons:
        result = insert_season(season=season, season_type=season_type, limit=limit)
        total_inserted += result["inserted"]
        all_errors.extend(result["errors"])

    # Refresh shots view once all seasons complete ingestion
    refresh_shots_view()

    logger.info(f"\n{'='*50}")
    logger.info(f"ALL SEASONS COMPLETE")
    logger.info(f"Total rows inserted: {total_inserted}")
    logger.info(f"Total failed games: {len(all_errors)}")

    if all_errors:
        logger.warning("Failed games:")
        for err in all_errors:
            logger.warning(f"  {err['game_id']} - {err['error']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBA PBP Ingestion Pipeline")
    parser.add_argument("--season", type=str, help="Single season (e.g. 2024-25). Omit to run all seasons.")
    parser.add_argument("--season_type", type=str, default="Regular Season", help=" 'Regular Season' or 'Playoffs'")
    parser.add_argument("--game_id", type=str, help="Single game ID to insert (requires --season and --season_type)")
    parser.add_argument("--limit", type=int, default=None, help="Max games per season (for testing)")
    args = parser.parse_args()

    if args.game_id:
        if not args.season:
            parser.error("--game_id requires --season")
        insert_game(game_id=args.game_id, season=args.season, season_type=args.season_type)
    elif args.season:
        result = insert_season(season=args.season, season_type=args.season_type, limit=args.limit)
        refresh_shots_view()
    else:
        insert_seasons(limit=args.limit)
    