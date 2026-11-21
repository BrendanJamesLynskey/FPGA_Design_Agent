"""The virtual sequences of the pyuvm bench (brief 123): the eleven directed scenarios and the constrained-random mix of brief 112, ported one for one.
`VseqBase` holds the helpers. pyuvm's `uvm_sequence.start_item` needs the sequence to run on one sequencer, so a virtual sequence sends its items straight to
the sequencer of the agent it wants (`sqr.start_item` / `sqr.finish_item`, which is what `start_item(item, -1, p_sequencer.usr)` does in SystemVerilog)."""
from __future__ import annotations

import os

import cocotb
from cocotb.triggers import RisingEdge
from pyuvm import uvm_sequence

from . import refmodels as ref
from .items import PATTERNS, FrameItem, LineItem, XgItem, make_payload

# PYUVM_BLIND=1 leaves out the two patterns that brief 112 added after seeing mutants M13 and M15 survive (the flush-state lock loss, the residue-bit FCS errors),
# which gives the 'before hindsight' mutant result
BLIND = os.environ.get("PYUVM_BLIND") == "1"

RES_MASK = [0xDB710641, 0x6D930AC3, 0xDB261586, 0x6D3D2D4D, 0xDA7A5A9A, 0x6F85B375, 0xDF0B66EA, 0x6567CB95, 0xCACF972A, 0x4EEE2815, 0x9DDC502A, 0xE0C9A615, 0x1AE24A6B,
            0x35C494D6, 0x6B8929AC, 0xD7125358, 0x7555A0F1, 0xEAAB41E2, 0x0E278585, 0x1C4F0B0A, 0x389E1614, 0x713C2C28, 0xE2785850, 0x1F81B6E1, 0x3F036DC2, 0x7E06DB84,
            0xFC0DB708, 0x236A6851, 0x46D4D0A2, 0x8DA9A144, 0xC02244C9, 0x5B358FD3]


class VseqBase(uvm_sequence):
    def __init__(self, name="vseq", env=None):
        super().__init__(name)
        self.env = env
        self.rng = env.rng if env is not None else None
        self.line_mode = False

    # ---- time and state
    async def clks(self, n: int) -> None:
        for _ in range(n):
            await RisingEdge(self.env.dut.clk)

    async def wait_lock(self, timeout: int = 30000, extra: int = 20) -> None:
        """Wait for the reference receiver's lock (the DUT's is checked clock for clock by the scoreboard), then a few clocks more."""
        t = 0
        while not self.env.sb.rrx.lock and t < timeout:
            await RisingEdge(self.env.dut.clk); t += 1
        if t >= timeout:
            self.env.sb.fail("RXPCS", "SEQ: the receiver did not lock")
        await self.clks(extra)

    def e2e(self, on: bool) -> None:
        self.env.sb.e2e_en = on
        if not on:
            self.env.sb.e2e_q.clear()

    async def drain(self, n: int = 400) -> None:
        await self.clks(n)

    async def par(self, *coros) -> None:
        """fork ... join."""
        tasks = [cocotb.start_soon(c) for c in coros]
        for t in tasks:
            await t

    # ---- items
    @staticmethod
    async def _send(sqr, item) -> None:
        await sqr.start_item(item)
        await sqr.finish_item(item)

    async def frame(self, l: int, p: bool = False, g: int = 0, pt: str = "PAT_RANDOM", noise: bool = False) -> None:
        await self._send(self.env.usr.sqr, FrameItem(payload=make_payload(self.rng, l, pt), pat=pt, poison=p, noise_poison=noise, gap=g))

    async def rand_frame(self, lo: int, hi: int, glo: int = 0, ghi: int = 40, poison_pct: int = 10) -> None:
        r = self.rng
        pt = r.choices(PATTERNS, weights=[8, 1, 1, 1, 1])[0]
        await self._send(self.env.usr.sqr, FrameItem(payload=make_payload(r, r.randint(lo, hi), pt), pat=pt, poison=r.randrange(100) < poison_pct, gap=r.randint(glo, ghi)))

    async def xg(self, words, tag: str = "") -> None:
        await self._send(self.env.xg.sqr, XgItem(words=words, tag=tag))

    async def line(self, kind: str, n: int = 0, mask: int = 0, skip: int = 0) -> None:
        await self._send(self.env.line.sqr, LineItem(kind=kind, n=n, mask=mask, skip=skip))

    async def line_blocks(self, q) -> None:
        await self._send(self.env.line.sqr, LineItem(kind="BLOCKS", blks=q))

    # ---- helpers
    def rbytes(self, n: int) -> bytes:
        return self.rng.randbytes(n)

    @staticmethod
    def blocks_of(words):
        return [ref.encode_rtl(d, c, True) for d, c in words]

    @staticmethod
    def idle_blocks(n: int):
        return [ref.encode_rtl(*ref.IDLE_WORD)] * n

    def raw(self, sh: int, typ: int):
        return sh, (self.rng.getrandbits(56) << 8) | typ

    def os_block(self, j: int):
        return self.raw(0b10, ref.pcs.T_OS[j])

    def bad_type_block(self):
        return self.raw(0b10, self.rng.choice([0x00, 0x01, 0x10, 0x20, 0x40, 0x80, 0xF0, 0xC3, 0x5A, 0xA5]))

    def bad_sh_block(self):
        return self.raw(self.rng.choice([0b00, 0b11]), self.rng.getrandbits(8))


