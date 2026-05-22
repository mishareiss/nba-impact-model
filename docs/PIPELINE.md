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
    |   ├── build_features.py       # Feature engineering
    │   └── build_stints.py         # Lineup stint construction from PBP subs
    │
    ├── models/
    │   ├── train_xshot.py          # xShot model training
    │   ├── predict.py              # xShot inference → shot_predictions table
    │   ├── train_xrapm.py          # Single-season RAPM + xRAPM
    │   └── train_xrapm_v2.py       # 3-year pooled RAPM with box-score prior
    │
    └── analysis/
        └── build_views.py          # team_shot_quality + player_career_stats mat. views

dashboard/
├── app.py                          # Home page — league overview
├── pages/
│   ├── 1_Leaderboards.py           # Single-season + pooled impact leaderboards
│   ├── 2_Player_Profile.py         # Career trend charts per player
│   └── 3_Team_Analytics.py         # Team shot quality + season-over-season trends
└── utils/
    ├── db.py                       # SQLAlchemy engine + cached query() helper
    └── queries.py                  # Pre-written SQL functions for each page

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
    ├── player_shot_quality (mat. view)     # shot quality analytics per player/season
    ├── lineup_stints                       # 421,849 stints across 15,370 games
    ├── player_impact_ratings               # single-season RAPM + xRAPM (v1)
    ├── player_impact_pooled                # 3-year pooled RAPM + prior (v2)
    ├── player_impact_leaderboard (mat. view) # unified leaderboard with names + box stats
    ├── team_shot_quality (mat. view)         # offensive + defensive xShot metrics per team/season
    └── player_career_stats (mat. view)       # xShot + RAPM + box score joined per player/season

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
Trains XGBoost binary classifier to predict `shot_made` (1 = made / 0 = miss).
See `docs/XSHOT_MODEL.md` for full details.

### `src/models/train_xrapm.py`
Single-season RAPM and xRAPM via ridge regression on `lineup_stints`.
- Builds sparse design matrix X (stints × players, +1 home / −1 away)
- Fits ridge twice: once on xShot target (`y_xshot`), once on actual points (`y_actual`)
- Stores both coefficients per player per season in `player_impact_ratings`
- λ = 30,000 · min 1,000 possessions · fit_intercept=False
- Idempotent: DELETE + INSERT per season/season_type on each run

### `src/models/train_xrapm_v2.py`
3-year rolling pooled RAPM with box-score prior.
- Pools stints across 3-season windows (e.g. 2022-23 → 2024-25), reducing single-season lineup collinearity
- Builds box-score prior γ per player from `player_season_stats` plus/minus:
  `γ = (plus_minus / min) × 48 × PRIOR_WEIGHT (0.12)`, then centered to mean 0
- Fits RAPM+prior via reparameterization: minimize `‖y − Xβ‖² + λ‖β − γ‖²`
  by fitting on residual `y_adj = y − Xγ`, then `β_final = γ + coef*`
- Stores xRAPM, RAPM, rapm_prior, prior_estimate per player per window in `player_impact_pooled`
- **v2 limitations:** prior scale varies by era (teams with different offensive pace/efficiency); no direct era normalization; single-season noise partially persists for role players on dominant teams

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

### `src/analysis/build_views.py`
Creates (or replaces) two analytics materialized views used by the dashboard and trend analysis:
- `build_team_shot_quality()` — creates `team_shot_quality`. Derives offensive stats directly from `shot_predictions` grouped by shooting team, and defensive stats by joining `shot_predictions` with `games` to identify the opposing (defending) team.
- `build_player_career_stats()` — creates `player_career_stats`. Joins `player_shot_quality`, `player_impact_ratings`, and `player_season_stats` into a single queryable table keyed on `(person_id, team_id, season, season_type)`.
- `refresh_analytics_views()` — refreshes both views plus `player_impact_leaderboard` after new data is ingested.

Run: `python -m src.analysis.build_views`

### `dashboard/app.py`
Streamlit multi-page app entry point. Home page displays league overview metrics (total games, shots, league avg xShot, FG%) and season counts. Launch with `streamlit run dashboard/app.py`.

### `dashboard/utils/db.py`
SQLAlchemy engine wrapper for the dashboard. Imports the shared engine from `src.ingestion.db` and wraps `pd.read_sql()` in `@st.cache_data(ttl=300)` so query results are cached for 5 minutes across Streamlit reruns.

