# NBA Impact Model

A production-grade NBA analytics system that ingests, models, and surfaces play-by-play data to quantify **shot quality** and **player impact** independently of teammates and opponents.

Built on 2.68 million field goal attempts across 12 seasons (2014-15 through 2025-26), the system produces per-shot expected value estimates (xShot) that power downstream player evaluation and impact modeling.

## What This Project Includes

This project combines NBA data engineering, machine learning, and player analytics into a single end-to-end system.

At a high level, it:

- Collects and stores historical NBA play-by-play data across multiple seasons
- Reconstructs and analyzes every field goal attempt in the dataset
- Estimates shot difficulty using machine learning (`xShot`)
- Measures which players consistently make harder shots than expected
- Builds player impact models that account for teammate and opponent context
- Produces queryable analytics outputs for downstream dashboards, visualizations, and research

## What It Measures

**xShot** - The probability that a given field goal attempt is made, based solely on pre-shot information: shot location, shot type, and game context. Analagous to expected goals (xG) in soccer analytics.

From xShot, the system produces:

**Shot-Making Over Expected (SMOE)** - Measures how much a player outperforms or underperforms the expected value of their shot attempts based on shot quality. This isolates shot-making ability from raw scoring volume and shot selection. Players who rank highly consistently convert difficult attempts at above-expected rates while reliably finishing efficient opportunities. 2025-26 regular season leaders include elite scorers and shot creators such as Nikola Jokic, Kevin Durant, Shai Gilgeous-Alexander, Stephen Curry, Kawhi Leonard, and Jamal Murray, suggesting the model captures meaningful shooting talent and difficult shot-making ability.

**Player Impact / xRAPM** - *(In development)* Regularized adjusted plus-minus model estimating a player’s marginal impact on team scoring efficiency per 100 possessions. Uses ridge regression over lineup stint data to control for teammate and opponent strength while reducing multicollinearity and noise inherent in raw plus-minus metrics.

## Why This Matters

Raw box score statistics and even traditional plus-minus metrics are heavily influenced by context and short-term variance. Team scheme, lineup quality, role, shot variance, and opponent strength all affect observed outcomes, making it difficult to isolate underlying player impact.

This project focuses on process-based, context-adjusted evaluation:

- **xShot** estimates the probability a shot is made given its difficulty and context. Comparing actual results against expected results helps separate shot-making skill from shot selection, role, and shooting variance.

- **xRAPM** extends traditional regularized adjusted plus-minus by incorporating expected shot quality into possession-level evaluation. Instead of relying purely on made and missed shots, the model emphasizes the quality of opportunities created and allowed while still controlling for teammates and opponents on the floor.

The underlying assumption is that process tends to be more stable and predictive than short-term results alone. Together, these models aim to provide a more reliable estimate of individual player impact and sustainable performance.

## Engineering Design
- **Idempotent ingestion** - Every game can be re-fetched and re-inserted safely. `ingestion_log` checkpointing skips previous successsfully inserted games, enabling partial restarts without  duplicate data.
- **Temporal model validation** - Train/test split is strictly chronological (train: 2014-15 → 2022-23, test: 2023-24 + 2024-25). No future data leaks into training.
- **Calibrated probabilities** - XGBoost outputs validated against actual FG% across all 12 seasons (regular season + playoffs). Max deviation <2.5% per season, no systematic bias. Platt scaling not needed.
- **Queryable analytics layer** - All outputs live in Postgres, directly accessible to dashboards and downstream models without re-running Python.
- **Schema-driven transforms** - Column lists are derived dynamically from SQLAlchemy schema definitions, preventing schema drift bugs.

## Tech Stack

- **Data source:** NBA Stats API via `nba_api` (play-by-play, player/team box scores, metadata)
- **Storage:** PostgreSQL -raw PBP events, reference tables, materialized views
- **Machine Learning** XGBoost binary classifier, schikit-learn evaluation, joblib persistence
- **Feature store:** Parquet (`data/shots_features.parquet`) with JSON metadata sidecar
- **Orchestration:** Python 3.11, SQLAlchemy, pandas, numpy
- **Environment:** Conda (`environment.yml`)

## Setup

1. Create conda environment: `conda env create -f environment.yml`
2. Activate: `conda activate nba-impact`
3. Add `.env` with: `DB_URL=postgresql://user:password@host/db`
4. Create Postgres tables - see `docs/PIPELINE.md` for schema SQL

## Running the Pipeline

```
# 1. Ingest play-by-play (2014-15 → 2025-26, ~7.5M events)
python -m src.ingestion.pipeline

# Ingest a single season
python -m src.ingestion.pipeline --season 2024-25 --season_type "Regular Season"

# Retry a specific game by ID
python -m src.ingestion.pipeline --game_id 0021400001 --season 2024-25

2. Load reference tables (run once, re-run at start of each new season)
python -m src.ingestion.load_players
python -m src.ingestion.load_teams
python -m src.ingestion.load_player_stats
python -m src.ingestion.load_team_stats

# 3. Build ML feature dataset
python src/features/build_features.py

# 4. Train xShot model
python src/models/train_xshot.py

# 5. Generate xShot predictions → writes to shot_predictions table
python src/models/predict.py

# 6. Build lineup stints
python -m src.features.build_stints
```

## Project Status

|**Step**|**Status**|**Notes**|
|----|------|----------|
|PBP ingestion (2014-15 → 2025-26)|✅ Complete|~7.5M events, idempotent with checkpointing|
|`shots` materialized view|✅ Complete|2.68M field goal attempts|
|Reference tables (players, teams, box scores)|✅ Complete|All seasons 2014-15 → 2025-26, regular season + playoffs|
|Feature engineering|✅ Complete|30 features, parquet with metadata sidecar|
|xShot model v1 training|✅ Complete|XGBoost, 7.7% log loss reduction, calibrated|
|xShot prediction generation|✅ Complete|2.68M shots scored, stored in Postgres|
|Player shot quality analytics|✅ Complete|Validated - elite players rank as expected|
|Stint data construction|✅ Complete|Parse substitution events → lineup stints|
|Stint-level xShot aggregation|✅ Complete|Aggregate predictions to each lineup stint|
|xRAPM model|🔄 Next|Ridge regression on stint data|
|Queryable player impact ratings|📋 Planned|Postgres table, all seasons|
|Team shot quality analytics|📋 Planned|`team_shot_quality` materialized view|
|Season-over-season trend analysis|📋 Planned|Historical player/team comparisons|
|Interactive dashboard|📋 Planned|Player search, leaderboards, shot charts|
|Automated pipeline refresh|📋 Planned|New season ingestion + view refresh|


