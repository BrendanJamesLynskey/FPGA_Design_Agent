"""Reference model for P10-2 (phase-truncated DDS), sample for sample. Standalone: python only."""
import math

AW, LA, OW = 24, 8, 12
FWS = [0x0A3D71, 0x123457, 0x100000, 0x000000, 0x800000, 0xFFFFFF]
N = 1200


def lut():
    a = 2 ** (OW - 1) - 1
    return [math.floor(a * math.sin(2 * math.pi * i / 2 ** LA) + 0.5) for i in range(2 ** LA)]


def samples(fw, n=N):
    t, acc, out = lut(), 0, []
    for _ in range(n):
        out.append(t[acc >> (AW - LA)])
        acc = (acc + fw) & ((1 << AW) - 1)
    return out


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4444534E          # "DDSN"
FW, GO, STATUS, PTR, DATA = 0x00, 0x01, 0x02, 0x03, 0x04
