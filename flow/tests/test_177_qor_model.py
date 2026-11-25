"""Brief 177: the numpy predictors and the measures behind results/177_qor/evaluation.json."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/qor"))
from model import LogReg, Stumps, auc, go_stats  # noqa: E402


def test_auc_and_go_stats_on_a_known_case():
    y = np.array([1, 1, 0, 0]); p = np.array([0.9, 0.6, 0.7, 0.1])
    assert abs(auc(y, p) - 0.75) < 1e-9
    g = go_stats(y, p, 0.65)
    assert g["n_go"] == 2 and g["false_go"] == 1 and g["saved_fail_builds"] == 1 and g["wrongly_held"] == 1


def test_models_learn_a_separable_rule():
    rng = np.random.default_rng(1); X = rng.normal(size=(120, 3)); y = (X[:, 0] > 0).astype(int)
    for m in (LogReg(), Stumps(rounds=20)):
        assert auc(y, m.fit(X, y).predict_proba(X)) > 0.95
