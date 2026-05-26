import numpy as np
import pandas as pd
import joblib
import json
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timezone
from sklearn.metrics import log_loss, brier_score_loss
from sklearn.calibration import calibration_curve
from xgboost import XGBClassifier
from src.utils.logging import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

FEATURES = [
    "shot_distance", "shot_angle", "x_legacy", "y_legacy",
    "shot_zone", "is_corner_three", "is_paint",
    "shot_value", "is_three",
    "is_dunk", "is_layup", "is_alley_oop", "is_cutting",
    "is_putback", "is_tip", "is_finger_roll", "is_driving",
    "is_running", "is_pullup", "is_stepback",
    "is_fadeaway", "is_hook", "is_floating", "is_turnaround",
    "is_reverse", "is_bank",
    "period", "clock_seconds", "is_overtime", "is_playoffs",
]
LABEL = "made"

# Temporal split — train on older seasons, evaluate on recent
TRAIN_SEASONS_CUTOFF = "2022-23"  # test on 2023-24 and 2024-25


def load_data() -> pd.DataFrame:
    path = DATA_DIR / "shots_features.parquet"
    df = pd.read_parquet(path)
    logger.info(f"Loaded {len(df):,} shots")
    return df


def split_data(df: pd.DataFrame):
    train_mask = df["season"] <= TRAIN_SEASONS_CUTOFF
    test_mask = ~train_mask & (df["season"] != "2025-26")

    X_train = df.loc[train_mask, FEATURES]
    y_train = df.loc[train_mask, LABEL].astype(int)
    X_test = df.loc[test_mask, FEATURES]
    y_test = df.loc[test_mask, LABEL].astype(int)

    logger.info(f"Train: {len(X_train):,} shots ({df.loc[train_mask, 'season'].min()} → {TRAIN_SEASONS_CUTOFF})")
    logger.info(f"Test:  {len(X_test):,} shots ({df.loc[test_mask, 'season'].min()} → {df.loc[test_mask, 'season'].max()})")
    return X_train, y_train, X_test, y_test


def train(X_train, y_train, X_test, y_test) -> XGBClassifier:
    model = XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        eval_metric="logloss",
        early_stopping_rounds=20,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)
    logger.info(f"Best iteration: {model.best_iteration}")
    return model


def evaluate(model, X_test, y_test) -> tuple:
    """
    Compute holdout metrics. Returns (predictions, metrics_dict).
    metrics_dict is persisted to metadata JSON so the dashboard can display
    evaluation results without needing the model file.
    """
    preds = model.predict_proba(X_test)[:, 1]
    baseline = float(y_test.mean())

    ll = log_loss(y_test, preds)
    ll_base = log_loss(y_test, [baseline] * len(y_test))
    ll_reduction = (ll_base - ll) / ll_base * 100
    brier = brier_score_loss(y_test, preds)

    logger.info(f"Log loss:           {ll:.4f}")
    logger.info(f"Baseline log loss:  {ll_base:.4f} (always predict mean FG%)")
    logger.info(f"Log loss reduction: {ll_reduction:.1f}%")
    logger.info(f"Brier score:        {brier:.4f}")

    metrics = {
        "log_loss": round(ll, 4),
        "baseline_log_loss": round(ll_base, 4),
        "log_loss_reduction_pct": round(ll_reduction, 1),
        "brier_score": round(brier, 4),
        "test_n_shots": int(len(y_test)),
    }
    return preds, metrics


def export_artifacts(model, X_test, y_test, preds: np.ndarray, metrics: dict) -> None:
    """
    Export deployment-portable JSON artifacts to models/.

    These files are committed to the repo so the dashboard can display
    model evaluation results on any host — no pkl file required.

    Outputs:
        models/feature_importance.json  — normalised XGBoost gain importance
        models/calibration_data.json    — predicted vs actual make rate by bin
        models/feature_importance.png   — static chart (for README / reference)
        models/calibration.png          — static chart (for README / reference)
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # feature_importance.json
    raw_imp = model.feature_importances_
    total = float(raw_imp.sum())
    importance_data = {
        "features": FEATURES,
        "importance": [round(float(v) / total, 6) for v in raw_imp],
        "importance_raw": [round(float(v), 6) for v in raw_imp],
        "importance_type": "gain",
        "model_version": "xshot_v1",
    }
    with open(MODELS_DIR / "feature_importance.json", "w") as f:
        json.dump(importance_data, f, indent=2)
    logger.info("Saved feature_importance.json")

    # calibration_data.json
    fraction_pos, mean_pred = calibration_curve(y_test, preds, n_bins=20)
    calibration_data = {
        "mean_predicted": [round(float(v), 6) for v in mean_pred],
        "fraction_positive": [round(float(v), 6) for v in fraction_pos],
        "n_bins": 20,
        "model_version": "xshot_v1",
    }
    with open(MODELS_DIR / "calibration_data.json", "w") as f:
        json.dump(calibration_data, f, indent=2)
    logger.info("Saved calibration_data.json")

    # Static PNG plots (for reference / README)
    importance_series = pd.Series(model.feature_importances_, index=FEATURES)
    fig, ax = plt.subplots(figsize=(10, 8))
    importance_series.sort_values().plot(kind="barh", ax=ax)
    ax.set_title("xShot Feature Importance (XGBoost)")
    ax.set_xlabel("Importance score")
    plt.tight_layout()
    plt.savefig(MODELS_DIR / "feature_importance.png", dpi=150)
    plt.close()

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(mean_pred, fraction_pos, marker="o", label="xShot model")
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Actual make rate")
    ax.set_title("xShot Calibration Curve")
    ax.legend()
    plt.tight_layout()
    plt.savefig(MODELS_DIR / "calibration.png", dpi=150)
    plt.close()
    logger.info("Saved calibration.png and feature_importance.png")


def save_model(model, metrics: dict) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / "xshot_v1.pkl"
    joblib.dump(model, path)
    logger.info(f"Model saved to {path}")

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_seasons": f"2014-15 → {TRAIN_SEASONS_CUTOFF}",
        "test_seasons": "2023-24 → 2024-25",
        "features": FEATURES,
        "feature_count": len(FEATURES),
        "best_iteration": int(model.best_iteration),
        "xgboost_version": "3.2.0",
        "evaluation": metrics,
    }
    with open(MODELS_DIR / "xshot_v1_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved xshot_v1_metadata.json")


def main():
    df = load_data()
    X_train, y_train, X_test, y_test = split_data(df)
    model = train(X_train, y_train, X_test, y_test)
    preds, metrics = evaluate(model, X_test, y_test)
    export_artifacts(model, X_test, y_test, preds, metrics)
    save_model(model, metrics)
    logger.info("Training complete.")


if __name__ == "__main__":
    main()