### `dashboard/utils/queries.py`
Pre-written SQL helpers for each dashboard page:
- `get_single_season_leaderboard()` — v1 RAPM/xRAPM rankings from `player_career_stats`
- `get_pooled_leaderboard()` — v2 pooled leaderboard from `player_impact_leaderboard`
- `get_player_career()` / `get_player_pooled()` — per-player season trend data
- `get_team_shot_quality()` / `get_team_trend()` — team analytics queries

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

### `lineup_stints`
421,849 stints across 15,370 games (2014-15 → 2025-26, regular season + playoffs).
Each row is a contiguous period where both 5-player lineups were unchanged.
Key columns: `game_id`, `season`, `season_type`, `start_time`, `end_time`, `duration`,
`home_players` / `away_players` (integer arrays of 5 person_ids),
`home_points` / `away_points` / `net_points` (via score timeline),
`home_poss` / `away_poss` / `total_poss` (FGA + 0.44×FTA + TOV),
`home_xshot_pts` / `away_xshot_pts` (aggregated from `shot_predictions`).
Indexed on `game_id`, `(season, season_type)`.

### `player_impact_ratings`
Single-season RAPM and xRAPM. Primary key: `(person_id, season, season_type)`.
Key columns: `xrapm` (net xShot pts / 100 poss), `rapm` (net actual pts / 100 poss), `possessions`.
4,760 rows across 2014-15 → 2025-26. λ=30,000, min 1,000 poss.

### `player_impact_pooled`
3-year rolling pooled RAPM with box-score prior. Primary key: `(person_id, end_season, season_type)`.
Key columns: `xrapm`, `rapm`, `rapm_prior` (prior-adjusted), `prior_estimate` (γ), `possessions`, `window_seasons`.
4,914 rows across end seasons 2016-17 → 2025-26. λ=30,000, prior weight=0.12, min 2,000 poss.

### `player_impact_leaderboard` (materialized view)
Unified leaderboard joining both v1 and v2 ratings with player names, team tricodes, and season box score stats.
Key columns: `full_name`, `team`, `season`, `season_type`, `rating_type` (single / pooled_3yr),
`xrapm`, `rapm`, `rapm_minus_xrapm`, `rapm_prior`, `possessions`, `gp`, `min`, `pts`, `season_plus_minus`.
Indexed on `(season, season_type)`, `full_name`, `rapm_prior DESC`, `(rating_type, season, season_type)`.
Refresh with `REFRESH MATERIALIZED VIEW player_impact_leaderboard`.

### `team_shot_quality` (materialized view)
Offensive and defensive shot quality analytics per team per season. Created by `src/analysis/build_views.py`.
One row per `(team_id, season, season_type)`.

**Offensive columns** (shots taken by the team):
`fga`, `fgm`, `fg_pct`, `mean_xshot_off`, `actual_pts_off`, `expected_pts_off`, `pts_above_expected_off`

**Defensive columns** (shots allowed against the team — defending team identified via `games` table):
`fga_allowed`, `fgm_allowed`, `fg_pct_allowed`, `mean_xshot_def`, `actual_pts_allowed`, `expected_pts_allowed`, `pts_above_expected_def`

Also includes `team` (tricode) and `team_name` from the `teams` lookup.
Indexed on `(season, season_type)` and `team`.
Refresh with `REFRESH MATERIALIZED VIEW team_shot_quality`.

### `player_career_stats` (materialized view)
Cross-season player summary joining all three analytics outputs into a single queryable table.
Created by `src/analysis/build_views.py`. One row per `(person_id, team_id, season, season_type)`.

**Shot quality** (from `player_shot_quality`): `shots_attempted`, `actual_fg_pct`, `mean_xshot`, `fg_pct_above_expected`, `shot_actual_pts`, `shot_expected_pts`, `shot_pts_above_expected`

**Impact ratings** (from `player_impact_ratings`, LEFT JOIN — NULL if < 1,000 poss): `xrapm`, `rapm`, `rapm_minus_xrapm`, `possessions`

**Box score** (from `player_season_stats`, LEFT JOIN): `gp`, `min`, `pts`, `reb`, `ast`, `stl`, `blk`, `tov`, `season_plus_minus`

Indexed on `(person_id, season_type)`, `full_name`, `(season, season_type)`.
Refresh with `REFRESH MATERIALIZED VIEW player_career_stats`.

