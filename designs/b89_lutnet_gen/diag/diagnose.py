"""Brief 89 step 1: why did the brief 87 LUT network lose to the trivial rule? Short experiments on the train and
validation splits only (the test split is not loaded here). Writes results/b89/diagnosis.json.

    python3 -m designs.b89_lutnet_gen.diag.diagnose [--only D1 D2 ...]

D0  the 87 network itself, retrained exactly (its own code), seeds 0-2: train and validation accuracy, and how many
    neurons are constant or use few of their output codes
D1  input coding: the 87 tree ensemble (10 rounds x depth 3) on raw features, on the 87 2-bit quantile codes, and on
    3- and 4-bit codes; also logistic regression on the same
D2  the ceiling: a large tree ensemble on raw features (train against validation shows label noise / over-fitting)
D3  fan-in and wiring: the 87 tree ensemble restricted to each 3-feature subset (what one first-layer neuron can see),
    and which subsets the 87 seed-0 wiring chose
D4  training method: the 87 sparse structure trained with float hidden values (no quantisation) against the 87
    quantised training, both with the same vectorised trainer; and with BatchNorm before the quantiser
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np

from designs.b89_lutnet_gen.lutgen import data as Dm

ROOT = Dm.ROOT
OUT = ROOT / "results" / "b89" / "diagnosis.json"


def codes(X, Xtr, bits):
    """Quantile codes with 2^bits - 1 thresholds from the training split (87 used bits=2)."""
    n = (1 << bits) - 1
    cols = []
    for j in range(X.shape[1]):
        th = sorted({int(np.quantile(Xtr[:, j], (i + 1) / (n + 1))) for i in range(n)})
        cols.append((X[:, j:j + 1] > np.array(th)).sum(axis=1))
    return np.stack(cols, axis=1)


def gbt(Xa, ya, Xb, yb, n=10, depth=3, lr=0.3, seed=0):
    from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
    if n <= 20:
        m = GradientBoostingClassifier(n_estimators=n, max_depth=depth, learning_rate=lr, subsample=0.8,
                                       random_state=seed).fit(Xa, ya)
    else:
        m = HistGradientBoostingClassifier(max_iter=n, max_depth=depth, learning_rate=lr, random_state=seed).fit(Xa, ya)
    return round(float((m.predict(Xa) == ya).mean()), 4), round(float((m.predict(Xb) == yb).mean()), 4)


def logreg(Xa, ya, Xb, yb, onehot=False):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    if onehot:
        e = OneHotEncoder(handle_unknown="ignore").fit(Xa)
        A, B = e.transform(Xa), e.transform(Xb)
    else:
        s = StandardScaler().fit(Xa)
        A, B = s.transform(Xa), s.transform(Xb)
    m = LogisticRegression(max_iter=500).fit(A, ya)
    return round(float((m.predict(A) == ya).mean()), 4), round(float((m.predict(B) == yb).mean()), 4)


# ------------------------------------------------------------------------- a vectorised trainer of the 87 structure
def sparse_net(Ctr, ytr, Cv, yv, seed, layers=((16, 3, 2), (8, 3, 2), (3, 4, 4)), in_levels=4, epochs=10,
               quant=True, bn=False, hidden=16):
    """The 87 structure (each neuron: k wired inputs -> 16 -> 16 -> 1 MLP; hidden outputs 2-bit via sigmoid*3 and
    rounding; output 4-bit signed by rounding), trained the same way (Adam 3e-3, batch 512, straight-through), but
    all neurons of a layer in one batched matmul. quant=False keeps the hidden values float (sigmoid*3) and the
    scores float: an upper bound for the sparse structure. bn=True puts a BatchNorm before each quantiser."""
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_in, wiring, params = Ctr.shape[1], [], []
    mods = []
    for (n, k, _) in layers:
        wiring.append(torch.tensor(np.array([sorted(rng.choice(n_in, size=k, replace=False)) for _ in range(n)])))
        n_in = n
        W1 = torch.nn.Parameter(torch.randn(n, k, hidden) / np.sqrt(k)); b1 = torch.nn.Parameter(torch.zeros(n, hidden))
        W2 = torch.nn.Parameter(torch.randn(n, hidden, hidden) / np.sqrt(hidden)); b2 = torch.nn.Parameter(torch.zeros(n, hidden))
        W3 = torch.nn.Parameter(torch.randn(n, hidden, 1) / np.sqrt(hidden)); b3 = torch.nn.Parameter(torch.zeros(n, 1))
        m = [W1, b1, W2, b2, W3, b3]
        if bn:
            m.append(torch.nn.BatchNorm1d(n))
        mods.append(m)
        params += [p for p in m[:6]] + (list(m[6].parameters()) if bn else [])

    def fwd(x, train=True):
        for li, (n, k, bits) in enumerate(layers):
            W1, b1, W2, b2, W3, b3 = mods[li][:6]
            xi = x[:, wiring[li]] / (in_levels - 1 if li == 0 else 3.0)          # (B, n, k)
            h = torch.relu(torch.einsum("bnk,nkh->bnh", xi, W1) + b1)
            h = torch.relu(torch.einsum("bnh,nhg->bng", h, W2) + b2)
            z = torch.einsum("bnh,nho->bno", h, W3).squeeze(-1) + b3.squeeze(-1)
            if bn:
                mods[li][6].train(train)
                z = mods[li][6](z)
            last = li == len(layers) - 1
            if last:
                zq = torch.clamp(torch.round(z), -(1 << (bits - 1)), (1 << (bits - 1)) - 1)
                x = z + (zq - z).detach() if quant else z
            else:
                s = torch.sigmoid(z) * ((1 << bits) - 1)
                x = s + (torch.round(s) - s).detach() if quant else s
        return x

    ct, yt = torch.tensor(Ctr, dtype=torch.float32), torch.tensor(ytr)
    cv = torch.tensor(Cv, dtype=torch.float32)
    opt = torch.optim.Adam(params, lr=3e-3)
    g = torch.Generator().manual_seed(seed)
    hist = []
    for ep in range(epochs):
        perm = torch.randperm(len(ct), generator=g)
        for j in range(0, len(ct), 512):
            b = perm[j:j + 512]
            loss = torch.nn.functional.cross_entropy(fwd(ct[b]), yt[b])
            opt.zero_grad(); loss.backward(); opt.step()
        with torch.no_grad():
            hist.append(round(float((fwd(cv, False).argmax(1).numpy() == yv).mean()), 4))
    with torch.no_grad():
        tr = float((fwd(ct, False).argmax(1).numpy() == ytr).mean())
    return {"train": round(tr, 4), "val": hist[-1], "val_by_epoch": hist}


def d0(tr, va):
    """The 87 LUT network, retrained with its own code; neuron usage on the training split."""
    from designs.b87_ml_trading.model import arms as A
    out = []
    for s in (0, 1, 2):
        t0 = time.time()
        q = A.lut_fit(tr[0], tr[1], va[0], va[1], s)
        x = A.lut_codes(q["thresholds"], tr[0]).astype(np.int64)
        usage = []
        for li, (n, k, bits) in enumerate(q["layers"]):
            in_bits = 2 if li == 0 else q["layers"][li - 1][2]
            outs = []
            for j in range(n):
                addr = np.zeros(len(x), dtype=np.int64)
                for c in q["wiring"][li][j]:
                    addr = (addr << in_bits) | x[:, c]
                outs.append(np.array(q["tables"][li][j], dtype=np.int64)[addr])
            x = np.stack(outs, axis=1)
            usage.append([int(len(np.unique(x[:, j]))) for j in range(n)])
        pv = A.lut_predict_int(q, va[0])
        pt = A.lut_predict_int(q, tr[0])
        sc = A.lut_scores_int(q, va[0])
        ties = float((np.sort(sc, axis=1)[:, -1] == np.sort(sc, axis=1)[:, -2]).mean())
        out.append({"seed": s, "train": round(float((pt == tr[1]).mean()), 4), "val": round(float((pv == va[1]).mean()), 4),
                    "distinct_output_codes_per_neuron": usage,
                    "constant_neurons": [sum(1 for u in L if u == 1) for L in usage],
                    "val_share_with_tied_top_score": round(ties, 4),
                    "val_class_share_predicted": (np.bincount(pv, minlength=3) / len(pv)).round(4).tolist(),
                    "first_layer_wiring": q["wiring"][0], "seconds": round(time.time() - t0, 1)})
        print("D0", out[-1]["seed"], out[-1]["train"], out[-1]["val"], out[-1]["constant_neurons"], flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    d = Dm.load(("train", "val"))
    tr, va = d["train"], d["val"]
    Xtr, ytr, Xv, yv = tr[0], tr[1], va[0], va[1]
    rec = json.loads(OUT.read_text()) if OUT.exists() else {"schema": "b89-diagnosis/1", "splits_used": ["train", "val"]}
    run = lambda k: a.only is None or k in a.only
    if run("D1"):
        r = {"gbt_87cfg": {"raw": gbt(Xtr, ytr, Xv, yv)}, "logreg": {"raw": logreg(Xtr, ytr, Xv, yv)}}
        for b in (1, 2, 3, 4):
            Ct, Cv = codes(Xtr, Xtr, b), codes(Xv, Xtr, b)
            r["gbt_87cfg"][f"codes_{b}bit"] = gbt(Ct, ytr, Cv, yv)
            r["logreg"][f"onehot_codes_{b}bit"] = logreg(Ct, ytr, Cv, yv, onehot=True)
        Ct = codes(Xtr, Xtr, 2)
        r["distinct_2bit_codes_used_per_feature"] = [int(len(np.unique(Ct[:, j]))) for j in range(7)]
        r["note"] = "[train, val] accuracy; codes are quantile thresholds from train (87 used 2 bits)"
        rec["D1_input_coding"] = r
        print("D1", json.dumps(r), flush=True)
    if run("D2"):
        r = {}
        for n, dep in ((100, 4), (300, 6)):
            r[f"hgb_{n}x{dep}"] = gbt(Xtr, ytr, Xv, yv, n=n, depth=dep, lr=0.1)
        r["imbalance_rule_val"] = json.loads(Dm.B87_ACC.read_text())["arms"]["imbalance_rule"]["fit"]["val_accuracy"]
        r["note"] = "[train, val]; a large ensemble's validation accuracy is our estimate of what the features allow"
        rec["D2_ceiling"] = r
        print("D2", json.dumps(r), flush=True)
    if run("D3"):
        names = ["bid_sz", "ask_sz", "spread", "imb_bucket", "trade_sign_sum", "ofi16", "last_mid_dir"]
        subs = {}
        for c in itertools.combinations(range(7), 3):
            subs["+".join(names[i] for i in c)] = gbt(Xtr[:, c], ytr, Xv[:, c], yv)[1]
        single = {names[i]: gbt(Xtr[:, [i]], ytr, Xv[:, [i]], yv)[1] for i in range(7)}
        rec["D3_fan_in"] = {"single_feature_val": single,
                            "three_feature_subsets_val": dict(sorted(subs.items(), key=lambda t: -t[1])),
                            "note": "validation accuracy of the 87 tree config restricted to these raw features"}
        print("D3", json.dumps(single), list(rec["D3_fan_in"]["three_feature_subsets_val"].items())[:5], flush=True)
    if run("D4"):
        Ct, Cv = codes(Xtr, Xtr, 2), codes(Xv, Xtr, 2)
        r = {}
        for tag, kw in (("quantised_87", {}), ("float_hidden", {"quant": False}), ("quantised_bn", {"bn": True})):
            r[tag] = [sparse_net(Ct, ytr, Cv, yv, s, **kw) for s in (0, 1, 2)]
            print("D4", tag, [(x["train"], x["val"]) for x in r[tag]], flush=True)
        C3t, C3v = codes(Xtr, Xtr, 3), codes(Xv, Xtr, 3)
        r["float_hidden_3bit_inputs"] = [sparse_net(C3t, ytr, C3v, yv, s, quant=False, in_levels=8) for s in (0, 1, 2)]
        print("D4 f3", [(x["train"], x["val"]) for x in r["float_hidden_3bit_inputs"]], flush=True)
        r["note"] = ("vectorised re-implementation of the 87 structure, 10 epochs; same wiring draw as 87 for a seed "
                     "(numpy default_rng(seed).choice per neuron)")
        rec["D4_training"] = r
    if run("D0"):
        rec["D0_b87_network"] = d0(tr, va)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
