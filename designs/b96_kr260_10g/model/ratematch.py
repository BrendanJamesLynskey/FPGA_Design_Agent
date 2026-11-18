"""Twin of rtl/rate_match.sv (brief 96C): the receive-to-core elastic buffer with idle insertion and deletion.

A clock-by-clock model of two clock domains. ``RateMatch.w_edge`` is one edge of the write (receive, recovered) clock, ``r_edge`` one edge
of the read (core, transmit user) clock; ``run`` merges the two edge lists in time order. The two pointer crossings are modelled as the
RTL's xpm_cdc_gray does them (a gray register in the source domain, ``sync`` flops in the destination domain, a binary decode, optionally
one more register), so the RTL and this model can be compared output for output. Times are integers (femtoseconds); two edges at the same
time are refused (the RTL has no defined order for them).

Policy (the same text as the RTL header, restated so the two can be read side by side):

* the write side writes every valid block from the PCS, unless the buffer is full as the write side sees it (the read pointer it sees
  is old, so this is conservative): that block is dropped and counted in ``n_ovf``. Nothing else is ever dropped there;
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
    aw: int = 4
    hi: int = 4
    min_keep: int = 1
    sync: int = 2                 # DEST_SYNC_FF of both pointer crossings
    wp_reg: int = 1               # read side: 1 = a register after the decode of the write pointer (REG_OUTPUT)
    rp_reg: int = 1               # write side: the same for the read pointer
    lock_sync: int = 2
    # write side
    wptr: int = 0
    w_g: int = 0
    w_gs: list = field(default_factory=list)      # sync chain of the read pointer, in the write domain
    w_rp_q: int = 0
    n_ovf: int = 0
    n_wr: int = 0
    # read side
    rptr: int = 0
    r_g: int = 0
    r_gs: list = field(default_factory=list)      # sync chain of the write pointer, in the read domain
    r_wp_q: int = 0
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

    # -------------------------------------------------------------------------------------------------- write side
    def rp_seen(self) -> int:
        return self.w_rp_q if self.rp_reg else ungray(self.w_gs[-1], self.aw + 1)

    def w_edge(self, clr: bool, v: bool, blk: tuple) -> None:
        """One write-clock edge: ``v`` and ``blk`` = (d, c, os) are the inputs held before the edge."""
        full = ((self.wptr - self.rp_seen()) & self.mask) >= self.depth
        new_g = gray(self.wptr)
        new_gs = [self.r_g] + self.w_gs[:-1]
        new_rp_q = ungray(self.w_gs[-1], self.aw + 1)
        if v:
            if full:
                self.n_ovf += 1
            else:
                self.mem[self.wptr & (self.depth - 1)] = blk
                self.wptr = (self.wptr + 1) & self.mask
                self.n_wr += 1
        if clr:
            self.n_ovf = 0
            self.n_wr = 0
        self.w_g = new_g
        self.w_gs = new_gs
        self.w_rp_q = new_rp_q

    # -------------------------------------------------------------------------------------------------- read side
    def wp_seen(self) -> int:
        return self.r_wp_q if self.wp_reg else ungray(self.r_gs[-1], self.aw + 1)

    def r_edge(self, rst: bool, clr: bool, w_lock: bool) -> None:
        """One read-clock edge; ``w_lock`` is the write domain's lock level before the edge."""
        wp = self.wp_seen()
        lock_s = bool(self.r_ls[-1])
        fill = (wp - self.rptr) & self.mask
        head = self.mem[self.rptr & (self.depth - 1)]
        new_g = gray(self.rptr)
        new_gs = [self.w_g] + self.r_gs[:-1]
        new_wp_q = ungray(self.r_gs[-1], self.aw + 1)
        new_ls = [int(w_lock)] + self.r_ls[:-1]
        slot = self.pace != 32
        self.r_v = False
        if rst:
            self.rptr = wp
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
                if fill != 0:
                    self.rptr = (self.rptr + 1) & self.mask
                    self.n_drain += 1
            elif slot:
                self.fill_min = min(self.fill_min, fill)
                self.fill_max = max(self.fill_max, fill)
                if fill != 0:
                    d, c, os = head
                    self.r_v = True
                    self.r_blk = head
                    self.rptr = (self.rptr + 1) & self.mask
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
            else:
                d, c, os = head
                if fill > self.hi and not self.in_frame and self.idle_run >= self.min_keep and is_pure_idle(d, c, os):
                    self.rptr = (self.rptr + 1) & self.mask
                    self.n_del += 1
        if clr and not rst:
            self._clear()
        self.r_g = new_g
        self.r_gs = new_gs
        self.r_wp_q = new_wp_q
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
