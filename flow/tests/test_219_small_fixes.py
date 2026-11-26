"""Brief 219: small fixes from briefs 207, 208, 209a and the 209 pilot (flow side). Each test names the recorded evidence it stands on.

1  a run that holds a heavy slot runs its heavy steps inside it (flow/mutate.py take_lock, FDA_HEAVY_SLOT)
2  report_clock_networks runs last and alone: a crash in it costs only that report, recorded as unavailable (flow/checks)
3  cdc_inject holds a Gray bus as a whole while it steps (flow/cdc_inject.py, cdc_inj_pkg.sv); the 207 fixture
5  LOC site names are checked against the part's sites before synthesis (flow/xdc_sites.py); the 209 pilot's XDC
8  supplied data/ bus files and their copies are not mutation targets (flow/mutate.py)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from flow import cdc_inject
from flow import checks as C
from flow import mutate as M
from flow import xdc_sites

HERE = Path(__file__).parent
DATA = HERE / "data" / "219"
ROOT = HERE.parents[1]
FX207 = HERE / "fixtures" / "cdc_margin_207"


# ---- fix 1: the heavy slot the run already holds ----------------------------------------------------------------------------
def test_a_run_inside_its_own_slot_does_not_queue_for_another(tmp_path, monkeypatch):
    """209a: launched under take_heavy_slot.sh, V3's coverage and mutation steps took heavy_slot.lock themselves and waited forever."""
    shared = tmp_path / "heavy_slot.lock"
    shared.write_text("219: the run itself, 10:00, expected end 12:00\n")           # the slot the launcher took
    monkeypatch.setenv("FDA_HEAVY_LOCK", str(shared))                                # what the machine's step would queue on
    monkeypatch.setenv("FDA_HEAVY_SLOT", str(shared))                                # what the launcher exports after take_heavy_slot.sh --env
    t0 = time.monotonic()
    p, holder = M.take_lock("v3-mutation", wait_s=30, expect_s=60)
    assert (p, holder) == (None, "") and time.monotonic() - t0 < 2                   # no wait, nothing taken, nothing to release
    assert shared.read_text().startswith("219:")                                     # the slot's own lock is untouched


def test_the_protection_stays_when_no_slot_is_held(tmp_path, monkeypatch):
    lock = tmp_path / "lock"
    lock.write_text("someone-else big-job 10:00 11:00\n")
    monkeypatch.setenv("FDA_HEAVY_LOCK", str(lock))
    monkeypatch.delenv("FDA_HEAVY_SLOT", raising=False)
    p, holder = M.take_lock("j", wait_s=0.2, expect_s=60)
    assert p is None and holder.startswith("someone-else")                           # still refused while another job holds it
    monkeypatch.setenv("FDA_HEAVY_SLOT", str(tmp_path / "no_such_lock"))             # a stale variable is not a held slot
    assert M.held_slot() is None
    p, holder = M.take_lock("j", wait_s=0.2, expect_s=60)
    assert p is None and holder.startswith("someone-else")
    lock.unlink()
    p, holder = M.take_lock("j", wait_s=1, expect_s=60)                              # free: taken as before, and ours to release
    assert p == lock and holder == "" and lock.is_file()
    lock.unlink()


def test_the_fake_lock_directory_end_to_end(tmp_path, monkeypatch):
    """The agent's coverage step and the mutate CLI use take_lock: the run's own slot, then a waiter on a foreign one."""
    (tmp_path / "heavy_slot.lock").write_text("219: mine\n")
    monkeypatch.setenv("FDA_HEAVY_LOCK", str(tmp_path / "heavy_slot.lock"))
    monkeypatch.setenv("FDA_HEAVY_SLOT", str(tmp_path / "heavy_slot.lock"))
    res = []
    th = threading.Thread(target=lambda: res.append(M.take_lock("v3-coverage", 30, 900)))
    th.start()
    th.join(5)
    assert not th.is_alive() and res == [(None, "")]


# ---- fix 2: report_clock_networks last and alone -----------------------------------------------------------------------------
def _mini(tmp_path: Path) -> Path:
    d = tmp_path / "designs" / "mini"
    b = d / "build" / "base"
    b.mkdir(parents=True)
    (b / "timing_summary_synth.rpt").write_text("")
    (b / "post_synth.dcp").write_text("dcp")
    (d / "rtl").mkdir()
    (d / "rtl" / "m.sv").write_text("module m (input logic clk, output logic q);\n always_ff @(posedge clk) q <= ~q;\nendmodule\n")
    return d


