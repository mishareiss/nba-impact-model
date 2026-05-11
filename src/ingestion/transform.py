import re
import json
import pandas as pd
from src.utils.logging import get_logger
from src.ingestion.schema import INGEST_COLS

logger = get_logger(__name__)

# Columns where empty string should become NULL
EMPTY_TO_NULL = [
    "player_name", "player_name_i", "team_tricode", 
    "shot_result", "description", "sub_type", 
    "location", "score_home", "score_away",
]

FLOAT_COLS = ["x_legacy", "y_legacy", "shot_distance"]
INT_COLS = [
    "team_id", "person_id", "action_id", 
    "action_number", "period", "shot_value", 
    "points_total",
]
BOOL_COLS = ["is_field_goal", "video_available"]

def _to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_to_snake(c) for c in df.columns]
    return df

def clean_columns(df: pd.DataFrame, game_id: str, season: str, season_type: str) -> pd.DataFrame:
    df = df.copy()

    # Stamp metadata
    df["game_id"]       = game_id
    df["season"]        = season
    df["season_type"]   = season_type

    # Fix "NaN" string values before any other processing
    for col in ["sub_type", "action_type", "description"]:
        if col in df.columns:
            df[col] = df[col].replace("NaN", pd.NA)

    # Normalize empty strings to NULL
    for col in EMPTY_TO_NULL:
        if col in df.columns:
            df[col] = df[col].replace("", pd.NA)

    # Coerce floats
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce nullable ints
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Coerce booleans
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].map({1: True, 0: False, "1": True, "0": False})

    # Ensure all schema columns exist, fill missing with None
    for col in INGEST_COLS:
        if col not in df.columns:
            df[col] = None

    # Validate output matches expected schema
    missing = set(INGEST_COLS) - set(df.columns)
    if missing:
        logger.warning(f"Columns in schema but missing from DataFrame: {missing}")

    return df[INGEST_COLS]