# xShot Model - Model Card

## Objective

Predict the probability that any given field goal attempt is made, given only pre-shot information (location, shot type, game context). This produces an **xShot** value per shot, analogous to xG in soccer.

## Why XGBoost

- Handles mixed feature types natively (boolean flags + continuous variables)
- No feature scaling required
- Built-in early stopping prevents overfitting
- Fast inference at scale (2.68M+ shots)
- Highly interpretable via feature importance
- Strong baseline for tabular sports data

Alternatives considered: logistic regression (too simple, can't model zone x shot_type interactions), neural nets (harder to interpret, overkill for this data volume and feature set at v1).

## Training Setup

| Parameter | Value |
|-----------|-------|
| Algorithm | XGBoost binary classifier |
| n_estimators | 500 (early stopping at 127) |
| max_depth | 6 |
| learning_rate | 0.05 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| min_child_weight | 10 |
| early_stopping_rounds | 20 |

## Temporal Train/Test Split

**Critical design decision:** The split is temporal, not random. Random splits would leak future information into training.

- **Train:** 2014-15 → 2022-23 (1,995,322 shots)
- **Test:** 2023-24 → 2024-25 (466,446 shots)
- **Excluded from test:** 2025-26 (current in-progress season - no stable holdout)

## Features

### Spatial
| Feature | Description |
|---------|-------------|
| `shot_distance` | Distance from basket in feet |
| `shot_angle` | Angle from center of basket |
| `x_legacy`, `y_legacy` | Raw court coordinates |
| `shot_zone` | Zone category (numeric codes) |
| `is_corner_three` | Corner 3 geometry flag |
| `is_paint` | In-paint shot flag |

### Shot Value
| Feature | Description |
|---------|-------------|
| `shot_value` | 2 or 3 |
| `is_three` | Three-point attempt |

### Shot Type Indicators (Boolean Flags)
`is_dunk`, `is_layup`, `is_alley_oop`, `is_cutting`, `is_putback`, `is_tip`, `is_finger_roll`, `is_driving`, `is_running`, `is_pullup`, `is_stepback`, `is_fadeaway`, `is_hook`, `is_floating`, `is_turnaround`, `is_reverse`, `is_bank`

All derived via regex on the `sub_type` field (e.g., `sub_type` contains "Dunk" → `is_dunk = True`).

### Game Context
| Feature | Description |
|---------|-------------|
| `period` | Quarter/OT period number |
| `clock_seconds` | Seconds remaining in period |
| `is_overtime` | Period > 4 |
| `is_playoffs` | Playoff game flag |

## Results (v1, Test Set: 2023-24 + 2024-25)

| Metric | Value |
|--------|-------|
| Log loss | 0.6382 |
| Baseline log loss | 0.6914 |
| Log loss reduction | **7.7%** |
| Brier score | 0.2248 |

The baseline is a naive model that always predicts the mean FG% (≈46.2%).

## Production Validation

After scoring all 2.68M shots and aggregating to `player_shot_qualities`, the top performers by `points_above_expected` (PAE) in 2025-26 Regular Season are shown below:

 Player | Team | PAE | Mean xShot | Actual FG% |
|--------|------|-----|-------|------------|
| Nikola Jokić | DEN | +275.8 | 0.452 | 0.567 |
| Kevin Durant | HOU | +251.2 | 0.437 | 0.520 |
| Shai Gilgeous-Alexander | OKC | +220.53 | 0.471 | 0.553 |
| Jamal Murray | DEN | +173.7 | 0.432 | 0.476 |
| Luka Doncic | DEN | +171.2 | 0.416 | 0.505 |

**Interpretation:** Results pass the smell test. The model correctly identifies elite scorers and shot-makers. mid-range scorers in particular consistently outperform shot difficulty (KD, SGA, Murray). The table also stores `fg_pct_above_expected` which is the per-shot normalized metric; `points_above_expected` is volume-dependent.

## Feature Importance Analysis
**Top features:**
1. `is_dunk` (0.35) - by far the most important. Dunks go in at ~95%+ rate, a massive signal.
2. `shot_zone` (0.17) - zone captures most of the spatial signal compactly.
3. `shot_value` (0.09) - 3s vs 2s encode shot difficulty broadly.
4. `is_layup` (0.06) - second-highest percentage shot type after dunks.
5. `shot_distance` (0.06) - continuous distance adds signal within zones.

**Takeaway:** The model is dominated by shot type (is_dunk, is_layup, shot_zone) rather than pure location. This makes sense a 5-foot fadeaway and a 5-foot cutting layup are very different shots.

**Lowest importance:**
- `is_overtime`, `is_playoffs`, `shot_angle`, `period` - nearly zero contribution.

**Interpretation:** Game context features add virtually nothing to shot quality prediction. Whether a shot is taken in overtime or the playoffs does not meaningfully change its probability of going in - players don't shoot fundamentally differently in those situations after controlling for shot type and location.

**Action:** These features are not wrong to include (they don't hurt), but v2 could drop them to reduce model complexity.

## Calibration Analysis

The calibration curve closely follows the perfect diagonal with no systematic bias. Minor zig-zagging occurs in the 0.15-0.35 range (contested mid-range shots) - this is expected noise given the smaller sample sizes in those probability bins.

**Conclusion:** No post-hoc calibration correction (Platt scaling, isotonic regression) is needed. The model's predicted probabilities can be used directly as xShot values.

## Known Limitations

1. **No defender context.** The model has no information about shot contest level. A wide-open 3 and a heavily-contested 3 get the same features (same shot_zone, same is_three=1). This is the single biggest source of unexplained variance.
2. **No shooter identity.** Some players shoot above their shot quality expectation consistently (e.g., elite shooters). The model cannot distinguish these - this is a feature, not a bug, for the intended use case (measuring shot quality independent of shooter skill).
3. **Temporal drift.** The NBA has changed significantly since 2014-15 (3-point revolution). The model trains on 9 seasons of history, which may dampen recent 3-point shot difficulty changes.
4. **`is_dunk` dominance.** 35% of all feature importance rests on one feature. This means for non-dunk shots, the model is working harder. Inspect non-dunk shot predictions separately in v2.
5. **Playoffs systematically underestimated.** Observed in production across all 11 seasons: actual playoff FG% is consistently ~1-2.5% below predicted xShot. Playoff defense is more intense and contested, but `is_playoffs` had near-zero feature importance, meaning the model does not adjust for playoff context. This does not affect player rankings within a season but introduces a small systematic bias when comparing playoff vs regular season xShot values directly.

## V2 Improvement Candidates

- [ ] **Drop zero-importance features** (`is_overtime`, `is_playoffs`, `period`, `shot_angle`) - reduce noise, speed up inference
- [ ] **Lower learning rate** (0.02) with more iterations - may gain 1-2% log loss
- [ ] **Add `season` as a feature** - captures 3-point revolution drift over time
- [ ] **Add defender distance** - requires tracking data, not available in PBP
- [ ] **Separate dunk model** - dunks are nearly deterministic; removing them from the main model may improve mid-range/3-point calibration
- [ ] **Interaction features** - `is_driving × shot_distance`, `clock_seconds × shot_distance`
- [ ] **Shot type fine-graining** - "Driving Floating Jump Shot" and "Step Back Jump Shot" both map to jump shots; finer encoding may help
- [ ] **Playoff-specific adjustment** - small additive correction to xShot in playoff games (~-0.015 based on observed bias), or train a separate model on playoff data only

## Artifacts

| File | Description |
|------|-------------|
| `models/xshot_v1.pkl` | Trained XGBoost model (joblib format) |
| `models/xshot_v1_metadata.json` | Training metadata (timestamp, metrics, features) |
| `models/feature_importance.png` | Bar chart of XGBoost feature importances |
| `models/calibration.png` | Calibration curve: predicted probability vs actual make rate |