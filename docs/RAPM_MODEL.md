# RAPM / xRAPM Model Card

## Objective

Estimate each player's marginal contribution to team scoring efficiency per 100 possessions, independent of teammate and opponent quality. Two variants are produced:

- **RAPM** — net *actual* scoring margin per 100 possessions while that player was on court
- **xRAPM** — net *expected* scoring margin (xShot-based) per 100 possessions. Process-oriented; less susceptible to shooting variance and random clutch outcomes.

---

## Why Ridge Regression

RAPM is a linear regression problem: given a design matrix X where each row is a lineup stint and each column is a player (±1 for on-court presence), estimate coefficients that best explain the observed scoring margin while controlling for multi-collinearity.

- Players share court time → columns are correlated → OLS is ill-conditioned
- Ridge regression (L2 penalty) regularizes toward zero, shrinking role players and noisy estimates while preserving signal for players with large sample sizes
- Regularization also implicitly handles the "garbage time" problem: blowout-game stints carry disproportionate noise that ridge suppresses

Alternatives considered: LASSO (too aggressive — zeros out players with little data rather than shrinking them); Elastic Net (adds complexity without meaningful benefit at this scale).

---

## V1: Single-Season RAPM (`train_xrapm.py`)

### Design Matrix

Each row = one lineup stint. Each column = one player.

| Value | Meaning |
|-------|---------|
| `+1` | Player was on court for the **home** team |
| `−1` | Player was on court for the **away** team |
| `0` | Player was not on court |

Stints are weighted by `total_poss` (possession count) so longer stints have proportionally more influence on the regression.

### Targets

The design matrix is used twice with different targets:

- `y_xshot = (home_xshot_pts − away_xshot_pts) / total_poss × 100` → fits **xRAPM**
- `y_actual = (home_points − away_points) / total_poss × 100` → fits **RAPM**

Both use weighted least squares. `fit_intercept=False` (the intercept is absorbed into the team-level ridge shrinkage).

### Hyperparameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| λ (Ridge alpha) | 30,000 | Suppresses noise for role players and players with limited court time; empirically validated against star player rankings |
| Min possessions | 1,000 | Filters out players with too few stints for stable estimates (~15+ games) |

### Output

Stored in `player_impact_ratings`. One row per `(person_id, season, season_type)`. Idempotent: DELETE + INSERT on each run.

### Known Limitations

- **Single-season collinearity.** On dominant teams (e.g., the 2022-23 Nuggets), all starters share significant court time together. Ridge suppresses this but cannot fully disentangle individual contributions.
- **No home/away baseline.** Home advantage is not modeled as a separate effect. The ±1 encoding partially absorbs it, but systematic home/away performance differences may bias estimates slightly.
- **Role player inflation.** Players on strong teams who rarely play alongside opponents of note can still accumulate positive margins. With λ=30,000 this is largely suppressed but not eliminated.
- **Overtime and short games.** Unusual game states (massive blowouts, short playoff games) can create outlier stints. These are not downweighted beyond their possession count.

---

## V2: 3-Year Pooled RAPM with Box-Score Prior (`train_xrapm_v2.py`)

### Motivation

Single-season RAPM has two core problems:

1. **Noise.** One season of stints is insufficient to disentangle players with correlated playing time. Rolling 3-year windows multiply the data available per player by ~3×, stabilizing estimates.
2. **Star player underrating.** Elite players on strong teams are undervalued by ridge because their teammates also have positive margins. A box-score prior anchors estimates toward a player's historical plus/minus baseline, correctly elevating stars whose box score impact (scoring, playmaking) is independently measurable.

### Rolling Windows

10 windows are produced: **2016-17 through 2025-26** (end seasons), each covering 3 seasons.

| End Season | Window |
|-----------|--------|
| 2016-17 | 2014-15, 2015-16, 2016-17 |
| 2017-18 | 2015-16, 2016-17, 2017-18 |
| ... | ... |
| 2025-26 | 2023-24, 2024-25, 2025-26 |

Both regular season and playoffs are processed independently, producing 20 total runs (10 windows × 2 season types).

### Box-Score Prior

For each player, a prior `γ` is computed from `player_season_stats` over the window period:

```
γ = (Σ plus_minus / Σ min) × 48 × PRIOR_WEIGHT
```

- `plus_minus / min` = per-minute raw plus/minus
- `× 48` = scales to per-48-minutes (proxy for per-100-possessions)
- `PRIOR_WEIGHT = 0.12` = empirically chosen to provide meaningful signal without overwhelming the on-court data
- **Gamma is centered to mean 0** before use. This prevents the prior from introducing systematic league-wide bias (e.g., if all players have positive raw plus/minus, an uncentered prior would inflate all estimates)

Players without box score data receive `γ = 0` (no prior, falls back to pure ridge).

### Ridge Regression with Prior (Reparameterized)

Minimize:

```
‖y − Xβ‖² + λ‖β − γ‖²
```

This is equivalent to standard ridge on the residual target:

```
y_adj = y − X·γ
→ solve: ‖y_adj − X·β*‖² + λ‖β*‖²
→ β_final = γ + β*
```

