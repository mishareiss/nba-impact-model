# NBA Impact Model

An end-to-end NBA shot quality and player impact modeling system built on play-by-play data from the NBA Stats API (2014-15 through 2025-26).

## Goal

Build xShot (expected shot value) probabilities for every shot in the dataset, then use those probabilities to power:
- Shot quality above expectation (player + team)
- Stint-based impact modeling (xRAPM)
- Dashboard-ready analytics

## Tech Stack

- **Data source:** NBA Stats API via `nba_api`
- **Storage:** PostgreSQL (raw PBP) + materialized view (`shots`)
- **Feature store:** Parquet (`data/shots_features.parquet`)
- **Model:** XGBoost classifier
- **Language:** Python 3.11, SQLAlchemy, pandas, numpy

## Setup

1. Create conda environment: `conda env create -f environment.yml`
2. Activate: `conda activate nba-impact`
3. Add `.env` with: `DB_URL=postgresql://user:password@host/db`

## Running the Pipeline

```
# Ingest all seasons (2014-15 → 2025-26)
python -m src.ingestion.pipeline

# Ingest a single season
python -m src.ingestion.pipeline --season 2024-25 --season_type "Regular Season"

# Retry a specific game
python -m src.ingestion.pipeline --game_id 0021400001 --season 2024-25

# Build features
python src/features/build_features.py

# Train xShot model
python src/models/train_xshot.py
```

## Project Status

|**Step**|**Status**|
|----|------|
|PBP ingestion (2014-15 → 2025-26)|✅ Complete|
|`shots` materialized view|✅ Complete|
|Feature engineering|✅ Complete|
|xShot model v1 training|✅ Complete|
|xShot prediction generation|🔄 Next|
|Stint data + xRAPM|📋 Planned|
|Dashboard|📋 Planned|
