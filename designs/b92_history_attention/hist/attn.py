"""Tiny attention over the last N tokens, in integers (arm 3). Training (torch, straight-through) and the bit-exact numpy twin.

Integer definition (the RTL implements exactly this; `>>` is the arithmetic floor shift; clip(x, lo, hi)):
    c      the 7 current features, each coded to 0..15 by thresholds fitted on the training split ("cth")
    u_i    token of the event i places back (i = 0 is the current event): (ts, sv, ofi, 2 imb - 7); zero before a session starts
    q      = clip((Eq c)   >> sq, -8, 7)           d = 4 numbers          Eq  4 x 7   elements of the log4 weight format
    k_i    = clip((Ek u_i) >> sk, -8, 7)           d = 4                  Ek  4 x 4
    v_i    = clip((Ev u_i) >> sv, -8, 7)           m = 4                  Ev  4 x 4   (k_i and v_i are computed once, when
                                                                                       event i arrives, and kept in the window)
    s_i    = sum_d q_d k_id + pos_i                pos_i in -32..31 (learned position bias)
    top1   : j = the lowest index with s_j = max_i s_i (ties to the most recent event);  o = v_j
    relu   : a_i = clip(s_i >> sa, 0, 7);          o = clip((sum_i a_i v_i) >> so, -8, 7)
    output columns o_m + 8 in 0..15.
The log4 weight format is brief 91's: elements 0, +-1, +-2, +-4, .. +-64 (a weight is a shift).
Training uses float latent weights, the quantised forward pass above (all values are small integers, exact in float32), and
straight-through gradients through floor and round, the softmax of s / 8 as the surrogate gradient of the hard argmax, and a throwaway
float head (11 -> 32 -> 3) on top of the codes and the outputs. Only the integers are kept.
"""
from __future__ import annotations

import math

import numpy as np

from designs.b91_lowbit.lowbit import formats as F
from designs.b89_lutnet_gen.lutgen import model as M89

N_WIN = 16
D = 4
MV = 4
FM = F.get("log4")


def window_raw(T: np.ndarray, n: int = N_WIN) -> np.ndarray:
    """(T, n, 4) raw tokens of events t, t-1, ..; zeros before the session start."""
    L, c = T.shape
    out = np.zeros((L, n, c), dtype=np.int64)
    for k in range(n):
        out[k:, k, :] = T[:L - k]
    out[..., 3] = np.where(np.arange(L)[:, None] >= np.arange(n)[None, :], 2 * out[..., 3] - 7, 0)
    return out


def fit_cur_codes(Xtr: np.ndarray, ytr: np.ndarray) -> list:
    return M89.fit_thresholds(M89.Config(in_bits=[4] * 7, thresholds="quantile"), Xtr, ytr)


def twin(m: dict, C: np.ndarray, U: np.ndarray) -> np.ndarray:
    """C (n, 7) current-feature codes, U (n, N, 4) raw window tokens -> (n, 4) columns 0..15."""
    Eq, Ek, Ev = (np.asarray(m[k], dtype=np.int64) for k in ("Eq", "Ek", "Ev"))
    q = np.clip((C @ Eq.T) >> m["sq"], -8, 7)
    k = np.clip((U @ Ek.T) >> m["sk"], -8, 7)
    v = np.clip((U @ Ev.T) >> m["sv"], -8, 7)
    s = np.einsum("nd,nid->ni", q, k) + np.asarray(m["pos"], dtype=np.int64)[None, :]
    if m["form"] == "top1":
        j = np.argmax(s, axis=1)                                 # first maximum: the most recent event on a tie
        o = v[np.arange(len(v)), j]
    else:
        a = np.clip(s >> m["sa"], 0, 7)
        o = np.clip(np.einsum("ni,nim->nm", a, v) >> m["so"], -8, 7)
    return o + 8


