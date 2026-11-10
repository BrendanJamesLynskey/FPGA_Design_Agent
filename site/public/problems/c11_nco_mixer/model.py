"""Reference model for P11-1 (NCO and complex mixer), bit-exact. Standalone: python only."""
import math
import random

AW, LA, XW = 16, 8, 12
FWS = [0x1A2B, 0xF000]
LUT = [math.floor(16383 * math.sin(2 * math.pi * i / 2 ** LA) + 0.5) for i in range(2 ** LA)]


def stimulus(seed=11):
    runs = []
    for r, fw in enumerate(FWS):
        rng = random.Random(seed + r)
        xs = [rng.randrange(-2048, 2048) for _ in range(300)]
        xs += [int(round(2000 * math.sin(2 * math.pi * fw / 2 ** AW * k))) for k in range(250)]
        xs += [2047, -2048, 2047, -2048, 0, 1, -1] * 10 + [rng.randrange(-100, 100) for _ in range(130)]
        runs.append({"fw": fw, "x": xs[:750]})
    return runs


def mix(xs, fw):
    acc, out = 0, []
    for x in xs:
        idx = acc >> (AW - LA)
        s, c = LUT[idx], LUT[(idx + 2 ** (LA - 2)) % 2 ** LA]
        out.append((((x * c) >> 14), ((x * -s) >> 14)))
        acc = (acc + fw) % 2 ** AW
    return out


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4E434F4D          # "NCOM"
MASK, GO, STATUS, NOUT, VMASK, FW = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05
SAMP, OUT = 0x10, 0x20
LAT = 1
