"""Reference model of the NCO + mixer, written from the request only."""
import math

# Request: S[k] = floor(16383*sin(2*pi*k/256) + 0.5), signed 16 bits, 256 entries.
S = [math.floor(16383 * math.sin(2 * math.pi * k / 256) + 0.5) for k in range(256)]


def sin_idx(k):
    return S[k % 256]


def cos_idx(k):
    # Request: cosine of index k is S[(k + 64) mod 256].
    return S[(k + 64) % 256]


def wrap12(v):
    v &= 0xFFF
    return v - 0x1000 if v & 0x800 else v


def to_signed12(v):
    return wrap12(v)


class Nco:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = 0  # request: phase is 0 after reset

    def step(self, x, fw):
        """One enabled clock: index = top 8 bits of phase BEFORE the advance."""
        k = (self.phase >> 8) & 0xFF
        s, c = sin_idx(k), cos_idx(k)
        i = wrap12((x * c) >> 14)      # floor = arithmetic shift right
        q = wrap12((-x * s) >> 14)
        self.phase = (self.phase + fw) & 0xFFFF
        return i, q


def pack_out(i, q):
    """OUTn: [11:0] i_out, [27:16] q_out, two's complement, other bits 0."""
    return (i & 0xFFF) | ((q & 0xFFF) << 16)


def burst(nco, fw, samples, mask):
    """Run a 32-clock burst. Bit n of mask presents the next sample on clock n.
    Returns (packed outs list, nout, vmask). VMASK bit n = a result in clock n+1,
    n being the presenting clock, so vmask == mask (when enough samples loaded)."""
    outs = []
    vmask = 0
    idx = 0
    for n in range(32):
        if (mask >> n) & 1:
            i, q = nco.step(samples[idx], fw)
            idx += 1
            outs.append(pack_out(i, q))
            vmask |= 1 << n
    return outs, len(outs), vmask
