"""lutgen: a LUT-network generator. A network whose neurons each see a few quantised inputs is trained with the
quantisers in the loop, every neuron is enumerated into a truth table, and the tables are the model: the bit-exact
Python twin (`twin_scores`) and the RTL (rtl.py) are both read from them.

Method (our own code; the ideas are described with their sources in docs/design.md, no code from any of them):

1. Input encoder. Feature j (an unsigned integer) becomes a code c_j = #{t in T_j : x_j > t}, a count of threshold
   compares, so c_j is in 0 .. len(T_j). Thresholds come from the training split only: `quantile` (equal-population
   cuts), or `tree` (the split points a small boosted-tree ensemble on the training split uses most for that feature).
   A feature with no more distinct training values than codes is passed through exactly (thresholds min .. max-1).
2. Layers. Layer l has n_l neurons; each neuron reads fan_in codes of the previous layer (layer 1 reads the input
   codes), chosen once at construction: `random` (every input used at least once, then uniform), or `greedy` (layer 1
   only: subsets ranked by the training-split accuracy of a tiny tree on those features; later layers random).
   A neuron is a small dense float network (inputs -> hidden x depth -> 1) with BatchNorm, and its output is quantised
   to out_bits: a hidden code 0 .. 2^b-1 via a sigmoid and rounding, or for the score layer a signed integer by
   rounding and clamping. Rounding uses a straight-through gradient.
3. Output. `direct`: the last layer has one neuron per class and its outputs are the class scores. `additive`: the
   last layer has `per_class` neurons per class and each class score is the sum of its neurons' outputs.
4. Training: Adam with cosine decay, cross-entropy on the scores. The epoch kept is the one with the best validation
   accuracy (validation is used for model selection only; the test split is never seen here).
5. Enumeration: each neuron is evaluated in inference mode on every combination of its input codes, which gives its
   truth table. From here on only the tables exist.

Every option is a field of `Config` with its default and its meaning; docs/generator.md lists them with the ways a
user could guess them wrong.
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass, field

import numpy as np

MAX_ADDR_BITS = 12          # a neuron's table has 2^(fan_in x input bits) entries; refuse more than 4096


@dataclass
class Config:
    in_bits: list = field(default_factory=lambda: [2] * 7)   # code bits per input feature (codes 0 .. 2^b - 1)
    thresholds: str = "quantile"                              # "quantile" or "tree"
    layers: list = field(default_factory=lambda: [[16, 3, 2], [8, 3, 2]])  # hidden layers: [neurons, fan_in, out_bits]
    out_fan_in: int = 4                                       # fan-in of each score neuron
    out_bits: int = 4                                         # signed score bits of each score neuron
    output: str = "direct"                                    # "direct" (1 neuron per class) or "additive"
    per_class: int = 1                                        # score neurons per class when output = "additive"
    wiring: str = "random"                                    # "random" or "greedy" (layer 1 only)
    hidden: int = 16                                          # width of each neuron's inner float network
    depth: int = 2                                            # hidden layers inside each neuron
    batchnorm: bool = True                                    # BatchNorm before each quantiser
    freeze_bn: int = 0                                        # last epochs with BatchNorm statistics frozen
    learn_temperature: bool = False                           # loss on scores x a learned positive scale
    epochs: int = 20
    lr: float = 3e-3
    batch: int = 1024
    seed: int = 0
    n_classes: int = 3

    def to_dict(self):
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d):
        return Config(**{k: v for k, v in d.items() if k in {f.name for f in dataclasses.fields(Config)}})


# ------------------------------------------------------------------------------------------------------- encoder
def fit_thresholds(cfg: Config, X: np.ndarray, y: np.ndarray) -> list[list[int]]:
    th = []
    tree_cuts = _tree_cuts(X, y, cfg.seed) if cfg.thresholds == "tree" else None
    for j in range(X.shape[1]):
        n = (1 << cfg.in_bits[j]) - 1
        lo, hi = int(X[:, j].min()), int(X[:, j].max())
        if hi - lo <= n:                                   # exact pass-through: codes 0 .. hi-lo
            th.append(list(range(lo, hi)))
            continue
        if tree_cuts is not None and tree_cuts[j]:
            cuts = [t for t, _ in sorted(tree_cuts[j].items(), key=lambda t: -t[1])[:n]]
            th.append(sorted(cuts))
            continue
        qs = sorted({int(np.quantile(X[:, j], (i + 1) / (n + 1))) for i in range(n)})
        th.append([t for t in qs if lo <= t < hi])
    return th


def _tree_cuts(X, y, seed):
    """Integer split points of a small boosted-tree ensemble on the training split, with how often each is used."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=30, max_depth=3, learning_rate=0.2, random_state=seed).fit(X, y)
    cuts = [dict() for _ in range(X.shape[1])]
    for per_class in m._predictors:
        for p in per_class:
            for nd in p.nodes:
                if not nd["is_leaf"]:
                    f = int(nd["feature_idx"])
                    t = int(math.floor(nd["num_threshold"]))      # x <= threshold  <=>  x <= floor(t) for integers
                    cuts[f][t] = cuts[f].get(t, 0) + 1
    return cuts


