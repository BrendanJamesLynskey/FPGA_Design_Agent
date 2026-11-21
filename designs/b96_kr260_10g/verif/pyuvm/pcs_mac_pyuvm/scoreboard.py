"""The scoreboard of the pyuvm bench (brief 123): the same five checks as brief 112's, each against a Python reference model:
  TXMAC   frames the user offered -> the MAC's XGMII words, word for word (preamble, data, FCS or poisoned FCS, terminate, idles) and the interframe gap (>= 12 bytes)
  TXPCS   pcs_tx's TXDATA, clock for clock, against RefTxPcs fed the words pcs_tx was offered; adv (the one-in-33 pause) too
  RXPCS   pcs_rx's registered outputs, clock for clock, against RefRxPcs fed the words pcs_rx captured: lock, decoded words, x_os, six event pulses
  RXMAC   mac64_rx's frame outcomes (bytes, length, FCS verdict) in order against RefMacRx fed the reference PCS's outputs; abort counts
  E2E     (clean channel only) the frames received are the frames sent, FCS verdict equal to "not poisoned"
Streams are paired by clock number: a DUT output sampled at clock n+1 is the result of the inputs sampled at clock n.
pyuvm has no `uvm_analysis_imp_decl`; each stream gets a small subscriber (`Sink`) that forwards to a method."""
from __future__ import annotations

from collections import deque

from pyuvm import uvm_component, uvm_subscriber

from . import cov
from . import refmodels as ref

CHECKS = ["TXMAC", "TXMAC_IFG", "TXPCS", "RXPCS", "RXMAC", "E2E"]


class Sink(uvm_subscriber):
    def __init__(self, name, parent, fn):
        super().__init__(name, parent)
        self.fn = fn

    def write(self, tt):
        self.fn(tt)


