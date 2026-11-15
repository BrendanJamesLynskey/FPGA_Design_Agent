"""The decision arms: baselines, a boosted-tree ensemble, a small MLP and a LUT network, each trained in floating
point and then quantised to the integer form the RTL computes. Every `predict_int` here is the bit-exact reference
for the matching RTL (tests/test_b87_rtl.py compares them over the whole test split).

Training uses the train split only; every threshold or hyperparameter that is tuned is tuned on the validation split;
the test split is touched once, by evaluate.py, after the models are written.
"""
from __future__ import annotations

import math

import numpy as np

NF = 7          # features
NC = 3          # classes: 0 down, 1 flat, 2 up


def argmax_int(s: np.ndarray) -> np.ndarray:
    """Argmax with ties to the lowest class index (the RTL compares with >, so an equal later score never wins)."""
    return np.argmax(s, axis=1)


# ---------------------------------------------------------------------------------------------------------- baselines
def imbalance_rule_fit(Xv: np.ndarray, yv: np.ndarray) -> dict:
    """The trivial rule: up if the imbalance bucket >= hi, down if <= lo, else flat; (lo, hi) chosen on validation."""
    best = None
    for lo in range(-1, 7):
        for hi in range(lo + 1, 9):
            acc = float((imbalance_rule_predict({"lo": lo, "hi": hi}, Xv) == yv).mean())
            if best is None or acc > best[0]:
                best = (acc, lo, hi)
    return {"lo": best[1], "hi": best[2], "val_accuracy": best[0]}


def imbalance_rule_predict(m: dict, X: np.ndarray) -> np.ndarray:
    b = X[:, 3]
    return np.where(b >= m["hi"], 2, np.where(b <= m["lo"], 0, 1))


# ---------------------------------------------------------------------------------------------- (a) boosted trees
def gbt_fit(X, y, seed: int, n_rounds: int = 10, depth: int = 3, lr: float = 0.3):
    from sklearn.ensemble import GradientBoostingClassifier
    m = GradientBoostingClassifier(n_estimators=n_rounds, max_depth=depth, learning_rate=lr, subsample=0.8,
                                   random_state=seed)
    m.fit(X, y)
    return m


def gbt_quantise(m, frac_bits: int = 8) -> dict:
    """Integer form: thresholds become `x <= floor(t)` on the integer features (exact), leaf values and the prior
    become signed fixed point with `frac_bits` fraction bits; the class score is the integer sum."""
    init = m.init_.predict_proba(np.zeros((1, NF)))[0] if hasattr(m.init_, "predict_proba") else None
    prior = np.log(np.clip(init, 1e-12, 1)) if init is not None else np.zeros(NC)
    sc = 1 << frac_bits
    trees = []                                  # per round, per class
    for r in range(m.estimators_.shape[0]):
        for k in range(NC):
            t = m.estimators_[r, k].tree_
            nodes = []
            for i in range(t.node_count):
                if t.children_left[i] == -1:
                    nodes.append({"leaf": int(round(m.learning_rate * float(t.value[i].ravel()[0]) * sc))})
                else:
                    nodes.append({"f": int(t.feature[i]), "t": int(math.floor(t.threshold[i])),
                                  "l": int(t.children_left[i]), "r": int(t.children_right[i])})
            trees.append({"round": r, "cls": k, "nodes": nodes})
    return {"kind": "gbt", "frac_bits": frac_bits, "prior": [int(round(p * sc)) for p in prior],
            "depth": int(m.max_depth), "trees": trees}


def gbt_scores_int(q: dict, X: np.ndarray) -> np.ndarray:
    s = np.tile(np.array(q["prior"], dtype=np.int64), (len(X), 1))
    for tr in q["trees"]:
        nd = tr["nodes"]
        idx = np.zeros(len(X), dtype=np.int64)
        for _ in range(q["depth"] + 1):
            out = idx.copy()
            for i, n in enumerate(nd):
                if "leaf" in n:
                    continue
                sel = idx == i
                out[sel] = np.where(X[sel, n["f"]] <= n["t"], n["l"], n["r"])
            idx = out
        leaf = np.array([n.get("leaf", 0) for n in nd], dtype=np.int64)
        s[:, tr["cls"]] += leaf[idx]
    return s


def gbt_predict_int(q, X):
    return argmax_int(gbt_scores_int(q, X))


# ------------------------------------------------------------------------------------------------------- (b) MLP
MLP_OFFSETS = np.array([0, 0, 0, 0, 8, 128, 1])      # the fabric subtracts these: signed inputs
MLP_FIN = 6                                           # input scale 2^-6
MLP_SIZES = (NF, 16, 8, NC)


def _mlp_torch(seed):
    import torch
    torch.manual_seed(seed)
    return torch.nn.ModuleList([torch.nn.Linear(a, b) for a, b in zip(MLP_SIZES[:-1], MLP_SIZES[1:])])


