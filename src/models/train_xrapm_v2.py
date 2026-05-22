import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger
from src.models.train_xrapm import (
    build_player_index,
    build_matrix,
    compute_player_possessions,
    fit_rapm,
    LAMBDA,
)

logger = get_logger(__name__)

# Ridge regularization for the prior-adjusted fit.
# Can be tuned independently from the plain RAPM lambda.
LAMBDA_PRIOR = 30000

# Minimum possession-weight for a player to appear in pooled results.
# Higher than v1 because 3-year windows have more data.
MIN_POSSESSIONS_POOLED = 2000

# Number of seasons in each rolling window.
WINDOW_SIZE = 3

# How strongly the box-score prior pulls estimates toward it.
# 0 = pure ridge RAPM, 1 = pure box-score.
# Tune between 0.08–0.20: higher → stars benefit more, role-player noise dampens.
PRIOR_WEIGHT = 0.12


def create_pooled_table():
    """Create player_impact_pooled table. Safe to call on re-runs."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_impact_pooled (
                person_id       INTEGER NOT NULL,
                end_season      TEXT    NOT NULL,
                season_type     TEXT    NOT NULL,
                window_seasons  TEXT    NOT NULL,
                xrapm           FLOAT,
                rapm            FLOAT,
                rapm_prior      FLOAT,
                prior_estimate  FLOAT,
                possessions     FLOAT,
                PRIMARY KEY (person_id, end_season, season_type)
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pip_end_season
            ON player_impact_pooled (end_season, season_type)
        """))
    logger.info("player_impact_pooled table ready")


def load_stints_pooled(seasons: list[str], season_type: str) -> pd.DataFrame:
    """Load stints across all seasons in the window in a single query."""
    query = text("""
        SELECT home_players, away_players, home_points, away_points,
               home_xshot_pts, away_xshot_pts, total_poss
        FROM lineup_stints
        WHERE season      = ANY(:seasons)
          AND season_type = :season_type
          AND total_poss  >= 1
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"seasons": seasons, "season_type": season_type})
    logger.info(f"Loaded {len(df):,} pooled stints ({seasons}) {season_type}")
    return df


def season_windows(all_seasons: list[str], window_size: int = WINDOW_SIZE) -> list[tuple[str, list[str]]]:
    """
    Build rolling windows of `window_size` seasons.
    Returns [(end_season, [s1, s2, ..., end_season]), ...].
    First window requires `window_size` full seasons, so the first
    end_season is all_seasons[window_size - 1].
    """
    out = []
    for i in range(window_size - 1, len(all_seasons)):
        window = all_seasons[i - window_size + 1: i + 1]
        out.append((window[-1], window))
    return out


def load_box_scores(seasons: list[str], season_type: str) -> pd.DataFrame:
    """Load raw per-player box score totals across all seasons in the window."""
    query = text("""
        SELECT person_id, team_id, gp, min, pts, reb, ast, stl, blk, tov,
               fgm, fga, ftm, fta, plus_minus
        FROM player_season_stats
        WHERE season      = ANY(:seasons)
          AND season_type = :season_type
          AND min         > 0
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"seasons": seasons, "season_type": season_type})


