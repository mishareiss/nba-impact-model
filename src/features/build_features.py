import numpy as np
import pandas as pd
import re
import json
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def load_shots() -> pd.DataFrame:
    query = """
        SELECT
            game_id, action_id, season,
            season_type, period, clock,
            person_id, player_name, team_id,
            team_tricode, sub_type,
            shot_distance, shot_angle, shot_zone,
            is_corner_three, shot_value, x_legacy,
            y_legacy, made
        FROM shots
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    logger.info(f"Loaded {len(df):,} shots from DB")
    return df

def parse_clock(clock_str) -> float | None:
    if not clock_str:
        return None
    m = re.match(r'PT(\d+)M([\d.]+)S', str(clock_str))
    if not m:
        return None
    return int(m.group(1)) * 60 + float(m.group(2))

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # clock
    df['clock_seconds'] = df['clock'].apply(parse_clock)

    # handle "NaN" string values - treat as null
    df['sub_type'] = df['sub_type'].replace('NaN', pd.NA)

    # shot_zone encoding - must be numeric for XGBoost
    df['shot_zone'] = df['shot_zone'].astype('category')
    zone_codes = dict(enumerate(df['shot_zone'].cat.categories))
    logger.info(f"shot_zone categories: ({len(zone_codes)}: {zone_codes})")
    df['shot_zone'] = df['shot_zone'].cat.codes # -w if NaN, otherwise 0-indexed int

    # Vectorized shot type classification using np.select
    s = df['sub_type'].str.lower().fillna('')
    conditions = [
        s.str.contains('alley',         regex=False),
        s.str.contains('cutting',       regex=False),
        s.str.contains('putback',       regex=False),
        s.str.contains('tip',           regex=False),
        s.str.contains('dunk',          regex=False),
        s.str.contains('slam',          regex=False),
        s.str.contains('finger',        regex=False),
        s.str.contains('layup',         regex=False),
        s.str.contains('float',         regex=False),
        s.str.contains('hook',          regex=False),
        s.str.contains('step',          regex=False),
        s.str.contains('fade',          regex=False),
        s.str.contains('turnaround',    regex=False),
        s.str.contains('pull',          regex=False),
    ]
    choices = [
        'alley_oop', 'cutting', 'putback', 
        'tip', 'dunk', 'dunk', 
        'finger_roll', 'layup', 'floater', 
        'hook', 'stepback', 'fadeaway', 
        'turnaround', 'pullup',
    ]
    df['shot_type'] = np.select(conditions, choices, default='jump_shot')
    # Replace empty sub_type (unknown) with 'unknown'
    df.loc[df['sub_type'].isna(), 'shot_type'] = 'unknown'

    # Boolean flags from sub_type
    df['is_dunk']        = s.str.contains('dunk|slam',    regex=True)
    df['is_layup']       = s.str.contains('layup',        regex=False)
    df['is_alley_oop']   = s.str.contains('alley',        regex=False)
    df['is_cutting']     = s.str.contains('cutting',      regex=False)
    df['is_putback']     = s.str.contains('putback',      regex=False)
    df['is_tip']         = s.str.contains('tip',          regex=False)
    df['is_finger_roll'] = s.str.contains('finger',       regex=False)
    df['is_driving']     = s.str.contains('driv',         regex=False)
    df['is_running']     = s.str.contains('running',      regex=False)
    df['is_pullup']      = s.str.contains('pull',         regex=False)
    df['is_stepback']    = s.str.contains('step',         regex=False)
    df['is_fadeaway']    = s.str.contains('fade',         regex=False)
    df['is_hook']        = s.str.contains('hook',         regex=False)
    df['is_floating']    = s.str.contains('float',        regex=False)
    df['is_turnaround']  = s.str.contains('turnaround',   regex=False)
    df['is_reverse']     = s.str.contains('reverse',      regex=False)
    df['is_bank']        = s.str.contains('bank',         regex=False)

    # coordinate-based flags
    # paint: 16ft wide (x: -80 to 80), extends to free throw line (~15ft = 150 units)
    df['is_paint'] = (
        (df['x_legacy'].abs() <= 80) &
        (df['y_legacy'] >= -52.5) &
        (df['y_legacy'] <= 137.5)
    )

    # game context
    df['is_overtime']   = df['period'] > 4
    df['is_playoffs']   = df['season_type'] == 'Playoffs'
    df['is_three']      = df['shot_value'] == 3

    return df

ID_COLS = [
    'game_id', 'action_id', 'season', 
    'person_id', 'player_name', 'team_tricode', 
    'shot_type'
]

FEATURES = [
    # spatial
    'shot_distance', 'shot_angle', 'x_legacy', 'y_legacy',
    'shot_zone', 'is_corner_three', 'is_paint',
    # shot value
    'shot_value', 'is_three',
    # shot mechanics
    'is_dunk', 'is_layup', 'is_alley_oop', 'is_cutting',
    'is_putback', 'is_tip', 'is_finger_roll', 'is_driving',
    'is_running', 'is_pullup', 'is_stepback',
    'is_fadeaway', 'is_hook', 'is_floating', 'is_turnaround',
    'is_reverse', 'is_bank',
    # game context
    'period', 'clock_seconds', 'is_overtime', 'is_playoffs',
]

LABEL = 'made'

def main():
    print("Loading shots from DB...")
    df = load_shots()
    print(f"    Loaded {len(df):,} shots")

    print("Engineering features...")
    df = build_features(df)

    # Drop rows missing critical features
    before = len(df)
    critical = ['shot_distance', 'x_legacy', 'y_legacy', 'clock_seconds']
    df = df.dropna(subset=critical)
    dropped = before - len(df)
    if dropped > 0:
        logger.warning(f"Dropped {dropped:,} rows with missing critical features")
    logger.info(f"Final dataset: {len(df):,} shots")

    # Select final columns
    out = df[ID_COLS + FEATURES + [LABEL]]

    # Validate - no NaNs allowes in features going to model
    null_counts = out[FEATURES].isnull().sum()
    nulls_present = null_counts[null_counts > 0]
    if len(nulls_present) > 0:
        logger.error(f"NaNs found in features - model training will fail:\n{nulls_present}")
        raise ValueError("Feature matrix contains NaN values. Fix before training.")
    logger.info("Validation passed - no Nans in feature matrix")

    # Save parquet
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "shots_features.parquet"
    out.to_parquet(out_path, index=False)

    # Save metadata
    seasons = sorted(out['season'].unique().tolist())
    metadata = {
        "built_at":         datetime.now(timezone.utc).isoformat(),
        "row_count":        len(out),
        "seasons":          seasons,
        "seasons_count":    len(seasons),
        "feature_count":    len(FEATURES),
        "label":            LABEL,
        "label_rate":       round(float(out[LABEL].mean()), 4),
    }

    meta_path = DATA_DIR / "shots_features_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Saved {len(out):,} rows to {out_path}")
    logger.info(f"Metadata saved to {meta_path}")
    logger.info(f"Label rate (FG%): {metadata['label_rate']}")
    logger.info(f"Seasons: {seasons[0]} → {seasons[-1]}")

    # Summary
    logger.info("\nShot type distribution:")
    for shot_type, count in out['shot_type'].value_counts().items():
        logger.info(f"  {shot_type:15s} {count:>8,}")
        
if __name__ == "__main__":
    main()