def mlp_fit(X, y, Xv, yv, seed: int, epochs: int = 30, qat_epochs: int = 15) -> dict:
    """Float training, then quantisation-aware fine-tuning with the exact integer arithmetic of the RTL (straight-
    through gradients). Weights: int8 with a power-of-two scale per layer; activations: uint8 after ReLU with a
    power-of-two scale per layer, floor rounding and saturation. Returns the float and the integer model."""
    import torch
    torch.set_num_threads(2)
    layers = _mlp_torch(seed)
    xt = torch.tensor((X - MLP_OFFSETS) / 2 ** MLP_FIN, dtype=torch.float32)
    yt = torch.tensor(y)
    opt = torch.optim.Adam(layers.parameters(), lr=3e-3)
    g = torch.Generator().manual_seed(seed)

    def fwd(x, q=None):
        for i, L in enumerate(layers):
            if q is None:
                x = L(x)
            else:
                fw, fin = q["fw"][i], q["fin"][i]
                w = L.weight + (torch.clamp(torch.round(L.weight * 2 ** fw), -128, 127) / 2 ** fw - L.weight).detach()
                bsc = 2 ** (fw + fin)
                b = L.bias + (torch.round(L.bias * bsc) / bsc - L.bias).detach()
                x = x @ w.T + b
            if i < len(layers) - 1:
                x = torch.relu(x)
                if q is not None:
                    fa = q["fa"][i]
                    xq = torch.clamp(torch.floor(x * 2 ** fa), 0, 255) / 2 ** fa
                    x = x + (xq - x).detach()
        return x

    def train(nep, q=None, lr=3e-3):
        for gr in opt.param_groups:
            gr["lr"] = lr
        for _ in range(nep):
            perm = torch.randperm(len(xt), generator=g)
            for j in range(0, len(xt), 512):
                b = perm[j:j + 512]
                loss = torch.nn.functional.cross_entropy(fwd(xt[b], q), yt[b])
                opt.zero_grad()
                loss.backward()
                opt.step()

    train(epochs)
    with torch.no_grad():
        flt = {"W": [L.weight.numpy().copy() for L in layers], "b": [L.bias.numpy().copy() for L in layers]}
        # scales: weights from the float weights; activations from the 99.9th percentile on the training split
        fw = [int(math.floor(math.log2(127 / float(L.weight.abs().max())))) for L in layers]
        fa, fin, x = [], [MLP_FIN], xt
        for i, L in enumerate(layers[:-1]):
            x = torch.relu(L(x))
            p = float(torch.quantile(x[:20000].flatten(), 0.999)) or 1.0
            fa.append(int(math.floor(math.log2(255 / p))))
            fin.append(fa[-1])
    q = {"fw": fw, "fa": fa, "fin": fin}
    train(qat_epochs, q, lr=1e-3)
    with torch.no_grad():
        Wi = [np.clip(np.round(L.weight.numpy() * 2 ** fw[i]), -128, 127).astype(np.int64) for i, L in enumerate(layers)]
        bi = [np.round(L.bias.numpy() * 2 ** (fw[i] + fin[i])).astype(np.int64) for i, L in enumerate(layers)]
    qm = {"kind": "mlp", "sizes": list(MLP_SIZES), "offsets": MLP_OFFSETS.tolist(), "fin": fin, "fw": fw, "fa": fa,
          "W": [w.tolist() for w in Wi], "b": [b.tolist() for b in bi]}
    return {"float": flt, "int": qm}


def mlp_float_predict(f, X):
    x = (X - MLP_OFFSETS) / 2 ** MLP_FIN
    for i, (W, b) in enumerate(zip(f["W"], f["b"])):
        x = x @ W.T + b
        if i < len(f["W"]) - 1:
            x = np.maximum(x, 0)
    return np.argmax(x, axis=1)


def mlp_logits_int(q: dict, X: np.ndarray) -> np.ndarray:
    x = (X - np.array(q["offsets"])).astype(np.int64)
    n = len(q["W"])
    for i in range(n):
        acc = x @ np.array(q["W"][i], dtype=np.int64).T + np.array(q["b"][i], dtype=np.int64)
        if i == n - 1:
            return acc
        sh = q["fw"][i] + q["fin"][i] - q["fa"][i]
        a = acc >> sh if sh >= 0 else acc << -sh            # arithmetic shift: floor
        x = np.clip(a, 0, 255)


def mlp_predict_int(q, X):
    return argmax_int(mlp_logits_int(q, X))


# ------------------------------------------------------------------------------------------------ (c) LUT network
# Our own generator in the style of LogicNets / NeuraLUT (method only; no code from either): every input feature is
# cut to a 2-bit code by three integer thresholds; each neuron sees a few codes (sparse, fixed random wiring), is
# trained as a small dense sub-network, and is then enumerated over all its input codes into a truth table, which the
# RTL holds as a LUT. Output neurons give a 4-bit signed score per class.
LUT_LAYERS = ((16, 3, 2), (8, 3, 2), (NC, 4, 4))     # (neurons, fan-in, output bits) per layer


