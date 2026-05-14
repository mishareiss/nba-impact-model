import joblib
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import Table, Column, Text, Integer, Float, SmallInteger, TIMESTAMP, MetaData, text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

DATA_DIR    = Path(__file__).resolve().parent.parent.parent / "data"
MODELS_DIR  = Path(__file__).resolve().parent.parent.parent / "models"

FEATURES = [
  'shot_distance', 'shot_angle', 'x_legacy', 'y_legacy',
  'shot_zone', 'is_corner_three', 'is_paint',
  'shot_value', 'is_three',
  'is_dunk', 'is_layup', 'is_alley_oop', 'is_cutting',
  'is_putback', 'is_tip', 'is_finger_roll', 'is_driving',
  'is_running', 'is_pullup', 'is_stepback',
  'is_fadeaway', 'is_hook', 'is_floating', 'is_turnaround',
  'is_reverse', 'is_bank',
  'period', 'clock_seconds', 'is_overtime', 'is_playoffs',
]

BATCH_SIZE = 10_000

metadata = MetaData()
shot_predictions = Table(
  "shot_predictions", metadata,
  Column("game_id",      Text,        nullable=False),
  Column("action_id",    Integer,     nullable=False),
  Column("person_id",    Integer),
  Column("team_id",      Integer),
  Column("season",       Text),
  Column("season_type",  Text),
  Column("xshot",        Float,       nullable=False),
  Column("shot_made",    SmallInteger, nullable=False),
  Column("shot_value",   SmallInteger, nullable=False),
  Column("xshot_points", Float,       nullable=False),
  Column("predicted_at", TIMESTAMP,   server_default=text("NOW()")),
)

def load_model():
    path = MODELS_DIR / "xshot_v1.pkl"
    model = joblib.load(path)
    logger.info(f"Loaded model from {path}")
    return model

def load_features() -> pd.DataFrame:
    path = DATA_DIR / "shots_features.parquet"
    df = pd.read_parquet(path)
    logger.info(f"Loaded {len(df):,} shots from parquet")
    return df

def validate(df: pd.DataFrame):
    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        raise ValueError(f"Missing features in parquet: {missing}")
    null_counts = df[FEATURES].isnull().sum()
    nulls = null_counts[null_counts > 0]
    if len(nulls) > 0:
        raise ValueError(f"NaNs found in features:\n{nulls}")
    logger.info("Validation passed")

def predict(model, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["xshot"] = model.predict_proba(df[FEATURES])[:, 1]
    df["xshot_points"] = df["xshot"] * df["shot_value"]
    df["shot_made"] = df["made"].astype(int)
    logger.info(f"Predictions generated - mean xshot: {df['xshot'].mean():.4f}")
    return df

def upsert_predictions(df: pd.DataFrame):
    rows = df[[
        "game_id", "action_id", "person_id", "team_id",
        "season", "season_type", "xshot", "shot_made",
        "shot_value", "xshot_points",
    ]].to_dict(orient="records")

    total = len(rows)
    written = 0

    with engine.begin() as conn:
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            stmt = pg_insert(shot_predictions).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["game_id", "action_id"],
                set_={
                    "xshot": stmt.excluded.xshot,
                    "xshot_points": stmt.excluded.xshot_points,
                    "predicted_at": text("NOW()"),
                },
            )
            conn.execute(stmt)
            written += len(batch)
            logger.info(f"Upserted {written:,} / {total:,} rows")

    logger.info(f"Done - {written:,} rows written to shot_predictions")

def log_summary(df: pd.DataFrame):
    logger.info(f"Summary by season and season_type:")
    summary = (
        df.groupby(["season", "season_type"])
        .agg(
            shots       = ("xshot", "count"),
            mean_xshot  = ("xshot", "mean"),
            actual_fg   = ("shot_made", "mean"),
        )
        .round(4)
    )
    for season, row in summary.iterrows():
        logger.info(
          f"  {season}  shots={row['shots']:>7,}  "
          f"xshot={row['mean_xshot']:.4f}  "
          f"actual={row['actual_fg']:.4f}"
      )

def main():
    model = load_model()
    df = load_features()
    validate(df)
    df = predict(model, df)
    upsert_predictions(df)
    log_summary(df)
    logger.info("predict.py complete.")

if __name__ == "__main__":
    main()