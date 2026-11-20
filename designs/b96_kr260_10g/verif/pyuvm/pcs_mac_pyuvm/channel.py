"""The bit-level channel between TXDATA and RXDATA, in Python (brief 123). A line-for-line port of brief 112's SystemVerilog `line_channel.sv`: a bit FIFO that can
insert or delete single bits (a slipped receiver alignment), an initial fill that sets the first alignment, and two fault injectors at its input: a word XOR mask
(bit errors) and a burst of corrupted sync headers (both header bits forced to 0 for hdr_cnt blocks, hdr_skip good blocks between corrupted ones). One `step`
per clock edge, with the controls the line agent set at the previous edge; it returns the word the receiver captures at the next edge."""
from __future__ import annotations

PRE = 260        # bits of pre-stream fill: valid sync headers only, so the receiver can lock on the fill's own grid
M64 = (1 << 64) - 1


class Controls:
    """What the line agent drives into the channel for one clock."""
    __slots__ = ("line_mode", "init_off", "drv_word", "drv_valid", "drv_first", "flip_mask", "hdr_load", "hdr_cnt", "hdr_skip", "slip_ins", "slip_del")

    def __init__(self) -> None:
        self.line_mode = False
        self.init_off = 0
        self.drv_word = 0
        self.drv_valid = False
        self.drv_first = False
        self.flip_mask = 0
        self.hdr_load = False
        self.hdr_cnt = 0
        self.hdr_skip = 0
        self.slip_ins = False
        self.slip_del = False


class LineChannel:
    def __init__(self) -> None:
        self.rst_d = True
        self.tx_valid_d = False
        self.out_word = 0
        self._reset_state()

    def _reset_state(self) -> None:
        self.fifo = 0
        self.hdr_n = self.skip_n = self.skip_cfg = 0
        self.cur_bad = False
        self.bitpos = 0
        self.started = False
        for b in range(PRE):
            if b % 66 == 0:
                self.fifo |= 1 << b
        # the receiver's first edge after reset captures this word, word 0 of the fill; the first pop after reset gives word 1
        self.out_word = self.fifo & M64
        self.fifo >>= 64
        self.fill = PRE - 64
        self.absn = PRE

    def step(self, rst: bool, tx_word: int, c: Controls) -> int:
        tx_valid = (not rst) and (not self.rst_d)
        in_valid = c.drv_valid if c.line_mode else tx_valid
        in_first = c.drv_first if c.line_mode else (tx_valid and not self.tx_valid_d)
        self.rst_d = rst
        self.tx_valid_d = tx_valid
        if rst:
            self._reset_state()
            return self.out_word
        if c.hdr_load:
            self.hdr_n, self.skip_cfg, self.skip_n = c.hdr_cnt, c.hdr_skip, 0
        if in_valid:
            if in_first or not self.started:
                # pad the fill so the first stream bit lands init_off bits after a multiple of 66 on the receiver's grid
                pad = (c.init_off % 66 - self.absn % 66 + 66) % 66
                for b in range(pad):
                    if (self.absn + b) % 66 == 0:
                        self.fifo |= 1 << (self.fill + b)
                self.fill += pad
                self.absn += pad
                self.bitpos = 0
                self.started = True
            w = ((c.drv_word if c.line_mode else tx_word) ^ c.flip_mask) & M64
            # the sync headers of the blocks this word touches: block starts at stream bit positions 66k
            for i in range(64):
                r = (self.bitpos + i) % 66
                if r == 0:
                    self.cur_bad = self.hdr_n > 0 and self.skip_n == 0
                if self.cur_bad and r < 2:
                    w &= ~(1 << i)
                if r == 1:
                    if self.cur_bad:
                        self.hdr_n -= 1
                        self.skip_n = self.skip_cfg
                        self.cur_bad = False
                    elif self.skip_n > 0:
                        self.skip_n -= 1
            self.bitpos += 64
            if c.slip_ins:
                self.fifo |= (w << 1) << self.fill
                self.fill += 65
                self.absn += 65
            elif c.slip_del and self.fill > 100:
                self.fifo |= (w >> 1) << self.fill
                self.fill += 63
                self.absn += 63
            else:
                self.fifo |= w << self.fill
                self.fill += 64
                self.absn += 64
        if self.fill >= 64:
            self.out_word = self.fifo & M64
            self.fifo >>= 64
            self.fill -= 64
        else:
            self.out_word = 0
        return self.out_word
