"""cocotb tests of the brief 59A transactor (axi_tx_tb: axi_tx_sys + axil_mem_model), driven by the same host code and
the same programs as the board (axi_tx/host/host.py). Each run's results go to build/59a/sim/<name>.json, so a board run
can be compared with the simulation of the same program (axi_tx/host/run_board.py --compare)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

from axi_tx.host import host, model, regs
from axi_tx.host.program import assemble
from shell.tests.window_bfm import WindowBfm

ROOT = Path(__file__).resolve().parents[2]
PROGS = ROOT / "axi_tx" / "programs"
OUT = Path(os.environ.get("AXI_TX_SIM_OUT", ROOT / "build" / "59a" / "sim"))


_CLK = {"task": None}


async def boot(dut):
    t = _CLK["task"]
    if t is None or t.done():                        # one clock per test (cocotb ends it with the test); later runs reset
        _CLK["task"] = cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await Timer(1, unit="ns")                        # out of a ReadOnly phase left by the previous run's last read
    dut.ev_in.value = 0
    bfm = WindowBfm(dut, dut.clk)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 2)
    return bfm


async def run(dut, name: str, lite_bug: str = "none", stream_bug: str = "none", tag: str | None = None, capture=True):
    bfm = await boot(dut)
    prog = assemble(PROGS / f"{name}.yaml")
    prog.lite_bug, prog.stream_bug = lite_bug, stream_bug
    r = await host.arun(host.run_program(prog, capture=capture), bfm)
    pred = model.run(prog)
    r["model_compare"] = model.compare(pred, r["log"])
    r["model_counts"] = pred.counts
    OUT.mkdir(parents=True, exist_ok=True)
    keep = {k: v for k, v in r.items() if k not in ("log_raw",)}
    (OUT / f"{tag or name}.json").write_text(json.dumps(keep, indent=1, default=str) + "\n")
    return r, pred


def assert_clean(r, pred):
    assert "done" in r["status"]["flags"], r["status"]
    assert not {"hang", "error"} & set(r["status"]["flags"]), r["status"]
    assert sum(r["lite_rules"]["counts"].values()) == 0, r["lite_rules"]
    assert sum(r["stream_rules"]["counts"].values()) == 0, r["stream_rules"]
    for k in ("sb_mism", "exp_mism", "resp_mism", "n_txn", "sb_checked", "sb_unchecked"):
        assert r[k] == pred.counts[k], (k, r[k], pred.counts[k])
    assert r["model_compare"]["match"], r["model_compare"]
    if r["n_txn"] <= 256:
        assert r["digest_check"]


@cocotb.test()
async def bram_random_rw_clean(dut):
    """Random and sequential traffic to the memory target: no rule fires, every read matches the scoreboard and the
    model, every write order and both READY directions are covered."""
    r, pred = await run(dut, "bram_random_rw")
    assert_clean(r, pred)
    assert r["sb_checked"] > 100 and r["sb_mism"] == 0
    m = r["lite_mon"]
    assert m["order_aw_first"] > 0 and m["order_w_first"] > 0 and m["order_same"] > 0, m
    assert m["wstrb_partial"] > 0 and m["wstrb_full"] > 0
    assert m["hs_B"] == m["hs_AW"] == m["hs_W"] and m["hs_R"] == m["hs_AR"]
    assert m["wait_B_0"] > 0 and m["wait_B_2-3"] + m["wait_B_4-15"] > 0      # BREADY back-pressure happened
    assert m["wlat_n"] + m["rlat_n"] == r["n_txn"]
    assert not r["capture"]["triggered"]
    r, pred = await run(dut, "bram_strobes")
    assert_clean(r, pred)
    assert r["sb_checked"] == 16


@cocotb.test()
async def periph_regs_clean(dut):
    """Our peripheral without a bug: responses as expected (OKAY, SLVERR, DECERR), no rule fires."""
    r, pred = await run(dut, "periph_regs")
    assert_clean(r, pred)
    m = r["lite_mon"]
    assert m["bresp_SLVERR"] > 0 and m["bresp_DECERR"] > 0 and m["rresp_DECERR"] > 0
    # a second run of the same program is the same traffic, cycle for cycle (the digest includes every latency)
    r2, _ = await run(dut, "periph_regs", tag="periph_regs_repeat")
    assert r2["digest"] == r["digest"] and r2["cycles"] == r["cycles"], (hex(r["digest"]), hex(r2["digest"]))


@cocotb.test()
async def periph_seeded_bugs(dut):
    """Each seeded bug of the peripheral is caught by the rule it breaks (or by the scoreboard), and only by that."""
    expect = {"b_early": "B_EARLY", "r_live": "R_HOLD", "r_glitch": "R_HOLD", "exokay": "EXOKAY", "no_strb": None}
    for bug, rule in expect.items():
        r, _ = await run(dut, "periph_regs", lite_bug=bug, tag=f"periph_regs_{bug}")
        fired = {k for k, v in r["lite_rules"]["counts"].items() if v}
        if rule is None:
            assert not fired, (bug, fired)
            assert r["sb_mism"] > 0, (bug, r["sb_mism"])
        else:
            assert fired == {rule}, (bug, fired)
            assert r["lite_rules"]["first"] == rule
            assert r["capture"]["triggered"]
            trig = r["capture"]["rows"][r["capture"]["trigger_index"]]
            assert trig["lite_viol"] >> [n for n, _, _ in regs.LITE_RULES].index(rule) & 1, trig
        dut._log.info("bug %s: rules %s, sb_mism %d", bug, fired, r["sb_mism"])


@cocotb.test()
async def master_inject(dut):
    """The transactor's own injected faults fire the master-side rules."""
    r, _ = await run(dut, "master_inject")
    c = r["lite_rules"]["counts"]
    assert c["AW_HOLD"] > 0 and c["W_HOLD"] > 0 and c["AR_HOLD"] > 0, c
    assert {k for k, v in c.items() if v} == {"AW_HOLD", "W_HOLD", "AR_HOLD"}, c


@cocotb.test()
async def stream_clean_and_bugs(dut):
    """Packets through the FIFO: clean, then each stream bug caught (TLAST lost: the sink; TKEEP wiring: the HOLD rule)."""
    r, pred = await run(dut, "stream_packets")
    assert_clean(r, pred)
    assert r["sink"]["packets"] == pred.counts["stream_packets"] and r["sink"]["beats"] == pred.counts["stream_beats"]
    assert all(r["sink"][k] == 0 for k in ("data_mism", "keep_mism", "last_mism", "unexpected")), r["sink"]
    sm = r["stream_mon"]
    assert sm["stall"] > 0 and sm["plen_16+"] > 0 and sm["plen_1"] > 0
    r, _ = await run(dut, "stream_packets", stream_bug="lose_last", tag="stream_packets_lose_last")
    assert r["sink"]["last_mism"] > 0 and sum(r["stream_rules"]["counts"].values()) == 0, (r["sink"], r["stream_rules"])
    r, _ = await run(dut, "stream_packets", stream_bug="keep_wire", tag="stream_packets_keep_wire")
    assert r["stream_rules"]["counts"]["HOLD"] > 0, r["stream_rules"]
