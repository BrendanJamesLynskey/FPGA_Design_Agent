"""The four agents of the pyuvm bench (brief 123), same roles as brief 112's:
  usr_agent   active: frames into mac64_tx's source interface; monitor: the frames the MAC accepted
  xg_agent    active: XGMII words injected straight into pcs_tx; monitors: the MAC's output and pcs_tx's input
  line_agent  active: the GT side. Loopback: faults into the channel. Line mode: its own 66B stream (raw blocks, any type or sync header, own scrambler)
  rx_agent    passive: pcs_rx's outputs every clock and mac64_rx's frames
Timing idiom: every component waits for RisingEdge(clk) and reads the signals then, which in cocotb gives the values from just before the edge (what the clocking
block's `input #1step` gives in SystemVerilog); drivers write after the edge and the DUT sees the value at the next edge."""
from __future__ import annotations

from cocotb.triggers import RisingEdge
from pyuvm import ConfigDB, uvm_agent, uvm_analysis_port, uvm_driver, uvm_monitor, uvm_sequencer

from . import cov
from . import refmodels as ref
from .channel import Controls, LineChannel
from .items import FrameItem, LineItem, RxFrameObs, XgItem


def rd(h) -> int:
    """A signal as an int; an unresolved (X/Z) value, only seen before the first reset, reads as 0."""
    try:
        return int(h.value)
    except ValueError:
        return 0