# ------------------------------------------------------------------------------------------------------ loopback, user-side frames
class VseqSmoke(VseqBase):
    async def body(self):
        await self.wait_lock(); self.e2e(True)
        for a in [(60,), (64,), (1514, 0, 0), (61, 0, 5), (100, 1, 0), (60, 0, 0), (1514, 0, 0)]:
            await self.frame(*a)
        await self.drain(); self.e2e(False)


class VseqLens(VseqBase):
    async def body(self):
        big = [127, 128, 129, 255, 256, 511, 512, 1023, 1024, 1500, 1514, 1600, 4000, 9000]
        await self.wait_lock(); self.e2e(True)
        for l in range(60, 100):
            await self.frame(l, 0, l % 3)
        for i, b in enumerate(big):
            await self.frame(b, 0, i % 4)
        for l in range(60, 76):
            await self.frame(l, 0, 0)
        await self.drain(); self.e2e(False)


class VseqGaps(VseqBase):
    async def body(self):
        g = [0, 0, 1, 2, 3, 4, 5, 8, 12, 16, 17, 32, 33, 34, 64, 100, 300, 520]
        await self.wait_lock(); self.e2e(True)
        for i, gi in enumerate(g):
            await self.frame(60 + (i * 7) % 90, 0, gi)
        for _ in range(30):
            await self.rand_frame(60, 300, 0, 3, 0)
        await self.frame(60, 0, 300); await self.frame(61, 0, 300); await self.frame(9000, 0, 300); await self.frame(9000, 0, 2)   # a long gap after a minimum frame and after a jumbo
        # added after the first merge of this bench showed these two length-by-gap bins open (215 of 217): a minimum frame after a short gap, a 1400-byte frame after a long one
        await self.frame(60, 0, 2); await self.frame(1400, 0, 300)
        await self.drain(); self.e2e(False)


class VseqBadfcs(VseqBase):
    async def body(self):
        await self.wait_lock(); self.e2e(True)
        for i in range(48):
            await self.frame(60 + (i * 13) % 200, (i % 3) == 0, i % 4, PATTERNS[i % 5], True)
        await self.frame(1514, 1, 0, "PAT_ONES", True); await self.frame(60, 1, 0, "PAT_ZEROS", True); await self.frame(60, 0, 0)
        await self.drain(); self.e2e(False)


# ------------------------------------------------------------------------------------------------------ loopback, XGMII injection
def put_err(w, wi: int, ln: int):
    """An error character in lane ln of word wi."""
    d, c = w[wi]
    w[wi] = ((d & ~(0xFF << (8 * ln))) | (ref.ERRC << (8 * ln)), c | (1 << ln))
    return w