def encode(th: list[list[int]], X: np.ndarray) -> np.ndarray:
    return np.stack([(X[:, j:j + 1] > np.array(t, dtype=np.int64)).sum(axis=1) if t else np.zeros(len(X), np.int64)
                     for j, t in enumerate(th)], axis=1).astype(np.int64)


def code_bits(th):
    return [max(1, math.ceil(math.log2(len(t) + 1))) for t in th]


# ------------------------------------------------------------------------------------------------------ structure
def layer_specs(cfg: Config) -> list[dict]:
    """[{n, k, bits, signed}] for every layer including the score layer."""
    L = [{"n": n, "k": k, "bits": b, "signed": False} for n, k, b in cfg.layers]
    n_out = cfg.n_classes * (cfg.per_class if cfg.output == "additive" else 1)
    L.append({"n": n_out, "k": cfg.out_fan_in, "bits": cfg.out_bits, "signed": True})
    return L


def make_wiring(cfg: Config, in_bits_eff, Xc=None, y=None) -> list[list[list[int]]]:
    rng = np.random.default_rng(cfg.seed)
    wiring, n_in = [], len(in_bits_eff)
    for li, sp in enumerate(layer_specs(cfg)):
        k = min(sp["k"], n_in)
        if li == 0 and cfg.wiring == "greedy":
            w = _greedy_subsets(Xc, y, k, sp["n"], cfg.seed)
        else:
            w = []
            order = list(rng.permutation(n_in))            # cover every input once before repeating
            for _ in range(sp["n"]):
                pick = []
                while order and len(pick) < k:
                    c = order.pop(0)
                    if c not in pick:
                        pick.append(int(c))
                while len(pick) < k:
                    c = int(rng.integers(n_in))
                    if c not in pick:
                        pick.append(c)
                w.append(sorted(pick))
        wiring.append(w)
        n_in = sp["n"]
    return wiring


def _greedy_subsets(Xc, y, k, n, seed):
    """Rank every k-subset of the input codes by the training accuracy of a depth-3 tree on it; take the best n,
    skipping a subset whose features are all already covered by two chosen subsets (spreads the wiring)."""
    import itertools
    from sklearn.tree import DecisionTreeClassifier
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(Xc), size=min(40000, len(Xc)), replace=False)
    sc = []
    for c in itertools.combinations(range(Xc.shape[1]), k):
        m = DecisionTreeClassifier(max_depth=3, random_state=seed).fit(Xc[idx][:, c], y[idx])
        sc.append((float(m.score(Xc[idx][:, c], y[idx])), c))
    sc.sort(key=lambda t: -t[0])
    out, use = [], np.zeros(Xc.shape[1], int)
    for _, c in sc:
        if len(out) == n:
            break
        if all(use[i] >= 2 for i in c) and len(out) < len(sc) - n:
            continue
        out.append(sorted(int(i) for i in c))
        use[list(c)] += 1
    for _, c in sc:                                       # fewer subsets than neurons: repeat the best
        if len(out) == n:
            break
        out.append(sorted(int(i) for i in c))
    return out