class Sys:
    """The reset and mode controls shared by the test, the line agent and the sequences (SystemVerilog: `sys_if`)."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.line_mode = False
        self.init_off = 0
        self.rst_tx = True
        self.rst_rx_sys = True
        dut.rst_tx.value = 1
        dut.rst_rx.value = 1

    async def apply_reset(self, line_mode: bool, off: int, cycles: int = 6) -> None:
        """Both resets for `cycles` clocks with the chosen mode and initial bit offset, then released right after an edge."""
        self.line_mode, self.init_off = line_mode, off
        self.rst_tx = self.rst_rx_sys = True
        self.dut.rst_tx.value = 1
        self.dut.rst_rx.value = 1
        for _ in range(cycles):
            await RisingEdge(self.dut.clk)
        self.rst_tx = self.rst_rx_sys = False
        self.dut.rst_tx.value = 0
        self.dut.rst_rx.value = 0


# ------------------------------------------------------------------------------------------------------ usr agent
class UsrDriver(uvm_driver):
    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "dut")
        self.rng = ConfigDB().get(self, "", "rng")

    async def run_phase(self):
        d = self.dut
        d.s_valid.value = 0; d.s_last.value = 0; d.s_data.value = 0; d.s_nb1.value = 0; d.s_poison.value = 0
        while True:
            f = await self.seq_item_port.get_next_item()
            await self.drive_frame(f)
            self.seq_item_port.item_done()

    async def drive_frame(self, f: FrameItem) -> None:
        d = self.dut
        for _ in range(f.gap):
            d.s_valid.value = 0; d.s_last.value = 0; d.s_poison.value = 0
            await RisingEdge(d.clk)
        n = f.len
        nw = (n + 7) // 8
        for i in range(nw):
            last = i == nw - 1
            d.s_valid.value = 1
            d.s_data.value = int.from_bytes(f.payload[i * 8:i * 8 + 8].ljust(8, b"\0"), "little")
            d.s_last.value = int(last)
            d.s_nb1.value = (n - i * 8 - 1) if last else 7
            d.s_poison.value = int(f.poison) if last else (self.rng.getrandbits(1) if f.noise_poison else 0)
            while True:                      # the word is taken at the edge where s_ready (read before it) was high
                await RisingEdge(d.clk)
                if rd(d.s_ready):
                    break
        d.s_valid.value = 0; d.s_last.value = 0; d.s_poison.value = 0


class UsrMonitor(uvm_monitor):
    def build_phase(self):
        self.ap = uvm_analysis_port("ap", self)          # one (payload, poison, gap) per frame whose last word the MAC took
        self.dut = ConfigDB().get(self, "", "dut")

    async def run_phase(self):
        d = self.dut
        buf = bytearray(); idle = 0; in_frame = False; gap = 0
        while True:
            await RisingEdge(d.clk)
            v, r = rd(d.s_valid), rd(d.s_ready)
            if v and r:
                if not in_frame:
                    in_frame, gap = True, idle
                last = rd(d.s_last)
                buf += rd(d.s_data).to_bytes(8, "little")[:(rd(d.s_nb1) + 1) if last else 8]
                if last:
                    self.ap.write((bytes(buf), bool(rd(d.s_poison)), gap))
                    buf = bytearray(); in_frame = False; idle = 0
            elif not in_frame and not v:
                idle += 1


class UsrAgent(uvm_agent):
    def build_phase(self):
        self.mon = UsrMonitor("mon", self)
        self.sqr = uvm_sequencer("sqr", self)
        self.drv = UsrDriver("drv", self)

    def connect_phase(self):
        self.drv.seq_item_port.connect(self.sqr.seq_item_export)


# ------------------------------------------------------------------------------------------------------ xg agent
class XgDriver(uvm_driver):
    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "dut")

    async def run_phase(self):
        d = self.dut
        d.direct.value = 0
        while True:
            x: XgItem = await self.seq_item_port.get_next_item()
            for w, c in x.words:
                d.direct.value = 1; d.dx_d.value = w; d.dx_c.value = c
                while True:                  # pcs_tx takes the word at the edge where adv (read before it) was high
                    await RisingEdge(d.clk)
                    if rd(d.adv):
                        break
            d.direct.value = 0
            self.seq_item_port.item_done()


class XgMonitor(uvm_monitor):
    def build_phase(self):
        self.ap_mac = uvm_analysis_port("ap_mac", self)     # every clock: (cyc, rst, adv, d, c) of the MAC's output
        self.ap_pin = uvm_analysis_port("ap_pin", self)     # every clock: the same for pcs_tx's input (after the mux)
        self.dut = ConfigDB().get(self, "", "dut")

    async def run_phase(self):
        d = self.dut
        cyc = 1
        await RisingEdge(d.clk)              # the first edge: nothing driven yet
        while True:
            await RisingEdge(d.clk)
            rst, adv = rd(d.rst_tx) != 0, rd(d.adv)
            self.ap_mac.write((cyc, rst, adv, rd(d.mx_d), rd(d.mx_c)))
            self.ap_pin.write((cyc, rst, adv, rd(d.p_d), rd(d.p_c)))
            cyc += 1


class XgAgent(uvm_agent):
    def build_phase(self):
        self.mon = XgMonitor("mon", self)
        self.sqr = uvm_sequencer("sqr", self)
        self.drv = XgDriver("drv", self)

    def connect_phase(self):
        self.drv.seq_item_port.connect(self.sqr.seq_item_export)


# ------------------------------------------------------------------------------------------------------ line agent
class LineDriver(uvm_driver):
    """Item thread (blocks queue up, throttled; the other items take effect once the queued blocks have gone out) and the stream loop (one clock at a time:
    the channel step, then the controls for the next one)."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "dut")
        self.sys: Sys = ConfigDB().get(self, "", "sys")
        self.rng = ConfigDB().get(self, "", "rng")
        self.chan = LineChannel()
        self.ctl = Controls()
        self.scr = ref.pcs.Scrambler()
        self.blkq: list = []
        self.acc = 0; self.fill = 0; self.started = False
        self.pend_flip = 0; self.pend_hdr = 0; self.pend_skip = 0; self.pend_ins = False; self.pend_del = False; self.pend_rst = 0; self.ber_ppm = 0
        self.stats = dict(flips=0, hdr=0, ins=0, dele=0, rst=0, blocks=0)

    async def run_phase(self):
        import cocotb
        t1 = cocotb.start_soon(self.stream_loop())
        await self.item_loop()
        t1.cancel()

    async def drain(self):
        while self.blkq:
            await RisingEdge(self.dut.clk)

    async def item_loop(self):
        clk = self.dut.clk
        while True:
            it: LineItem = await self.seq_item_port.get_next_item()
            k = it.kind
            if k == "BLOCKS":
                if not self.sys.line_mode:
                    self.logger.error("LINEDRV: BLOCKS item in loopback mode")
                for b in it.blks:
                    while len(self.blkq) >= 4:
                        await RisingEdge(clk)
                    self.blkq.append(b); self.stats["blocks"] += 1
            elif k == "FLIP":
                await self.drain(); self.pend_flip = it.mask; self.stats["flips"] += 1; cov.sample_err("EK_BIT_FLIP")
            elif k == "HDR":
                await self.drain(); self.pend_hdr, self.pend_skip = it.n, it.skip; self.stats["hdr"] += 1; cov.sample_err("EK_HDR_BURST")
            elif k == "SLIP_INS":
                await self.drain(); self.pend_ins = True; self.stats["ins"] += 1; cov.sample_err("EK_SLIP_INS")
            elif k == "SLIP_DEL":
                await self.drain(); self.pend_del = True; self.stats["dele"] += 1; cov.sample_err("EK_SLIP_DEL")
            elif k == "WAIT":
                await self.drain()
                for _ in range(it.n):
                    await RisingEdge(clk)
            elif k == "RXRESET":
                await self.drain(); self.pend_rst = it.n; self.stats["rst"] += 1; cov.sample_err("EK_RX_RESET")
                for _ in range(it.n + 2):
                    await RisingEdge(clk)
            elif k == "BER":
                await self.drain(); self.ber_ppm = it.n
            self.seq_item_port.item_done()

    async def stream_loop(self):
        d, c, rng = self.dut, self.ctl, self.rng
        idle_blk = ref.encode_rtl(*ref.IDLE_WORD)
        while True:
            await RisingEdge(d.clk)
            # 1. the channel's clock edge: the word the receiver captures at the next edge (controls were set at the previous edge)
            rst_tx = rd(d.rst_tx) != 0
            d.gt_rx_d.value = self.chan.step(rst_tx, rd(d.gt_tx_d), c)
            # 2. the controls for the next clock
            flip = self.pend_flip; self.pend_flip = 0
            if self.ber_ppm > 0 and rng.randrange(1000000) < self.ber_ppm * 64:
                flip ^= 1 << rng.randrange(64); self.stats["flips"] += 1; cov.sample_err("EK_BIT_FLIP")
            c.flip_mask = flip
            c.hdr_load, c.hdr_cnt, c.hdr_skip = self.pend_hdr > 0, self.pend_hdr, self.pend_skip
            self.pend_hdr = 0
            c.slip_ins, c.slip_del = self.pend_ins, self.pend_del
            self.pend_ins = self.pend_del = False
            req = self.pend_rst > 0
            if req:
                self.pend_rst -= 1
            d.rst_rx.value = int(self.sys.rst_rx_sys or req)
            c.line_mode, c.init_off = self.sys.line_mode, self.sys.init_off
            if not self.sys.line_mode or self.sys.rst_tx:
                c.drv_valid = c.drv_first = False; c.drv_word = 0
                self.started = False; self.fill = 0; self.acc = 0; self.scr = ref.pcs.Scrambler()
                if self.sys.rst_tx:
                    self.blkq.clear()
            else:
                c.drv_first = not self.started
                self.started = True
                while self.fill < 190 and self.blkq:
                    sh, p = self.blkq.pop(0)
                    self.acc |= (sh | (self.scr.word(p) << 2)) << self.fill; self.fill += 66
                while self.fill < 64:
                    sh, p = idle_blk
                    self.acc |= (sh | (self.scr.word(p) << 2)) << self.fill; self.fill += 66
                c.drv_valid = True
                c.drv_word = self.acc & ((1 << 64) - 1)
                self.acc >>= 64; self.fill -= 64