class VseqXg(VseqBase):
    async def body(self):
        rb, fw = self.rbytes, ref.frame_words
        await self.wait_lock()
        # clean frames, start in lane 0 and in lane 4, every terminate lane (lengths 60..75 cover every residue mod 8)
        for l in range(60, 76):
            await self.xg(fw(rb(l), False, False), f"l0 len {l}")
            await self.xg(fw(rb(l), True, False), f"l4 len {l}")
        await self.xg(fw(rb(300), True, True), "l4 bad fcs")
        await self.xg(fw(rb(1000), False, True), "l0 bad fcs")
        # error characters inside a frame, in the preamble word, in the terminate word
        for k in range(6):
            w = fw(rb(80 + 3 * k), bool(k % 2), False)
            await self.xg(put_err(w, 1 + (k % 4), k % 8), "error character in data")
        # a frame cut short: idles where data should be; a second start inside a frame; a terminate without a start
        w = fw(rb(100), False, False); await self.xg(w[0:3], "cut: idles follow")
        w = fw(rb(100), False, False); v = w[0:4] + [w[0]] + fw(rb(70), False, False); await self.xg(v, "second start inside a frame")
        for k in range(8):
            d = ref.IDLE_D & ~(0xFF << (8 * k)) | (ref.TERM << (8 * k))
            await self.xg([(d, 0xFF)], f"lone terminate lane {k}")
        # start followed at once by a terminate, in lane 0 and lane 4 (a frame with no data)
        for k in range(8):
            t = (ref.IDLE_D & ~(0xFF << (8 * k)) | (ref.TERM << (8 * k)), (0xFF << k) & 0xFF)
            await self.xg([(int.from_bytes(bytes([ref.START, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0xD5]), "little"), 0x01), t], f"start then terminate lane {k}")
            await self.xg([(int.from_bytes(bytes([ref.IDLE] * 4 + [ref.START, 0x55, 0x55, 0x55]), "little"), 0x1F), t], f"lane-4 start then terminate lane {k}")
        # ordered sets, local-fault sequences, start in another lane, malformed control vectors, bad data words: pcs_tx must turn them into error blocks
        for i in range(12):
            d, c = int.from_bytes(bytes([ref.IDLE] * 4 + [0x9C, 0x01, 0x00, 0x00]), "little"), 0x01 << (i % 2)
            if i >= 4:
                d = self.rng.getrandbits(64); c = self.rng.getrandbits(8)
                if c in (0x00, 0xFF):
                    c = 0x5A
            await self.xg([(d, c)], "ordered set or malformed word")
        # FCS errors that move the CRC residue in exactly one bit position (a receiver whose FCS compare ignores one residue bit fails the frame of that bit)
        for b, m in enumerate([] if BLIND else RES_MASK):
            await self.xg(fw(rb(64 + b % 8), False, False, m), f"residue bit {b} only")
        # frames after all that: the receiver must still be locked and framing
        for l in range(60, 70):
            await self.xg(fw(rb(l), bool(l % 2), False), "recovery frame")
        await self.drain()


