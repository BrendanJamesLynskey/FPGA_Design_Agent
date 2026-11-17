"""Python reference for the 10GBASE-R PCS of brief 96 (IEEE 802.3 clause 49, written from the block formats and the
state diagram, not from any implementation).

Everything here is bit-serial or big-integer arithmetic, deliberately unlike the RTL (64 bits in parallel), so the two
do not share a structure. ``TxPcs`` and ``RxPcs`` are cycle models of the RTL's registers (one call = one clock edge);
the lower-level functions (``Scrambler``, ``encode_block``, ``decode_block``, ``gearbox_words``, ``BlockLock``) stand alone.

XGMII convention: eight lanes, lane i = byte i of a 64-bit integer ``d`` and bit i of the 8-bit ``c`` (1 = control char).
Control characters: IDLE 0x07, START 0xFB, TERM 0xFD, ERROR 0xFE.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

IDLE, START, TERM, ERR = 0x07, 0xFB, 0xFD, 0xFE
M58 = (1 << 58) - 1
M66 = (1 << 66) - 1
M64 = (1 << 64) - 1

# block types (payload bits 7:0)
T_CTRL, T_S0, T_S4 = 0x1E, 0x78, 0x33
T_TERM = [0x87, 0x99, 0xAA, 0xB4, 0xCC, 0xD2, 0xE1, 0xFF]   # terminate in lane k
T_OS = (0x2D, 0x4B, 0x55, 0x66)                              # ordered sets (counted, shown as idle)


# ---------------------------------------------------------------------------------------------------- scrambler
class Scrambler:
    """Self-synchronising scrambler x^58 + x^39 + 1, one bit at a time. ``hist`` bit 0 is the newest scrambled bit."""

    def __init__(self, seed: int = 0) -> None:
        self.hist = seed & M58

    def bit(self, d: int) -> int:
        o = d ^ ((self.hist >> 38) & 1) ^ ((self.hist >> 57) & 1)
        self.hist = ((self.hist << 1) | o) & M58
        return o

    def word(self, d: int, n: int = 64) -> int:
        return sum(self.bit((d >> i) & 1) << i for i in range(n))


class Descrambler:
    def __init__(self, seed: int = 0) -> None:
        self.hist = seed & M58

    def bit(self, s: int) -> int:
        o = s ^ ((self.hist >> 38) & 1) ^ ((self.hist >> 57) & 1)
        self.hist = ((self.hist << 1) | s) & M58
        return o

    def word(self, s: int, n: int = 64) -> int:
        return sum(self.bit((s >> i) & 1) << i for i in range(n))


# ---------------------------------------------------------------------------------------------------- block codes
def _lane(d: int, i: int) -> int:
    return (d >> (8 * i)) & 0xFF


def _ctl7(ch: int) -> int:
    """XGMII control character -> 7-bit control code (idle 0x00, everything else coded as error 0x1E)."""
    return 0x00 if ch == IDLE else 0x1E


def encode_block(d: int, c: int) -> tuple[int, int]:
    """One XGMII word -> (sync header, 64-bit payload) as the transmitter sends it. Words the MAC never produces
    (start in lane 4, ordered sets, anything malformed) become an all-error block, as an encoder must not invent them."""
    if c == 0x00:
        return 0b01, d
    err_block = (0b10, T_CTRL | sum(0x1E << (8 + 7 * i) for i in range(8)))
    if c == 0xFF and all(_lane(d, i) in (IDLE, ERR) for i in range(8)):
        return 0b10, T_CTRL | sum(_ctl7(_lane(d, i)) << (8 + 7 * i) for i in range(8))
    if c == 0x01 and _lane(d, 0) == START:
        return 0b10, T_S0 | (d & ~0xFF)
    if c == 0x1F and _lane(d, 4) == START and all(_lane(d, i) in (IDLE, ERR) for i in range(4)):
        # start in lane 4 (not produced by our MAC; the test benches use it to exercise the receiver)
        return 0b10, T_S4 | sum(_ctl7(_lane(d, i)) << (8 + 7 * i) for i in range(4)) | ((d >> 40) << 40)
    for k in range(8):
        want = (0xFF << k) & 0xFF
        if c == want and _lane(d, k) == TERM and all(_lane(d, i) in (IDLE, ERR) for i in range(k + 1, 8)):
            p = T_TERM[k] | ((d & ((1 << (8 * k)) - 1)) << 8)
            base = 8 + 8 * k + (7 - k)
            for i in range(k + 1, 8):
                p |= _ctl7(_lane(d, i)) << (base + 7 * (i - k - 1))
            return 0b10, p
    return err_block


def decode_block(sh: int, p: int) -> tuple[int, int, str]:
    """(sync header, payload) -> (d, c, note). note is '' for a normal block, 'sh' for an invalid sync header, 'type' for
    an unknown block type, 'os' for an ordered set (shown as idles)."""
    all_err = (sum(ERR << (8 * i) for i in range(8)), 0xFF)
    all_idle = (sum(IDLE << (8 * i) for i in range(8)), 0xFF)
    if sh == 0b01:
        return p & M64, 0x00, ""
    if sh != 0b10:
        return *all_err, "sh"
    t = p & 0xFF

    def ctl(i0: int, base: int) -> tuple[int, int]:
        d = c = 0
        for j, i in enumerate(range(i0, 8)):
            code = (p >> (base + 7 * j)) & 0x7F
            d |= (IDLE if code == 0 else ERR) << (8 * i)
            c |= 1 << i
        return d, c

    if t == T_CTRL:
        d, c = ctl(0, 8)
        return d, c, ""
    if t == T_S0:
        return (p & ~0xFF & M64) | START, 0x01, ""
    if t == T_S4:
        d, c = ctl(0, 8)
        d &= (1 << 32) - 1
        c &= 0x0F
        d |= START << 32
        c |= 0x10
        d |= (p >> 40) << 40
        return d, c, ""
    if t in T_TERM:
        k = T_TERM.index(t)
        d = (p >> 8) & ((1 << (8 * k)) - 1)
        d |= TERM << (8 * k)
        c = 1 << k
        if k < 7:
            dd, cc = ctl(k + 1, 8 + 8 * k + (7 - k))
            d |= dd
            c |= cc
        return d, c, ""
    if t in T_OS:
        return *all_idle, "os"
    return *all_err, "type"


# ---------------------------------------------------------------------------------------------------- bit streams
def block_bits(sh: int, payload: int) -> list[int]:
    """A 66-bit block as sent: the two sync-header bits (bit 0 first), then the 64 payload bits, least significant first."""
    return [(sh >> 0) & 1, (sh >> 1) & 1] + [(payload >> i) & 1 for i in range(64)]


def bits_to_words(bits: list[int]) -> list[int]:
    return [sum(b << i for i, b in enumerate(bits[j:j + 64])) for j in range(0, len(bits) - 63, 64)]


def words_to_bits(words: list[int]) -> list[int]:
    return [(w >> i) & 1 for w in words for i in range(64)]


# ---------------------------------------------------------------------------------------------------- TX cycle model
class TxPcs:
    """The transmitter's register behaviour: one ``step`` per clock edge. ``adv`` (before the edge) says whether the word
    offered is taken; it is 0 for one clock in 33 (the gearbox pause)."""

    def __init__(self) -> None:
        self.scr = Scrambler(0)
        self.acc = 0
        self.n = 0
        self.out = 0

    @property
    def adv(self) -> int:
        return 0 if self.n == 64 else 1

    def step(self, d: int, c: int) -> int:
        if self.adv:
            sh, p = encode_block(d, c)
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


# ---------------------------------------------------------------------------------------------------- block lock
@dataclass
class BlockLock:
    """Clause 49 block-lock state diagram as built: 64 valid headers with no invalid one to lock; in lock, 16 invalid headers
    inside a 64-header window lose it; every failure while hunting, and a loss, slips one bit. After a slip the next block
    (formed before the slip took effect) is ignored."""
    lock: bool = False
    sh_cnt: int = 0
    inv_cnt: int = 0
    settle: int = 0
    slips: int = 0
    losses: int = 0
    locks: int = 0

    def block(self, sh: int) -> bool:
        """Feed one block's header; returns True when a bit slip is requested."""
        if self.settle:
            self.settle -= 1
            return False
        valid = sh in (0b01, 0b10)
        self.sh_cnt += 1
        if not valid:
            self.inv_cnt += 1
        slip = False
        if not valid and (not self.lock or self.inv_cnt == 16):
            if self.lock:
                self.losses += 1
            self.lock = False
            slip = True
            self.slips += 1
            self.settle = 1
            self.sh_cnt = self.inv_cnt = 0
        elif self.sh_cnt == 64:
            if not self.lock and self.inv_cnt == 0:
                self.lock = True
                self.locks += 1
            self.sh_cnt = self.inv_cnt = 0
        return slip