def lut_input_thresholds(X) -> list[list[int]]:
    th = []
    for j in range(NF):
        qs = sorted({int(np.quantile(X[:, j], p)) for p in (0.25, 0.5, 0.75)})
        while len(qs) < 3:
            qs.append(qs[-1] + 1)
        th.append(qs)
    return th


def lut_codes(th, X) -> np.ndarray:
    return np.stack([(X[:, j:j + 1] > np.array(th[j])).sum(axis=1) for j in range(NF)], axis=1)   # 0..3


def lut_fit(X, y, Xv, yv, seed: int, epochs: int = 25) -> dict:
    import torch
    torch.set_num_threads(2)
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    th = lut_input_thresholds(X)
    wiring, n_in = [], NF
    for (n, k, _) in LUT_LAYERS:
        wiring.append([sorted(rng.choice(n_in, size=k, replace=False).tolist()) for _ in range(n)])
        n_in = n
    subs = torch.nn.ModuleList()
    for (n, k, _) in LUT_LAYERS:
        subs.append(torch.nn.ModuleList([torch.nn.Sequential(torch.nn.Linear(k, 16), torch.nn.ReLU(),
                                                             torch.nn.Linear(16, 16), torch.nn.ReLU(),
                                                             torch.nn.Linear(16, 1)) for _ in range(n)]))

    def q_out(z, bits, last):
        if last:                                   # signed 4-bit score
            zq = torch.clamp(torch.round(z), -(1 << (bits - 1)), (1 << (bits - 1)) - 1)
        else:                                      # unsigned 2-bit code
            zq = torch.clamp(torch.round(torch.sigmoid(z) * ((1 << bits) - 1)), 0, (1 << bits) - 1)
            z = torch.sigmoid(z) * ((1 << bits) - 1)
        return z + (zq - z).detach()

    def fwd(c):                                     # c: codes (N, NF) float 0..3
        x = c
        for li, (n, k, bits) in enumerate(LUT_LAYERS):
            outs = [q_out(subs[li][j](x[:, wiring[li][j]] / 3.0), bits, li == len(LUT_LAYERS) - 1)
                    for j in range(n)]
            x = torch.cat(outs, dim=1)
        return x

    ct = torch.tensor(lut_codes(th, X), dtype=torch.float32)
    yt = torch.tensor(y)
    opt = torch.optim.Adam(subs.parameters(), lr=3e-3)
    g = torch.Generator().manual_seed(seed)
    for _ in range(epochs):
        perm = torch.randperm(len(ct), generator=g)
        for j in range(0, len(ct), 512):
            b = perm[j:j + 512]
            loss = torch.nn.functional.cross_entropy(fwd(ct[b]), yt[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
    # enumerate each neuron into its truth table
    tables = []
    with torch.no_grad():
        for li, (n, k, bits) in enumerate(LUT_LAYERS):
            in_bits = 2 if li == 0 else LUT_LAYERS[li - 1][2]
            combos = np.array(np.meshgrid(*[np.arange(1 << in_bits)] * k, indexing="ij")).reshape(k, -1).T
            # address = concatenation, first wired input in the most significant bits
            addr = np.zeros(len(combos), dtype=np.int64)
            for c in range(k):
                addr = (addr << in_bits) | combos[:, c]
            lt = []
            for j in range(n):
                z = subs[li][j](torch.tensor(combos / 3.0 if li == 0 else combos / 3.0, dtype=torch.float32))
                o = q_out(z, bits, li == len(LUT_LAYERS) - 1).numpy().ravel().astype(np.int64)
                tab = np.zeros(1 << (in_bits * k), dtype=np.int64)
                tab[addr] = o
                lt.append(tab.tolist())
            tables.append(lt)
    return {"kind": "lutnet", "thresholds": th, "layers": [list(x) for x in LUT_LAYERS], "wiring": wiring,
            "tables": tables}


def lut_scores_int(q: dict, X: np.ndarray) -> np.ndarray:
    x = lut_codes(q["thresholds"], X).astype(np.int64)
    for li, (n, k, bits) in enumerate(q["layers"]):
        in_bits = 2 if li == 0 else q["layers"][li - 1][2]
        outs = []
        for j in range(n):
            addr = np.zeros(len(x), dtype=np.int64)
            for c in q["wiring"][li][j]:
                addr = (addr << in_bits) | x[:, c]
            outs.append(np.array(q["tables"][li][j], dtype=np.int64)[addr])
        x = np.stack(outs, axis=1)
    return x


def lut_predict_int(q, X):
    return argmax_int(lut_scores_int(q, X))
