import numpy as np
import pandas as pd
from scipy.sparse import lil_matrix, csr_matrix
from sklearn.linear_model import Ridge
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

LAMBDA    = 30000   # regularization for net RAPM / xRAPM  (+1/-1 encoding)
OD_LAMBDA = 15000   # regularization for O-RAPM / D-RAPM   (+1/0 encoding)
MIN_POSSESSIONS = 1000


def create_table():
    """Create / migrate player_impact_ratings. Safe to call on re-runs."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_impact_ratings (
                person_id    INTEGER NOT NULL,
                season       TEXT    NOT NULL,
                season_type  TEXT    NOT NULL,
                xrapm        FLOAT,
                rapm         FLOAT,
                o_rapm       FLOAT,
                d_rapm       FLOAT,
                possessions  FLOAT,
                PRIMARY KEY (person_id, season, season_type)
            )
        """))
        for col in ("rapm", "o_rapm", "d_rapm"):
            conn.execute(text(
                f"ALTER TABLE player_impact_ratings ADD COLUMN IF NOT EXISTS {col} FLOAT"
            ))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pir_season
            ON player_impact_ratings (season, season_type)
        """))
    logger.info("player_impact_ratings table ready")


def load_stints(season: str, season_type: str) -> pd.DataFrame:
    """Load all stints for one season from Postgres."""
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT home_players, away_players,
                   home_points, away_points,
                   home_xshot_pts, away_xshot_pts,
                   home_poss, away_poss, total_poss
            FROM lineup_stints
            WHERE season      = :season
              AND season_type = :season_type
              AND total_poss  >= 1
        """), conn, params={"season": season, "season_type": season_type})
    logger.info(f"Loaded {len(df):,} stints for {season} {season_type}")
    return df


def build_player_index(df: pd.DataFrame) -> dict:
    """
    Collect every unique player ID across all stints and assign a column index.
    Returns {person_id: column_index} — deterministic, sorted by person_id.
    """
    all_ids: set = set()
    for players in df["home_players"]:
        all_ids.update(players)
    for players in df["away_players"]:
        all_ids.update(players)
    return {pid: i for i, pid in enumerate(sorted(all_ids))}


def build_matrix(df: pd.DataFrame, player_idx: dict):
    """
    Net RAPM design matrix — ±1 encoding, fit_intercept=False.

    X (stints × players):
        +1  player on home team
        -1  player on away team
         0  not on court

    y_xshot: net xShot pts per 100 poss (home perspective) — process target
    y_actual: net actual pts per 100 poss (home perspective) — outcome target
    w: total possessions per stint
    """
    n_stints  = len(df)
    n_players = len(player_idx)

    X       = lil_matrix((n_stints, n_players), dtype=np.float32)
    y_xshot = np.zeros(n_stints, dtype=np.float64)
    y_actual = np.zeros(n_stints, dtype=np.float64)
    w       = np.zeros(n_stints, dtype=np.float64)

    for i, row in enumerate(df.itertuples()):
        for pid in row.home_players:
            if pid in player_idx:
                X[i, player_idx[pid]] = 1.0
        for pid in row.away_players:
            if pid in player_idx:
                X[i, player_idx[pid]] = -1.0

        poss = row.total_poss
        y_xshot[i]  = (row.home_xshot_pts - row.away_xshot_pts) / poss * 100
        y_actual[i] = (row.home_points    - row.away_points)    / poss * 100
        w[i] = poss

    return csr_matrix(X), y_xshot, y_actual, w


def build_od_matrix(df: pd.DataFrame, player_idx: dict):
    """
    Offensive / Defensive RAPM design matrix — +1/0 encoding, doubled observations.

    Each stint produces TWO rows:
      row 2i  : home team perspective
                  - home players = +1 (they are the offense / the defense)
                  - away players = 0
                  - y_off = home pts / home_poss × 100   (home team's offense)
                  - y_def = away pts / away_poss × 100   (opponent pts allowed by home)

      row 2i+1: away team perspective (symmetric)

    O-RAPM coefficient = how much a player improves their team's offensive efficiency
                         above league average (positive = better scorer)
    D-RAPM coefficient = negative of the defensive regression coefficient
                         (positive = better defender; high raw coef = more pts allowed)

    fit_intercept=True is used so the intercept absorbs league-average efficiency
    (~110 pts/100 poss) and coefficients represent per-player deviations.
    """
    n_stints  = len(df)
    n_players = len(player_idx)
    n_obs     = 2 * n_stints

    X     = lil_matrix((n_obs, n_players), dtype=np.float32)
    y_off = np.zeros(n_obs, dtype=np.float64)
    y_def = np.zeros(n_obs, dtype=np.float64)
    w     = np.zeros(n_obs, dtype=np.float64)

    for i, row in enumerate(df.itertuples()):
        hp = max(float(row.home_poss), 0.5)
        ap = max(float(row.away_poss), 0.5)
        home_pts = float(row.home_points)
        away_pts = float(row.away_points)

        # Home team row
        for pid in row.home_players:
            if pid in player_idx:
                X[2 * i, player_idx[pid]] = 1.0
        y_off[2 * i] = home_pts / hp * 100   # home offense efficiency
        y_def[2 * i] = away_pts / ap * 100   # pts allowed by home defense
        w[2 * i]     = hp

        # Away team row
        for pid in row.away_players:
            if pid in player_idx:
                X[2 * i + 1, player_idx[pid]] = 1.0
        y_off[2 * i + 1] = away_pts / ap * 100   # away offense efficiency
        y_def[2 * i + 1] = home_pts / hp * 100   # pts allowed by away defense
        w[2 * i + 1]     = ap

    return csr_matrix(X), y_off, y_def, w


def compute_player_possessions(df: pd.DataFrame, player_idx: dict) -> dict:
    """Sum total possession-weight per player across all stints."""
    poss_map = {pid: 0.0 for pid in player_idx}
    for _, row in df.iterrows():
        p = row["total_poss"]
        for pid in row["home_players"] + row["away_players"]:
            if pid in poss_map:
                poss_map[pid] += p
    return poss_map


def fit_rapm(X, y, w, lam: float = LAMBDA) -> np.ndarray:
    """
    Net RAPM ridge regression. fit_intercept=False because the ±1 design
    is symmetric and the intercept would only capture home/away bias.
    """
    model = Ridge(alpha=lam, fit_intercept=False)
    model.fit(X, y, sample_weight=w)
    return model.coef_


def fit_od_rapm(X, y, w, lam: float = OD_LAMBDA) -> np.ndarray:
    """
    O/D RAPM ridge regression. fit_intercept=True so the intercept captures
    league-average efficiency; coefficients represent deviations from that average.
    """
    model = Ridge(alpha=lam, fit_intercept=True)
    model.fit(X, y, sample_weight=w)
    return model.coef_


def run_season(season: str, season_type: str):
    df = load_stints(season, season_type)
    if df.empty:
        logger.warning(f"No stints for {season} {season_type}, skipping")
        return

    player_idx = build_player_index(df)
    logger.info(f"Player pool: {len(player_idx)} players")

    # ── Net RAPM and xRAPM (±1 encoding) ────────────────────────────────────
    X, y_xshot, y_actual, w = build_matrix(df, player_idx)
    logger.info(f"Net matrix: {X.shape}, {X.nnz:,} nonzero entries")

    coefs_xrapm = fit_rapm(X, y_xshot,  w)
    coefs_rapm  = fit_rapm(X, y_actual, w)

    # ── O-RAPM and D-RAPM (+1/0 doubled encoding) ────────────────────────────
    X_od, y_off, y_def, w_od = build_od_matrix(df, player_idx)
    logger.info(f"O/D matrix: {X_od.shape}, {X_od.nnz:,} nonzero entries")

    coefs_orapm =  fit_od_rapm(X_od, y_off, w_od)
    coefs_drapm = -fit_od_rapm(X_od, y_def, w_od)   # negate: high raw = more pts allowed = bad

    poss_map   = compute_player_possessions(df, player_idx)
    idx_to_pid = {i: pid for pid, i in player_idx.items()}

    results = []
    for i in range(len(coefs_xrapm)):
        pid  = idx_to_pid[i]
        poss = poss_map[pid]
        if poss < MIN_POSSESSIONS:
            continue
        results.append({
            "person_id":   pid,
            "season":      season,
            "season_type": season_type,
            "xrapm":       round(float(coefs_xrapm[i]), 4),
            "rapm":        round(float(coefs_rapm[i]),  4),
            "o_rapm":      round(float(coefs_orapm[i]), 4),
            "d_rapm":      round(float(coefs_drapm[i]), 4),
            "possessions": round(poss, 1),
        })

    logger.info(f"Inserting {len(results)} ratings for {season} {season_type}")

    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM player_impact_ratings
            WHERE season = :season AND season_type = :season_type
        """), {"season": season, "season_type": season_type})
        if results:
            conn.execute(text("""
                INSERT INTO player_impact_ratings
                    (person_id, season, season_type, xrapm, rapm, o_rapm, d_rapm, possessions)
                VALUES
                    (:person_id, :season, :season_type, :xrapm, :rapm, :o_rapm, :d_rapm, :possessions)
            """), results)

    by_rapm   = sorted(results, key=lambda r: r["rapm"],   reverse=True)
    by_orapm  = sorted(results, key=lambda r: r["o_rapm"], reverse=True)
    by_drapm  = sorted(results, key=lambda r: r["d_rapm"], reverse=True)
    logger.info("RAPM  top 5: " + str([(r["person_id"], r["rapm"])   for r in by_rapm[:5]]))
    logger.info("O-RAPM top5: " + str([(r["person_id"], r["o_rapm"]) for r in by_orapm[:5]]))
    logger.info("D-RAPM top5: " + str([(r["person_id"], r["d_rapm"]) for r in by_drapm[:5]]))


def main():
    create_table()

    seasons = [
        "2014-15", "2015-16", "2016-17", "2017-18", "2018-19",
        "2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
        "2024-25", "2025-26",
    ]

    for season in seasons:
        for season_type in ["Regular Season", "Playoffs"]:
            try:
                run_season(season, season_type)
            except Exception as e:
                logger.error(f"Failed {season} {season_type}: {e}")

    logger.info("Done")


if __name__ == "__main__":
    main()
