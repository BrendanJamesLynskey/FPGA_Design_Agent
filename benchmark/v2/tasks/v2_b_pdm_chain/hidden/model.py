"""Golden model of v2_b_pdm_chain, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

from itertools import accumulate
from types import SimpleNamespace

CTRL, STATUS, COUNT, CAP0 = 0x00, 0x01, 0x02, 0x40
DESIGN_ID = 0x50444D43          # "PDMC"
FS_PDM = 3_125_000
LAT_BITS = 96                   # PDM samples before audio sample 0; one audio sample per 64 more
HB_TAPS = (-1, 0, 9, 16, 9, 0, -1)
FIR_TAPS = (2, -6, 16, -48, 584, -48, 16, -6, 2)


class _Flag:
    """Limit to the 16-bit range and remember that a limit acted."""

    def __init__(self) -> None:
        self.hit = 0

    def __call__(self, v: int) -> int:
        out = max(-32768, min(32767, v))
        self.hit |= int(out != v)
        return out


def _cic(bits) -> list[int]:
    """Stage 1: three integrators, keep every 16th value, three combs, drop the two fills."""
    third = list(accumulate(accumulate(accumulate(1 if b else -1 for b in bits))))[15::16]
    delays = [0, 0, 0]
    outs = []
    for v in third:
        for j in range(3):
            v, delays[j] = v - delays[j], v
        outs.append(v)
    return outs[2:]


def _halfband(xs, limit) -> list[int]:
    """Stages 3 and 4: seven taps, a result for every even sample, convergent_pc rounding."""
    hist_pc = [0] * 7
    outs = []
    for n, x in enumerate(xs, 1):
        hist_pc = [x] + hist_pc[:-1]
        if n % 2 == 0:
            total = sum(t * h for t, h in zip(HB_TAPS, hist_pc))
            whole, frac = divmod(total, 32)
            outs.append(limit(whole + (frac > 16 or (frac == 16 and whole % 2 == 1))))
    return outs


def _fir(xs, limit) -> list[int]:
    """Stage 5: nine taps, one result per sample, ties up."""
    hist_pc = [0] * 9
    outs = []
    for x in xs:
        hist_pc = [x] + hist_pc[:-1]
        outs.append(limit((sum(t * h for t, h in zip(FIR_TAPS, hist_pc)) + 256) >> 9))
    return outs


def _dc_block(xs, limit) -> list[int]:
    """Stage 6: x - xp + yp - (yp >> 7), limited, the limited value fed_pc back."""
    prev_x = prev_y = 0
    outs = []
    for x in xs:
        y = limit(x - prev_x + prev_y - (prev_y >> 7))
        outs.append(y)
        prev_x, prev_y = x, y
    return outs


def run(bits) -> SimpleNamespace:
    """The audio samples and the SAT flag for a PDM bit stream_pc (all stages, from empty)."""
    limit = _Flag()
    scaled = [limit(8 * c) for c in _cic(bits)]
    audio = _dc_block(_fir(_halfband(_halfband(scaled, limit), limit), limit), limit)
    return SimpleNamespace(out=audio, sat_pc=limit.hit)


def first_audio(bits, n: int = 64) -> list[int]:
    return run(bits).out[:n]


def sat_within(bits, n: int = 64) -> int:
    """SAT as the chain sees it once audio sample n-1 has been stored: all bits up to LAT_BITS + 64 (n - 1)."""
    return run(list(bits)[:LAT_BITS + 64 * (n - 1)]).sat_pc
