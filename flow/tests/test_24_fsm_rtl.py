"""Brief 24, simulation (Icarus + cocotb): the reference controller's variants against each other and the bench, and the FSM
coverage check on real designs, with the test-removal mutants that must make it fail."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from flow import cocotb_run
from flow import fsm_coverage as fc

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "flow" / "tests" / "fixtures" / "fsm_discipline"
RTL = [FX / "rtl" / f for f in ("fsm_front.sv", "ctl_sep.sv", "ctl_mono.sv", "tb_ctl.sv")]


def run_ref(name: str, mono: int, out: int, tmp: Path, testcase=None, monkeypatch=None) -> Path:
    monkeypatch.setenv("FDA_FSM_TRACE", str(tmp))
    monkeypatch.syspath_prepend(str(FX / "bench"))
    cocotb_run.run(name, "tb_ctl", RTL, "ctl_cocotb", FX / "bench", parameters={"MONO": mono, "OUT": out}, testcase=testcase)
    return tmp / f"{name}.fsmtrace"


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs iverilog")
def test_separated_and_monolithic_are_cycle_equivalent(tmp_path: Path) -> None:
    exe = tmp_path / "eq.vvp"
    srcs = [FX / "rtl" / f for f in ("fsm_front.sv", "ctl_sep.sv", "ctl_mono.sv", "tb_equiv.sv")]
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), *map(str, srcs)], check=True)
    out = subprocess.run(["vvp", str(exe)], check=True, capture_output=True, text=True).stdout
    assert "EQUIV_OK" in out, out


@pytest.mark.parametrize("mono,out", [(0, 0), (1, 0), (0, 2), (1, 2)])
def test_the_cycle_exact_bench_passes_for_combinational_and_lookahead_outputs(mono, out, tmp_path, monkeypatch) -> None:
    run_ref(f"fsm24_ref_{mono}{out}", mono, out, tmp_path, monkeypatch=monkeypatch)


def test_registered_outputs_fail_the_latency_bench(tmp_path, monkeypatch) -> None:
    with pytest.raises(AssertionError):                    # one cycle late: the bench's cycle-exact expectations break
        run_ref("fsm24_ref_01", 0, 1, tmp_path, monkeypatch=monkeypatch)


def test_reference_bench_covers_every_state_and_transition(tmp_path, monkeypatch) -> None:
    tr = run_ref("fsm24_ref_cov", 0, 0, tmp_path, monkeypatch=monkeypatch)
    rep = fc.evaluate(FX, [tr])
    f = rep["fsms"][0]
    assert rep["pass"] and (f["states_hit"], f["n_states"], f["transitions_hit"], f["transitions_listed"]) == (11, 11, 13, 13)


def test_removing_the_timeout_test_makes_the_check_fail(tmp_path, monkeypatch) -> None:
    tr = run_ref("fsm24_ref_mut", 0, 0, tmp_path, monkeypatch=monkeypatch,
                 testcase=["test_burst_and_ack", "test_nack_retries_the_burst", "test_response_backpressure"])
    f = fc.evaluate(FX, [tr])["fsms"][0]
    assert not f["pass"] and f["states_missed"] == ["ERR"] and f["transitions_missed"] == ["ERR->COOL", "WACK->ERR"]


def board(design: str, tb: str, mod: str, params: dict, name: str, tmp: Path, monkeypatch, testcase=None) -> Path:
    d = ROOT / "designs" / design
    t = d / "tests"
    srcs = [s for s in sorted((d / "rtl").glob("*.sv")) if not s.name.endswith("_top.sv")] + [t / f"{tb}.sv"]
    monkeypatch.setenv("FDA_FSM_TRACE", str(tmp))
    cocotb_run.run(name, tb, srcs, mod, t, parameters=params, testcase=testcase)
    return tmp / f"{name}.fsmtrace"


def test_qspi_rdid_full_and_without_the_primed_read(tmp_path, monkeypatch) -> None:
    d = ROOT / "designs" / "b2_qspi_jedec"
    full = board("b2_qspi_jedec", "tb_qspi", "qspi_cocotb", {"HALF": 4}, "fsm24_qspi", tmp_path, monkeypatch)
    f = fc.evaluate(d, [full])["fsms"][0]
    assert f["pass"] and (f["states_hit"], f["transitions_hit"]) == (8, 11)
    mut = board("b2_qspi_jedec", "tb_qspi", "qspi_cocotb", {"HALF": 4}, "fsm24_qspi_mut", tmp_path, monkeypatch,
                testcase="test_writes_to_any_register_send_nothing_else")
    g = fc.evaluate(d, [mut])["fsms"][0]
    assert not g["pass"] and g["transitions_missed"] == ["S_IDLE->S_SETUP"] and g["states_missed"] == []


def test_i2c_pointer_read_full_and_without_the_nack_test(tmp_path, monkeypatch) -> None:
    d = ROOT / "designs" / "b2_tmp_adt7420"
    full = board("b2_tmp_adt7420", "tb_tmp", "tmp_cocotb", {"QUARTER": 5}, "fsm24_i2c", tmp_path, monkeypatch)
    f = fc.evaluate(d, [full])["fsms"][0]
    assert f["pass"] and (f["states_hit"], f["transitions_hit"]) == (7, 11)
    mut = board("b2_tmp_adt7420", "tb_tmp", "tmp_cocotb", {"QUARTER": 5}, "fsm24_i2c_mut", tmp_path, monkeypatch,
                testcase=["test_id_and_temperature", "test_clock_stretching", "test_one_byte_then_two_repeat"])
    g = fc.evaluate(d, [mut])["fsms"][0]
    assert not g["pass"] and g["transitions_missed"] == ["S_RACK->S_STOP"]


def test_cocotb_sampler_feeds_the_functional_bins(tmp_path, monkeypatch) -> None:
    """The in-bench route: start_fsm_coverage on the reference controller, bins exported with coverage_db (FDA_COV_OUT)."""
    import yaml
    monkeypatch.setenv("FDA_FSM_SAMPLER", "1")
    monkeypatch.syspath_prepend(str(FX / "bench"))
    cocotb_run.run("fsm24_ref_sampler", "tb_ctl", RTL, "ctl_cocotb", FX / "bench", parameters={"MONO": 0, "OUT": 0},
                   extra_env={"FDA_FSM_SAMPLER": "1"})
    cov = yaml.safe_load((ROOT / "build" / "sim" / "fsm24_ref_sampler" / "coverage_func.yml").read_text())
    assert cov["top.fsm_ctl.states"]["size"] == 11 and cov["top.fsm_ctl.states"]["coverage"] == 11
    assert cov["top.fsm_ctl.transitions"]["coverage"] == 13


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs iverilog")
def test_a_one_clock_reset_is_lost_when_the_reset_is_gated_by_the_enable(tmp_path: Path) -> None:
    """The reset-with-enable lesson (brief 24): async, sync-over-enable and async-assert/sync-release see a one-clock reset at every
    phase of a one-in-four enable; the synchronous reset that is only looked at on an enable tick sees it one time in four."""
    exe = tmp_path / "rc.vvp"
    srcs = [FX / "rtl" / f for f in ("fsm_front.sv", "ctl_sep.sv", "tb_reset_ce.sv")]
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), *map(str, srcs)], check=True)
    out = subprocess.run(["vvp", str(exe)], check=True, capture_output=True, text=True).stdout
    rows = [dict(kv.split("=") for kv in l.split()[1:]) for l in out.splitlines() if l.startswith("RESET_CE")]
    assert len(rows) == 4
    assert all(r["async"] == r["sync_over_ce"] == r["async_assert_sync_release"] == "1" for r in rows)
    assert sorted(r["sync_gated_by_ce"] for r in rows) == ["0", "0", "0", "1"]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs iverilog")
def test_output_styles_latency(tmp_path: Path) -> None:
    """Clocks from an input to the output it causes (0 = the same clock): combinational, registered (+1 everywhere), lookahead (the
    same as combinational, except the Mealy cmd_ack, which a lookahead register cannot give)."""
    exe = tmp_path / "lat.vvp"
    srcs = [FX / "rtl" / f for f in ("fsm_front.sv", "ctl_sep.sv", "tb_latency.sv")]
    subprocess.run(["iverilog", "-g2012", "-o", str(exe), *map(str, srcs)], check=True)
    out = subprocess.run(["vvp", str(exe)], check=True, capture_output=True, text=True).stdout
    rows = {int(l.split()[1].split("=")[1]): {kv.split("=")[0]: int(kv.split("=")[1]) for kv in l.split()[2:]}
            for l in out.splitlines() if l.startswith("LAT")}
    c, r, k = rows[0], rows[1], rows[2]
    assert c == {"cmd_valid_to_cmd_ack": 0, "cmd_valid_to_req": 2, "gnt_to_addr_v": 1, "gnt_to_valid": 2, "ack_to_rsp_valid": 1}
    assert all(r[n] == c[n] + 1 for n in c)
    assert k["cmd_valid_to_cmd_ack"] == 1 and all(k[n] == c[n] for n in c if n != "cmd_valid_to_cmd_ack")
