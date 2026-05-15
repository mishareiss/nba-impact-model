from nba_api.stats.static import players as nba_players
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Table, Column, Integer, Text, MetaData
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

metadata = MetaData()
players = Table(
    "players", metadata,
    Column("person_id", Integer, primary_key=True),
    Column("first_name", Text),
    Column("last_name", Text),
    Column("full_name", Text),
)

def load_players():
    all_players = nba_players.get_players()
    logger.info(f"Found {len(all_players):,} players")

    rows = [
        {
            "person_id": p["id"],
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "full_name": p["full_name"],
        }
        for p in all_players
    ]
   

    insert_stmt = pg_insert(players).values(rows)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["person_id"],
        set_={
            "first_name": insert_stmt.excluded.first_name,
            "last_name": insert_stmt.excluded.last_name,
            "full_name": insert_stmt.excluded.full_name,
        }
    )

    with engine.begin() as conn:
        conn.execute(stmt)

    logger.info(f"Upserted {len(rows):,} players to DB")

if __name__ == "__main__":
    load_players()