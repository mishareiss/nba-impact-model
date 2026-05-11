from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import text
from src.ingestion.schema import play_by_play, ingestion_log
from src.ingestion.db import engine
from src.utils.logging import get_logger
import pandas as pd

logger = get_logger(__name__)

def upsert_pbp(df: pd.DataFrame) -> int:
    """
    Insert play-by-play rows using ON CONFLICT DO NOTHING.
    Returns the number of rows actually inserted.
    """
    records = df.where(pd.notna(df), other=None).to_dict(orient="records")
    if not records:
        return 0

    stmt = pg_insert(play_by_play).values(records)
    stmt = stmt.on_conflict_do_nothing(index_elements=["game_id", "action_id"])

    with engine.begin() as conn:
        result = conn.execute(stmt)

    inserted = result.rowcount
    logger.debug(f"Inserted {inserted}/{len(records)} rows")
    return inserted

def log_ingestion(
        game_id: str, 
        season: str, 
        season_type: str, 
        status: str, 
        row_count: int = 0, 
        error_msg: str = None
    ):
    stmt = pg_insert(ingestion_log).values(
        game_id=game_id,
        season=season,
        season_type=season_type,
        status=status,
        row_count=row_count,
        error_msg=error_msg,
    ).on_conflict_do_update(
        index_elements=["game_id"],
        set_={
            "status": status, "row_count": row_count, 
            "error_msg": error_msg, "inserted_at": text("NOW()")
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)

def is_already_ingested(game_id: str) -> bool:
    stmt = text("SELECT status FROM ingestion_log WHERE game_id = :gid")
    with engine.connect() as conn:
        row = conn.execute(stmt, {"gid": game_id}).fetchone()
    return row is not None and row[0] == "success"

def refresh_shots_view():
    try:
        with engine.begin() as conn:
            conn.execute(text("REFRESH MATERIALIZED VIEW shots"))
        logger.info(f"Refreshed materialized view: shots")
    except Exception as e:
        logger.error(f"Failed to refresh shots view: {e}")