def train(form: str, seed: int, C, U, y, Cv, Uv, yv, epochs: int = 12, log=print) -> dict:
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    ct, ut, yt = torch.tensor(C, dtype=torch.float32), torch.tensor(U, dtype=torch.float32), torch.tensor(y)
    cvt, uvt = torch.tensor(Cv, dtype=torch.float32), torch.tensor(Uv, dtype=torch.float32)

    def fl(x):
        return x + (torch.floor(x) - x).detach()

    def qw(v):
        u = torch.clamp(v, -64, 64)
        return u + (F.quantize_t(u.detach(), FM) - u).detach()

    v_q = torch.nn.Parameter(torch.randn(D, 7) * 3)
    v_k = torch.nn.Parameter(torch.randn(D, 4) * 3)
    v_v = torch.nn.Parameter(torch.randn(MV, 4) * 3)
    pos = torch.nn.Parameter(torch.zeros(N_WIN))
    head = torch.nn.Sequential(torch.nn.Linear(7 + MV, 32), torch.nn.ReLU(), torch.nn.Linear(32, 3))
    sh = {}
    with torch.no_grad():               # shifts from the initial scale: the 99th percentile of the raw sums maps to about 7
        def sft(x):
            return max(0, int(math.ceil(math.log2(max(float(np.quantile(np.abs(x.numpy()), 0.99)), 1.0) / 7))))
        sh["sq"] = sft(ct[:20000] @ qw(v_q).T)
        sh["sk"] = sft(ut[:5000].reshape(-1, 4) @ qw(v_k).T)
        sh["sv"] = sft(ut[:5000].reshape(-1, 4) @ qw(v_v).T)

    def fwd(c, u, hard_eval=False):
        q = torch.clamp(fl((c @ qw(v_q).T) / 2 ** sh["sq"]), -8, 7)
        k = torch.clamp(fl((u @ qw(v_k).T) / 2 ** sh["sk"]), -8, 7)
        v = torch.clamp(fl((u @ qw(v_v).T) / 2 ** sh["sv"]), -8, 7)
        p = torch.clamp(pos + (torch.round(pos) - pos).detach(), -32, 31)
        s = (q[:, None, :] * k).sum(-1) + p[None, :]
        if form == "top1":
            soft = torch.softmax(s / 8.0, dim=1)
            hard = torch.nn.functional.one_hot(torch.argmax(s, dim=1), N_WIN).float()
            w = hard + soft - soft.detach()
            o = (w[:, :, None] * v).sum(1)
        else:
            a = torch.clamp(fl(s / 2 ** sh["sa"]), 0, 7)
            o = torch.clamp(fl((a[:, :, None] * v).sum(1) / 2 ** sh["so"]), -8, 7)
        return o

    with torch.no_grad():
        if form == "relu":
            q = torch.clamp(torch.floor((ct[:5000] @ qw(v_q).T) / 2 ** sh["sq"]), -8, 7)
            k = torch.clamp(torch.floor((ut[:5000] @ qw(v_k).T) / 2 ** sh["sk"]), -8, 7)
            v = torch.clamp(torch.floor((ut[:5000] @ qw(v_v).T) / 2 ** sh["sv"]), -8, 7)
            s = (q[:, None, :] * k).sum(-1)
            pos_ = s[s > 0]
            sh["sa"] = max(0, int(math.ceil(math.log2(max(float(np.quantile(pos_.numpy(), 0.99)) if len(pos_) else 1.0, 1.0) / 7))))
            a = torch.clamp(torch.floor(s / 2 ** sh["sa"]), 0, 7)
            tot = (a[:, :, None] * v).sum(1)
            sh["so"] = max(0, int(math.ceil(math.log2(max(float(np.quantile(np.abs(tot.numpy()), 0.99)), 1.0) / 7))))
    params = [v_q, v_k, v_v, pos] + list(head.parameters())
    opt = torch.optim.Adam(params, lr=3e-3)
    steps = epochs * math.ceil(len(ct) / 1024)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    g = torch.Generator().manual_seed(seed)
    best = None

    def export():
        with torch.no_grad():
            e = lambda v: F.quantize_np(np.clip(v.detach().numpy().astype(np.float64), -64, 64), FM).tolist()  # noqa: E731
            return {"form": form, "Eq": e(v_q), "Ek": e(v_k), "Ev": e(v_v),
                    "pos": np.clip(np.rint(pos.detach().numpy()), -32, 31).astype(np.int64).tolist(), **sh}

    for ep in range(epochs):
        perm = torch.randperm(len(ct), generator=g)
        for j in range(0, len(ct), 1024):
            b = perm[j:j + 1024]
            o = fwd(ct[b], ut[b])
            loss = torch.nn.functional.cross_entropy(head(torch.cat([ct[b] / 15, o / 8], 1)), yt[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
            sch.step()
        m = export()
        with torch.no_grad():
            ov = torch.tensor(twin(m, Cv, Uv) - 8, dtype=torch.float32)
            va = float((head(torch.cat([cvt / 15, ov / 8], 1)).argmax(1).numpy() == yv).mean())
        log(f"attn {form} seed {seed} epoch {ep + 1}/{epochs} val(throwaway head) {va:.4f}")
        if best is None or va > best[0]:
            best = (va, ep, m)
    m = best[2]
    m["throwaway_val_accuracy"] = round(best[0], 4)
    m["epoch_kept"] = best[1] + 1
    m["seed"] = seed
    return m


def torch_forward_check(m: dict, C, U) -> np.ndarray:
    """The training forward pass with this model's integers (for the test that it equals the twin)."""
    import torch
    ct, ut = torch.tensor(C, dtype=torch.float32), torch.tensor(U, dtype=torch.float32)
    Eq, Ek, Ev = (torch.tensor(m[k], dtype=torch.float32) for k in ("Eq", "Ek", "Ev"))
    q = torch.clamp(torch.floor((ct @ Eq.T) / 2 ** m["sq"]), -8, 7)
    k = torch.clamp(torch.floor((ut @ Ek.T) / 2 ** m["sk"]), -8, 7)
    v = torch.clamp(torch.floor((ut @ Ev.T) / 2 ** m["sv"]), -8, 7)
    s = (q[:, None, :] * k).sum(-1) + torch.tensor(m["pos"], dtype=torch.float32)[None, :]
    if m["form"] == "top1":
        o = v[torch.arange(len(v)), torch.argmax(s, 1)]
    else:
        a = torch.clamp(torch.floor(s / 2 ** m["sa"]), 0, 7)
        o = torch.clamp(torch.floor((a[:, :, None] * v).sum(1) / 2 ** m["so"]), -8, 7)
    return o.numpy().astype(np.int64) + 8
