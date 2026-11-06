"""Reference model for P14-1 (the Nexys tiny CNN). Standalone numpy: it rebuilds the integer network from cnn_params.hex and cnn_images.hex (the files the design loads) and
evaluates it. Layout: 612 weights (conv1 36: [oc][ky][kx]; conv2 288: [oc][ic][ky][kx]; dense 288: [o][i], i = c*9 + y*3 + x), 16 int32 biases, then M1, S1, M2, S2."""
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LETTERS = "HVBX"


def _s8(v):
    return v - 256 if v >= 128 else v


def _s32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def load():
    p = [int(t, 16) for t in (HERE / "cnn_params.hex").read_text().split()]
    w = np.array([_s8(v & 0xFF) for v in p[:612]], dtype=np.int64)
    b = np.array([_s32(v) for v in p[612:628]], dtype=np.int64)
    m1, s1, m2, s2 = p[628:632]
    imgs = np.array([_s8(int(t, 16)) for t in (HERE / "cnn_images.hex").read_text().split()], dtype=np.int64).reshape(8, 12, 12)
    return w, b, (m1, s1, m2, s2), imgs


def requant_relu(acc, m, s):
    return np.clip((acc * m + (1 << (s - 1))) >> s, 0, 127)


def forward(img, w, b, cfg):
    m1, s1, m2, s2 = cfg
    w1, w2, w3 = w[:36].reshape(4, 3, 3), w[36:324].reshape(8, 4, 3, 3), w[324:].reshape(4, 72)
    a1 = np.zeros((4, 10, 10), dtype=np.int64)
    for oc in range(4):
        for ky in range(3):
            for kx in range(3):
                a1[oc] += w1[oc, ky, kx] * img[ky:ky + 10, kx:kx + 10]
        a1[oc] += b[oc]
    a1 = requant_relu(a1, m1, s1)
    p1 = a1.reshape(4, 5, 2, 5, 2).max(axis=(2, 4))
    a2 = np.zeros((8, 3, 3), dtype=np.int64)
    for oc in range(8):
        for ic in range(4):
            for ky in range(3):
                for kx in range(3):
                    a2[oc] += w2[oc, ic, ky, kx] * p1[ic, ky:ky + 3, kx:kx + 3]
        a2[oc] += b[4 + oc]
    a2 = requant_relu(a2, m2, s2)
    return w3 @ a2.reshape(72) + b[12:16]


def reference_output():
    w, b, cfg, imgs = load()
    out = []
    for k in range(8):
        lg = forward(imgs[k], w, b, cfg)
        cls = int(np.argmax(lg))                             # numpy picks the lowest index on a tie, as the design does
        out.append({"image": k, "logits": [int(v) for v in lg], "uart": LETTERS[cls] + "\n", "digit": cls})
    return {"images": out}


# ---- benchmark wrapper (from spec.yaml) ----
DESIGN_ID = None
SEG_OF = {0: 0x40, 1: 0x79, 2: 0x24, 3: 0x30}