CRASH_LOG = (DATA / "clock_networks_segfault.txt").read_text()                     # the recorded 208 crash (results/208/records/gotchas)


def test_a_crash_in_clock_networks_costs_only_that_report(tmp_path):
    d = _mini(tmp_path)
    calls: list[list[str]] = []

    def vivado(dcp: Path, out: Path, names: list[str]) -> tuple[int, str]:
        calls.append(list(names))
        for n in names:
            if n == "clock_networks":                      # what the Tcl does: a marker first, the process dies inside the report
                (out / f"{n}.not_run.txt").write_text("report unavailable: marker\n")
                (out / "clock_networks.rpt").write_text("Clock Networks partial\n")        # a half-written file
                return 139, CRASH_LOG
            (out / f"{n}.rpt").write_text(f"{n} report\n")
        return 0, "FDA-CHECKS-DONE"
    rep = C.run(d, ["clock_tree"], "synth", vivado=vivado)
    assert calls and "clock_networks" not in calls[0] and calls[-1] == ["clock_networks"]          # last, and in a session of its own
    assert len(calls) == 2 and "clock_utilization" in calls[0]
    ct = rep["checks"][0]
    assert ct["parts"]["clock_utilization"] == "ran"                                  # the reports of the first session survived
    assert ct["parts"]["clock_networks"].startswith("not run:") and "report unavailable" in ct["parts"]["clock_networks"]
    assert ct["incomplete"] and not rep["pass"] and "PARTIAL" in rep["digest"]        # never a pass
    assert rep["vivado"]["rc"] == 139 and [s["rc"] for s in rep["vivado"]["sessions"]] == [0, 139]


def test_a_crash_that_left_no_marker_is_still_unavailable(tmp_path):
    d = _mini(tmp_path)

    def vivado(dcp: Path, out: Path, names: list[str]) -> tuple[int, str]:
        if names == ["clock_networks"]:
            return 139, CRASH_LOG                          # died before the Tcl wrote anything
        for n in names:
            (out / f"{n}.rpt").write_text(f"{n} report\n")
        return 0, "ok"
    rep = C.run(d, ["clock_tree"], "synth", vivado=vivado)
    why = (d / "build" / "checks" / "base" / "synth" / "clock_networks.not_run.txt").read_text()
    assert "report unavailable" in why and "rc 139" in why
    assert rep["checks"][0]["incomplete"]


def test_the_session_tcl_orders_clock_networks_last_and_marks_each_report():
    tcl = (ROOT / "flow" / "checks" / "vivado_checks.tcl").read_text()
    assert 'if {$n ne "clock_networks"}' in tcl and tcl.index("lappend order clock_networks") > tcl.index("lappend order $n")
    assert "report unavailable" in tcl and "file delete $out/$name.not_run.txt" in tcl
    b = (ROOT / "flow" / "build.tcl").read_text()
    assert b.index("report_clock_networks") > b.index("io_dump_paths $out/io_paths_synth.txt")        # last of the synthesis reports
    assert b.index("report_clock_networks") < b.index("stage synth_reports")
    assert "clock_networks_synth.not_run.txt" in b


def test_the_standards_rule_reads_a_crash_marker_as_not_run():
    src = (ROOT / "flow" / "standards_check.py").read_text()
    assert "clock_networks_synth.not_run.txt" in src


# ---- fix 3: Gray buses ---------------------------------------------------------------------------------------------------------
needs_icarus = pytest.mark.skipif(not shutil.which("iverilog"), reason="needs Icarus")


def test_gray_signals_are_found_through_the_drivers():
    t = cdc_inject.strip_comments((FX207 / "rtl" / "cdc207_top.v").read_text())
    g = cdc_inject.gray_signals(t)
    assert {"wgray_a", "rgray_b", "wsend_a", "rsend_b"} <= g                          # named, built by bin2gray, or driven by one
    assert "wq1_b" in g and "lvl_s1" not in g and "wbin_a" not in g                      # the crossing register carries the code; a binary count does not
    assert "n" in cdc_inject.gray_signals("wire [3:0] n = b ^ (b >> 1);")             # an unnamed Gray conversion
    assert not cdc_inject.gray_signals("reg [3:0] d; always @(posedge c) d <= d + 1;")


