from ingestion.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1;"))
    print("Connection works:", result.fetchone())