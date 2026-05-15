from nba_api.stats.static import teams as nba_teams
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Table, Column, Integer, Text, MetaData
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

metadata = MetaData()
teams =Table(
    "teams", metadata,
    Column("team_id",   Integer, primary_key=True),
    Column("tricode",   Text),
    Column("full_name", Text),
    Column("city",      Text),
    Column("nickname",  Text),
)

def load_teams():
    all_teams = nba_teams.get_teams()
    logger.info(f"Found {len(all_teams)} teams")

    rows = [
        {
            "team_id": t["id"],
            "tricode": t["abbreviation"],
            "full_name": t["full_name"],
            "city": t["city"],
            "nickname": t["nickname"],
        }
        for t in all_teams
    ]

    insert_stmt = pg_insert(teams).values(rows)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["team_id"],
        set_={
            "tricode": insert_stmt.excluded.tricode,
            "full_name": insert_stmt.excluded.full_name,
            "city": insert_stmt.excluded.city,
            "nickname": insert_stmt.excluded.nickname,
        },
    )

    with engine.begin() as conn:
        conn.execute(stmt)

    logger.info(f"Upserted {len(rows):,} teams")

if __name__ == "__main__":
    load_teams()