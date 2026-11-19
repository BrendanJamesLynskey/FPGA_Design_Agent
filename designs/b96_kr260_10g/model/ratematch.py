"""Twin of rtl/rate_match.sv (brief 96C): the receive-to-core elastic buffer with idle insertion and deletion.

A clock-by-clock model of two clock domains. ``RateMatch.w_edge`` is one edge of the write (receive, recovered) clock, ``r_edge`` one edge
of the read (core, transmit user) clock; ``run`` merges the two edge lists in time order. The two pointer crossings are modelled as the
RTL's xpm_cdc_gray does them (a gray register in the source domain, ``sync`` flops in the destination domain, a binary decode, optionally
one more register), so the RTL and this model can be compared output for output. Times are integers (femtoseconds); two edges at the same
time are refused (the RTL has no defined order for them).

Policy (the same text as the RTL header, restated so the two can be read side by side):

* the write side writes every valid block from the PCS, unless the FIFO macro says full (it sees an old read pointer, so this is conservative): that block is dropped
  and counted in ``n_ovf``. Nothing else is ever dropped there;
* the reader outputs at most one block a clock, in 32 of every 33 clocks (the *slot* clocks; the 33rd, the *pause* clock, is the same
  cadence the transmit gearbox has);
* in a slot clock: with at least one block visible it pops and outputs the head; with none visible and the last output not inside a frame
  it inserts one idle block; with none visible and the last output inside a frame it outputs nothing (a one-clock bubble, ``n_stall``);
* in the pause clock: if the visible fill is above ``hi``, the last output was not inside a frame, at least ``min_keep`` pure idle blocks
  were just output, and the head is a pure idle block, the head is popped and not output (deleted, ``n_del``);
* a block is *inside a frame* from a start block (lane 0 or lane 4) or a data block until the next block that is neither;
  a pure idle block is an all-idle control block that is not an ordered set; ordered sets, error blocks and terminate blocks
  are never inserted, duplicated or deleted;
* while the (synchronised) block lock is low the reader discards what is in the buffer, one block a clock, and outputs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

IDLE_D = 0x0707070707070707
IDLE_BLK = (IDLE_D, 0xFF, 0)


def gray(b: int) -> int:
    return b ^ (b >> 1)


def ungray(g: int, width: int) -> int:
    b = 0
    for i in range(width - 1, -1, -1):
        b |= (((g >> i) ^ (b >> (i + 1))) & 1) << i
    return b


def is_pure_idle(d: int, c: int, os: int) -> bool:
    return c == 0xFF and d == IDLE_D and not os


def in_frame_after(d: int, c: int) -> bool:
    """True for a block after which the stream is inside a frame: a start block (lane 0 or lane 4) or a data block."""
    if c == 0x00:
        return True
    if c == 0x01 and (d & 0xFF) == 0xFB:
        return True
    if c == 0x1F and ((d >> 32) & 0xFF) == 0xFB:
        return True
    return False


@dataclass
class RateMatch:
    """Model of rtl/rate_match.sv around the repo's Icarus stand-in of xpm_fifo_async (flow/cdc_models/xpm_cdc_models.sv, FWFT with read data count), not around the
    real macro: the real macro's latencies differ in detail. The stand-in's start-up handshake is assumed finished (the bench holds the read reset long enough)."""
    aw: int = 4
    hi: int = 4
    min_keep: int = 0
    sync: int = 2                 # CDC_SYNC_STAGES of the macro
    lock_sync: int = 2
    # write side
    wbin: int = 0
    wg: int = 0
    w_gs: list = field(default_factory=list)      # synchroniser of the read gray pointer, write domain
    wfull: bool = False
    n_ovf: int = 0
    n_wr: int = 0
    # read side
    rbin: int = 0
    rg: int = 0
    r_gs: list = field(default_factory=list)      # synchroniser of the write gray pointer, read domain
    rempty: bool = True
    r_ls: list = field(default_factory=list)
    pace: int = 0
    in_frame: bool = False
    idle_run: int = 0
    r_v: bool = False
    r_blk: tuple = IDLE_BLK
    r_lock: bool = False
    n_ins: int = 0
    n_del: int = 0
    n_stall: int = 0
    n_out: int = 0
    n_drain: int = 0
    fill_min: int = (1 << 32) - 1
    fill_max: int = 0
    mem: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.depth = 1 << self.aw
        self.mask = (1 << (self.aw + 1)) - 1
        self.mem = [(0, 0, 0)] * self.depth
        self.w_gs = [0] * self.sync
        self.r_gs = [0] * self.sync
        self.r_ls = [0] * self.lock_sync

    def w_edge(self, clr: bool, v: bool, blk: tuple) -> None:
        """One write-clock edge; v and blk = (d, c, os) are the inputs held before the edge."""
        rq = self.w_gs[-1]
        new_gs = [self.rg] + self.w_gs[:-1]
        wr = v and not self.wfull
        wbn = (self.wbin + (1 if wr else 0)) & self.mask
        if wr:
            self.mem[self.wbin & (self.depth - 1)] = blk
        if v:
            if self.wfull:
                self.n_ovf += 1
            else:
                self.n_wr += 1
        top2 = ((~(rq >> (self.aw - 1))) & 3) << (self.aw - 1)
        self.wfull = gray(wbn) == (top2 | (rq & ((1 << (self.aw - 1)) - 1)))
        self.wbin = wbn
        self.wg = gray(wbn)
        self.w_gs = new_gs
        if clr:
            self.n_ovf = 0
            self.n_wr = 0

    def r_edge(self, rst: bool, clr: bool, w_lock: bool) -> None:
        """One read-clock edge; w_lock is the write domain's lock level before the edge."""
        wq = self.r_gs[-1]
        lock_s = bool(self.r_ls[-1])
        fill = (ungray(wq, self.aw + 1) - self.rbin) & self.mask
        head = self.mem[self.rbin & (self.depth - 1)]
        can_read = not self.rempty
        slot = self.pace != 32
        d, c, os = head
        do_pop = (not rst) and can_read and lock_s and slot
        do_del = ((not rst) and can_read and lock_s and (not slot) and fill > self.hi and (not self.in_frame) and self.idle_run >= self.min_keep and is_pure_idle(d, c, os))
        rd_en = do_pop or do_del or ((not rst) and can_read and not lock_s)
        new_gs = [self.wg] + self.r_gs[:-1]
        new_ls = [int(w_lock)] + self.r_ls[:-1]
        rbn = (self.rbin + (1 if (rd_en and can_read) else 0)) & self.mask
        self.r_v = False
        if rst:
            self.pace = 0
            self.in_frame = False
            self.idle_run = 0
            self.r_lock = False
            self.r_blk = IDLE_BLK
            self._clear()
        else:
            self.pace = 0 if self.pace == 32 else self.pace + 1
            self.r_lock = lock_s
            if not lock_s:
                self.in_frame = False
                self.idle_run = 0
                if can_read:
                    self.n_drain += 1
            elif slot:
                self.fill_min = min(self.fill_min, fill)
                self.fill_max = max(self.fill_max, fill)
                if can_read:
                    self.r_v = True
                    self.r_blk = head
                    self.in_frame = in_frame_after(d, c)
                    self.idle_run = min(self.idle_run + 1, 3) if is_pure_idle(d, c, os) else 0
                    self.n_out += 1
                elif not self.in_frame:
                    self.r_v = True
                    self.r_blk = IDLE_BLK
                    self.idle_run = min(self.idle_run + 1, 3)
                    self.n_ins += 1
                    self.n_out += 1
                else:
                    self.n_stall += 1
            elif do_del:
                self.n_del += 1
            if clr:
                self._clear()
        self.rempty = gray(rbn) == wq
        self.rbin = rbn
        self.rg = gray(rbn)
        self.r_gs = new_gs
        self.r_ls = new_ls

    def _clear(self) -> None:
        self.n_ins = self.n_del = self.n_stall = self.n_out = self.n_drain = 0
        self.fill_min = (1 << 32) - 1
        self.fill_max = 0


