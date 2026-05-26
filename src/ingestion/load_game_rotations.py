import time
import pandas as pd
from nba_api.stats.endpoints import gamerotation
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

def load_game_ids() -> list[str]:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT game_id FROM games ORDER BY game_id"))]

def already_ingested(game_id: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM game_rotations WHERE game_id = :g LIMIT 1"),
            {"g": game_id}
        ).fetchone()
    return row is not None

def fetch_rotation(game_id: str, retries: int = 3) -> list[dict]:
    for attempt in range(1, retries + 1):
        try:
            rot = gamerotation.GameRotation(game_id=game_id)
            rows = []
            for df in rot.get_data_frames():
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    rows.append({
                        "game_id":   game_id,
                        "team_id":   int(row["TEAM_ID"]),
                        "person_id": int(row["PERSON_ID"]),
                        "in_time":   round(row["IN_TIME_REAL"] / 10, 2),
                        "out_time":  round(row["OUT_TIME_REAL"] / 10, 2),
                        "pt_diff":   int(row["PT_DIFF"]) if pd.notna(row["PT_DIFF"]) else None,
                    })
            return rows
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning(f"Game {game_id} attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)  # 2s, 4s backoff
    raise RuntimeError(f"All {retries} attempts failed for {game_id}")



def insert_rotation(rows: list[dict]):
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(text("""
          INSERT INTO game_rotations (game_id, team_id, person_id, in_time, out_time, pt_diff)
          VALUES (:game_id, :team_id, :person_id, :in_time, :out_time, :pt_diff)
      """), rows)

def main():
    game_ids = load_game_ids()
    logger.info(f"Found {len(game_ids):,} games to process")
    inserted = 0
    skipped = 0
    errors = 0

    for i, game_id in enumerate(game_ids, 1):
        if already_ingested(game_id):
            skipped += 1
            time.sleep(0.05)
            continue
        try:
            rows = fetch_rotation(game_id)
            insert_rotation(rows)
            inserted += 1
            if i % 500 == 0:
                logger.info(f"[{i}/{len(game_ids)}] inserted={inserted} skipped={skipped}")
            time.sleep(0.7)
        except Exception as e:
            logger.error(f"Game {game_id} failed: {e}")
            errors += 1

    logger.info(f"Done - {inserted} inserted, {skipped} skipped, {errors} errors")

if __name__ == "__main__":
    main()