# ------------------------------------------------------------------------------------------------------ line mode: the line agent's own block stream
class VseqLineBlocks(VseqBase):
    async def body(self):
        rb, fw, lb, ib = self.rbytes, ref.frame_words, self.line_blocks, self.idle_blocks
        bo = self.blocks_of
        await self.wait_lock()
        # frames from raw blocks, lane 0 and lane 4, every terminate lane
        for l in range(60, 84):
            await lb(bo(fw(rb(l), False, (l % 5) == 0)))
            await lb(ib(1 + l % 3))
            await lb(bo(fw(rb(l), True, (l % 7) == 0)))
            await lb(ib(1 + l % 2))
        # ordered sets of all four types, between frames and inside one
        for j in range(4):
            await lb([self.os_block(j)] + ib(2))
        q = bo(fw(rb(200), False, False)); q.insert(5, self.os_block(1)); await lb(q)
        await lb(ib(3))
        # all-error control blocks, unknown block types, a single bad sync header (lock holds), data blocks outside a frame
        for _ in range(4):
            await lb([ref.err_block(), self.bad_type_block(), self.bad_sh_block()]); await lb(ib(2))
        await lb([(0b01, self.rng.getrandbits(64)) for _ in range(4)])
        # terminate blocks of every lane with no start, start blocks of both kinds back to back, a bad type inside a frame
        for k in range(8):
            d = ref.IDLE_D & ~(0xFF << (8 * k)) | (ref.TERM << (8 * k))
            for i in range(k):
                d = d & ~(0xFF << (8 * i)) | (self.rng.getrandbits(8) << (8 * i))
            await lb([ref.encode_rtl(d, (0xFF << k) & 0xFF)])
        q = bo(fw(rb(90), False, False)); q.insert(4, self.bad_type_block()); await lb(q)
        q = bo(fw(rb(90), True, False)); q.insert(3, self.bad_sh_block()); await lb(q)
        q = bo(fw(rb(90), False, False)); q = q[0:2] + q; await lb(q)                      # a second start inside the frame
        for l in range(60, 70):
            await lb(bo(fw(rb(l), bool(l % 2), False)))
        await lb(ib(40))
        # lock lost while a frame is in progress: 15 bad headers spread over 30 blocks, then a frame with the 16th bad header either in its 5th block (even
        # phases) or straight after its terminate block (odd phases: a lane-4 frame with the terminate in lane 5, 6 or 7, so mac64_rx is in its flush state
        # when the lock drops: the one place where its lock-loss branch is not made redundant by the error word the bad header delivers). The 64-block window
        # of the lock FSM has an unknown phase, so the pattern is tried at 12 phases
        for ph in range(12):
            await lb(ib(3 + 5 * ph))
            q = []
            for _ in range(15):
                q.append(self.bad_sh_block()); q.append(ref.encode_rtl(ref.IDLE_D, 0xFF))
            await lb(q)
            if ph % 2 == 0 or BLIND:
                q = bo(fw(rb(100), False, False)); q.insert(5, self.bad_sh_block())
            else:
                q = bo(fw(rb(61 + (ph // 2) % 3 + 8 * (ph // 6)), True, False)); q.append(self.bad_sh_block())
            await lb(q)
            await lb(ib(20))
            await self.wait_lock(60000)
        await self.drain()


# ------------------------------------------------------------------------------------------------------ loopback faults and lock
class VseqHdr(VseqBase):
    HB = [15, 16, 17, 30, 70]
    HD = [40, 30, 60, 100, 20]

    async def body(self):
        await self.wait_lock(); self.e2e(True)
        for i in range(6):
            await self.frame(60 + 20 * i)
        self.e2e(False)
        # isolated header errors: counted, lock holds
        for i in range(3):
            await self.par(self.frame(300, 0, 0), self._after(25, "HDR", 1 + i))
            await self.drain(60)
        # 15 inside the window: the limit; 16 and more: the lock is lost (in a frame, then idle), the receiver hunts and locks again
        for hb, hd in zip(self.HB, self.HD):
            await self.par(self._two(), self._after(hd, "HDR", hb))
            await self.drain(100)
            await self.wait_lock()
        # sparse corruption: every (skip+1)th header bad, 16 of them
        for sk in range(3, 15):
            await self.par(self._many(40), self._after(40, "HDR", 16, sk))
            await self.drain(100)
            await self.wait_lock()
        self.e2e(True)
        for i in range(8):
            await self.frame(70 + i)
        await self.drain(); self.e2e(False)

    async def _two(self):
        await self.frame(1514, 0, 0); await self.frame(200, 0, 0)

    async def _many(self, n):
        for _ in range(n):
            await self.frame(60, 0, 0)

    async def _after(self, n, kind, arg, skip=0):
        await self.clks(n); await self.line(kind, arg, 0, skip)


class VseqSlip(VseqBase):
    async def body(self):
        await self.wait_lock()
        for r in range(4):
            await self.par(self._frames(), self._slips(r))
            await self.drain(100)
            await self.wait_lock(60000)                      # hunting: one slip per 64 blocks until the alignment is found again
        self.e2e(True)
        for i in range(6):
            await self.frame(64 + i)
        await self.drain(); self.e2e(False)

    async def _frames(self):
        for i in range(6):
            await self.frame(100 + 50 * i, 0, 2)

    async def _slips(self, r):
        await self.clks(60 + 30 * r)
        await self.line("SLIP_DEL" if r % 2 else "SLIP_INS")
        if r >= 2:
            await self.clks(40); await self.line("SLIP_INS")


class VseqBer(VseqBase):
    async def body(self):
        await self.wait_lock()
        for ppm in [0, 20, 300, 2000, 30000]:
            await self.line("BER", ppm)
            for _ in range(14):
                await self.rand_frame(60, 700, 0, 6, 0)
            await self.drain(100)
            await self.line("BER", 0)
            await self.drain(100)
            await self.wait_lock(60000)
        self.e2e(True)
        for i in range(6):
            await self.frame(66 + i)
        await self.drain(); self.e2e(False)


class VseqRxreset(VseqBase):
    async def body(self):
        await self.wait_lock()
        for r in range(3):
            await self.par(self._frames(), self._rst(r))
            await self.drain(100)
            await self.wait_lock(60000)
        self.e2e(True)
        for i in range(6):
            await self.frame(62 + i)
        await self.drain(); self.e2e(False)

    async def _frames(self):
        for i in range(6):
            await self.frame(300 + 100 * i, 0, 1)

    async def _rst(self, r):
        await self.clks(50 + 70 * r); await self.line("RXRESET", 1 + 2 * r)


class VseqOffsets(VseqBase):
    """A clean frame burst after resetting with each initial bit offset: lock acquisition from every alignment class."""

    async def body(self):
        for off in [0, 1, 2, 5, 17, 33, 50, 60, 62, 64, 65, 66, 100, 131, 132]:
            await self.env.sys.apply_reset(False, off)
            await self.wait_lock(60000); self.e2e(True)
            for k in range(4):
                await self.frame(60 + (off + k) % 40, 0, k)
            await self.drain(300); self.e2e(False)


# ------------------------------------------------------------------------------------------------------ constrained random
class VseqRand(VseqBase):
    n_actions = 60

    async def body(self):
        r = self.rng
        bers = [0, 0, 50, 300, 1000]
        await self.wait_lock(60000)
        for a in range(self.n_actions):
            x = r.randrange(100)
            if x < 45:
                for _ in range(r.randint(1, 4)):
                    c = r.randrange(100)
                    if self.line_mode:
                        n = r.randint(60, 90) if c < 60 else r.randint(91, 400)
                        await self.line_blocks(self.blocks_of(ref.frame_words(self.rbytes(n), bool(r.getrandbits(1)), r.randrange(10) == 0)))
                    elif c < 50: await self.rand_frame(60, 90)
                    elif c < 80: await self.rand_frame(91, 300)
                    elif c < 97: await self.rand_frame(301, 1514)
                    else: await self.rand_frame(1515, 6000, 0, 4, 5)
            elif x < 55:
                if self.line_mode: await self.line_blocks(self.idle_blocks(r.randint(1, 30)))
                else: await self.clks(r.randint(1, 200))
            elif x < 65:
                await self.line("FLIP", 0, 1 << r.randrange(64))
            elif x < 70:
                await self.line("HDR", r.choice([1, 3, 8, 15, 16, 17, 25]))
            elif x < 73:
                await self.line("SLIP_INS" if r.getrandbits(1) else "SLIP_DEL")
            elif x < 77 and not self.line_mode:
                w = ref.frame_words(self.rbytes(r.randint(60, 120)), bool(r.getrandbits(1)), r.randrange(6) == 0)
                if r.randrange(3) == 0:
                    put_err(w, r.randrange(len(w)), r.randrange(8))
                await self.xg(w, "random xg")
            elif x < 80:
                await self.line("RXRESET", r.randint(1, 4))
            elif x < 82 and self.line_mode:
                await self.line_blocks([self.os_block(r.randrange(4)), self.bad_type_block(), ref.err_block()])
            elif x < 90:
                await self.line("BER", r.choice(bers))
            else:
                await self.clks(r.randint(1, 50))
            if a % 15 == 14:
                await self.line("BER", 0); await self.drain(300)
        await self.line("BER", 0); await self.drain(600)