class LineMonitor(uvm_monitor):
    def build_phase(self):
        self.ap_tx = uvm_analysis_port("ap_tx", self)       # every clock: (cyc, rst, word) TXDATA of pcs_tx
        self.ap_rx = uvm_analysis_port("ap_rx", self)       # every clock: RXDATA, the word pcs_rx captures
        self.dut = ConfigDB().get(self, "", "dut")

    async def run_phase(self):
        d = self.dut
        cyc = 1
        await RisingEdge(d.clk)
        while True:
            await RisingEdge(d.clk)
            self.ap_tx.write((cyc, rd(d.rst_tx) != 0, rd(d.gt_tx_d)))
            self.ap_rx.write((cyc, rd(d.rst_rx) != 0, rd(d.gt_rx_d)))
            cyc += 1


class LineAgent(uvm_agent):
    def build_phase(self):
        self.mon = LineMonitor("mon", self)
        self.sqr = uvm_sequencer("sqr", self)
        self.drv = LineDriver("drv", self)

    def connect_phase(self):
        self.drv.seq_item_port.connect(self.sqr.seq_item_export)


# ------------------------------------------------------------------------------------------------------ rx agent (passive)
class RxMonitor(uvm_monitor):
    def build_phase(self):
        self.ap_pcs = uvm_analysis_port("ap_pcs", self)     # every clock: the receive PCS's registered outputs (a tuple, see RXO_FIELDS)
        self.ap_frame = uvm_analysis_port("ap_frame", self)  # one RxFrameObs per frame outcome of mac64_rx (frame at m_end, abort at m_err)
        self.dut = ConfigDB().get(self, "", "dut")

    async def run_phase(self):
        d = self.dut
        cyc = 1
        accs: list = []; cur = None
        await RisingEdge(d.clk)
        while True:
            await RisingEdge(d.clk)
            rst = rd(d.rst_rx) != 0
            xv = rd(d.x_v)
            self.ap_pcs.write((cyc, rst, rd(d.lock), xv, rd(d.x_os), rd(d.x_d), rd(d.x_c),
                               (rd(d.ev_sh_err), rd(d.ev_type_err), rd(d.ev_os), rd(d.ev_slip), rd(d.ev_loss), rd(d.ev_lock))))
            # frames: rx_sop opens one, m_v words extend the newest, m_err abandons the newest, m_end closes the oldest (it can arrive after the next sop)
            if rd(d.rx_sop):
                cur = bytearray(); accs.append(cur)
            if rd(d.m_v):
                if cur is None:
                    cur = bytearray(); accs.append(cur)
                cur += rd(d.m_d).to_bytes(8, "little")[:rd(d.m_nb)]
            if rd(d.m_err):
                if accs:
                    accs.pop()
                cur = None
                self.ap_frame.write(RxFrameObs(cyc, aborted=True))
            if rd(d.m_end):
                f = accs.pop(0) if accs else bytearray()
                if not accs:
                    cur = None
                self.ap_frame.write(RxFrameObs(cyc, bytes(f), bool(rd(d.m_fcs_ok)), False, rd(d.m_len)))
            if rst:
                accs.clear(); cur = None
            cyc += 1


class RxAgent(uvm_agent):
    def build_phase(self):
        self.mon = RxMonitor("mon", self)
