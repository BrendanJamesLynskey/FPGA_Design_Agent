"""Protocol checker of the pyuvm bench (brief 123): the properties of brief 112's `sva/pcs_mac_sva.sv`, as a Python monitor.
Icarus 12 does not run concurrent SVA (`assert property` with sequences), and the repo has no Verilator installed locally, so the assertions cannot be bound into
the RTL as in 112. This component samples the same signals every clock (before the edge, as an SVA does) and checks the same implications by hand with one clock of
history. It is a hand translation, not a tool feature: temporal operators (`|=>`, `[*32]`, `$rose`, `$past`) become variables."""
from __future__ import annotations

from pyuvm import ConfigDB, uvm_monitor
from cocotb.triggers import RisingEdge

from .agents import rd

PROPS = ["adv_single", "adv_rhythm", "ready_implies_adv", "source_stable", "no_underrun", "sop_start_char", "eop_terminate", "sop_pulse",
         "xv_needs_lock", "ev_lock_needs_lock", "ev_loss_shape", "slip_while_unlocked", "lock_rise_has_ev_lock", "lock_fall_has_ev_loss", "ev_lock_loss_exclusive",
         "block_event_needs_lock", "m_nb_range", "m_sof_has_m_v", "underrun_only_when_injected", "injected_underruns_seen"]


class ProtocolChecker(uvm_monitor):
    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "dut")
        self.fails = {p: 0 for p in PROPS}
        self.checks = {p: 0 for p in PROPS}
        self.fault_mode = False          # fault injection (brief 158): a test that stalls the source on purpose sets it with inject_underruns(n)
        self.fault_budget = 0; self.fault_seen = 0
        self.cover = dict(pause=0, full_33=0, sop=0, eop=0, lock=0, loss=0, hunting_slip=0, frame_good=0, frame_bad=0, abort=0, end_and_abort_same_clock=0, underrun_injected=0)

    def inject_underruns(self, n: int) -> None:
        """Fault-injection mode: `n` underruns of mac64_tx are expected. `no_underrun` stays the rule outside this mode; inside it, an underrun is allowed only while the budget lasts
        (`underrun_only_when_injected`) and all of them must have been seen by the end of the test (`injected_underruns_seen`)."""
        self.fault_mode = True; self.fault_budget += n

    def check_phase(self):
        if self.fault_mode:
            self._chk("injected_underruns_seen", self.fault_seen == self.fault_budget, f"{self.fault_seen} underruns seen, {self.fault_budget} injected")

    @property
    def errors(self) -> int:
        return sum(self.fails.values())

    def _chk(self, p: str, cond: bool, msg: str) -> None:
        self.checks[p] += 1
        if not cond:
            self.fails[p] += 1
            if self.fails[p] <= 3:
                self.logger.error(f"SVA {p}: {msg}")

    async def run_phase(self):
        d = self.dut
        await RisingEdge(d.clk)
        pt = {}             # previous clock's samples
        run = None          # adv-high clocks since the last pause (None until a pause has been seen)
        while True:
            await RisingEdge(d.clk)
            rt, rr = rd(d.rst_tx) != 0, rd(d.rst_rx) != 0
            adv, rdy, val = rd(d.adv), rd(d.s_ready), rd(d.s_valid)
            sdat, slast, snb = rd(d.s_data), rd(d.s_last), rd(d.s_nb1)
            sop, eop, und = rd(d.sop), rd(d.eop), rd(d.underrun)
            lock, xv, evl, evo, evs = rd(d.lock), rd(d.x_v), rd(d.ev_lock), rd(d.ev_loss), rd(d.ev_slip)
            ev_blk = rd(d.ev_sh_err) or rd(d.ev_type_err) or rd(d.ev_os)
            mv, msof, mnb, mend, merr, mok = rd(d.m_v), rd(d.m_sof), rd(d.m_nb), rd(d.m_end), rd(d.m_err), rd(d.m_fcs_ok)
            if rt:
                run = None          # an assertion attempt is abandoned by a reset (disable iff)
            if not rt and not pt.get("rt", True):
                if not adv:
                    self.cover["pause"] += 1
                if pt.get("adv") == 0:
                    self._chk("adv_single", adv == 1, "adv low for two clocks in a row")
                if not adv:
                    if run is not None:
                        self._chk("adv_rhythm", run == 32, f"{run} clocks between pauses, not 32")
                        if run == 32:
                            self.cover["full_33"] += 1
                    run = 0
                elif run is not None:
                    run += 1
                self._chk("ready_implies_adv", (not rdy) or adv, "s_ready high while the PCS pauses")
                if pt.get("val") and not pt.get("rdy"):
                    self._chk("source_stable", val and sdat == pt["sdat"] and slast == pt["slast"] and snb == pt["snb"], "source word changed or dropped before s_ready")
                if self.fault_mode:
                    if und:
                        self.fault_seen += 1; self.cover["underrun_injected"] += 1
                        self._chk("underrun_only_when_injected", self.fault_seen <= self.fault_budget, "more underruns than were injected")
                else:
                    self._chk("no_underrun", not und, "underrun")
                if sop:
                    self.cover["sop"] += 1
                    self._chk("sop_start_char", (rd(d.mx_d) & 0xFF) == 0xFB and rd(d.mx_c) == 0x01, "sop without a start character in lane 0")
                if eop:
                    self.cover["eop"] += 1
                    mc = rd(d.mx_c)
                    self._chk("eop_terminate", mc != 0 and (mc >> 7) & 1, "eop without a terminate word")
                if pt.get("sop"):
                    self._chk("sop_pulse", not sop, "sop held for two clocks")
            if not rr and pt:
                if xv:
                    self._chk("xv_needs_lock", pt.get("lock", 0), "x_v without lock one clock earlier")
                if evl:
                    self.cover["lock"] += 1
                    self._chk("ev_lock_needs_lock", lock, "ev_lock while not locked")
                if evo:
                    self.cover["loss"] += 1
                    self._chk("ev_loss_shape", (not lock) and evs, "ev_loss while locked, or without a slip")
                if evs:
                    if not evo:
                        self.cover["hunting_slip"] += 1
                    self._chk("slip_while_unlocked", not lock, "slip while locked")
                if lock and not pt.get("lock", 1):
                    self._chk("lock_rise_has_ev_lock", evl, "lock rose without ev_lock")
                if not lock and pt.get("lock", 0):
                    self._chk("lock_fall_has_ev_loss", evo or pt.get("rr", False), "lock fell without ev_loss and without a reset")
                self._chk("ev_lock_loss_exclusive", not (evl and evo), "ev_lock and ev_loss together")
                if ev_blk:
                    self._chk("block_event_needs_lock", pt.get("lock", 0), "a block event without lock")
                if mv:
                    self._chk("m_nb_range", 1 <= mnb <= 8, "m_nb outside 1..8 with m_v")
                if msof:
                    self._chk("m_sof_has_m_v", mv, "m_sof without m_v")
                if mend and mok: self.cover["frame_good"] += 1
                if mend and not mok: self.cover["frame_bad"] += 1
                if merr: self.cover["abort"] += 1
                if mend and merr: self.cover["end_and_abort_same_clock"] += 1
            pt = dict(rt=rt, rr=rr, adv=adv, val=val, rdy=rdy, sdat=sdat, slast=slast, snb=snb, sop=sop, lock=lock)