def run(w_clk, r_clk, w_in, *, w_lock=None, r_rst=None, clr=None, w_clr=None, **kw):
    """Drive the model from rising-edge times (sorted ints).

    ``w_in[i]`` is ``(v, d, c, os)`` held before write edge i (bench-style: set after the previous edge). ``w_lock[i]`` is the lock level
    held before write edge i (default 1), ``r_rst[j]`` and ``clr[j]`` are held before read edge j (default 0). A write edge also takes
    ``clr[j]`` of the *write* counters through ``w_clr`` (not used: the bench clears nothing in the write domain mid-run).
    Returns (out, model): ``out[j]`` is the reader's registered output (v, blk, lock) after read edge j.
    """
    m = RateMatch(**kw)
    ev = [(t, 0, i) for i, t in enumerate(w_clk)] + [(t, 1, i) for i, t in enumerate(r_clk)]
    ev.sort()
    for a, b in zip(ev, ev[1:]):
        if a[0] == b[0]:
            raise ValueError(f"two clock edges at the same time {a[0]}")
    out = [None] * len(r_clk)
    lock_now = 1
    for _t, which, i in ev:
        if which == 0:
            v, d, c, os = w_in[i] if i < len(w_in) else (0, 0, 0, 0)
            m.w_edge(bool(w_clr[i]) if w_clr and i < len(w_clr) else False, bool(v), (d, c, os))
            # the lock level the bench holds after this edge is the one the reader's synchroniser sees from now on
            lock_now = 1 if w_lock is None else (w_lock[i + 1] if i + 1 < len(w_lock) else w_lock[-1])
        else:
            m.r_edge(bool(r_rst[i]) if r_rst else False, bool(clr[i]) if clr else False, bool(lock_now))
            out[i] = (m.r_v, m.r_blk, m.r_lock)
    return out, m
