"""Brief 91 model: a small integer MLP whose weights are in one of the formats of formats.py, trained with the
quantisers in the loop, exported to integers, with a bit-exact Python twin. The RTL (rtl.py) is read from the exported
integers alone, as the twin is.

Network. Inputs are integer columns: the brief 89 quantile codes of each feature (0 .. 2^A - 1; "code" input) or, for
the binary format, thermometer bits of those thresholds ("thermo" input). Hidden layer l, neuron j:

    z = sum_i e_ji * x_i            exact integer; e_ji a signed element of the weight format
    a = clip((z + B_j) >> sh_j, 0, amax)       amax = 2^A - 1 (A = 1 for binary); arithmetic shift, floor

the score layer: s_j = (sum_i e_ji x_i) * 2^k_j + B_j  (k_j = shmax - sh_j >= 0, a left shift, wiring), class =
argmax s with ties to the lowest class. The real weight is c_j e with c_j = 2^-sh_j (a power-of-two scale per neuron),
and the real bias is B_j c_j, so that a = clip(floor(c_j z + B_j c_j)) is the rounded and clipped real activation.

Training (our own code): float latent weights v_ji (in the real units), per-neuron p_j with sh_j = clamp(round(-p_j),
0, 14), bias b_j. The forward pass is the integer pipeline above exactly (wq = c e, rounded bias, floor, clip);
the backward pass is straight-through: identity through the element quantiser inside the grid, identity through floor
and round, zero through the clip. Binary hidden activations use the derivative of a sigmoid of width sqrt(fan-in)/2
instead (their clip would otherwise pass no gradient). The loss is cross-entropy on the real scores times a learned
positive scale (the brief 89 lesson: integer scores directly as logits cannot express small logit differences). The
epoch kept is the one whose integer twin has the best validation accuracy; the test split is never read here.
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass, field

import numpy as np

from designs.b89_lutnet_gen.lutgen import model as M89
from . import formats as F

SH_MAX = 14


@dataclass
class Config:
    fmt: str = "int4"                 # binary_t3, binary_t7, ternary, int4, mxfp4, log4, log4_nz, log4p1
    hidden: list = field(default_factory=lambda: [16, 8])
    act_bits: int = 4                 # input code bits and hidden activation bits (binary: 1 and thermometer levels)
    epochs: int = 25
    lr: float = 3e-3
    lr_scale: float = 2e-2            # learning rate of the per-neuron scale exponents and biases
    batch: int = 1024
    seed: int = 0
    n_classes: int = 3

    def to_dict(self):
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d):
        return Config(**{k: v for k, v in d.items() if k in {f.name for f in dataclasses.fields(Config)}})

    @property
    def fm(self):
        return F.get(self.fmt)

    @property
    def thermo_levels(self):
        return int(self.fmt.split("_t")[1]) if self.fmt.startswith("binary") else 0


# ------------------------------------------------------------------------------------------------------- inputs
def fit_input(cfg: Config, X, y) -> dict:
    if cfg.fm.binary:
        lv = cfg.thermo_levels
        bits = max(1, math.ceil(math.log2(lv + 1)))
        kind = "thermo"
    else:
        bits, kind = cfg.act_bits, "code"
    th = M89.fit_thresholds(M89.Config(in_bits=[bits] * X.shape[1], thresholds="quantile", seed=cfg.seed), X, y)
    if kind == "thermo":
        amax = [1] * sum(len(t) for t in th)
    else:
        amax = [len(t) for t in th]
    return {"kind": kind, "thresholds": th, "amax": amax}


def encode_input(inp: dict, X: np.ndarray) -> np.ndarray:
    if inp["kind"] == "code":
        return M89.encode(inp["thresholds"], X)
    cols = [(X[:, j] > t).astype(np.int64) for j, ts in enumerate(inp["thresholds"]) for t in ts]
    return np.stack(cols, axis=1) if cols else np.zeros((len(X), 0), np.int64)


# ------------------------------------------------------------------------------------------------------------ twin
def twin_layers(m: dict, X: np.ndarray) -> list[np.ndarray]:
    """Integer evaluation: the input columns, every hidden activation layer, and the scores (last)."""
    x = encode_input(m["input"], X)
    outs = [x]
    for L in m["layers"]:
        W = np.asarray(L["W"], dtype=np.int64).reshape(L["n"], L["n_in"])
        z = x @ W.T
        if L["kind"] == "hidden":
            x = np.clip((z + np.asarray(L["B"], dtype=np.int64)) >> np.asarray(L["sh"], dtype=np.int64), 0, L["amax"])
        else:
            x = (z << np.asarray(L["k"], dtype=np.int64)) + np.asarray(L["B"], dtype=np.int64)
        outs.append(x)
    return outs


def twin_scores(m, X):
    return twin_layers(m, X)[-1]


def twin_predict(m, X):
    """argmax of the integer scores, ties to the lowest class index (the RTL compares with >)."""
    return np.argmax(twin_scores(m, X), axis=1)


def twin_predict_xnor(m, X):
    """Binary format only: the same classes computed the FINN way, with bipolar activations and XNOR-popcount, then
    the thresholds. Used by a test to show it is the same function as the integer form."""
    x = encode_input(m["input"], X)
    for L in m["layers"]:
        W = np.asarray(L["W"], dtype=np.int64).reshape(L["n"], L["n_in"])
        xb = 2 * x - 1                                           # bipolar
        pop = ((xb[:, None, :] * W[None]) > 0).sum(-1)           # XNOR then popcount of agreements
        z = 2 * pop - L["n_in"]                                  # = sum_i W_ji xb_i
        z = (z + W.sum(1)[None]) // 2                            # back to sum_i W_ji x_i (exact: parity matches)
        if L["kind"] == "hidden":
            x = np.clip(z + np.asarray(L["B"], dtype=np.int64), 0, 1)
        else:
            x = z + np.asarray(L["B"], dtype=np.int64)
    return np.argmax(x, axis=1)


# -------------------------------------------------------------------------------------------------------- training
def train(cfg: Config, Xtr, ytr, Xv, yv, log=print) -> dict:
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(cfg.seed)
    fm = cfg.fm
    inp = fit_input(cfg, Xtr, ytr)
    Ctr, Cv = encode_input(inp, Xtr), encode_input(inp, Xv)
    sizes = [len(inp["amax"])] + list(cfg.hidden) + [cfg.n_classes]
    amax_h = 1 if fm.binary else (1 << cfg.act_bits) - 1
    nl = len(sizes) - 1
    gmax = float(fm.max_mag)

    def rs(x):                                    # round, straight-through
        return x + (torch.round(x) - x).detach()

    def fl(x):
        return x + (torch.floor(x) - x).detach()

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.v = torch.nn.ParameterList([torch.nn.Parameter(torch.randn(sizes[l + 1], sizes[l]) / math.sqrt(sizes[l]))
                                             for l in range(nl)])
            self.p = torch.nn.ParameterList([torch.nn.Parameter(torch.zeros(sizes[l + 1]), requires_grad=not fm.binary)
                                             for l in range(nl)])
            self.b = torch.nn.ParameterList([torch.nn.Parameter(torch.zeros(sizes[l + 1])) for l in range(nl)])
            self.logtau = torch.nn.Parameter(torch.zeros(()))

        def sh(self, l):
            if fm.binary:
                return torch.zeros(sizes[l + 1])
            return torch.clamp(rs(-self.p[l]), 0, SH_MAX)

        def weights(self, l):
            sh = self.sh(l)
            c = torch.pow(2.0, -sh)
            u = torch.clamp(self.v[l] / c[:, None], -gmax, gmax)
            e = u + (F.quantize_t(u.detach(), fm) - u).detach()
            return c[:, None] * e, c, sh

        def layer(self, l, x):
            wq, c, sh = self.weights(l)
            z = x @ wq.T
            if l < nl - 1:
                pre = z + rs(self.b[l] / c) * c
                if fm.binary:
                    w = math.sqrt(sizes[l]) / 2 + 1e-6
                    hard = (pre >= 1).float()
                    s = torch.sigmoid((pre - 1) / w)
                    return hard + (s - s.detach())
                return torch.clamp(fl(pre), 0, amax_h)
            scale = torch.pow(2.0, sh.max())
            return z + rs(self.b[l] * scale) / scale

        def forward(self, x):
            for l in range(nl):
                x = self.layer(l, x)
            return x

    net = Net()
    # data-dependent initialisation, layer by layer: activations about a quarter of the range wide, centred
    with torch.no_grad():
        x = torch.tensor(Ctr[:20000], dtype=torch.float32)
        for l in range(nl):
            hid = l < nl - 1
            tgt = 0.25 * amax_h if hid else 1.0
            if fm.binary:
                z = x @ torch.sign(net.v[l]).T
                net.b[l].copy_((1.0 - z.median(0).values) if hid else -z.mean(0))
            else:
                y = x @ net.v[l].T
                g = tgt / (y.std(0) + 1e-6)
                net.v[l].mul_(g[:, None])
                y = y * g
                net.b[l].copy_(((amax_h + 1) / 2 - y.mean(0)) if hid else -y.mean(0))
                mx = net.v[l].abs().max(1).values
                net.p[l].copy_(torch.clamp(torch.log2(mx / gmax), -SH_MAX, 0))
            x = net.layer(l, x)
        net.logtau.copy_(-torch.log(x.std() + 1e-6))      # logits of unit scale at the start
    opt = torch.optim.Adam([{"params": list(net.v), "lr": cfg.lr},
                            {"params": list(net.p) + list(net.b) + [net.logtau], "lr": cfg.lr_scale}])
    steps = cfg.epochs * math.ceil(len(Ctr) / cfg.batch)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    ct, yt = torch.tensor(Ctr, dtype=torch.float32), torch.tensor(ytr)
    g = torch.Generator().manual_seed(cfg.seed)
    best, hist = None, []
    for ep in range(cfg.epochs):
        perm = torch.randperm(len(ct), generator=g)
        for j in range(0, len(ct), cfg.batch):
            b = perm[j:j + cfg.batch]
            loss = torch.nn.functional.cross_entropy(net(ct[b]) * torch.exp(net.logtau), yt[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
            sch.step()
        m = _export(cfg, net, inp, sizes, amax_h)
        va = float((twin_predict(m, Xv) == yv).mean())
        hist.append(round(va, 4))
        if best is None or va > best[0]:
            best = (va, ep, m)
        log(f"lowbit: {cfg.fmt} seed {cfg.seed} epoch {ep + 1}/{cfg.epochs} val {va:.4f}")
    m = best[2]
    m["val_accuracy"] = round(best[0], 4)
    m["epoch_kept"] = best[1] + 1
    m["val_by_epoch"] = hist
    m["train_accuracy"] = round(float((twin_predict(m, Xtr) == ytr).mean()), 4)
    return m


def _export(cfg, net, inp, sizes, amax_h) -> dict:
    import torch
    fm = cfg.fm
    layers = []
    with torch.no_grad():
        nl = len(sizes) - 1
        shs = [net.sh(l).numpy().astype(np.int64) for l in range(nl)]
        for l in range(nl):
            sh = shs[l]
            e = F.quantize_np(net.v[l].numpy().astype(np.float64) * (2.0 ** sh)[:, None], fm)
            b = net.b[l].numpy().astype(np.float64)
            if l < nl - 1:
                layers.append({"kind": "hidden", "n": sizes[l + 1], "n_in": sizes[l], "amax": amax_h,
                               "W": e.tolist(), "sh": sh.tolist(), "B": np.rint(b * 2.0 ** sh).astype(np.int64).tolist()})
            else:
                smax = int(sh.max())
                layers.append({"kind": "score", "n": sizes[l + 1], "n_in": sizes[l], "W": e.tolist(),
                               "sh": sh.tolist(), "shmax": smax, "k": (smax - sh).tolist(),
                               "B": np.rint(b * 2.0 ** smax).astype(np.int64).tolist()})
    return {"config": cfg.to_dict(), "input": inp, "layers": layers}


def save(m, path):
    path.write_text(json.dumps(m))


def load(path):
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------------------------- bounds (for RTL)
def bounds(m: dict) -> list[dict]:
    """Exact worst-case range of every neuron's accumulator (before the shift) and of its inputs, by interval
    arithmetic over the true input ranges: the widths in the RTL come from these, never truncating silently."""
    xlo = [0] * len(m["input"]["amax"])
    xhi = list(m["input"]["amax"])
    out = []
    for L in m["layers"]:
        W = np.asarray(L["W"], dtype=np.int64).reshape(L["n"], L["n_in"])
        accs = []
        for j in range(L["n"]):
            lo = hi = int(L["B"][j])
            k = L["k"][j] if L["kind"] == "score" else 0
            for i in range(L["n_in"]):
                w = int(W[j, i]) << k
                a, b = w * xlo[i], w * xhi[i]
                lo += min(a, b)
                hi += max(a, b)
            accs.append((lo, hi))
        out.append({"acc": accs})
        if L["kind"] == "hidden":
            xlo, xhi = [0] * L["n"], [L["amax"]] * L["n"]
    return out


def weight_stats(m: dict) -> dict:
    W = np.concatenate([np.asarray(L["W"]).ravel() for L in m["layers"]])
    return {"weights": int(W.size), "zero_share": round(float((W == 0).mean()), 4),
            "terms": int(sum(len(F.csd(abs(int(w)))) for w in W))}
