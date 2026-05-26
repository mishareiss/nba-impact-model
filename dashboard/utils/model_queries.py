"""
Model artifact loaders and evaluation queries.

Separates model-evaluation concerns from player/team queries.py.
All JSON loaders read from models/ at the repo root so they work on any
deployment host — no pkl file required.

Query functions are cached with st.cache_data; JSON loaders use
st.cache_resource (the files are read once and never change at runtime).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .db import query

# Repo root → models/
_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


# ---------------------------------------------------------------------------
# JSON artifact loaders  (deployment-portable, no pkl needed)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_feature_importance() -> dict:
    """
    Load normalised XGBoost gain importance from models/feature_importance.json.
    Returns dict with keys: features, importance, importance_raw, importance_type.
    Regenerate with: python -m src.models.export_model_artifacts
    """
    path = _MODELS_DIR / "feature_importance.json"
    with open(path) as f:
        return json.load(f)


@st.cache_resource(show_spinner=False)
def load_calibration_data() -> dict:
    """
    Load calibration curve data from models/calibration_data.json.
    Returns dict with keys: mean_predicted, fraction_positive, n_bins.
    """
    path = _MODELS_DIR / "calibration_data.json"
    with open(path) as f:
        return json.load(f)


@st.cache_resource(show_spinner=False)
def load_model_metadata() -> dict:
    """
    Load xShot model metadata from models/xshot_v1_metadata.json.
    Includes training config, feature list, and evaluation metrics.
    """
    path = _MODELS_DIR / "xshot_v1_metadata.json"
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Dataset summary  (counts for the hero section)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_dataset_summary() -> dict:
    """
    Return high-level counts describing the full dataset.
    Used on the Home page hero and dataset summary section.
    """
    results = {}

    for key, sql in [
        ("games",   "SELECT COUNT(*) AS n FROM games"),
        ("shots",   "SELECT COUNT(*) AS n FROM shot_predictions"),
        ("stints",  "SELECT COUNT(*) AS n FROM lineup_stints"),
        ("seasons", "SELECT COUNT(DISTINCT season) AS n FROM player_career_stats"),
        ("players", "SELECT COUNT(DISTINCT person_id) AS n FROM player_career_stats WHERE rapm IS NOT NULL"),
    ]:
        df = query(sql)
        results[key] = int(df.iloc[0]["n"]) if not df.empty else 0

    return results


# ---------------------------------------------------------------------------
# Shot difficulty distribution  (xShot histogram for Model Explorer)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_shot_difficulty_dist() -> pd.DataFrame:
    """
    Aggregate xShot probabilities into 0.02-wide bins across all shot_predictions.
    Returns ~50 rows — fast to query, small to transmit.

    Used on Model Explorer to visualise the distribution of predicted shot
    difficulty, demonstrating the model captures a wide probability range.
    """
    return query(
        """
        SELECT
            (FLOOR(xshot / 0.02) * 0.02)::float   AS xshot_bin,
            COUNT(*)                                AS n_shots,
            ROUND(AVG(xshot)::numeric, 4)           AS mean_xshot,
            ROUND(AVG(shot_made)::numeric, 4)       AS actual_make_rate
        FROM shot_predictions
        GROUP BY FLOOR(xshot / 0.02)
        ORDER BY xshot_bin
        """
    )


# ---------------------------------------------------------------------------
# Year-to-year stability data  (for stability analysis section)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_stability_data(min_poss: int = 300) -> pd.DataFrame:
    """
    Build consecutive-season pairs for RAPM / xRAPM stability analysis.

    For each player with at least min_poss possessions in two consecutive
    Regular Season seasons, returns a row with their year-N and year-(N+1)
    RAPM and xRAPM values.

    Year-over-year R² for xRAPM vs RAPM is the key insight:
    xRAPM is more stable (process > outcomes).
    """
    df = query(
        """
        SELECT
            MAX(person_id)  AS person_id,
            full_name,
            season,
            MAX(rapm)        AS rapm,
            MAX(xrapm)       AS xrapm,
            MAX(possessions) AS possessions
        FROM player_career_stats
        WHERE season_type   = 'Regular Season'
          AND possessions   >= :min_poss
          AND rapm          IS NOT NULL
          AND xrapm         IS NOT NULL
        GROUP BY person_id, full_name, season
        ORDER BY person_id, season
        """,
        {"min_poss": min_poss},
    )
    if df.empty:
        return df

    df = df.sort_values(["person_id", "season"]).reset_index(drop=True)

    # Shift within each player group to get next-season values
    grp = df.groupby("person_id")
    df["rapm_next"]   = grp["rapm"].shift(-1)
    df["xrapm_next"]  = grp["xrapm"].shift(-1)
    df["season_next"] = grp["season"].shift(-1)
    df["poss_next"]   = grp["possessions"].shift(-1)

    pairs = df.dropna(subset=["rapm_next", "xrapm_next"]).copy()

    # Verify seasons are truly consecutive (no gap years)
    def _start_year(s: str) -> int:
        try:
            return int(str(s).split("-")[0])
        except Exception:
            return 0

    pairs["yr_a"] = pairs["season"].apply(_start_year)
    pairs["yr_b"] = pairs["season_next"].apply(_start_year)
    pairs = pairs[pairs["yr_b"] == pairs["yr_a"] + 1].copy()

    return pairs[[
        "full_name",
        "season", "rapm", "xrapm", "possessions",
        "season_next", "rapm_next", "xrapm_next", "poss_next",
    ]].rename(columns={
        "season":      "season_a",
        "rapm":        "rapm_a",
        "xrapm":       "xrapm_a",
        "possessions": "poss_a",
        "season_next": "season_b",
        "rapm_next":   "rapm_b",
        "xrapm_next":  "xrapm_b",
        "poss_next":   "poss_b",
    }).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Process vs Results scatter data  (all players, one season)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def get_process_vs_results(season: str, season_type: str, min_poss: int = 300) -> pd.DataFrame:
    """
    For each qualifying player: mean xShot (shot difficulty) vs FG% above expected (shot-making).
    Used on Player Profile and Model Explorer to show the shot quality landscape.

    Quadrant interpretation:
      High xShot + High FG% above expected → elite difficult-shot maker
      Low xShot  + High FG% above expected → efficient but shot-selection dependent
      High xShot + Low  FG% above expected → creates hard shots but doesn't convert
    """
    return query(
        """
        SELECT
            MAX(person_id)                              AS person_id,
            full_name,
            MAX(team)                                   AS team,
            MAX(mean_xshot)                             AS mean_xshot,
            MAX(fg_pct_above_expected)                  AS fg_pct_above_expected,
            MAX(shot_pts_above_expected)                AS shot_pts_above_expected,
            MAX(shots_attempted)                        AS shots_attempted,
            MAX(rapm)                                   AS rapm,
            MAX(xrapm)                                  AS xrapm,
            MAX(possessions)                            AS possessions
        FROM player_career_stats
        WHERE season      = :season
          AND season_type = :season_type
          AND possessions >= :min_poss
          AND mean_xshot  IS NOT NULL
          AND fg_pct_above_expected IS NOT NULL
        GROUP BY person_id, full_name
        """,
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )
