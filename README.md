# NBA Impact Model

A production-grade NBA analytics system that ingests, models, and surfaces play-by-play data to quantify **shot quality** and **player impact** independently of teammates and opponents.

Built on **2.68 million field goal attempts across 12 seasons** (2014-15 through 2025-26), the system produces per-shot expected value estimates (xShot) that power a full basketball analytics dashboard.

## Live Dashboard

8 pages accessible at `localhost:8501` when running locally:

| Page | What it shows |
|------|--------------|
| **Home** | System overview, KPI summary, pipeline architecture |
| **Leaderboards** | xRAPM, RAPM, O/D splits, xShot overperformance — ranked with percentiles, filterable by team and position |
| **Player Profile** | Shot charts, percentile profile, season trends, analyst interpretation |
| **Lineup Evaluation** | Actual vs expected net rating for 5-player units |
| **Decision Support** | Buy-low / sell-high / hidden contributor / breakout candidate categories |
| **Daily Stat Challenge** | Guess the Top 5 for today's stat category — Wordle-style, new puzzle every day |
| **Methodology** | xShot model docs, RAPM/xRAPM design, calibration, feature importance, limitations |
| **Glossary** | Definitions for all model terms and metrics |

## Screenshots

![Home](dashboard-screenshots/home.png)

![Leaderboards](dashboard-screenshots/leaderboards.png)

![Player Profile](dashboard-screenshots/player-profile.png)

![Lineup Evaluation](dashboard-screenshots/lineup-evaluation.png)

![Decision Support](dashboard-screenshots/decision-support.png)

![Daily Stat Challenge](dashboard-screenshots/daily-stat-challenge.png)

![Methodology](dashboard-screenshots/methodology.png)

![Glossary](dashboard-screenshots/glossary.png)

## What It Measures

### xShot
The probability that a given field goal attempt is made, based solely on pre-shot observable context: shot location, shot type (dunk, layup, pull-up, etc.), and game context (clock, period, playoffs). Analogous to expected goals (xG) in soccer analytics. **The model does not know who is shooting** — it measures shot difficulty, not shooter quality.

**Model**: XGBoost binary classifier, 30 features, trained on 2014-15→2022-23, tested on 466k held-out shots from 2023-24→2024-25. Achieves **7.7% log-loss reduction** over a mean-FG% naive baseline.

### RAPM / xRAPM
Ridge regression over 421,849 lineup stints, estimating each player's marginal impact on team scoring margin per 100 possessions while controlling for all teammates and opponents.

- **RAPM** — actual net scoring margin (includes shot-making variance and luck)
- **xRAPM** — xShot-derived expected scoring margin (removes variance, measures process)
- **RAPM − xRAPM** — the process gap: positive = outscoring process (may regress), negative = underscoring process (may improve)
- **O-RAPM / D-RAPM** — offensive and defensive decomposition via doubled design matrix

## Architecture

```
NBA Stats API (nba_api)
        ↓
  PostgreSQL DB
    play_by_play (7.5M events)
    player_season_stats
    games, players, teams
        ↓
  Feature Engineering
    30 shot features (spatial, shot-type, context)
        ↓
  XGBoost xShot Model
    P(make) per field goal attempt
    → shot_predictions (2.68M rows)
        ↓
  Stint Construction
    5v5 possession segments
    → lineup_stints (421,849 stints)
        ↓
  RAPM / xRAPM (Ridge Regression)
    v1: single-season, λ=30k
    v2: 3-year pooled + box-score prior
    → player_impact_leaderboard
        ↓
  Materialized Views
    player_career_stats
    player_shot_zones
    team_shot_quality
        ↓
  Streamlit Dashboard (8 pages)
```

## Key Results

| Metric | Value |
|--------|-------|
| xShot log-loss reduction | **7.7%** over naive baseline |
| Test shots | 466,000 (2023-24 → 2024-25) |
| xRAPM year-over-year R² | Consistently exceeds RAPM R² |
| Pooled estimate noise | ~40% lower std vs single-season |
| Lineup stints processed | 421,849 across 15,370 games |
| Seasons covered | 12 (2014-15 → 2025-26, Regular Season + Playoffs) |

## Project Structure