This reparameterization means `sklearn.linear_model.Ridge` can be used directly without modification.

### Hyperparameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| λ (Ridge alpha) | 30,000 | Same as v1; consistency across versions |
| Prior weight | 0.12 | ~10-15% of the estimate anchored to box score; prevents prior domination |
| Min possessions | 2,000 | Higher threshold for pooled model (3× data available) |

### Output

Stored in `player_impact_pooled`. One row per `(person_id, end_season, season_type)`.
Key columns: `xrapm`, `rapm`, `rapm_prior`, `prior_estimate` (γ), `possessions`, `window_seasons`.

---

## Results

### V1 — 2024-25 Regular Season (RAPM, top 5)

| Player | Team | RAPM | xRAPM | Poss |
|--------|------|------|-------|------|
| Shai Gilgeous-Alexander | OKC | +1.67 | +1.02 | 7,787 |
| Payton Pritchard | BOS | +1.26 | +0.40 | 4,128 |
| Luguentz Dort | OKC | +1.25 | +0.60 | 5,918 |
| Jarrett Allen | CLE | +1.19 | +0.18 | 6,254 |
| Nikola Jokić | DEN | +1.00 | −0.13 | 7,787 |

The RAPM−xRAPM gap for Jokić (+1.13) reflects significant shot-making above expectation — his actual scoring margin outperforms his expected shot quality, consistent with his elite finishing and playmaking converting high-xShot opportunities at above-expected rates.

### V2 — 2025-26 (RAPM+Prior, top 5)

| Player | Team | RAPM+Prior | Window |
|--------|------|------------|--------|
| Stephen Curry | GSW | +7.96 | 2016-17 |
| Stephen Curry | GSW | +6.84 | 2018-19 |
| Stephen Curry | GSW | +6.59 | 2017-18 |
| Kevin Durant | GSW | +6.29 | 2016-17 |
| André Iguodala | GSW | +6.27 | 2016-17 |

Historical windows correctly surface the dominant GSW dynasty. Current-era (2025-26 window) top players include Jokić, SGA, and Tatum.

### Interpretation of RAPM − xRAPM

| Sign | Interpretation |
|------|---------------|
| Large positive | Outscores expected lineup margins — strong finishing, free throw drawing, clutch conversion |
| Near zero | Actual and expected impact align — predictable player |
| Large negative | Underscores expected margins — possibly over-reliant on high-difficulty shots that don't convert |

---

## Known Limitations

1. **Prior era dependency.** The box-score prior uses raw plus/minus, which is heavily era-dependent. Pace, 3-point rates, and defensive rules differ significantly across 2014-26. A prior derived from a rate stat in 2015-16 (slow, low-scoring era) is not directly comparable to 2024-25. The `PRIOR_WEIGHT=0.12` partially mitigates this by keeping the prior influence small.

2. **Lineup collinearity persists in dominant teams.** The Warriors 2016-17 window has Curry, Durant, Green, Thompson, and Iguodala all in the top 5 of rapm_prior. Some of this is legitimate (the team genuinely had 5 above-average players), but lineup collinearity means ridge cannot fully separate their individual contributions even at 3-year scale.

3. **No opponent quality adjustment within windows.** Teams play different schedules and face different opponent talent levels in different seasons. These effects are absorbed into the intercept-free ridge but not explicitly modeled.

4. **Traded players.** A player traded mid-season appears in stints from both teams. The model correctly attributes their margin to the lineups they were part of, but the prior uses aggregated plus/minus across both team contexts, which may be noisy for mid-season trades.

5. **Rookies and debut seasons.** Players without box-score history in the 3-year window get `γ = 0`. Their estimates are pure ridge — unbiased but noisier than veterans.

---

## V3 Improvement Candidates

- [ ] **Era normalization for prior.** Normalize `plus_minus` to per-100-possession units and adjust for era-level offensive rating to make the prior scale-invariant across seasons.
- [ ] **Opponent-adjusted possessions.** Weight stints by opponent quality (e.g., opponent RAPM) rather than raw possession count.
- [ ] **Bayesian hierarchical model.** Replace the reparameterized ridge with a proper Bayesian model (Stan / PyMC). This enables credible intervals per player and explicit uncertainty quantification.
- [ ] **Separate offensive and defensive RAPM.** The current model captures net margin. Splitting into O-RAPM and D-RAPM requires separate targets (offensive efficiency vs points allowed per possession).
- [ ] **xRAPM prior.** Use the player's historical xRAPM from v1 as the prior for v2, creating a self-referential refinement loop that incorporates both box-score and shot-quality signals.
- [ ] **Larger windows for stars.** Role players benefit from short windows (less data needed for stable estimates). Stars benefit from longer windows (more data to disentangle from teammates). An adaptive window length could improve both.

---

## Artifacts

| File | Description |
|------|-------------|
| `player_impact_ratings` | Single-season RAPM + xRAPM (v1), all seasons |
| `player_impact_pooled` | 3-year pooled RAPM + prior (v2), all windows |
| `player_impact_leaderboard` | Materialized view: unified leaderboard with names, teams, box stats |
