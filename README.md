# NBA Shot Quality & Impact Model

### ▶ Live dashboard: **[mishareiss.github.io/nba-impact-model](https://mishareiss.github.io/nba-impact-model/)**

Which NBA players actually make their teams better, and who makes shots they "shouldn't"? This project scores the
difficulty of every NBA field-goal attempt since 2014-15 with an XGBoost model (**xShot**, think expected goals in soccer)
and compares each player's real shooting to it. Separately, it rates each player's impact on his team's scoring margin per
100 possessions with regularized adjusted plus-minus (**RAPM**) over 422K lineup stints. It is the whole pipeline end to
end: ingestion from the NBA Stats API into PostgreSQL, feature engineering, modeling, calibration, and a public dashboard.

[![Dashboard screenshot](docs/dashboard.png)](https://mishareiss.github.io/nba-impact-model/)

## Key results

| | |
|---|---|
| **Shots modeled** | 2.7M field-goal attempts, 12 seasons (2014-15 → 2025-26, regular season + playoffs) |
| **xShot accuracy** | **7.7% lower log loss** than a league-average baseline (0.638 vs. 0.691) on 466K held-out shots |
| **Calibration** | Predicted and actual make rates line up across all 20 probability bins (Brier 0.225) |
| **Impact ratings** | Ridge-regression RAPM over 421,849 five-on-five lineup stints in 15,439 games |
| **Stability** | Pooling three seasons with a box-score prior cuts rating noise by ~40% vs. single seasons |

## What the dashboard shows

1. **Who makes their team better?** 3-season impact (RAPM + box-score prior) leaderboard by season.
2. **Who beats shot difficulty?** Each player's actual FG% minus the FG% xShot expects on his shots.
3. **Player profile.** Shot chart colored by make rate vs. expected, plus impact over time.
4. **How good is the model?** Calibration on held-out seasons.

## Methodology (short version)

**xShot.** An XGBoost binary classifier predicts P(make) from 30 pre-shot features: location (distance, angle, zone,
corner three), shot type (dunk, layup, pull-up, step-back, floater…) and context (period, clock, overtime, playoffs).
The model is never told who is shooting, so it measures *shot difficulty*, not shooter skill. The split is by time
(train 2014-15 → 2022-23, test 2023-24 → 2024-25) to avoid leakage. Details: [`docs/XSHOT_MODEL.md`](docs/XSHOT_MODEL.md).

**RAPM.** Play-by-play is cut into stints where the same ten players are on the floor. A weighted ridge regression
(one column per player, ±1 for home/away) estimates each player's effect on scoring margin per 100 possessions while
controlling for all teammates and opponents. The dashboard's impact rating pools three seasons of stints and adds a
box-score prior, which cuts noise by about 40% vs. single seasons. Details: [`docs/RAPM_MODEL.md`](docs/RAPM_MODEL.md).

**In progress: xRAPM.** The same regression with each shot re-scored by its xShot value, to separate process from
shooting luck. With the current shared ridge penalty the xShot-based target is over-shrunk (ratings compress toward 0),
so it's being retuned with its own penalty and prior before it's promoted to the dashboard.

**Limitations.** No player-tracking data (defender distance, etc.), so xShot difficulty is location- and play-type-based.
Ridge shrinkage compresses impact ratings toward zero, so they run smaller than on public RAPM sites.

## How the site works

The dashboard is a static page (`site/`) with HTML, [Observable Plot](https://observablehq.com/plot/) and precomputed
JSON in `site/data/`. There's no database or server behind it and no secrets in the repo, and GitHub Pages serves it
for free with no cold starts. `scripts/export_static.py` produces the JSON from the local PostgreSQL database.

```
NBA Stats API ──► PostgreSQL ──► features ──► xShot (XGBoost) ──► lineup stints ──► RAPM (ridge + prior)
   (nba_api)      7.5M events                 2.7M predictions                      │
                                                                                     ▼
                                   scripts/export_static.py ──► site/data/*.json ──► GitHub Pages
```

## Run it locally

**Just the dashboard** (uses the committed JSON, no database needed):

```bash
git clone https://github.com/mishareiss/nba-impact-model.git
cd nba-impact-model/site
python -m http.server 8000      # open http://localhost:8000
```

**The full pipeline** (needs PostgreSQL; takes hours because of NBA API rate limits):

```bash
conda env create -f environment.yml && conda activate nba-impact
cp .env.example .env            # set DB_URL=postgresql://user:pass@localhost:5432/nba

python -m src.ingestion.pipeline            # play-by-play → PostgreSQL
python -m src.ingestion.load_player_stats   # box-score stats
python -m src.features.build_features       # 30 shot features
python -m src.models.train_xshot            # train xShot
python -m src.models.predict                # score every FGA
python -m src.features.build_stints         # lineup stints
python -m src.models.train_xrapm            # single-season RAPM
python -m src.models.train_xrapm_v2         # pooled 3-season ratings + prior
python -m src.analysis.build_views          # materialized views
python scripts/export_static.py             # refresh site/data/
pytest tests/
```

## Repo layout

```
src/ingestion/   NBA API → PostgreSQL (retry/backoff, idempotent upserts)
src/features/    shot features, lineup stint construction
src/models/      xShot training + inference, RAPM
src/analysis/    materialized views
scripts/         export_static.py (DB → dashboard JSON)
site/            the public dashboard (static)
models/          model metadata, calibration, feature importance
docs/            pipeline and model write-ups
tests/           pytest suite
```

**Stack:** Python · pandas · XGBoost · scikit-learn · PostgreSQL · SQLAlchemy · Observable Plot · GitHub Actions/Pages

Built by **Misha Reiss**.