# ---------------------------------------------------------------------------------------------------- RX cycle model
@dataclass
class RxPcs:
    """The receiver's register behaviour, one ``step`` per clock edge with one 64-bit word from the GT. Outputs a list of
    (d, c, note) for every block that leaves the decoder with the lock held (``out``), and the same block count per word."""
    acc: int = 0
    cnt: int = 0
    blk: tuple[int, int] | None = None   # (sh, payload) registered after stage A
    slip_r: bool = False
    fsm: BlockLock = field(default_factory=BlockLock)
    desc: Descrambler = field(default_factory=Descrambler)
    out: list[tuple[int, int, str]] = field(default_factory=list)
    x: tuple[int, int, str] | None = None   # the registered decoder output this cycle (None = valid low)
    t: int = 0                               # steps taken
    ext_t: list = field(default_factory=list)  # step at which each block was extracted (its last bit arrived)
    xs: list = field(default_factory=list)     # (x valid, d, c) after each step
    sh_err: int = 0
    type_err: int = 0
    os_cnt: int = 0

    def step(self, word: int) -> tuple[int, int, str] | None:
        # stage B and the FSM: operate on the block registered at the previous edge
        x_n = None
        slip_n = False
        if self.blk is not None:
            sh, p = self.blk
            pd = self.desc.word(p)
            d, c, note = decode_block(sh, pd)
            if self.fsm.lock:
                x_n = (d, c, note)
                if note == "sh":
                    self.sh_err += 1
                elif note == "type":
                    self.type_err += 1
                elif note == "os":
                    self.os_cnt += 1
            slip_n = self.fsm.block(sh)
        # stage A: merge the new word, apply the registered slip, extract at most one block
        m = self.acc | (word << self.cnt)
        k = self.cnt + 64
        if self.slip_r:
            m >>= 1
            k -= 1
        blk_n = None
        if k >= 66:
            blk_n = (m & 3, (m >> 2) & M64)
            m >>= 66
            k -= 66
        if blk_n is not None:
            self.ext_t.append(self.t)
        self.acc, self.cnt, self.blk, self.slip_r, self.x = m, k, blk_n, slip_n, x_n
        self.xs.append((1, x_n[0], x_n[1]) if x_n is not None else (0, None, None))
        self.t += 1
        if x_n is not None:
            self.out.append(x_n)
        return x_n


