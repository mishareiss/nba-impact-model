from src.ingestion.db import engine
from src.ingestion.schema import play_by_play as schema_table
from sqlalchemy import inspect
insp = inspect(engine)
print("=== TABLES IN DB ===")
print(insp.get_table_names())
print("\n=== play_by_play COLUMNS IN DB ===")
db_cols = {c["name"]: c for c in insp.get_columns("play_by_play")}
for name, info in db_cols.items():
  print(f"  {name:25s} {str(info['type']):20s} nullable={info['nullable']}")
print("\n=== COLUMNS IN schema.py ===")
schema_cols = {c.name: c for c in schema_table.columns}
for name, col in schema_cols.items():
  print(f"  {name:25s} {str(col.type):20s} nullable={col.nullable}")
print("\n=== DIFF ===")
db_names = set(db_cols.keys())
schema_names = set(schema_cols.keys())
only_in_db = db_names - schema_names
only_in_schema = schema_names - db_names
if only_in_db:
  print(f"  In DB but NOT in schema.py: {only_in_db}")
if only_in_schema:
  print(f"  In schema.py but NOT in DB: {only_in_schema}")
if not only_in_db and not only_in_schema:
  print("  Column names match!")
print("\n=== UNIQUE CONSTRAINTS IN DB ===")
print(insp.get_unique_constraints("play_by_play"))
print("\n=== INDEXES IN DB ===")
print(insp.get_indexes("play_by_play"))