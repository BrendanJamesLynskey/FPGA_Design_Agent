"""Brief 70: what the reset check gained from the measurements (results/70_resets): REQP-1840 as a second form of HDL-RST-03,
the unnamed-net polarity fix (b59a), and the reset-cost and AMD-IP reset tables agreeing with their records. The tests that
elaborate a design skip, with a reason, where the OSS CAD Suite is not installed (CI's reset-elab job runs them)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import checks as C
from flow.checks import elab
from flow.checks import resets as R

needs_tool = pytest.mark.skipif(elab.find_tool() is None, reason="yosys (OSS CAD Suite) not installed: set FDA_OSS_CAD")


def _design(tmp: Path, sv: str, name: str = "x") -> Path:
    d = tmp / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "build.yaml").write_text(f"top: {name}\nsources: [rtl/*.sv]\n")
    (d / "rtl" / "x.sv").write_text(sv)
    return d


def _blocking_rules(d: Path) -> set[str]:
    r = C.run_one("resets", d, "rtl", root=d)
    assert r.get("parts", {}).get("source") == "ran", r
    return {f["rule"] for f in r.get("findings", []) if f.get("blocking")}


def test_reqp_1840_is_a_reset_row_of_rule_hdl_rst_03() -> None:
    assert "REQP-1840" in R.AMD_DRC
    rows = [{"rule": "REQP-1840", "severity": "Warning", "description": "RAMB18 async control check", "count": 1},
            {"rule": "REQP-1", "severity": "Warning", "description": "unrelated", "count": 1}]
    out = R.amd_findings(None, rows, None, "synth")
    assert [f["code"] for f in out] == ["REQP-1840"]
    import yaml
    rules = {r["id"]: r for r in yaml.safe_load((Path(__file__).resolve().parents[1] / "hdl_rules.yaml").read_text())["rules"]}
    assert "REQP-1840" in rules["HDL-RST-03"]["checks"]["vivado"]
    assert "REQP-1840" in C.CHECKS["resets"].codes["vivado"]


@needs_tool
def test_two_unnamed_nets_are_not_one_reset(tmp_path: Path) -> None:
    # the b59a case: a data flop whose D is `sel < 3 ? v : 0` is inferred as a synchronous-reset flop on the comparator's
    # output, an unnamed net; the real reset is tested the other way round. The two must not be read as one reset.
    sv = ("module x(input clk, input rst_n, input [2:0] sel, input [7:0] v, output logic [7:0] q, output logic [7:0] r);\n"
          "  always_ff @(posedge clk) q <= (sel < 3'd3) ? v : 8'd0;\n"
          "  always_ff @(posedge clk) if (!rst_n) r <= 8'd0; else r <= v;\n"
          "endmodule\n")
    assert _blocking_rules(_design(tmp_path, sv)) == set()


@needs_tool
def test_one_named_reset_in_both_polarities_is_still_caught(tmp_path: Path) -> None:
    one = ("module x(input clk, input rst, input [7:0] v, output logic [7:0] q, output logic [7:0] r);\n"
           "  always_ff @(posedge clk) if (rst) q <= 8'd0; else q <= v;\n"
           "  always_ff @(posedge clk) if (!rst) r <= v; else r <= 8'd0;\n"      # the same level resets: one polarity
           "endmodule\n")
    assert _blocking_rules(_design(tmp_path / "a", one)) == set()
    two = ("module x(input clk, input rst, input [7:0] v, output logic [7:0] q, output logic [7:0] r);\n"
           "  always_ff @(posedge clk) if (rst) q <= 8'd0; else q <= v;\n"
           "  always_ff @(posedge clk) if (!rst) r <= 8'd0; else r <= v;\n"      # opposite levels reset: two polarities
           "endmodule\n")
    assert "HDL-RST-02" in _blocking_rules(_design(tmp_path / "b", two))


def test_the_dds_sine_table_is_what_rtoi_gave() -> None:
    """ip_lib/dds_awg's constant function replaces $rtoi (which the reset check's front end cannot run): the same values."""
    import math
    for lut_w, out_w in ((4, 4), (8, 12), (10, 16), (12, 24)):
        n = 1 << lut_w
        for i in range(n):
            v = math.sin(2.0 * math.pi * i / n) * ((1 << (out_w - 1)) - 1)
            rtoi = int(v)                                   # truncation toward zero
            t = round(v)
            if v >= 0.0 and float(t) > v:
                t -= 1
            elif v < 0.0 and float(t) < v:
                t += 1
            assert t == rtoi, (lut_w, out_w, i)


# ---- the AMD IP reset map (flow/amd_ip_resets.py) against the survey of the install's HDL ------------------------------------
def _survey() -> dict:
    import json
    return json.loads((Path(__file__).resolve().parents[2] / "results" / "70_resets" / "records" / "ip_reset_survey.json").read_text())["ips"]


def test_every_map_entry_is_complete_and_the_note_builder_runs() -> None:
    from flow import amd_ip_resets as AIR
    for name, e in AIR.MAP.items():
        assert {"title", "port", "style", "needs", "source"} <= set(e), name
        notes = AIR.notes_for(name)
        assert len(notes) >= 3 and all(isinstance(n, str) and n for n in notes), name


def test_ips_found_in_scripts_and_block_designs(tmp_path: Path) -> None:
    from flow import amd_ip_resets as AIR
    (tmp_path / "bd.tcl").write_text("create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst\n"
                                     "create_ip -name axi_gpio -vendor xilinx.com -library ip -module_name g\n"
                                     "# xilinx.com:ip:unknown_ip:1.0 is not in the map\n")
    assert set(AIR.scan([tmp_path])) == {"proc_sys_reset", "axi_gpio"}


def test_map_claims_agree_with_the_survey_of_the_install() -> None:
    """The entries that say 'no asynchronous reset' have no asynchronous process in the survey of AMD's readable HDL, and the
    register slice, which the map says uses one, has."""
    from flow import amd_ip_resets as AIR
    sv = _survey()
    keys = {"proc_sys_reset": "proc_sys_reset", "axi_gpio": "axi_gpio", "axi_uartlite": "axi_uartlite", "axi_timer": "axi_timer",
            "axi_intc": "axi_intc", "axi_iic": "axi_iic", "axi_quad_spi": "axi_quad_spi", "axi_dma": "axi_dma", "axi_cdma": "axi_cdma",
            "axi_register_slice": "axi_register_slice"}
    for name, key in keys.items():
        style = AIR.MAP[name]["style"].lower()
        if "asynchronous clear" in style or "asynchronous reset outside" in style:
            assert sv[key]["async_procs"] > 0, name
        else:
            assert sv[key]["async_procs"] == 0, (name, sv[key]["async_procs"])


def test_psr_note_quotes_the_record() -> None:
    import json
    from flow import amd_ip_resets as AIR
    rec = json.loads((Path(__file__).resolve().parents[2] / "results" / "70_resets" / "records" / "psr_sequence.json").read_text())["default"]
    note = [n for n in AIR.notes_for("proc_sys_reset") if n.startswith("measured sequence")][0]
    assert f"clock {rec['power_up_release_cycle']['bus_struct_reset']}" in note
    assert f"the core (mb_reset) at {rec['power_up_release_cycle']['mb_reset']}" in note


def test_measured_costs_agree_with_the_records() -> None:
    """flow/checks/reset_costs.json and records/matrix_summary.json are what results/70_resets/summary.py gives from the matrix
    records (the numbers the check quotes cannot drift from the measurement)."""
    import subprocess
    import sys
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / "results" / "70_resets" / "summary.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_check_quotes_a_cost_with_each_finding_it_can_cost() -> None:
    for code in ("RST-ASYNC-01", "RST-DSPRAM-01", "RST-POL-01", "RST-POL-02"):
        for part in ("xc7a100tcsg324-1", "xck26-sfvc784-2LV-c"):
            assert R.cost_note(code, part).startswith("measured"), (code, part)
    assert R.cost_note("RST-LUT-01", "xc7a100tcsg324-1") == ""
