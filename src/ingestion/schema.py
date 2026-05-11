from sqlalchemy import (
    MetaData, Table, Column, 
    Text, Integer, Float, BigInteger, 
    Boolean, SmallInteger, 
    DateTime, UniqueConstraint, Index, text
)

metadata = MetaData()


play_by_play = Table(
  "play_by_play", metadata,
  Column("id",              Integer,     primary_key=True, autoincrement=True),
  Column("game_id",         Text,        nullable=False),
  Column("action_id",       Integer,     nullable=False),
  Column("action_number",   Integer),
  Column("period",          SmallInteger),
  Column("clock",           Text),           # store raw, parse downstream
  Column("team_id",         BigInteger),
  Column("team_tricode",    Text),
  Column("person_id",       BigInteger),
  Column("player_name",     Text),
  Column("player_name_i",   Text),
  Column("action_type",     Text),
  Column("sub_type",        Text),
  Column("description",     Text),
  Column("is_field_goal",   Boolean),
  Column("shot_result",     Text),          # "Made Shot" / "Missed Shot" / NULL
  Column("shot_value",      SmallInteger),  # 2 or 3
  Column("shot_distance",   Float),
  Column("x_legacy",        Float),
  Column("y_legacy",        Float),
  Column("points_total",    SmallInteger),
  Column("score_home",      Text),          # "85" — parse downstream
  Column("score_away",      Text),
  Column("location",        Text),
  Column("video_available", Boolean),
  Column("order_number",    Integer),
  Column("qualifiers",      Text),
  Column("season",          Text),
  Column("season_type",     Text),
  Column("ingested_at", DateTime(timezone=True), server_default=text("NOW()")),

  UniqueConstraint("game_id", "action_id", name="uq_game_action"),
  Index("ix_pbp_game_id",    "game_id"),
  Index("ix_pbp_action_type","action_type"),
  Index("ix_pbp_person_id",  "person_id"),
)

ingestion_log = Table(
    "ingestion_log", metadata,
    Column("game_id",       Text, primary_key=True),
    Column("season",        Text),
    Column("season_type",   Text),
    Column("status",        Text, nullable=False),
    Column("row_count",     Integer),
    Column("error_msg",     Text),
    Column("inserted_at", DateTime(timezone=True), server_default=text("NOW()")),
)

INGEST_COLS = [
    c.name for c in play_by_play.columns
    if c.name not in ("id", "ingested_at")
]