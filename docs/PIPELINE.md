# Pipeline Architecture

## Overview

```
NBA Stats API
└── src/
    ├── ingestion/
    │   ├── fetch.py                # API calls, retries, backoff
    │   ├── transform.py            # Cleaning, column normalization
    │   ├── load.py                 # Upsert to Postgres
    |   ├── load_players.py         # `players` table
    |   ├── load_teams.py           # `teams` table
    |   ├── load_player_stats.py    # `player_season_stats` table
    |   └── load_team_stats.py      # `team_season_stats` table
    │
    ├── features/
    │   └── build_features.py       # Feature engineering
    │
    └── models/
        ├── train_xshot.py          # Model training
        └── predict.py              # Inference → shot_predictions table

Database
└── Postgres
    ├── play_by_play                        # ~7.5M total rows, all event types
    ├── ingestion_log                       # per-game ingestion status
    ├── shots (mat. view)                   # field goal attempts only (~2.68M)
    ├── shot_predictions                    # one xshot value per field goal attempt
    ├── players                             # player ID → full name lookup
    ├── teams                               # team ID → tricode, full name
    ├── player_season_stats                 # box score totals per player/team/season
    ├── team_season_stats                   # box score totals per team/season
    └── player_shot_quality (mat. view)     # materialized view - shot quality analytics

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
    - Which seasons are ingested is controlled by `SEASONS`
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

### `src/models/predict.py`
Loads trained model and full feature parquet, runs inference on all 2.68M shots, and upserts results to the `shot_predictions` table.
- Validates all features present and no NaNs before inference
- Computes `xshot_points = xshot x shot_value`
- Upserts in batches of 10,000 rows using `ON CONFLICT (game_id, action_id) DO UPDATE`
- Logs per-season summary of mean xshot vs actual FG% for sanity checking

### `src/utils/logging.py`
Centralized logger factory. Call `get_logger(__name__)` in any module.

### `src/ingestion/load_players.py`
Populates the `players` table using `nba_api.stats.static.players` - a local static file, no API call required. Returns every player in NBA history with first name, last name, and full name. Upsers on `person_id`.

### `src/ingestion/load_teams.py`
Populates the `teams` table using `nba_api.stats.static.teams` - a local static file, no API call required. Returns all 30 current NBA teams with tricode, full name, city, and nickname. Upserts on `team_id`.

### `src/ingestion/load_player_stats.py`
Fetches full box score season totals for all players via `LeagueDashPlayerStats`. Loops all 12 seasons × 2 season types = 24 API calls (~30 seconds). Stores GP, MIN, PTS, REB, AST, STL, BLK, TOV, FGM, FGA, FG%, 3PM, 3PA, 3P%, FTM, FTA, FT%, OREB, DREB, PF, +/-. Traded players get one row per team.

### `src/ingestion/load_team_stats.py`
Same as `load_player_stats.py` but for teams via `LeagueDashTeamStats`. One per row per team per season per season type (regular season/playoffs). Primary key: `(team_id, season, season_type)`.

## Database Schema

### `play_by_play`
Raw play-by-play events. ~7.5M total rows across all event types (shots, fouls, turnovers, substitutions, etc.).
Key columns: `game_id`, `event_id`, `period`, `clock`, `player_id`, `shot_distance`, `x_legacy`, `y_legacy`, `shot_zone_basic`, `shot_result`, `action_type`, `sub_type`, `season`, `season_type`.

### `ingestion_log`
One row per `game_id`. Columns: `game_id`, `season`, `season_type`, `status` (success/error/empty), `row_count`, `error_msg`, `inserted_at`.

### `shots` (materialized view)
Filtered to field goal attempts only (`action_type = 'Field Goal'`). Used as the source for feature engineering. Refresh with `REFRESH MATERIALIZED VIEW shots`.

### `shot_predictions`
One row per field goal attempt. Primary key: `(game_id, action_id)`.
Key columns: `person_id`, `team_id`, `season`, `season_type`, `xshot` (predicted make probability), `shot_made` (actual outcome), `shot_value` (2 or 3), `xshot_points` (xshot × shot_value).
Indexed on `season`, `person_id`, `team_id` for fast aggregation queries.

### `players`
Static lookup table. One row per player in NBA history. Columns: `person_id` (PK), `first_name`, `last_name`, `full_name`. Source: `nba_api.stats.static.players`.

### `teams`
Static lookup table. One row per NBA team. Columns: `team_id` (PK), `tricode`, `full_name`, `city`, `nickname`. Source: `nba_api.stats.static.teams`.

### `player_season_stats`
ull box score season totals per player per team per season. Primary key: `(person_id, team_id, season, season_type)`. Traded players appear as multiple rows. Columns include GP, MIN, PTS, REB, AST, STL, BLK, TOV, FGM/FGA/FG%, FG3M/FG3A/FG3%, FTM/FTA/FT%, OREB, DREB, PF, plus_minus.

### `team_season_stats`
Full box score season totals per team per season. Primary key: `(team_id, season, season_type)`. Same columns as `player_season_stats` minus `person_id`.

### `player_shot_quality` (materialized view)
Shot quality analytics per player per team per season. Primary key: `(person_id, team_id, season, season_type)`. Key columns: `player_name`, `team_tricode`, `gp`, `min`, `shots_attempted`, `actual_fg_pct`, `mean_xshot`, `fg_pct_above_expected`, `actual_points`, `expected_points`, `points_above_expected`. Indexed on `(season, season_type)`, `player_name`. Refresh with `REFRESH MATERIALIZED VIEW player_shot_quality`.