def aggregate_player_box(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse multiple (season × team) rows into one row per player.
    Sums gp, min, plus_minus across all rows (traded players included).
    """
    rows = []
    for pid, g in df.groupby("person_id"):
        gp  = g["gp"].sum()
        m   = g["min"].sum()
        pm  = g["plus_minus"].sum()
        if m <= 0:
            continue
        rows.append({
            "person_id":   pid,
            "gp":          gp,
            "min":         m,
            "plus_minus":  pm,
        })
    return pd.DataFrame(rows)


def box_prior_per100(row) -> float:
    """
    Compute per-player prior γ in the same units as the RAPM target
    (net points per 100 possessions).

    Formula: (plus_minus / min) * 48 * PRIOR_WEIGHT
      - plus_minus / min       → net pts per minute on court
      - × 48                   → scale to per-48-min (≈ per-100-team-poss)
      - × PRIOR_WEIGHT         → shrink to avoid overwhelming stint signal

    PRIOR_WEIGHT = 0.12 puts γ in roughly ±0.5–1.5 for rotation players,
    which is proportionate to pooled RAPM values of ±1–3.
    """
    if row["min"] <= 0:
        return 0.0
    return (row["plus_minus"] / row["min"]) * 48.0 * PRIOR_WEIGHT


def build_gamma(player_idx: dict, box_df: pd.DataFrame) -> np.ndarray:
    """
    Build prior vector γ aligned to player_idx column ordering.
    Players with no box score data get γ = 0 (shrink toward league average).
    After building, center the vector so that the league-average prior is 0,
    preventing systematic bias in the y_adj = y - X@γ transformation.
    """
    n = len(player_idx)
    gamma = np.zeros(n, dtype=np.float64)
    prior_map = {
        row["person_id"]: box_prior_per100(row)
        for _, row in box_df.iterrows()
    }
    for pid, i in player_idx.items():
        gamma[i] = prior_map.get(pid, 0.0)

    # Center: mean prior across all players in this pool → 0
    # This ensures the prior doesn't introduce a systematic home/away or
    # overall scoring bias into the residual regression.
    gamma -= gamma.mean()
    return gamma


def fit_rapm_with_prior(X, y, w, gamma: np.ndarray, lam: float = LAMBDA_PRIOR) -> np.ndarray:
    """
    Ridge regression with a box-score prior via reparameterization.

    Instead of minimizing ||y - Xβ||² + λ||β||² (shrink toward 0),
    we minimize ||y - Xβ||² + λ||β - γ||² (shrink toward γ).

    Achieved by substituting β* = β - γ and fitting on y_adj = y - Xγ:
        β_final = γ + β*

    Precondition: gamma must be centered (mean ~0) to avoid bias in y_adj.
    """
    y_adj = y - X.dot(gamma)
    model = Ridge(alpha=lam, fit_intercept=False)
    model.fit(X, y_adj, sample_weight=w)
    return gamma + model.coef_


def run_pooled_window(end_season: str, seasons: list[str], season_type: str):
    df = load_stints_pooled(seasons, season_type)
    if df.empty:
        logger.warning(f"No stints for window {seasons} {season_type}, skipping")
        return

    player_idx = build_player_index(df)
    logger.info(f"Player pool: {len(player_idx)} players")

    X, y_xshot, y_actual, w = build_matrix(df, player_idx)
    logger.info(f"Matrix: {X.shape}, {X.nnz:,} nonzero entries")

    coefs_xrapm = fit_rapm(X, y_xshot, w)
    coefs_rapm  = fit_rapm(X, y_actual, w)

    box_raw = load_box_scores(seasons, season_type)
    box_agg = aggregate_player_box(box_raw)
    gamma   = build_gamma(player_idx, box_agg)
    logger.info(f"Prior γ: min={gamma.min():.3f} max={gamma.max():.3f} mean={gamma.mean():.3f}")

    coefs_rapm_prior = fit_rapm_with_prior(X, y_actual, w, gamma)

    poss_map   = compute_player_possessions(df, player_idx)
    idx_to_pid = {i: pid for pid, i in player_idx.items()}
    window_label = ",".join(seasons)

    results = []
    for i in range(len(coefs_rapm)):
        pid  = idx_to_pid[i]
        poss = poss_map[pid]
        if poss < MIN_POSSESSIONS_POOLED:
            continue
        results.append({
            "person_id":      pid,
            "end_season":     end_season,
            "season_type":    season_type,
            "window_seasons": window_label,
            "xrapm":          round(float(coefs_xrapm[i]),     4),
            "rapm":           round(float(coefs_rapm[i]),       4),
            "rapm_prior":     round(float(coefs_rapm_prior[i]), 4),
            "prior_estimate": round(float(gamma[i]),            4),
            "possessions":    round(poss, 1),
        })

    logger.info(f"Inserting {len(results)} ratings for {end_season} {season_type}")

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM player_impact_pooled
            WHERE end_season = :end AND season_type = :st
        """), {"end": end_season, "st": season_type})
        if results:
            conn.execute(text("""
                INSERT INTO player_impact_pooled (
                    person_id, end_season, season_type, window_seasons,
                    xrapm, rapm, rapm_prior, prior_estimate, possessions
                ) VALUES (
                    :person_id, :end_season, :season_type, :window_seasons,
                    :xrapm, :rapm, :rapm_prior, :prior_estimate, :possessions
                )
            """), results)

    by_rapm  = sorted(results, key=lambda r: r["rapm"],       reverse=True)
    by_prior = sorted(results, key=lambda r: r["rapm_prior"], reverse=True)
    logger.info("Pooled RAPM top 5:      " + str([(r["person_id"], r["rapm"])       for r in by_rapm[:5]]))
    logger.info("RAPM+prior   top 5:     " + str([(r["person_id"], r["rapm_prior"]) for r in by_prior[:5]]))


def main():
    create_pooled_table()

    all_seasons = [
        "2014-15", "2015-16", "2016-17", "2017-18", "2018-19",
        "2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
        "2024-25", "2025-26",
    ]

    for end_season, window in season_windows(all_seasons, WINDOW_SIZE):
        for season_type in ["Regular Season", "Playoffs"]:
            try:
                run_pooled_window(end_season, window, season_type)
            except Exception as e:
                logger.error(f"Failed {end_season} {season_type}: {e}")

    logger.info("Done")


if __name__ == "__main__":
    main()
