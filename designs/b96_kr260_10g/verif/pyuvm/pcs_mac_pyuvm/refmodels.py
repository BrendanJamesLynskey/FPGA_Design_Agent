"""Reference models of the pyuvm bench (brief 123). Plain Python, no cocotb and no pyuvm in here, so they run (and are unit-tested) without a simulator.

Where they come from: the block encode/decode, the bit-serial scrambler and `TxPcs` are the repo's own `model/pcs.py` (brief 96; bit-serial, written from the
clause 49 block formats, nothing shared with the RTL's parallel expressions). Brief 112's SystemVerilog models are themselves a port of that file, so reusing it
here adds no new independence from 112 and costs no second copy. Three things 112 added are added here too, as Python:
  * `encode_rtl`   pcs_tx's behaviour as built: a lane-4 start and an ordered set become the all-error block (`model/pcs.py` encodes S4, the RTL does not)
  * `RefRxPcs`     a clock-by-clock model of pcs_rx's registered outputs including the six event pulses and x_os (pcs.RxPcs keeps counters, not per-clock pulses)
  * `RefMacRx`     the frames and aborts mac64_rx must report, with its pipeline delay and the flush state of a lane-4 frame"""
from __future__ import annotations

import zlib

from designs.b96_kr260_10g.model import pcs

IDLE, START, TERM, ERRC = pcs.IDLE, pcs.START, pcs.TERM, pcs.ERR
IDLE_D = sum(IDLE << (8 * i) for i in range(8))
ERR_D = sum(ERRC << (8 * i) for i in range(8))
IDLE_WORD = (IDLE_D, 0xFF)
M64 = (1 << 64) - 1

BLOCK_KINDS = ["BK_DATA", "BK_IDLE", "BK_S0", "BK_S4", "BK_T0", "BK_T1", "BK_T2", "BK_T3", "BK_T4", "BK_T5", "BK_T6", "BK_T7", "BK_OS", "BK_ERRCTL", "BK_BADTYPE", "BK_BADSH"]


def lane(d: int, i: int) -> int:
    return (d >> (8 * i)) & 0xFF


# ---------------------------------------------------------------------------------------------------- block codes
def err_block() -> tuple[int, int]:
    return 0b10, pcs.T_CTRL | sum(0x1E << (8 + 7 * i) for i in range(8))


def encode_rtl(d: int, c: int, with_s4: bool = False) -> tuple[int, int]:
    """One XGMII word -> (sync header, payload) as pcs_tx does it. With `with_s4` a lane-4 start is a real S4 block (the line agent puts lane-4 frames on the
    wire that way, since pcs_tx cannot)."""
    if c == 0x1F and lane(d, 4) == START and not with_s4:
        return err_block()
    return pcs.encode_block(d, c)


def kind_of(sh: int, p: int) -> str:
    t = p & 0xFF
    if sh == 0b01:
        return "BK_DATA"
    if sh != 0b10:
        return "BK_BADSH"
    if t == pcs.T_CTRL:
        return "BK_ERRCTL" if any(((p >> (8 + 7 * i)) & 0x7F) for i in range(8)) else "BK_IDLE"
    if t == pcs.T_S0:
        return "BK_S0"
    if t == pcs.T_S4:
        return "BK_S4"
    if t in pcs.T_TERM:
        return f"BK_T{pcs.T_TERM.index(t)}"
    if t in pcs.T_OS:
        return "BK_OS"
    return "BK_BADTYPE"


# ---------------------------------------------------------------------------------------------------- frames
def fcs_bytes(data: bytes, poison: bool = False, xor_mask: int = 0) -> bytes:
    f = zlib.crc32(data)
    if poison:
        f = ~f & 0xFFFFFFFF
    return (f ^ xor_mask).to_bytes(4, "little")