```
nba-impact-model/
├── dashboard/               # Streamlit application
│   ├── Home.py              # Dashboard home page
│   ├── pages/               # 8 pages (Leaderboards → Glossary)
│   └── utils/               # db, queries, shot_queries, viz, theme, court
├── src/
│   ├── ingestion/           # Data pipeline: NBA API → PostgreSQL
│   │   ├── pipeline.py      # End-to-end runner (--season, --season_type flags)
│   │   ├── fetch.py         # API calls with retry/backoff
│   │   ├── load.py          # Play-by-play upsert
│   │   ├── load_player_stats.py  # Traditional stats + position data
│   │   └── schema.py        # SQLAlchemy table definitions
│   ├── features/
│   │   ├── build_features.py  # 30-feature engineering for xShot
│   │   ├── build_stints.py    # Lineup stint construction
│   │   └── build_views.py     # Materialized view refresh
│   ├── models/
│   │   ├── train_xshot.py     # XGBoost xShot model
│   │   ├── predict.py         # xShot inference on all FGA
│   │   ├── train_xrapm.py     # Single-season RAPM/xRAPM
│   │   └── train_xrapm_v2.py  # Pooled + prior RAPM (v2)
│   └── analysis/
│       └── build_views.py     # team_shot_quality + player_career_stats views
├── models/                  # Trained model artifacts + metadata
│   ├── xshot_v1.pkl         # XGBoost model (pickle)
│   ├── xshot_v1_metadata.json
│   ├── feature_importance.json
│   └── calibration_data.json
├── tests/                   # pytest test suite
│   ├── test_queries.py      # DB query schema + filter tests
│   ├── test_game_logic.py   # Game seed stability, position mapping
│   └── test_model.py        # Model artifact load + prediction range
├── docs/
│   ├── PIPELINE.md          # Full pipeline documentation
│   ├── XSHOT_MODEL.md       # xShot model design and evaluation
│   └── RAPM_MODEL.md        # RAPM/xRAPM model design
├── dashboard-screenshots/   # Dashboard page screenshots
├── .env.example             # Environment variable template
├── environment.yml          # Conda environment definition
└── requirements.txt         # pip dependencies
```

## Setup

```bash
# Clone and set up environment
git clone https://github.com/mishareiss/nba-impact-model.git
cd nba-impact-model
conda env create -f environment.yml
conda activate nba-impact

# Configure database
cp .env.example .env
# Edit .env: set DATABASE_URL=postgresql://user:pass@localhost/nba

# Run full pipeline
python -m src.ingestion.pipeline                    # Ingest play-by-play (all seasons)
python -m src.ingestion.load_player_stats           # Traditional stats + position
python -m src.features.build_features               # Feature engineering
python -m src.models.train_xshot                    # Train xShot model
python -m src.models.predict                        # Run inference on all FGA
python -m src.features.build_stints                 # Construct lineup stints
python -m src.models.train_xrapm                    # Single-season RAPM/xRAPM
python -m src.models.train_xrapm_v2                 # Pooled RAPM (v2)
python -m src.features.build_views                  # Refresh materialized views

# Launch dashboard
streamlit run dashboard/Home.py

# Run tests
pytest tests/
```

## Tests

```bash
pytest tests/ -v
```

The test suite covers:
- SQL query functions (column schema, filter correctness, row count sanity)
- Game logic (seed stability, position mapping, stat category structure)
- Model artifact (loads without error, predictions in valid probability range)

## Resume Bullets

- Engineered an end-to-end NBA analytics platform ingesting 7.5M play-by-play events via NBA Stats API and storing in PostgreSQL, supporting 12 seasons of shot predictions and player impact ratings
- Trained an XGBoost shot quality model (xShot) on 2.68M field goal attempts with 30 spatial and contextual features, achieving 7.7% log-loss reduction over a naive baseline on a 466k-shot holdout
- Built RAPM and xRAPM player impact models via Ridge regression over 421,849 5v5 lineup stints, demonstrating that process-based xRAPM has higher year-over-year R² than outcome-based RAPM
- Developed an 8-page Streamlit analytics dashboard with interactive shot charts, percentile profiles, lineup evaluation (actual vs expected net rating), automated player categorisation (buy-low/sell-high), and a daily stat challenge mini-game
- Implemented a pooled 3-year RAPM model anchored to a box-score prior, reducing single-season estimation noise by ~40% via Bayesian shrinkage toward historical per-minute baselines

## Tech Stack

Python · PostgreSQL · SQLAlchemy · XGBoost · scikit-learn · Streamlit · Plotly · pandas · NumPy · SciPy · nba_api
