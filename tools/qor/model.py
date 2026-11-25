"""Brief 177: small tabular predictors in numpy only (no sklearn in the flow's environment).

LogReg: L2 logistic regression on standardised features, fitted by Newton steps.
Stumps: gradient-boosted decision stumps (log-loss), a tree-ensemble stand-in at this data size.
auc, brier, reliability, go_stats: the measures the brief asks for.
"""
from __future__ import annotations
import numpy as np


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class LogReg:
    def __init__(self, l2=1.0, iters=50):
        self.l2, self.iters = l2, iters

    def fit(self, X, y):
        X = np.asarray(X, float); y = np.asarray(y, float)
        self.mu = X.mean(0); self.sd = X.std(0); self.sd[self.sd == 0] = 1.0
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]
        w = np.zeros(Z.shape[1]); R = self.l2 * np.eye(Z.shape[1]); R[0, 0] = 0
        for _ in range(self.iters):
            p = sigmoid(Z @ w)
            g = Z.T @ (p - y) + R @ w
            H = (Z * (p * (1 - p))[:, None]).T @ Z + R + 1e-6 * np.eye(Z.shape[1])
            step = np.linalg.solve(H, g)
            w -= step
            if np.abs(step).max() < 1e-8:
                break
        self.w = w
        return self

    def predict_proba(self, X):
        X = np.asarray(X, float)
        return sigmoid(np.c_[np.ones(len(X)), (X - self.mu) / self.sd] @ self.w)


class Stumps:
    def __init__(self, rounds=60, lr=0.2):
        self.rounds, self.lr = rounds, lr

    def fit(self, X, y):
        X = np.asarray(X, float); y = np.asarray(y, float)
        p0 = min(max(y.mean(), 1e-3), 1 - 1e-3)
        self.f0 = np.log(p0 / (1 - p0)); F = np.full(len(y), self.f0); self.stumps = []
        for _ in range(self.rounds):
            r = y - sigmoid(F); best = None
            for j in range(X.shape[1]):
                for t in np.unique(X[:, j])[:-1]:
                    m = X[:, j] <= t
                    if m.sum() < 3 or (~m).sum() < 3:
                        continue
                    a, b = r[m].mean(), r[~m].mean()
                    loss = ((r[m] - a) ** 2).sum() + ((r[~m] - b) ** 2).sum()
                    if best is None or loss < best[0]:
                        best = (loss, j, t, a, b)
            if best is None:
                break
            _, j, t, a, b = best
            self.stumps.append((j, t, a * 4 * self.lr, b * 4 * self.lr))
            F += np.where(X[:, j] <= t, a, b) * 4 * self.lr
        return self

    def predict_proba(self, X):
        X = np.asarray(X, float); F = np.full(len(X), self.f0)
        for j, t, a, b in self.stumps:
            F += np.where(X[:, j] <= t, a, b)
        return sigmoid(F)


def auc(y, s):
    y = np.asarray(y); s = np.asarray(s, float)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def brier(y, p):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def reliability(y, p, bins=(0, 0.2, 0.4, 0.6, 0.8, 1.0001)):
    y = np.asarray(y); p = np.asarray(p); out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.any():
            out.append((lo, min(hi, 1.0), int(m.sum()), float(p[m].mean()), float(y[m].mean())))
    return out


def go_stats(y, p, t):
    """go = predicted pass (p >= t). false-go = routed fail among the go builds; saved = fraction of all builds
    that are no-go AND would have failed (a failing route not paid for); lost = passing builds wrongly held back."""
    y = np.asarray(y); go = np.asarray(p) >= t
    n_go = int(go.sum()); fails = int((y == 0).sum())
    return dict(t=t, n_go=n_go, false_go=int(((y == 0) & go).sum()),
                false_go_rate=float(((y == 0) & go).sum() / n_go) if n_go else float("nan"),
                saved_fail_builds=int(((y == 0) & ~go).sum()), fails=fails,
                saved_fraction_of_fails=float(((y == 0) & ~go).sum() / fails) if fails else float("nan"),
                wrongly_held=int(((y == 1) & ~go).sum()), passes=int((y == 1).sum()))