def frame_words(data: bytes, lane4: bool = False, poison: bool = False, fcs_xor: int = 0) -> list[tuple[int, int]]:
    """One frame's XGMII words: preamble, data, FCS (good, deliberately bad, or xor-ed), terminate, idles to the word end. lane4 puts four idle bytes first."""
    s = bytes([START] + [0x55] * 6 + [0xD5]) + bytes(data) + fcs_bytes(data, poison, fcs_xor)
    cs = [1] + [0] * (len(s) - 1)
    if lane4:
        s = bytes([IDLE] * 4) + s
        cs = [1] * 4 + cs
    s += bytes([TERM])
    cs += [1]
    while len(s) % 8:
        s += bytes([IDLE])
        cs += [1]
    return [(int.from_bytes(s[i:i + 8], "little"), sum(b << j for j, b in enumerate(cs[i:i + 8]))) for i in range(0, len(s), 8)]


def term_lane(d: int, c: int) -> int:
    for k in range(8):
        if c == (0xFF << k) & 0xFF and lane(d, k) == TERM:
            return k
    return -1


# ---------------------------------------------------------------------------------------------------- transmit PCS
class RefTxPcs(pcs.TxPcs):
    """pcs.TxPcs with the RTL's encoder (no S4, no ordered sets)."""

    def reset(self) -> None:
        self.__init__()

    def step(self, d: int, c: int) -> int:
        if self.adv:
            sh, p = encode_rtl(d, c)
            blk = sh | (self.scr.word(p) << 2)
            m = self.acc | (blk << self.n)
            self.out = m & M64
            self.acc = m >> 64
            self.n += 2
        else:
            self.out = self.acc & M64
            self.acc >>= 64
            self.n = 0
        return self.out