class Scoreboard(uvm_component):
    max_msgs = 8

    def build_phase(self):
        self.usr = Sink("usr", self, self.write_usr)
        self.macw = Sink("macw", self, self.write_macw)
        self.pin = Sink("pin", self, self.write_pin)
        self.gtx = Sink("gtx", self, self.write_gtx)
        self.grx = Sink("grx", self, self.write_grx)
        self.rxo = Sink("rxo", self, self.write_rxo)
        self.rxf = Sink("rxf", self, self.write_rxf)
        self.rtx, self.rrx, self.rmac = ref.RefTxPcs(), ref.RefRxPcs(), ref.RefMacRx()
        self.compared = {k: 0 for k in CHECKS}
        self.mismatch = {k: 0 for k in CHECKS}
        self.e2e_en = False
        self.sent_q: deque = deque(); self.obs_q: deque = deque()
        self.cur_words: list = []; self.in_frame = False; self.gap_bytes = 0; self.have_prev = False; self.last_tl_mac = 0
        self.exp_tx: dict = {}; self.dut_tx: dict = {}
        self.exp_rx: dict = {}; self.dut_rx: dict = {}
        self.exp_frames: deque = deque(); self.dut_frames: deque = deque(); self.e2e_q: deque = deque()
        self.abort_ref = self.abort_dut = 0
        self.had_lock = False; self.slips_since_reset = 0; self.frame_open_ref = False

    # ---- bookkeeping
    def fail(self, chk: str, msg: str) -> None:
        self.mismatch[chk] += 1
        if self.mismatch[chk] <= self.max_msgs:
            self.logger.error(f"SB {chk}: {msg}")

    def ok(self, chk: str) -> None:
        self.compared[chk] += 1

    @property
    def errors(self) -> int:
        return sum(self.mismatch.values())

    # ---- TXMAC
    def write_usr(self, t) -> None:
        payload, poison, gap = t
        self.sent_q.append((payload, poison))
        cov.sample_frame(payload, poison, gap)
        if self.e2e_en:
            self.e2e_q.append((payload, poison))
        self.cmp_txmac()

    def write_macw(self, t) -> None:
        cyc, rst, adv, d, c = t
        if rst:
            self.in_frame = False; self.cur_words = []; self.have_prev = False; self.gap_bytes = 0
            return
        if not adv:                                          # the PCS does not take the word on a pause clock
            return
        w = (d, c)
        if not self.in_frame:
            if w == ref.IDLE_WORD:
                self.gap_bytes += 8
            elif c == 0x01 and ref.lane(d, 0) == ref.START:
                self.in_frame, self.cur_words = True, [w]
                if self.have_prev:
                    self.ok("TXMAC_IFG")
                    if self.gap_bytes < 12:
                        self.fail("TXMAC_IFG", f"interframe gap {self.gap_bytes} byte times, less than 12")
                    cov.sample_ifg(self.gap_bytes, self.last_tl_mac)
            else:
                self.fail("TXMAC", f"neither idle nor a start between frames: d={d:016x} c={c:02x}")
        else:
            self.cur_words.append(w)
            k = ref.term_lane(d, c)
            if k >= 0:
                self.in_frame, self.have_prev, self.gap_bytes, self.last_tl_mac = False, True, 8 - k, k
                self.obs_q.append(self.cur_words); self.cur_words = []
        self.cmp_txmac()

    def cmp_txmac(self) -> None:
        while self.sent_q and self.obs_q:
            (payload, poison), got = self.sent_q.popleft(), self.obs_q.popleft()
            want = ref.frame_words(payload, False, poison)
            self.ok("TXMAC")
            if got != want:
                fd = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), -1)
                self.fail("TXMAC", f"frame of {len(payload)} bytes (poison={poison}): {len(got)} words out, {len(want)} expected, first difference at word {fd}")

    # ---- TXPCS
    def write_pin(self, t) -> None:
        cyc, rst, adv, d, c = t
        if rst:
            self.rtx.reset(); o = 0
        else:
            if self.rtx.adv != adv:
                self.fail("TXPCS", f"adv at clock {cyc}: DUT {adv}, model {self.rtx.adv}")
            o = self.rtx.step(d, c)
            if adv and any((c >> i) & 1 and ref.lane(d, i) == ref.ERRC for i in range(8)):
                cov.sample_err("EK_ERR_CHAR_XGMII")
        self.exp_tx[cyc] = o
        self.cmp_tx(cyc + 1)

    def write_gtx(self, t) -> None:
        cyc, rst, d = t
        if cyc == 0:
            return
        self.dut_tx[cyc] = d
        self.cmp_tx(cyc)

    def cmp_tx(self, m: int) -> None:
        if m > 0 and (m - 1) in self.exp_tx and m in self.dut_tx:
            self.ok("TXPCS")
            e, g = self.exp_tx.pop(m - 1), self.dut_tx.pop(m)
            if e != g:
                self.fail("TXPCS", f"TXDATA at clock {m}: DUT {g:016x}, model {e:016x}")

    # ---- RXPCS + RXMAC
    def write_grx(self, t) -> None:
        cyc, rst, word = t
        r, mac = self.rrx, self.rmac
        if rst:
            r.reset(); mac.reset(); self.had_lock = False; self.slips_since_reset = 0
        else:
            mac.step(r.lock, r.x_v, r.x_d, r.x_c)
            self.frame_open_ref = mac.st != mac.IDLE_
            r.step(word)
            while mac.done:
                rf = mac.done.pop(0)
                if rf.aborted:
                    self.abort_ref += 1
                else:
                    self.exp_frames.append(rf)
                cov.sample_rxf(rf.s4, rf.tlane, rf.fcs_ok, rf.aborted)
            if r.blk_done:
                cov.sample_blk(r.blk_kind, r.blk_locked)
            if r.ev["lock"]:
                cov.sample_lock("LK_RELOCK" if self.had_lock else "LK_ACQUIRE", self.slips_since_reset); self.had_lock = True
            if r.ev["loss"]:
                cov.sample_lock("LK_LOSS_IN_FRAME" if self.frame_open_ref else "LK_LOSS_IDLE")
            if r.ev["slip"] and not r.ev["loss"]:
                cov.sample_lock("LK_SLIP_HUNT")
            if r.ev["slip"]:
                self.slips_since_reset += 1
        self.exp_rx[cyc] = (int(r.lock), int(r.x_v), int(r.x_os), r.events(), r.x_d, r.x_c)
        self.cmp_rx(cyc + 1)
        self.cmp_frames()

    def write_rxo(self, o) -> None:
        cyc, rst, lock, xv, xos, xd, xc, ev = o
        if cyc == 0:
            return
        self.dut_rx[cyc] = (lock, xv, xos, ev, xd, xc)
        self.cmp_rx(cyc)

    def cmp_rx(self, m: int) -> None:
        if m > 0 and (m - 1) in self.exp_rx and m in self.dut_rx:
            e, d = self.exp_rx.pop(m - 1), self.dut_rx.pop(m)
            bad = e[:4] != d[:4] or (e[1] and e[4:] != d[4:])
            self.ok("RXPCS")
            if bad:
                self.fail("RXPCS", f"clock {m}: DUT lock={d[0]} v={d[1]} os={d[2]} ev={d[3]} d={d[4]:016x} c={d[5]:02x}; model lock={e[0]} v={e[1]} os={e[2]} ev={e[3]} d={e[4]:016x} c={e[5]:02x}")

    def write_rxf(self, f) -> None:
        if f.aborted:
            self.abort_dut += 1
            if self.e2e_en:
                self.fail("E2E", "mac64_rx aborted a frame on a clean channel")
            return
        self.dut_frames.append(f)
        self.cmp_frames()

    def cmp_frames(self) -> None:
        while self.exp_frames and self.dut_frames:
            e, d = self.exp_frames.popleft(), self.dut_frames.popleft()
            self.ok("RXMAC")
            if not (e.length == d.length and e.fcs_ok == d.fcs_ok and e.data == d.data):
                self.fail("RXMAC", f"frame: DUT len={d.length} fcs_ok={d.fcs_ok} bytes={len(d.data)}; model len={e.length} fcs_ok={e.fcs_ok} bytes={len(e.data)}")
            if self.e2e_en:
                if not self.e2e_q:
                    self.fail("E2E", "frame received that was never sent")
                else:
                    payload, poison = self.e2e_q.popleft()
                    want = payload + ref.fcs_bytes(payload, poison)
                    self.ok("E2E")
                    if not (d.data == want and d.length == len(want) and d.fcs_ok == (not poison)):
                        self.fail("E2E", f"sent {len(payload)} bytes poison={poison}; received len={d.length} fcs_ok={d.fcs_ok}")

    # ---- end of test
    def check_phase(self):
        if self.sent_q:
            self.fail("TXMAC", f"{len(self.sent_q)} frames offered but never seen on the MAC's output")
        if self.obs_q:
            self.fail("TXMAC", f"{len(self.obs_q)} frames on the MAC's output that were not offered")
        if self.in_frame:
            self.fail("TXMAC", "the test ended inside a frame on the MAC's output")
        if self.exp_frames:
            self.fail("RXMAC", f"{len(self.exp_frames)} frames the reference receiver found were not reported by mac64_rx")
        if self.dut_frames:
            self.fail("RXMAC", f"{len(self.dut_frames)} frames reported by mac64_rx that the reference receiver did not find")
        self.ok("RXMAC")
        if self.abort_ref != self.abort_dut:
            self.fail("RXMAC", f"aborted frames: DUT {self.abort_dut}, model {self.abort_ref}")
        if self.e2e_en and self.e2e_q:
            self.fail("E2E", f"{len(self.e2e_q)} frames sent were never received")

    def report_phase(self):
        for k in CHECKS:
            self.logger.info(f"SB_SUMMARY check={k} compared={self.compared[k]} mismatches={self.mismatch[k]}")
        self.logger.info(f"SB_SUMMARY aborts model={self.abort_ref} dut={self.abort_dut} frames_model_total={self.rmac.n_frames}")