# ---------------------------------------------------------------------------------------------------- frames
def fcs(frame: bytes) -> bytes:
    return zlib.crc32(frame).to_bytes(4, "little")


def frame_words(frame: bytes, lane0: bool = True) -> list[tuple[int, int]]:
    """XGMII words of one frame (preamble, data, FCS, terminate), starting in lane 0 (or lane 4 after four idle lanes) and
    ending with the terminate lane followed by idles in the same word. No gap words."""
    data = bytes([START] + [0x55] * 6 + [0xD5]) + frame + fcs(frame)
    cs = [1] + [0] * (len(data) - 1)
    if not lane0:
        data = bytes([IDLE] * 4) + data
        cs = [1] * 4 + cs
    data += bytes([TERM])
    cs += [1]
    while len(data) % 8:
        data += bytes([IDLE])
        cs += [1]
    out = []
    for i in range(0, len(data), 8):
        out.append((int.from_bytes(data[i:i + 8], "little"), sum(b << j for j, b in enumerate(cs[i:i + 8]))))
    return out


IDLE_WORD = (sum(IDLE << (8 * i) for i in range(8)), 0xFF)


def parse_xgmii(words: list[tuple[int, int]]) -> list[dict]:
    """Independent frame parser for the checks: returns one dict per frame {data, fcs_ok, start_lane, term_lane, gap_before}."""
    frames = []
    cur = None
    idles_since = None   # idle/other bytes since the last terminate
    for d, c in words:
        for i in range(8):
            b, ctl = _lane(d, i), (c >> i) & 1
            if cur is None:
                if ctl and b == START:
                    cur = bytearray()
                    frames.append({"start_lane": i, "gap_before": idles_since})
                    idles_since = None
                elif idles_since is not None:
                    idles_since += 1
            else:
                if ctl and b == TERM:
                    raw = bytes(cur[7:])    # drop the preamble tail (6 x 0x55 and SFD)
                    ok = zlib.crc32(raw[:-4]).to_bytes(4, "little") == raw[-4:] if len(raw) > 4 else False
                    frames[-1].update(data=raw[:-4], fcs_ok=ok, term_lane=i, preamble_ok=bytes(cur[:7]) == bytes([0x55] * 6 + [0xD5]))
                    cur = None
                    idles_since = 1   # the terminate counts toward the gap
                elif ctl:
                    frames[-1].update(error=True)
                else:
                    cur.append(b)
    return frames
