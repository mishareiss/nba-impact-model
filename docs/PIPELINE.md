# Pipeline Architecture

## Overview

```
NBA Stats API
└── src/
    ├── ingestion/
    │   ├── fetch.py                # API calls, retries, backoff
    │   ├── transform.py            # Cleaning, column normalization
    │   └── load.py                 # Upsert to Postgres
    │
    ├── features/
    │   └── build_features.py       # Feature engineering
    │
    └── models/
        ├── train_xshot.py          # Model training
        └── predict.py              # Inference → shot_predictions table

Database
└── Postgres
    ├── play_by_play                # ~7.5M total rows, all event types
    ├── shots (materialized view)   # field goal attempts only (~2.68M)
    └── shot_predictions            # one xshot value per field goal attempt

Data Artifacts
└── data/
    └── shots_features.parquet      # ML-ready dataset

Model
└── models/
    └── xshot_v1.pkl                # Trained model
```

## File Reference

### `src/ingestion/db.py`
Initializes SQLAlchemy engine. Reads `DB_URL` from `.env`. Configured with connection pooling (`pool_size=5`, `max_overflow=10`, `pool_recycle=3600`, `pool_pre_ping=True`).

### `src/ingestion/schema.py`
Single source of truth for database schema. Defines:
- `play_by_play` table - all raw PBP columns
- `ingestion_log` table - checkpointing per game_id
- `INGEST_COLS` - dynamically derived from `play_by_play` columns (excludes `id`, `ingested_at`)

**Why dynamic `INGEST_COLS`:** Prevents schema drift bugs where manually-maintained column lists fall out of sync with the actual table definition. Any column added to `schema.py` is automatically included in `transform.py`.

### `src/ingestion/fetch.py`
Calls `PlayByPlayV3` endpoint via `nba_api`. Implements:
- 3 retries with true exponential backoff (1s → 2s → 4s)
- Empty DataFrame detection (some games have no API data)
- Re-raises `KeyboardInterrupt` so Ctrl+C works cleanly

### `src/ingestion/transform.py`
Cleans and normalizes raw API output:
- Converts camelCase column names to snake case via `_to_snake()`
- Fixes literal "NaN" strings in `sub_type`, `action_type`, `description` → `pd.NA`
- Coerces numeric columns
- Adds `game_id`, `season`, `season_type` metadata columns
- Filters to `INGEST_COLS` to match DB schema

### `src/ingestion/load.py`
Handles database writes:
- `insert_rows()` - bulk upsert to `play_by_play` using `ON CONFLICT (game_id, event_id) DO NOTHING` (idempotent)
- `log_ingestion()` - writes/updates status in `ingestion_log`
- `is_already_ingested()` - checks `ingestion_log` before API call
- `refresh_shots_view()` - runs `REFRESH MATERIALIZED VIEW shots` after ingestion

### `src/ingestion/pipeline.py`
Orchestrates full ingestion:
- `ingest_season(season, season_type)` - fetches all game IDs for a season, ingests each
- `ingest_seasons()` - loops all seasons 2014-15 → 2025-26 (regular season + playoffs)
    - Which seasons are ingested is controled by `SEASONS`
- `ingest_game(game_id, season, season_type)` - single game retry utility
- Skips games already in `ingestion_log` with status `success`

### `src/features/build_features.py`
Loads the `shots` materialized view and engineers the ML features set:
- `parse_clock()` - converts ISO 8601 clock strings ("PT05M30.00S") to float seconds
- `shot_zone` - encoded as numeric category codes (not strings)
- `shot_angle` - computed from `x_legacy`, `y_legacy`
- `is_corner_three` - geometry-based flag for corner threes only
- Boolean shot type flags - derived via regex on `sub_type`
- `shot_type` categorical - derived via `np.select` on `sub_type` (vectorized)
- Saves to `data/shots_features.parquet` with metadata JSON sidecar

### `src/models/train_xshot.py`
Trains XGBoost binary classifier to predict `shot_made` (1 = made /0 = miss)
See `docs/XSHOT_MODEL.md` for full details.

### `src/models/predict/py`
Loads trained model and full feature parquet, runs inference on all 2.68M shots, and upserts results to the `shot_predictions` table.
- Validates all features present and no NaNs before inference
- Computes `xshot_points = xshot x shot_value`
- Upserts in batches of 10,000 rows using `ON CONFLICT (game_id, action_id) DO UPDATE`
- Logs per-season summary of mean xshot vs actual FG% for sanity checking

### `src/utils/logging.py`
Centralized logger factory. Call `get_logger(__name__)` in any module.

## Database Schema

### `play_by_play`
~Raw play-by-play events. ~7.5M total rows across all event types (shots, fouls, turnovers, substitutions, etc.).
Key columns: `game_id`, `event_id`, `period`, `clock`, `player_id`, `shot_distance`, `x_legacy`, `y_legacy`, `shot_zone_basic`, `shot_result`, `action_type`, `sub_type`, `season`, `season_type`.

### `ingestion_log`
One row per `game_id`. Columns: `game_id`, `season`, `season_type`, `status` (success/error/empty), `row_count`, `error_msg`, `inserted_at`.

### `shots` (materialized view)
Filtered to field goal attempts only (`action_type = 'Field Goal'`). Used as the source for feature engineering. Refresh with `REFRESH MATERIALIZED VIEW shots`.

### `shot_predictions`
One row per field goal attempt. Primary key: `(game_id, action_id)`.
Key columns: `person_id`, `team_id`, `season`, `season_type`, `xshot` (predicted make probability), `shot_made` (actual outcome), `shot_value` (2 or 3), `xshot_points` (xshot × shot_value).
Indexed on `season`, `person_id`, `team_id` for fast aggregation queries.
