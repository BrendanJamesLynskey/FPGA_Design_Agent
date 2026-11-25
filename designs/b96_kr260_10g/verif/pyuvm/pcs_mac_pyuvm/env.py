"""The environment and the thirteen tests of the pyuvm bench (brief 123). The tests keep brief 112's names (`t_smoke` ... `t_rand_line`) and intents: each is a
mode (loopback through the real transmit chain, or the line agent driving the receiver), an initial bit offset and one virtual sequence."""
from __future__ import annotations

import json
import random
from pathlib import Path

import cocotb
from cocotb.triggers import First, Timer
from cocotb_coverage.coverage import coverage_db
from pyuvm import ConfigDB, uvm_env, uvm_test

from . import seqs
from .agents import LineAgent, RxAgent, Sys, UsrAgent, XgAgent
from .checker import ProtocolChecker
from .scoreboard import Scoreboard

CTX: dict = {}      # filled by the cocotb entry before run_test: dut, seed, out_dir


class Env(uvm_env):
    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "dut")
        self.rng = ConfigDB().get(self, "", "rng")
        self.sys: Sys = ConfigDB().get(self, "", "sys")
        self.usr = UsrAgent("usr", self)
        self.xg = XgAgent("xg", self)
        self.line = LineAgent("line", self)
        self.rx = RxAgent("rx", self)
        self.sb = Scoreboard("sb", self)
        self.chk = ProtocolChecker("chk", self)

    def connect_phase(self):
        self.usr.mon.ap.connect(self.sb.usr.analysis_export)
        self.usr.mon.ap_abort.connect(self.sb.usr_abort.analysis_export)
        self.xg.mon.ap_mac.connect(self.sb.macw.analysis_export)
        self.xg.mon.ap_pin.connect(self.sb.pin.analysis_export)
        self.line.mon.ap_tx.connect(self.sb.gtx.analysis_export)
        self.line.mon.ap_rx.connect(self.sb.grx.analysis_export)
        self.rx.mon.ap_pcs.connect(self.sb.rxo.analysis_export)
        self.rx.mon.ap_frame.connect(self.sb.rxf.analysis_export)


class PcsMacBaseTest(uvm_test):
    line_mode = False
    vseq_cls = seqs.VseqSmoke
    random_offset = False

    def build_phase(self):
        dut = CTX["dut"]
        self.seed = CTX["seed"]
        self.rng = random.Random(self.seed)
        ConfigDB().set(None, "*", "dut", dut)
        ConfigDB().set(None, "*", "rng", self.rng)
        ConfigDB().set(None, "*", "sys", Sys(dut))
        self.env = Env("env", self)
        self.init_off = self.rng.randint(0, 131) if self.random_offset else 0
        self.timed_out = False

    async def run_phase(self):
        self.raise_objection()
        vs = self.vseq_cls("vs", self.env)
        vs.line_mode = self.line_mode
        await self.env.sys.apply_reset(self.line_mode, self.init_off)
        task = cocotb.start_soon(vs.start(None))
        timer = cocotb.start_soon(_sleep_ms(6))
        await First(task, timer)
        timer.cancel()
        if not task.done():
            self.timed_out = True
            task.cancel()
            self.logger.error("WATCHDOG: the test ran 6 ms of simulated time")
        self.drop_objection()

    def report_phase(self):
        sb = self.env.sb
        errs = sb.errors + self.env.chk.errors + (1 if self.timed_out else 0)
        self.errors = errs
        name = type(self).__name__
        self.logger.info(f"RESULT {'PASS' if errs == 0 else 'FAIL'} test={name} seed={self.seed} errors={errs}")
        out = CTX.get("out_dir")
        if out:
            out = Path(out); out.mkdir(parents=True, exist_ok=True)
            tag = f"{name}_seed{self.seed}"
            (out / f"{tag}.json").write_text(json.dumps({
                "test": name, "seed": self.seed, "errors": errs, "compared": sb.compared, "mismatch": sb.mismatch,
                "aborts_model": sb.abort_ref, "aborts_dut": sb.abort_dut, "frames_model": sb.rmac.n_frames,
                "line_stats": self.env.line.drv.stats, "protocol_fails": self.env.chk.fails, "protocol_checks": self.env.chk.checks, "protocol_cover": self.env.chk.cover, "init_off": self.init_off}, indent=1))
            coverage_db.export_to_yaml(str(out / f"cov_{tag}.yml"))


async def _sleep_ms(n):
    await Timer(n, "ms")


def _mk(name, vseq, line_mode=False, random_offset=False):
    return type(name, (PcsMacBaseTest,), {"vseq_cls": vseq, "line_mode": line_mode, "random_offset": random_offset})


t_smoke = _mk("t_smoke", seqs.VseqSmoke)
t_lens = _mk("t_lens", seqs.VseqLens)
t_gaps = _mk("t_gaps", seqs.VseqGaps)
t_badfcs = _mk("t_badfcs", seqs.VseqBadfcs)
t_underrun = _mk("t_underrun", seqs.VseqUnderrun)
t_xg = _mk("t_xg", seqs.VseqXg)
t_line_blocks = _mk("t_line_blocks", seqs.VseqLineBlocks, line_mode=True)
t_hdr = _mk("t_hdr", seqs.VseqHdr)
t_slip = _mk("t_slip", seqs.VseqSlip)
t_ber = _mk("t_ber", seqs.VseqBer)
t_rxreset = _mk("t_rxreset", seqs.VseqRxreset)
t_offsets = _mk("t_offsets", seqs.VseqOffsets)
t_rand = _mk("t_rand", seqs.VseqRand, random_offset=True)
t_rand_line = _mk("t_rand_line", seqs.VseqRand, line_mode=True, random_offset=True)

TESTS = ["t_smoke", "t_lens", "t_gaps", "t_badfcs", "t_underrun", "t_xg", "t_line_blocks", "t_hdr", "t_slip", "t_ber", "t_rxreset", "t_offsets", "t_rand", "t_rand_line"]