def _sim_207(tmp_path: Path, bad: int, seed: int | None) -> str:
    plus: list[str] = []
    src, plus, _ = cdc_inject.prepare([FX207 / "rtl" / "cdc207_top.v"], tmp_path / f"w{bad}_{seed}", seed)
    exe = tmp_path / f"sim{bad}_{seed}"
    subprocess.run(["iverilog", "-g2012", f"-DBADV={bad}", "-o", str(exe), "-s", "tb_cdc207", str(FX207 / "rtl" / "tb_cdc207.v"),
                    *map(str, src)], check=True, capture_output=True)
    return subprocess.run(["vvp", "-n", str(exe), *plus], capture_output=True, text=True, timeout=300).stdout


@needs_icarus
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_the_good_gray_fifo_is_no_longer_flagged_on_any_seed(tmp_path, seed):
    """207: the read pointer (156 MHz to 100 MHz, two source steps between two destination edges) was 'seen ahead of its source' for
    1 cycle in 2 of 5 seeds on the good design (seeds 1 and 3, measured again before the fix)."""
    out = _sim_207(tmp_path, 0, seed)
    assert "PASS tb_cdc207" in out and "POINTER" not in out


@needs_icarus
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_a_real_pointer_fault_still_fails_on_every_seed(tmp_path, seed):
    """B1 (binary pointers, crossed bit by bit) fails in 5 of 5 seeds, before and after the fix."""
    out = _sim_207(tmp_path, 1, seed)
    assert "FAIL tb_cdc207" in out or "FIFO: got" in out


@needs_icarus
def test_a_binary_bus_is_torn_as_before(tmp_path):
    """No Gray name or conversion in the cone: the per-bit hold is generated exactly as before."""
    t = ("module m(input clk_a, input clk_b, input [3:0] cnt_a, output reg [3:0] q2);\n"
         "(* ASYNC_REG = \"TRUE\" *) reg [3:0] q1;\nalways @(posedge clk_b) begin q1 <= cnt_a; q2 <= q1; end\nendmodule\n")
    new, info = cdc_inject.inject_text(t, 100)
    assert "bus_steps" not in new and "__b < $bits(q1)" in new and info["sites"] == 1
    g = t.replace("cnt_a", "cnt_gray_a")
    newg, _ = cdc_inject.inject_text(g, 100)
    assert "bus_steps" in newg and "GRAY_STEPS" in newg


# ---- fix 5: LOC site names against the part ------------------------------------------------------------------------------------
PART = "xck26-sfvc784-2LV-c"


def test_the_pilot_xdc_with_the_wrong_site_is_refused_before_synthesis():
    r = xdc_sites.check((DATA / "p1_run3_design.xdc").read_text(), PART, "kr260")
    assert r["checked"] and len(r["problems"]) == 1
    msg = xdc_sites.message(r["problems"])
    assert msg.startswith("constraints stage:") and "IBUFDS_GTE4_X1Y6" in msg and "line 13" in msg
    assert "GTHE4_COMMON_X0Y1" in msg and "IBUFDS0_GTHE4" in msg and "Y6/Y5" in msg      # the board's own answer, from its package pins


def test_the_pilot_xdc_that_passed_is_accepted():
    r = xdc_sites.check((DATA / "p1_run1_design.xdc").read_text(), PART, "kr260")
    assert r["checked"] and r["problems"] == []


def test_real_gt_sites_pass_and_missing_ones_name_the_choices():
    ok = "set_property LOC GTHE4_CHANNEL_X0Y6 [get_cells u_gt]\nset_property -dict {LOC GTHE4_COMMON_X0Y1 IOSTANDARD LVDS} [get_cells c]\n"
    assert xdc_sites.check(ok, PART)["problems"] == []
    bad = "set_property LOC GTHE4_CHANNEL_X0Y16 [get_cells u_gt]  ;# not a channel of this part\nset_property LOC BUFG_GT_X0Y200 [get_cells b]\n"
    r = xdc_sites.check(bad, PART)
    assert len(r["problems"]) == 2 and "GTHE4_CHANNEL_X0Y0," in r["problems"][0]


