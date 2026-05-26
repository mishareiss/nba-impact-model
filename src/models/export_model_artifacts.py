"""
One-time (and idempotent) script to export deployment-portable JSON artifacts
from the existing trained xShot model.

Run this after any retrain, or once now to generate the files for the first time:

    python -m src.models.export_model_artifacts

Outputs (all committed to the repo — no pkl required at runtime):
    models/feature_importance.json  — normalised XGBoost gain importance per feature
    models/calibration_data.json    — predicted vs actual make rate, 20 equal-frequency bins
    models/xshot_v1_metadata.json   — updated with evaluation metrics section

The pkl file is only needed to run this script. The dashboard reads only JSON.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"

sys.path.insert(0, str(ROOT))
from src.utils.logging import get_logger

logger = get_logger(__name__)

TRAIN_SEASONS_CUTOFF = "2022-23"


def load_model():
    path = MODELS_DIR / "xshot_v1.pkl"
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found at {path}. "
            "Run `python -m src.models.train_xshot` first."
        )
    logger.info(f"Loading model from {path}")
    return joblib.load(path)


def load_test_data(features: list[str]) -> tuple:
    path = DATA_DIR / "shots_features.parquet"
    logger.info(f"Loading test data from {path}")
    df = pd.read_parquet(path)

    test_mask = (df["season"] > TRAIN_SEASONS_CUTOFF) & (df["season"] != "2025-26")
    X_test = df.loc[test_mask, features]
    y_test = df.loc[test_mask, "made"].astype(int)

    logger.info(f"Test set: {len(X_test):,} shots ({df.loc[test_mask, 'season'].min()} → {df.loc[test_mask, 'season'].max()})")
    return X_test, y_test


def export(model, X_test, y_test) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    features = list(X_test.columns)
    preds = model.predict_proba(X_test)[:, 1]
    baseline = float(y_test.mean())

    # Evaluation metrics
    ll = log_loss(y_test, preds)
    ll_base = log_loss(y_test, [baseline] * len(y_test))
    ll_reduction = (ll_base - ll) / ll_base * 100
    brier = brier_score_loss(y_test, preds)

    logger.info(f"Log loss:           {ll:.4f}")
    logger.info(f"Baseline log loss:  {ll_base:.4f}")
    logger.info(f"Log loss reduction: {ll_reduction:.1f}%")
    logger.info(f"Brier score:        {brier:.4f}")

    metrics = {
        "log_loss": round(ll, 4),
        "baseline_log_loss": round(ll_base, 4),
        "log_loss_reduction_pct": round(ll_reduction, 1),
        "brier_score": round(brier, 4),
        "test_n_shots": int(len(y_test)),
    }

    # --- feature_importance.json ---
    raw_imp = model.feature_importances_
    total = float(raw_imp.sum())
    importance_data = {
        "features": features,
        "importance": [round(float(v) / total, 6) for v in raw_imp],
        "importance_raw": [round(float(v), 6) for v in raw_imp],
        "importance_type": "gain",
        "model_version": "xshot_v1",
    }
    path_fi = MODELS_DIR / "feature_importance.json"
    with open(path_fi, "w") as f:
        json.dump(importance_data, f, indent=2)
    logger.info(f"Saved {path_fi}")

    # --- calibration_data.json ---
    fraction_pos, mean_pred = calibration_curve(y_test, preds, n_bins=20)
    calibration_data = {
        "mean_predicted": [round(float(v), 6) for v in mean_pred],
        "fraction_positive": [round(float(v), 6) for v in fraction_pos],
        "n_bins": 20,
        "model_version": "xshot_v1",
    }
    path_cal = MODELS_DIR / "calibration_data.json"
    with open(path_cal, "w") as f:
        json.dump(calibration_data, f, indent=2)
    logger.info(f"Saved {path_cal}")

    # --- update xshot_v1_metadata.json with evaluation section ---
    meta_path = MODELS_DIR / "xshot_v1_metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            metadata = json.load(f)
    else:
        metadata = {}

    metadata["evaluation"] = metrics
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Updated {meta_path} with evaluation metrics")


def main():
    model = load_model()
    features = model.feature_names_in_.tolist() if hasattr(model, "feature_names_in_") else None
    if features is None:
        # Fall back to metadata JSON
        meta_path = MODELS_DIR / "xshot_v1_metadata.json"
        with open(meta_path) as f:
            features = json.load(f)["features"]

    X_test, y_test = load_test_data(features)
    export(model, X_test, y_test)
    logger.info("Export complete. Commit models/*.json to make artifacts deployment-portable.")


if __name__ == "__main__":
    main()
