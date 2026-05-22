import numpy as np
import pandas as pd
from scipy.sparse import lil_matrix, csr_matrix
from sklearn.linear_model import Ridge
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

LAMBDA = 30000
MIN_POSSESSIONS = 1000


def create_table():
    """Create player_impact_ratings table. Safe to call on re-runs."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_impact_ratings (
                person_id    INTEGER NOT NULL,
                season       TEXT    NOT NULL,
                season_type  TEXT    NOT NULL,
                xrapm        FLOAT,
                rapm         FLOAT,
                possessions  FLOAT,
                PRIMARY KEY (person_id, season, season_type)
            )
        """))
        conn.execute(text("""
            ALTER TABLE player_impact_ratings
            ADD COLUMN IF NOT EXISTS rapm FLOAT
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pir_season
            ON player_impact_ratings (season, season_type)
        """))
    logger.info("player_impact_ratings table ready")


def load_stints(season: str, season_type: str) -> pd.DataFrame:
    """Load all stints for one season from Postgres."""
    query = text("""
        SELECT home_players, away_players, home_points, away_points,
               home_xshot_pts, away_xshot_pts, total_poss
        FROM lineup_stints
        WHERE season      = :season
          AND season_type = :season_type
          AND total_poss  >= 1
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"season": season, "season_type": season_type})
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
    Build sparse design matrix X and response vectors y_xshot, y_actual.

    X (stints × players):
        +1  if player is on the home team in this stint
        -1  if player is on the away team in this stint
         0  otherwise

    y_xshot: net xShot pts per 100 poss (home perspective) — process target
    y_actual: net actual pts per 100 poss (home perspective) — outcome target
    w: total possessions per stint — longer stints get more weight
    """
    n_stints = len(df)
    n_players = len(player_idx)

    X = lil_matrix((n_stints, n_players), dtype=np.float32)
    y_xshot = np.zeros(n_stints, dtype=np.float64)
    y_actual = np.zeros(n_stints, dtype=np.float64)
    w = np.zeros(n_stints, dtype=np.float64)

    for i, row in enumerate(df.itertuples()):
        for pid in row.home_players:
            if pid in player_idx:
                X[i, player_idx[pid]] = 1.0
        for pid in row.away_players:
            if pid in player_idx:
                X[i, player_idx[pid]] = -1.0

        poss = row.total_poss
        y_xshot[i] = (row.home_xshot_pts - row.away_xshot_pts) / poss * 100
        y_actual[i] = (row.home_points  - row.away_points)  / poss * 100
        w[i] = poss

    return csr_matrix(X), y_xshot, y_actual, w


def compute_player_possessions(df: pd.DataFrame, player_idx: dict) -> dict:
    """
    Sum total possession-weight per player across all stints.
    Used to apply MIN_POSSESSIONS filter before storing results.
    """
    poss_map = {pid: 0.0 for pid in player_idx}
    for _, row in df.iterrows():
        p = row["total_poss"]
        for pid in row["home_players"] + row["away_players"]:
            if pid in poss_map:
                poss_map[pid] += p
    return poss_map


def fit_rapm(X, y, w, lam: float = LAMBDA) -> np.ndarray:
    """
    Fit ridge regression with possession weights. Returns one coefficient per player.
    fit_intercept=False: the design matrix is symmetric (+5 home, -5 away per stint),
    so a non-zero intercept would represent a systematic home/away bias unrelated to
    individual players.
    """
    model = Ridge(alpha=lam, fit_intercept=False)
    model.fit(X, y, sample_weight=w)
    return model.coef_


def run_season(season: str, season_type: str):
    df = load_stints(season, season_type)
    if df.empty:
        logger.warning(f"No stints for {season} {season_type}, skipping")
        return

    player_idx = build_player_index(df)
    logger.info(f"Player pool: {len(player_idx)} players")

    X, y_xshot, y_actual, w = build_matrix(df, player_idx)
    logger.info(f"Matrix: {X.shape}, {X.nnz:,} nonzero entries")

    coefs_xrapm = fit_rapm(X, y_xshot, w)
    coefs_rapm  = fit_rapm(X, y_actual, w)

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
                    (person_id, season, season_type, xrapm, rapm, possessions)
                VALUES
                    (:person_id, :season, :season_type, :xrapm, :rapm, :possessions)
            """), results)

    by_xrapm = sorted(results, key=lambda r: r["xrapm"], reverse=True)
    by_rapm  = sorted(results, key=lambda r: r["rapm"],  reverse=True)
    logger.info("xRAPM top 5: " + str([(r["person_id"], r["xrapm"]) for r in by_xrapm[:5]]))
    logger.info("RAPM  top 5: " + str([(r["person_id"], r["rapm"])  for r in by_rapm[:5]]))


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