# -------------------------------------------------------------------------------------------------------- training
def train(cfg: Config, Xtr, ytr, Xv, yv, log=print) -> dict:
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(cfg.seed)
    th = fit_thresholds(cfg, Xtr, ytr)
    in_bits_eff = code_bits(th)
    Ctr, Cv = encode(th, Xtr), encode(th, Xv)
    wiring = make_wiring(cfg, in_bits_eff, Ctr, ytr)
    specs = layer_specs(cfg)
    in_scale = [[max(1, len(t)) for t in th]]
    for sp in specs[:-1]:
        in_scale.append([(1 << sp["bits"]) - 1] * sp["n"])
    for li, sp in enumerate(specs):
        bits_in = in_bits_eff if li == 0 else [specs[li - 1]["bits"]] * specs[li - 1]["n"]
        if max(sum(bits_in[c] for c in w) for w in wiring[li]) > MAX_ADDR_BITS:
            raise ValueError(f"layer {li}: a neuron's table would have more than 2^{MAX_ADDR_BITS} entries")

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.W, self.B, self.bn = torch.nn.ParameterList(), torch.nn.ParameterList(), torch.nn.ModuleList()
            self.wire = [torch.tensor(w) for w in wiring]
            self.scale = [torch.tensor(np.array(s, dtype=np.float32)) for s in in_scale]
            for sp in specs:
                dims = [sp["k"]] + [cfg.hidden] * cfg.depth + [1]
                for a, b in zip(dims[:-1], dims[1:]):
                    self.W.append(torch.nn.Parameter(torch.randn(sp["n"], a, b) * math.sqrt(2.0 / a)))
                    self.B.append(torch.nn.Parameter(torch.zeros(sp["n"], b)))
                self.bn.append(torch.nn.BatchNorm1d(sp["n"]) if cfg.batchnorm else torch.nn.Identity())
            # the integer scores are argmax-ed in hardware, so any positive scale leaves the class unchanged; for the
            # loss a learned scale lets small logit differences be expressed with integer scores
            self.log_tau = torch.nn.Parameter(torch.tensor(math.log(0.25)), requires_grad=cfg.learn_temperature)

        def layer(self, li, x, quant=True):
            """x: (B, n_in) codes of the previous layer -> (B, n) outputs of layer li (codes or scores)."""
            sp = specs[li]
            h = (x / self.scale[li])[:, self.wire[li]]           # (B, n, k), each input in 0..1
            nl = cfg.depth + 1
            for d in range(nl):
                h = torch.einsum("bni,nio->bno", h, self.W[li * nl + d]) + self.B[li * nl + d]
                if d < nl - 1:
                    h = torch.relu(h)
            z = self.bn[li](h.squeeze(-1))
            if sp["signed"]:
                lo, hi = -(1 << (sp["bits"] - 1)), (1 << (sp["bits"] - 1)) - 1
                z = torch.clamp(z * 2.0, lo - 0.49, hi + 0.49)  # scale: BN output ~N(0,1) -> roughly +-2 levels
                return z + (torch.round(z) - z).detach() if quant else z
            s = torch.sigmoid(z) * ((1 << sp["bits"]) - 1)
            return s + (torch.round(s) - s).detach() if quant else s

        def forward(self, c):
            x = c
            for li in range(len(specs)):
                x = self.layer(li, x)
            return scores_from_last(x)

    def scores_from_last(x):
        if cfg.output == "additive":
            return x.view(len(x), cfg.n_classes, cfg.per_class).sum(-1)
        return x

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=cfg.lr)
    steps = cfg.epochs * math.ceil(len(Ctr) / cfg.batch)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    ct, yt, cv = torch.tensor(Ctr, dtype=torch.float32), torch.tensor(ytr), torch.tensor(Cv, dtype=torch.float32)
    g = torch.Generator().manual_seed(cfg.seed)
    best, hist = None, []
    for ep in range(cfg.epochs):
        net.train()
        if ep >= cfg.epochs - cfg.freeze_bn:              # train against the statistics the tables will use
            for b in net.bn:
                b.eval()
        perm = torch.randperm(len(ct), generator=g)
        for j in range(0, len(ct), cfg.batch):
            b = perm[j:j + cfg.batch]
            sc = net(ct[b]).float()
            if cfg.learn_temperature:
                sc = sc * torch.exp(net.log_tau)
            loss = torch.nn.functional.cross_entropy(sc, yt[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
            sch.step()
        net.eval()
        with torch.no_grad():
            tables = _enumerate(net, specs, wiring, in_bits_eff)
        m = {"config": cfg.to_dict(), "thresholds": th, "code_bits": in_bits_eff, "layers": specs, "wiring": wiring,
             "tables": tables}
        va = float((twin_predict(m, Xv) == yv).mean())
        hist.append(round(va, 4))
        if best is None or va > best[0]:
            best = (va, ep, m)
        log(f"lutgen: seed {cfg.seed} epoch {ep + 1}/{cfg.epochs} val {va:.4f}")
    m = best[2]
    m["val_accuracy"] = round(best[0], 4)
    m["epoch_kept"] = best[1] + 1
    m["val_by_epoch"] = hist
    m["train_accuracy"] = round(float((twin_predict(m, Xtr) == ytr).mean()), 4)
    return m


def _enumerate(net, specs, wiring, in_bits_eff) -> list[list[list[int]]]:
    """Truth table of every neuron: entry `addr` is the neuron's output for the input codes packed into addr, the
    first wired input in the most significant bits."""
    import torch
    tables = []
    for li, sp in enumerate(specs):
        bits_in = in_bits_eff if li == 0 else [specs[li - 1]["bits"]] * specs[li - 1]["n"]
        n_prev = len(bits_in)
        lt = []
        for j, w in enumerate(wiring[li]):
            ab = [bits_in[c] for c in w]
            A = sum(ab)
            addr = np.arange(1 << A)
            x = np.zeros((1 << A, n_prev), dtype=np.float32)
            sh = A
            for c, b in zip(w, ab):
                sh -= b
                x[:, c] = (addr >> sh) & ((1 << b) - 1)
            out = net.layer(li, torch.tensor(x)).numpy()[:, j]
            lt.append(np.rint(out).astype(np.int64).tolist())
        tables.append(lt)
    return tables


# ------------------------------------------------------------------------------------------------------------ twin
def twin_layers(m: dict, X: np.ndarray) -> list[np.ndarray]:
    """Bit-exact integer evaluation from the tables: the codes of every layer (the last are the score neurons)."""
    x = encode(m["thresholds"], X)
    bits_in = m["code_bits"]
    outs = [x]
    for li, sp in enumerate(m["layers"]):
        cols = []
        for j, w in enumerate(m["wiring"][li]):
            addr = np.zeros(len(x), dtype=np.int64)
            for c in w:
                addr = (addr << bits_in[c]) | x[:, c]
            cols.append(np.asarray(m["tables"][li][j], dtype=np.int64)[addr])
        x = np.stack(cols, axis=1)
        bits_in = [sp["bits"]] * sp["n"]
        outs.append(x)
    return outs


def twin_scores(m: dict, X: np.ndarray) -> np.ndarray:
    x = twin_layers(m, X)[-1]
    cfg = m["config"]
    if cfg["output"] == "additive":
        return x.reshape(len(x), cfg["n_classes"], cfg["per_class"]).sum(-1)
    return x


def twin_predict(m: dict, X: np.ndarray) -> np.ndarray:
    """Class = argmax of the scores, ties to the lowest class index (the RTL compares with >)."""
    return np.argmax(twin_scores(m, X), axis=1)


def save(m: dict, path):
    path.write_text(json.dumps(m))


def table_bits(m: dict) -> dict:
    """Size measures that predict LUT cost: address bits and table entries per neuron."""
    bits_in = m["code_bits"]
    addr = []
    for li, sp in enumerate(m["layers"]):
        addr.append([sum(bits_in[c] for c in w) for w in m["wiring"][li]])
        bits_in = [sp["bits"]] * sp["n"]
    return {"address_bits": addr,
            "table_bits_total": int(sum((1 << a) * sp["bits"] for A, sp in zip(addr, m["layers"]) for a in A))}
