"""
Tests for the xShot model artifact — verifies the saved model loads,
predicts in the expected probability range, and has expected metadata.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import json
import pickle
import pytest
import numpy as np

MODELS_DIR = _root / "models"
MODEL_PATH = MODELS_DIR / "xshot_v1.pkl"
METADATA_PATH = MODELS_DIR / "xshot_v1_metadata.json"
FEATURE_IMPORTANCE_PATH = MODELS_DIR / "feature_importance.json"


class TestModelArtifacts:
    def test_model_file_exists(self):
        assert MODEL_PATH.exists(), f"Model file not found: {MODEL_PATH}"

    def test_metadata_file_exists(self):
        assert METADATA_PATH.exists(), f"Metadata file not found: {METADATA_PATH}"

    def test_feature_importance_file_exists(self):
        assert FEATURE_IMPORTANCE_PATH.exists()

    def test_metadata_has_required_keys(self):
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        required = {"features", "feature_count", "train_seasons", "test_seasons", "evaluation"}
        missing = required - set(meta.keys())
        assert not missing, f"Missing metadata keys: {missing}"

    def test_metadata_feature_count_reasonable(self):
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        n_features = len(meta["features"])
        assert 10 <= n_features <= 100, f"Unexpected feature count: {n_features}"

    def test_feature_importance_nonempty(self):
        with open(FEATURE_IMPORTANCE_PATH) as f:
            fi = json.load(f)
        assert len(fi) > 0

    def test_model_loads(self):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        assert model is not None

    def test_model_predicts_probabilities(self):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        with open(METADATA_PATH) as f:
            meta = json.load(f)

        features = meta["features"]
        n = len(features)
        X = np.zeros((5, n))

        preds = model.predict_proba(X)[:, 1]
        assert preds.shape == (5,)
        assert (preds >= 0).all() and (preds <= 1).all(), \
            "Model outputs outside [0, 1]"
        assert preds.mean() < 0.8, "Predictions look unreasonably high for zero-input shots"