# ---------------------------------------------------------------------------------------------------- receive PCS
class RefRxPcs:
    """pcs_rx clock by clock: one `step(word)` per edge; afterwards the registered outputs (lock, x_v, x_d, x_c, x_os and the six event pulses) are the
    attributes, as the RTL shows them one clock after the word was captured. Block lock as built: 64 valid headers with none invalid to lock, 16 invalid inside
    64 to lose it, a slip on every failure while hunting and on a loss, and the block formed before the slip takes effect is ignored."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.acc = 0
        self.cnt = 0
        self.blk = None            # (sh, payload) registered after stage A
        self.slip_r = False
        self.desc = pcs.Descrambler()
        self.lock = False
        self.sh_cnt = self.inv_cnt = self.settle = 0
        self.x_v = False
        self.x_d = self.x_c = 0
        self.x_os = False
        self.ev = dict(sh_err=0, type_err=0, os=0, slip=0, loss=0, lock=0)
        self.blk_done = False
        self.blk_kind = ""
        self.blk_locked = False

    def events(self) -> tuple:
        e = self.ev
        return (e["sh_err"], e["type_err"], e["os"], e["slip"], e["loss"], e["lock"])

    def step(self, word: int) -> None:
        ev = self.ev = dict(sh_err=0, type_err=0, os=0, slip=0, loss=0, lock=0)
        slip_n = False
        self.x_v = False
        self.blk_done = False
        if self.blk is not None:
            sh, p = self.blk
            pd = self.desc.word(p)
            d, c, note = pcs.decode_block(sh, pd)
            valid = sh in (0b01, 0b10)
            lock_old = self.lock
            self.x_d, self.x_c, self.x_os = d, c, note == "os"
            self.blk_done, self.blk_locked, self.blk_kind = True, lock_old, kind_of(sh, pd)
            if lock_old:
                self.x_v = True
                ev["sh_err"], ev["type_err"], ev["os"] = int(note == "sh"), int(note == "type"), int(note == "os")
            if self.settle > 0:
                self.settle = 0
            elif not valid and (not self.lock or self.inv_cnt == 15):
                ev["loss"] = int(self.lock)
                self.lock = False
                slip_n = True
                ev["slip"] = 1
                self.settle = 1
                self.sh_cnt = self.inv_cnt = 0
            elif self.sh_cnt == 63:
                if not self.lock and self.inv_cnt == 0:
                    self.lock = True
                    ev["lock"] = 1
                self.sh_cnt = self.inv_cnt = 0
            else:
                self.sh_cnt += 1
                if not valid:
                    self.inv_cnt += 1
        m = self.acc | (word << self.cnt)
        k = self.cnt + 64
        if self.slip_r:
            m >>= 1
            k -= 1
        nblk = None
        if k >= 66:
            nblk = (m & 3, (m >> 2) & M64)
            m >>= 66
            k -= 66
        self.acc, self.cnt, self.blk, self.slip_r = m, k, nblk, slip_n


# ---------------------------------------------------------------------------------------------------- receive MAC
class RxFrame:
    __slots__ = ("data", "fcs_ok", "length", "aborted", "s4", "tlane")

    def __init__(self, data=b"", fcs_ok=False, aborted=False, s4=False, tlane=0):
        self.data, self.fcs_ok, self.length, self.aborted, self.s4, self.tlane = bytes(data), fcs_ok, len(data), aborted, s4, tlane


class RefMacRx:
    """The frames mac64_rx reports (all bytes, FCS included, the CRC verdict) and the frames it aborts (an error or control word inside a frame, a second start,
    a start with no data, a lock loss), fed by RefRxPcs's outputs. Frames start in lane 0 or lane 4; the 7 preamble bytes are skipped. A frame's verdict is
    reported 2 clocks after its terminate (3 after a lane-4 flush); a reset in between loses it."""
    IDLE_, FRAME, FLUSH = 0, 1, 2

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.st = self.IDLE_
        self.fbytes = bytearray()
        self.skip = 0
        self.s4 = False
        self.done: list[RxFrame] = []
        self.pend_f = None
        self.pend_n = 0
        self.n_abort = self.n_frames = self.last_tl = 0

    def _abort(self) -> None:
        self.done.append(RxFrame(aborted=True, s4=self.s4))
        self.n_abort += 1
        self.st = self.IDLE_
        self.fbytes = bytearray()
        self.pend_n = 0

    def _finish(self, delay: int) -> None:
        b = bytes(self.fbytes)
        ok = len(b) >= 4 and zlib.crc32(b[:-4]).to_bytes(4, "little") == b[-4:]
        self.pend_f, self.pend_n = RxFrame(b, ok, False, self.s4, self.last_tl), delay
        self.fbytes = bytearray()

    def step(self, lock: bool, x_v: bool, d: int, c: int) -> None:
        if self.pend_n > 0:
            self.pend_n -= 1
            if self.pend_n == 0:
                self.done.append(self.pend_f)
                self.n_frames += 1
        if self.st == self.FLUSH:
            if not lock:
                self._abort()
            else:
                self.st = self.IDLE_
            return
        if not lock and self.st != self.IDLE_:
            self._abort()
            return
        if not x_v:
            return
        tl = term_lane(d, c)
        is0 = c == 0x01 and lane(d, 0) == START
        is4 = c == 0x1F and lane(d, 4) == START
        if self.st == self.IDLE_:
            if is0 or is4:
                self.st, self.fbytes, self.s4 = self.FRAME, bytearray(), is4
                self.skip = 4 if is4 else 0
        elif self.st == self.FRAME:
            if c == 0x00:
                for i in range(8):
                    if self.skip > 0:
                        self.skip -= 1
                    else:
                        self.fbytes.append(lane(d, i))
            elif tl >= 0:
                if self.skip > 0:
                    self._abort()
                else:
                    self.fbytes += bytes(lane(d, i) for i in range(tl))
                    self.last_tl = tl
                    if self.s4 and tl > 4:
                        self._finish(3)
                        self.st = self.FLUSH
                    else:
                        self._finish(2)
                        self.st = self.IDLE_
            else:
                self._abort()
