import os, math


def _load_coeffs(taps, uniq, width):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "data", "coeffs.hex"), os.path.join("data", "coeffs.hex")):
        if os.path.exists(p):
            try:
                vals = []
                for t in open(p).read().split():
                    v = int(t, 16) & ((1 << width) - 1)
                    if v >= 1 << (width - 1):
                        v -= 1 << width
                    vals.append(v)
                if len(vals) >= taps:
                    return vals[:taps]
                if len(vals) >= uniq:
                    h = vals[:uniq]
                    return h + h[::-1]
            except Exception:
                pass
    # fallback: symmetric windowed-sinc lowpass
    h = []
    fc = 0.2
    for k in range(taps):
        m = k - (taps - 1) / 2.0
        s = 2 * fc if m == 0 else math.sin(2 * math.pi * fc * m) / (math.pi * m)
        w = 0.54 - 0.46 * math.cos(2 * math.pi * k / (taps - 1))
        h.append(int(round(s * w * (1 << (width - 1)) * 0.98)))
    for k in range(taps // 2):
        h[taps - 1 - k] = h[k]
    return h


class Model:
    def __init__(self, TAPS=32, UNIQUE_COEFFS=16, DATA_WIDTH=16, COEFF_WIDTH=16,
                 FIFO_DEPTH=1024, ROUND_CONST=16384, SHIFT=15, MMCM_MULT=10,
                 MMCM_DIV=1, DESIGN_ID=546570241):
        self.TAPS = TAPS
        self.DW = DATA_WIDTH
        self.depth = FIFO_DEPTH
        self.rc = ROUND_CONST
        self.sh = SHIFT
        self.id = DESIGN_ID
        self.h = _load_coeffs(TAPS, UNIQUE_COEFFS, COEFF_WIDTH)
        self.reset()

    def reset(self):
        self.infifo = []
        self.outfifo = []
        self.hist = [0] * self.TAPS
        self.sat = 0
        self.done = 0
        self.scratch = 0
        self.busy = 0
        self.rdata = 0
        self.pend_w = None
        self.pend_r = None
        self.hb = 0
        self.cnt = 0
        self.inp = {}

    def _s16(self, v):
        v &= 0xFFFF
        return v - 65536 if v & 0x8000 else v

    def _filter(self, x):
        self.hist = [x] + self.hist[:-1]
        acc = sum(c * s for c, s in zip(self.h, self.hist))
        y = (acc + self.rc) >> self.sh
        sat = 0
        if y > 32767:
            y, sat = 32767, 1
        elif y < -32768:
            y, sat = -32768, 1
        return y & 0xFFFF, sat

    def read_reg(self, offset):
        o = offset & 0xFFF
        if o == 0:
            return self.id & 0xFFFFFFFF
        if o == 4:
            return 0
        if o == 8:
            return self.scratch
        if o == 16:
            return 0
        if o == 24:
            if not self.outfifo:
                return 0
            return 0x80000000 | self.outfifo.pop(0)
        if o == 28:
            return (self.busy & 1) | (len(self.infifo) << 4) | (len(self.outfifo) << 20)
        if o == 32:
            return self.sat
        if o == 36:
            return self.done
        return 0

    def write_reg(self, offset, value):
        o = offset & 0xFFF
        value &= 0xFFFFFFFF
        if o == 8:
            self.scratch = value
        elif o == 16:
            if value & 1:
                self.infifo = []
                self.outfifo = []
                self.hist = [0] * self.TAPS
                self.sat = 0
                self.done = 0
                self.busy = 0
            elif value & 2:
                if not self.busy and self.infifo:
                    self.busy = 1
        elif o == 20:
            if len(self.infifo) < self.depth:
                self.infifo.append(value & 0xFFFF)

    def step(self, inputs=None):
        if inputs:
            self.inp.update(inputs)
        i = self.inp
        # datapath: one sample per cycle
        if self.busy:
            if self.infifo and len(self.outfifo) < self.depth:
                x = self._s16(self.infifo.pop(0))
                y, s = self._filter(x)
                self.outfifo.append(y)
                self.sat = (self.sat + s) & 0xFFFFFFFF
                self.done = (self.done + 1) & 0xFFFFFFFF
            if not self.infifo or len(self.outfifo) >= self.depth:
                self.busy = 0
        # bus
        if self.pend_w is not None:
            self.write_reg(*self.pend_w)
            self.pend_w = None
        if self.pend_r is not None:
            self.rdata = self.read_reg(self.pend_r)
            self.pend_r = None
        if i.get("h_we"):
            self.pend_w = (i.get("h_addr", 0), i.get("h_wdata", 0))
        if i.get("h_re"):
            self.pend_r = i.get("h_addr", 0)
        self.inp["h_we"] = 0
        self.inp["h_re"] = 0
        self.cnt += 1
        if self.cnt >= (1 << 24):
            self.cnt = 0
            self.hb ^= 1
        return {"led": (self.hb << 1) | self.busy, "sfp_tx_disable": 1,
                "h_rdata": self.rdata}