def test_comments_and_other_locs_are_left_alone():
    assert xdc_sites.check("# set_property LOC IBUFDS_GTE4_X1Y6 [get_cells u]\nset_property LOC SLICE_X0Y0 [get_cells r]\n", PART)["problems"] == []


def test_a_part_without_data_says_not_checked():
    r = xdc_sites.check("set_property LOC IBUFDS_GTE4_X1Y6 [get_cells u]\n", "xc7a100tcsg324-1")
    assert r["checked"] is False and r["problems"] == [] and "not checked" in r["why"]


def test_prepare_refuses_the_wrong_site(tmp_path):
    """The build's first step (prepare.py) fails with the constraints-stage message, before Vivado starts. (build.yaml paths are relative to
    the repository root, so the throw-away design lives in a folder under it, removed afterwards.)"""
    rel = Path(f".t219_prepare_{os.getpid()}")
    d = ROOT / rel
    try:
        (d / "rtl").mkdir(parents=True)
        (d / "rtl" / "t.sv").write_text("module t(input a); endmodule\n")
        shutil.copy(DATA / "p1_run3_design.xdc", d / "design.xdc")
        (d / "build.yaml").write_text(f"top: t\npart: {PART}\nboard: kr260\nsources: [{rel}/rtl/t.sv]\nconstraints: [{rel}/design.xdc]\ngenerics: {{}}\n")
        cmd = ["python3", str(ROOT / "flow" / "prepare.py"), str(d), "--out", str(tmp_path / "out")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode != 0 and "constraints stage" in (r.stderr + r.stdout) and "IBUFDS_GTE4_X1Y6" in (r.stderr + r.stdout)
        shutil.copy(DATA / "p1_run1_design.xdc", d / "design.xdc")
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_the_link_planner_names_the_refclk_site_and_bel_from_the_board():
    import yaml
    from flow import gt_plan
    board = yaml.safe_load((ROOT / "boards" / "kr260" / "board.yaml").read_text())
    p = gt_plan.plan({"protocol": "raw", "line_rate_gbps": 10.3125, "lanes": 1}, board)
    assert p["refclk"] == {"pins": ["Y6", "Y5"], "func": "MGTREFCLK0P_224", "site": "GTHE4_COMMON_X0Y1", "bel": "IBUFDS0_GTHE4"}
    assert any("no IBUFDS_GTE4 site" in n for n in p["notes"])


# ---- fix 8: supplied bus files are not mutation targets ------------------------------------------------------------------------
BUS = "module jtag_bus(input clk, input a, output reg y);\n always @(posedge clk) if (a == 1'b1) y <= !y;\nendmodule\n"
CORE = "module core(input clk, input a, input b, output reg y);\n always @(posedge clk) if (a == b) y <= a + b;\nendmodule\n"


def _supplied(tmp_path: Path) -> Path:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "data" / "jtag_bus.sv").write_text(BUS)
    (d / "rtl" / "core.sv").write_text(CORE)
    return d


def test_data_files_are_never_candidates(tmp_path):
    d = _supplied(tmp_path)
    assert M.supplied_copies(d, d / "rtl") == {}
    c = M.generate_candidates(d / "rtl")
    assert c and {x["file"] for x in c} == {"core.sv"}                  # data/ is not read at all


def test_a_copy_of_the_supplied_file_in_rtl_is_excluded_too(tmp_path):
    d = _supplied(tmp_path)
    (d / "rtl" / "jtag_bus.sv").write_text(BUS)                           # the agent copied it anyway (identical)
    (d / "rtl" / "bus_copy.sv").write_text(BUS + "// a renamed copy\n")
    ex = M.supplied_copies(d, d / "rtl")
    assert set(ex) == {"jtag_bus.sv", "bus_copy.sv"} and "identical" in ex["jtag_bus.sv"] and "only modules" in ex["bus_copy.sv"]
    c = M.generate_candidates(d / "rtl", set(ex))
    assert {x["file"] for x in c} == {"core.sv"}
    assert {x["file"] for x in M.generate_candidates(d / "rtl")} == {"core.sv", "jtag_bus.sv", "bus_copy.sv"}      # without the rule they were targets
