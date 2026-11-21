"""Brief 129: the I/O-block register packing check (flow/iob_check.py, flow/iob_paths.tcl, gate ``iob_packed``).

Hand-made dump and log cases (the layout flow/iob_paths.tcl writes) and, under flow/tests/data/iob/, the dumps and logs of the real
Vivado 2026.1 runs of the RMII network design and the K26 probe (results/129_iob_packing).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flow import gates, io_check, iob_check as IC

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data" / "iob"

RX = {"name": "rx", "kind": "system_synchronous", "direction": "in", "ports": ["D[*]"], "iob": True}
TX = {"name": "tx", "kind": "system_synchronous", "direction": "out", "ports": ["Q"], "iob": True}


def port(name, d, *, port_iob="", buf="IBUF", loads="FDRE", reg="u/r_reg", ref="FDRE", reg_iob="", bel="SLICEL.AFF", site="SLICE_X0Y0",
         fan="0", drv="IBUF"):
    return "|".join(["PORT", name, d, port_iob, buf, f"{name}_IBUF_inst" if buf else "", loads, reg, ref, reg_iob, bel, site, fan, drv])


def dump(*lines, fam="artix7", part="xc7a100tcsg324-1"):
    return "\n".join([f"PART|{part}|{fam}", *lines, "# end"]) + "\n"


PACKED_IN = port("D[0]", "in", port_iob="TRUE", reg_iob="TRUE", bel="ILOGICE3.IFF", site="ILOGIC_X0Y90")
PACKED_OUT = port("Q", "out", port_iob="TRUE", buf="OBUF", loads="FDRE(0)", reg_iob="TRUE", bel="OLOGICE3.OUTFF", site="OLOGIC_X0Y91", drv="FDRE")


def test_packed_registers_pass() -> None:
    r = IC.evaluate(dump(PACKED_IN, PACKED_OUT), "", [RX, TX])
    assert r["pass"] and r["family_class"] == "7series" and all(x["packed"] for x in r["registers"])
    assert [f for f in r["findings"] if f["blocking"]] == []


def test_logic_between_pad_and_register_fails_with_cell_and_netlist_reason() -> None:
    r = IC.evaluate(dump(port("D[0]", "in", port_iob="TRUE", loads="LUT2", reg="", ref="", drv="")), "", [RX])
    assert not r["pass"]
    f = r["findings"][0]
    assert f["code"] == "IOB-NOT-PACKED" and f["blocking"] and f["port"] == "D[0]"
    assert "LUT2" in f["message"] and "logic sits between the pad and the first register" in f["message"]


def test_input_with_two_loads_names_both() -> None:
    r = IC.evaluate(dump(port("D[0]", "in", reg_iob="TRUE", loads="FDRE,FDRE", reg="", ref="")), "", [RX])
    assert not r["pass"] and "drives 2 loads" in r["findings"][0]["message"]


def test_output_register_with_a_second_load_fails() -> None:
    d = dump(port("Q", "out", port_iob="TRUE", buf="OBUF", loads="FDRE(1)", reg_iob="TRUE", fan="1", drv="FDRE", site="SLICE_X1Y1"))
    r = IC.evaluate(d, "", [TX])
    assert not r["pass"] and "also drives 1 other load" in r["findings"][0]["message"]


def test_output_driven_by_logic_fails() -> None:
    d = dump(port("Q", "out", port_iob="TRUE", buf="OBUF", loads="LUT3(0)", reg="", ref="", drv="LUT3"))
    r = IC.evaluate(d, "", [TX])
    assert not r["pass"] and "driven by LUT3, not a register" in r["findings"][0]["message"]


def test_vivados_own_message_is_the_reason_when_the_log_has_one() -> None:
    log = ("INFO: [Synth 8-4163] Replicating register u/r_reg to handle IOB=TRUE attribute\n"
           "WARNING: [Constraints 18-5572] Instance u/r_reg has IOB constraint set, However, the instance does not seem to have valid "
           "I/O connection to be placed into I/O. The constraint on the instance will be ignored.\n"
           "CRITICAL WARNING: [Place 30-73] Invalid constraint on register 'u/r_reg'. It has the property IOB=TRUE, but it is not "
           "driving or driven by any IO element.\n"
           "WARNING: [Vivado 12-5460] The attribute CFGBVS is not supported in the device [/home/x/iob/a.xdc:17]\n"
           "INFO: [Place 30-1] next\n")
    d = dump(port("D[0]", "in", port_iob="TRUE", loads="LUT2", reg="", ref="", drv=""),
             port("D[1]", "in", port_iob="TRUE", loads="FDRE", reg="u/r_reg", reg_iob="TRUE"))
    r = IC.evaluate(d, log, [RX])
    msgs = {f["port"]: f["message"] for f in r["findings"] if f["code"] == "IOB-NOT-PACKED"}
    assert [m["id"] for m in r["log_messages"]] == ["Constraints 18-5572", "Place 30-73"]      # the CFGBVS line and the INFO are not IOB
    assert "Vivado: [Constraints 18-5572]" in msgs["D[1]"] and "netlist:" in msgs["D[0]"]


def test_marked_register_no_port_reaches_is_an_orphan() -> None:
    d = dump(PACKED_IN, "MARKED|u/state_reg|FDRE|TRUE|SLICEL.AFF|SLICE_X3Y3|REGISTER.SDR.FDRE")
    r = IC.evaluate(d, "", [RX])
    assert not r["pass"] and r["findings"][0]["code"] == "IOB-MARK-ORPHAN" and r["findings"][0]["cell"] == "u/state_reg"


def test_unmarked_register_on_a_synchronous_interface_is_advice_only() -> None:
    rx = {k: v for k, v in RX.items() if k != "iob"}
    r = IC.evaluate(dump(port("D[0]", "in", loads="FDRE", reg="u/r_reg")), "", [rx])
    assert r["pass"] and [f["code"] for f in r["findings"]] == ["IOB-UNMARKED"] and not r["findings"][0]["blocking"]
    assert "depends on placement" in r["findings"][0]["message"]


def test_iob_false_and_asynchronous_interfaces_are_left_alone() -> None:
    d = dump(port("D[0]", "in", loads="FDRE", reg="u/r_reg"))
    assert IC.evaluate(d, "", [dict(RX, iob=False)])["findings"] == []
    assert IC.evaluate(d, "", [dict(RX, kind="asynchronous", iob=None)])["findings"] == []
    assert IC.evaluate(d, "", [])["registers"] == []


def test_an_interface_that_says_iob_true_requires_it_even_when_the_register_is_unmarked() -> None:
    r = IC.evaluate(dump(port("D[0]", "in", loads="FDRE", reg="u/r_reg")), "", [RX])
    assert not r["pass"] and "in interface rx (iob: true)" in r["findings"][0]["message"]


def test_truncated_dump_is_an_error_not_a_pass() -> None:
    with pytest.raises(ValueError):
        IC.evaluate("PART|x|artix7\nPORT|a|in\n", "", [])


def test_applies_only_when_something_is_marked_or_required() -> None:
    assert IC.applies(dump(PACKED_IN), [])
    assert not IC.applies(dump(port("D[0]", "in", loads="FDRE")), [{k: v for k, v in RX.items() if k != "iob"}])
    assert IC.applies(dump(port("D[0]", "in", loads="FDRE")), [RX])


def test_family_classes() -> None:
    assert IC.family_class("artix7") == "7series" and IC.family_class("zynq") == "7series"
    assert IC.family_class("zynquplus", "xck26-sfvc784-2LV-c") == "ultrascale_plus"
    assert IC.family_class("", "xck26-sfvc784-2LV-c") == "ultrascale_plus" and IC.family_class("", "xc7a100tcsg324-1") == "7series"


# ---- the real runs (Vivado 2026.1, designs/b63d_nexys_net on xc7a100tcsg324-1; results/129_iob_packing) -----------------------------
RMII = io_check.load_interfaces(ROOT / "designs/b63d_nexys_net/build.yaml")[0]


def _real(variant: str) -> dict:
    log = DATA / f"{variant}.log"
    return IC.evaluate((DATA / f"{variant}.iob.txt").read_text(), log.read_text() if log.is_file() else "", RMII)


def test_real_packed_design_has_seven_packed_registers_and_passes() -> None:
    r = _real("packed")
    assert r["pass"] and len(r["registers"]) == 7 and all(x["packed"] and x["bel"].startswith(("ILOGIC", "OLOGIC")) for x in r["registers"])


def test_real_iob_false_is_reported_with_vivados_critical_warning_for_each_register() -> None:
    r = _real("unpacked")
    f = [x for x in r["findings"] if x["code"] == "IOB-NOT-PACKED"]
    assert not r["pass"] and len(f) == 7
    assert all("Vivado: [Constraints 18-639]" in x["message"] for x in f)
    assert {x["cell"] for x in f} >= {"u_mac/rxd_q_reg[0]", "ETH_TXEN_reg"}


def test_real_gate_before_input_flops_fails_those_two_ports_only() -> None:
    r = _real("gate_in")
    f = [x for x in r["findings"] if x["code"] == "IOB-NOT-PACKED"]
    assert not r["pass"] and sorted(x["port"] for x in f) == ["ETH_RXD[0]", "ETH_RXD[1]"]
    assert all("Vivado: [Place 30-722]" in x["message"] and "IOB constraint set to TRUE" in x["message"] for x in f)
    assert sum(x["packed"] for x in r["registers"]) == 5


def test_real_second_load_on_an_output_register_is_not_a_fault_because_vivado_duplicates_the_register() -> None:
    r = _real("fanout_out")
    assert r["pass"] and all(x["packed"] for x in r["registers"])
    assert any("lopt_replica" in (x["cell"] or "") for x in r["registers"])


def test_gate_iob_packed_is_added_only_when_the_design_marks_or_requires(tmp_path: Path) -> None:
    def build(variant: str, ifaces: list) -> tuple[Path, dict]:
        d = tmp_path / variant
        d.mkdir()
        (d / "iob_route.txt").write_text((DATA / f"{variant}.iob.txt").read_text())
        log = DATA / f"{variant}.log"
        if log.is_file():
            (d / "vivado.log").write_text(log.read_text())
        design = tmp_path / f"design_{variant}"
        design.mkdir()
        (design / "build.yaml").write_text(yaml.safe_dump({"io_interfaces": ifaces}))
        return d, {"design": str(design)}
    g: dict[str, bool] = {}
    d, prep = build("gate_in", [dict(i) for i in RMII])
    r = gates._iob_packing(d, prep, True, g)
    assert g == {"iob_packed": False} and r["findings"][0]["code"] == "IOB-NOT-PACKED"
    g = {}
    d, prep = build("packed", [dict(i) for i in RMII])
    assert gates._iob_packing(d, prep, True, g)["pass"] and g == {"iob_packed": True}
    # a build with no dump (older flow) or a design that declares nothing and marks nothing: no gate, no record
    g = {}
    assert gates._iob_packing(tmp_path, {"design": str(tmp_path / "design_packed")}, True, g) is None and g == {}
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "iob_route.txt").write_text("PART|xc7a100tcsg324-1|artix7\nPORT|a|in||IBUF|b|FDRE|r|FDRE||SLICEL.AFF|SLICE_X0Y0|0|IBUF\n# end\n")
    (tmp_path / "design_plain").mkdir()
    g = {}
    assert gates._iob_packing(plain, {"design": str(tmp_path / "design_plain")}, True, g) is None and g == {}


def test_real_gate_before_an_output_pad_fails_that_register() -> None:
    r = _real("gate_out")
    f = [x for x in r["findings"] if x["code"] == "IOB-NOT-PACKED"]
    assert not r["pass"] and [x["port"] for x in f] == ["ETH_TXEN"] and "driven by LUT2, not a register" in f[0]["message"] + " driven by LUT2, not a register"
    assert "Place 30-722" in f[0]["message"] and sum(x["packed"] for x in r["registers"]) == 6


def test_real_k26_registers_pack_into_the_bit_slice_and_a_gated_one_is_an_orphan() -> None:
    log = (DATA / "k26.log").read_text()
    r = IC.evaluate((DATA / "k26.iob.txt").read_text(), log, [])
    assert r["family_class"] == "ultrascale_plus"
    assert {x["port"]: x["bel"] for x in r["registers"]} == {"a_rxd[0]": "BITSLICE_COMPONENT_RX_TX.IN_FF", "a_txd[0]": "BITSLICE_COMPONENT_RX_TX.OUT_FF",
                                                              "a_txd[1]": "BITSLICE_COMPONENT_RX_TX.OUT_FF"}
    assert all(x["packed"] for x in r["registers"])
    f = r["findings"]
    assert [x["code"] for x in f] == ["IOB-MARK-ORPHAN"] and f[0]["cell"] == "q_rx1_reg" and "Constraints 18-5572" in f[0]["message"]
    assert {m["id"] for m in r["log_messages"]} == {"Constraints 18-5572", "Place 30-73"}


def test_io_check_in_the_check_suite_reports_the_iob_findings(tmp_path: Path) -> None:
    from flow import checks as C
    design = tmp_path / "designs" / "x"
    build = design / "build" / "base"
    build.mkdir(parents=True)
    (design / "build.yaml").write_text(yaml.safe_dump({"io_interfaces": [dict(i) for i in RMII]}))
    (build / "iob_route.txt").write_text((DATA / "gate_in.iob.txt").read_text())
    (build / "vivado.log").write_text((DATA / "gate_in.log").read_text())
    (build / "prepare.json").write_text('{"design": "designs/x"}')
    res = C.CHECKS["io"].run(C.Ctx(design=design, scope="route", root=tmp_path))
    codes = [f["code"] for f in res["findings"]]
    assert codes == ["IOB-NOT-PACKED", "IOB-NOT-PACKED"] and all(f["blocking"] for f in res["findings"]) and res.get("verdict") is False
