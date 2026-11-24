"""Brief 206: the initial-value check (flow/checks/init_values.py) on the recorded Vivado 2026.1 netlist scans and logs
(results/206_power_up/records/init_scan/, written by fda_init_scan in flow/checks/vivado_checks.tcl on the brief's arms).

The property the check stands for: a register whose initial value of 1 keeps it out of a DSP or RAM block's own register
is reported, once per block, and a design whose registers next to hard blocks all start at 0 is not. Renaming cells or
reordering rows never changes the verdict."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import checks as C
from flow import lint_ruleset as LR
from flow.checks import init_values as I

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "results" / "206_power_up" / "records"
SCAN = REC / "init_scan"


def _scan(name: str) -> list[dict[str, str]]:
    return I.read_scan(SCAN / f"{name}_init_scan.tsv")


@pytest.mark.parametrize("part", ["xc7a35tcpg236-1", "xck26-sfvc784-2LV-c"])
def test_dsp_registers_with_init_one_are_one_finding_per_block(part: str) -> None:
    fs = I.scan_findings(_scan(f"{part}_x8r_1"))
    assert [f["code"] for f in fs] == ["INIT-HB-01"]
    f = fs[0]
    assert f["severity"] == "advisory" and "DSP" in f["message"]
    # X8: A and B (18 + 18) feed the multiplier, M (36) is fed by it; P sits behind M, not next to the block
    assert "36 feeding it" in f["message"] and "36 fed by it" in f["message"]


@pytest.mark.parametrize("part", ["xc7a35tcpg236-1", "xck26-sfvc784-2LV-c"])
@pytest.mark.parametrize("arm", ["x8r_0", "x9r_0", "x8b_0", "x9b_1", "x12b_1"])
def test_no_finding_when_every_register_next_to_a_block_starts_at_zero_or_was_absorbed(part: str, arm: str) -> None:
    # all-zero baselines; X9b gives the RAM's read and output registers the same value, so both go into the RAM
    assert I.scan_findings(_scan(f"{part}_{arm}")) == []


@pytest.mark.parametrize("part", ["xc7a35tcpg236-1", "xck26-sfvc784-2LV-c"])
def test_block_ram_output_register_with_its_own_value_is_reported(part: str) -> None:
    for arm in ("x9r_1", "x9c_1"):
        fs = I.scan_findings(_scan(f"{part}_{arm}"))
        assert [f["code"] for f in fs] == ["INIT-HB-01"] and "block RAM" in fs[0]["message"], (arm, fs)


def test_row_order_and_cell_names_do_not_change_the_verdict() -> None:
    rows = _scan("xc7a35tcpg236-1_x8r_1")
    renamed = [{**r, "cell": "renamed_" + r["cell"]} for r in reversed(rows)]
    a, b = I.scan_findings(rows), I.scan_findings(renamed)
    assert [(f["code"], f["where"], f["count"]) for f in a] == [(f["code"], f["where"], f["count"]) for f in b]


def test_a_register_feeding_a_ram_input_is_not_reported() -> None:
    # a block RAM's address and data inputs have no register to absorb one, whatever its INIT (review fix)
    rows = [{"cell": "a", "ref": "FDRE", "init": "1", "dir": "to", "block": "m", "block_ref": "RAMB36E1", "block_pin": "ADDRARDADDR[5]"}]
    assert I.scan_findings(rows) == []
    rows[0]["block_ref"] = "DSP48E1"
    assert [f["code"] for f in I.scan_findings(rows)] == ["INIT-HB-01"]


def test_rows_with_init_zero_are_ignored() -> None:
    rows = [{"cell": "r", "ref": "FDRE", "init": "0", "dir": "to", "block": "d", "block_ref": "DSP48E1", "block_pin": "A[0]"}]
    assert I.scan_findings(rows) == []


def test_uram_refused_for_initial_contents_from_the_recorded_log() -> None:
    fs = I.log_findings((REC / "init_scan" / "xck26_x11_1_synth_8_12183.log").read_text())
    assert [f["code"] for f in fs] == ["INIT-URAM-01"]
    assert fs[0]["where"].endswith("mem_reg") and fs[0]["count"] >= 1
    assert I.log_findings("INFO: [Synth 8-7052] unrelated\n") == []


def test_codes_are_registered_and_map_to_a_rule() -> None:
    c = C.CHECKS["init_values"]
    assert set(c.codes["init_values"]) == set(I.CODES)
    rs = LR.load_rules()
    assert {LR.rule_for(rs, "init_values", x) for x in I.CODES} == {"HDL-INIT-01"}
    assert "init_scan" in C.SESSION_ONLY


def test_check_reads_the_session_scan_and_the_build_log(tmp_path: Path) -> None:
    d = tmp_path / "d"
    b = d / "build" / "base"
    out = d / "build" / "checks" / "base" / "synth"
    out.mkdir(parents=True)
    b.mkdir(parents=True, exist_ok=True)
    (d / "build.yaml").write_text("top: x\nsources: [rtl/*.sv]\npart: xck26-sfvc784-2LV-c\n")
    (b / "post_synth.dcp").write_text("")
    (b / "vivado.log").write_text((REC / "init_scan" / "xck26_x11_1_synth_8_12183.log").read_text())
    (out / "init_scan.tsv").write_text((SCAN / "xck26-sfvc784-2LV-c_x8r_1_init_scan.tsv").read_text())
    r = C.run_one("init_values", d, "synth", root=d)
    codes = sorted(f.get("rule") or f.get("code") for f in r.get("findings", []))
    assert codes == ["HDL-INIT-01", "HDL-INIT-01"], r
    assert all(not f.get("blocking") for f in r["findings"])
    assert r.get("parts", {}).get("netlist") == "ran" and r["parts"].get("log") == "ran"


def test_check_without_a_scan_says_why(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "build" / "base").mkdir(parents=True)
    (d / "build.yaml").write_text("top: x\nsources: [rtl/*.sv]\n")
    r = C.run_one("init_values", d, "synth", root=d)
    assert r.get("parts", {}).get("netlist", "").startswith("not run")
