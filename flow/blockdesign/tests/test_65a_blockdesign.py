"""Brief 65A: the block-design format, validator, automation, address editor and generator (pure Python, no simulator).

Each validation rule has at least one adversarial design that must trip it with its own code and a message that names
the culprit, and a near-miss that must not. The sample design (designs/b65a_axil_soc) must validate with exactly the
diagnostics expected of it, and its committed generated files must equal what the generator writes now.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from flow.blockdesign import addrmap, components as C, generate, graph, model as M

ROOT = Path(__file__).resolve().parents[3]
FIX = Path(__file__).parent / "fixtures"
SAMPLE = ROOT / "designs" / "b65a_axil_soc"


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setenv("FDA_BD_COMPONENTS", str(FIX / "components"))
    C.load.cache_clear()
    yield
    C.load.cache_clear()


def base() -> dict:
    """A small valid top design: shell, bridge, crossbar to one register-wrapped DDS and one window-wrapped analyser."""
    return {
        "schema": M.SCHEMA_ID, "name": "t", "part": "xc7a100tcsg324-1",
        "ports": [{"name": "CLK", "dir": "in", "kind": "clock", "freq_mhz": 100},
                  {"name": "RSTN", "dir": "in", "kind": "reset", "polarity": "low", "async": True},
                  {"name": "RX", "dir": "in", "async": True}, {"name": "TX", "dir": "out"}],
        "clocks": [{"name": "sys", "port": "CLK", "reset": "RSTN"}],
        "instances": {
            "shell": {"component": "test_shell"},
            "host": {"component": "bd_win_axil_master"},
            "dds": {"component": "dds_awg", "variant": "lut",
                    "axi_lite": {"registers": {"control": [{"name": "STEP", "port": "step"}, {"name": "WAVE", "port": "wave"},
                                                            {"name": "AMP", "port": "amp_shift"}, {"name": "DIV"}],
                                               "status": [{"name": "SAMPLE", "port": "sample"}],
                                               "tick": {"div_reg": "DIV", "to": "tick"}}}},
            "la": {"component": "logic_analyser", "axi_lite": {"window": "window"}},
        },
        "connections": [{"from": "RX", "to": "shell.uart_rx"}, {"from": "shell.uart_tx", "to": "TX"},
                        {"from": "shell.window", "to": "host.window"}, {"from": "dds.sample", "to": "la.sample"},
                        {"from": "dds.tick", "to": "la.sample_en"}],
        "interconnect": [{"name": "xbar", "masters": ["host.m_axil"], "slaves": ["dds.s_axil", "la.s_axil"]}],
        "address_map": {"base": 0x40000000, "ranges": [{"slave": "dds.s_axil"}, {"slave": "la.s_axil"}]},
    }


def run(tmp_path: Path, d: dict, files: dict | None = None) -> M.Elab:
    for name, text in (files or {}).items():
        (tmp_path / name).write_text(text if isinstance(text, str) else yaml.safe_dump(text))
    p = tmp_path / "blockdesign.yaml"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    return M.elaborate(p)


def codes(E: M.Elab, sev: str = "error") -> list[str]:
    return [d.code for d in E.all_diags() if d.severity == sev]


def msgs(E: M.Elab, code: str) -> str:
    return " | ".join(d.text() for d in E.all_diags() if d.code == code)


# ---------------------------------------------------------------------------------------------------- the base cases
def test_base_design_is_clean(tmp_path):
    E = run(tmp_path, base())
    assert codes(E) == [], [d.text() for d in E.all_diags()]
    assert codes(E, "warning") == []
    assert {b.name for b in E.boxes.values() if b.generated} == {"xbar", "rst_sync_sys"}   # both automations ran


def test_sample_design_diagnostics_exactly():
    E = M.elaborate(SAMPLE / "blockdesign.yaml")
    got = sorted((d.severity, d.code, d.where) for d in E.all_diags())
    assert got == [("info", "BD-OPEN-01", "tone/instances/fd"), ("warning", "BD-ADDR-02", "address_map (xbar)")], got


def test_sample_generated_files_match_the_generator():
    """The drift check: gen/ and build.yaml are exactly what the generator writes from blockdesign.yaml today."""
    assert generate.check(SAMPLE) == [], "run: python3 -m flow.blockdesign generate designs/b65a_axil_soc"


# ------------------------------------------------------------------------------------------------------- schema
def test_schema_unknown_key_names_its_path(tmp_path):
    d = base()
    d["instances"]["dds"]["paramz"] = {}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-SCHEMA"]
    assert "instances/dds" in msgs(E, "BD-SCHEMA") and "paramz" in msgs(E, "BD-SCHEMA")


def test_schema_component_and_design_both(tmp_path):
    d = base()
    d["instances"]["dds"]["design"] = "x.yaml"
    E = run(tmp_path, d)
    assert "BD-SCHEMA" in codes(E) and "exactly one" in msgs(E, "BD-SCHEMA")


def test_schema_file_is_valid_json_schema():
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(M.schema())


# --------------------------------------------------------------------------------------------- components, params
def test_unknown_component(tmp_path):
    d = base()
    d["instances"]["dds"]["component"] = "dds_awgg"
    E = run(tmp_path, d)
    assert "BD-COMP-01" in codes(E) and "dds_awgg" in msgs(E, "BD-COMP-01")


def test_unknown_variant(tmp_path):
    d = base()
    d["instances"]["dds"]["variant"] = "dsp"
    E = run(tmp_path, d)
    assert "BD-COMP-02" in codes(E) and "bram, lut" in msgs(E, "BD-COMP-02")


def test_unknown_parameter(tmp_path):
    d = base()
    d["instances"]["dds"]["params"] = {"PHASE_WIDTH": 32}
    E = run(tmp_path, d)
    assert "BD-PARAM-01" in codes(E) and "PHASE_WIDTH" in msgs(E, "BD-PARAM-01")


def test_parameter_outside_declared_space(tmp_path):
    d = base()
    d["instances"]["dds"]["params"] = {"LUT_W": 20}
    E = run(tmp_path, d)
    assert "BD-PARAM-01" in codes(E) and "LUT_W=20" in msgs(E, "BD-PARAM-01")


# ------------------------------------------------------------------------------------------- parameter propagation
def test_width_propagates_into_an_unset_parameter(tmp_path):
    d = base()
    d["instances"]["dds"]["params"] = {"OUT_W": 12}
    E = run(tmp_path, d)
    assert codes(E) == []
    la = E.boxes["la"]
    assert la.params["WIDTH"] == 12 and "propagated from dds.sample" in la.origin["WIDTH"]


def test_width_mismatch_with_a_set_parameter(tmp_path):
    d = base()
    d["instances"]["dds"]["params"] = {"OUT_W": 12}
    d["instances"]["la"]["params"] = {"WIDTH": 16}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-WIDTH-01"]
    t = msgs(E, "BD-WIDTH-01")
    assert "dds.sample gives 12 bits but la.sample takes 16" in t and "la.WIDTH=16 is set" in t


def test_propagated_width_outside_the_space(tmp_path):
    d = base()
    d["instances"]["dds"]["params"] = {"PHASE_W": 48, "OUT_W": 40}
    E = run(tmp_path, d)
    assert "BD-PARAM-01" in codes(E) and "WIDTH=40 (propagated from dds.sample" in msgs(E, "BD-PARAM-01")


def test_clock_frequency_propagates_to_derived_parameters(tmp_path):
    d = base()
    d["ports"][0]["freq_mhz"] = 50
    E = run(tmp_path, d)
    assert codes(E) == []
    sh = E.boxes["shell"]
    assert sh.params["CLKS_PER_BIT"] == 434 and sh.params["TIMEOUT_CYCLES"] == 50000
    assert "derived from the sys clock (50 MHz)" in sh.origin["CLKS_PER_BIT"]


def test_derived_parameter_contradicted(tmp_path):
    d = base()
    d["instances"]["shell"]["params"] = {"CLKS_PER_BIT": 500}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-02"]
    assert "CLKS_PER_BIT=500 is given, but the sys clock (100 MHz) gives CLKS_PER_BIT=868" in msgs(E, "BD-PARAM-02")


def test_axi4_id_width_mismatch_and_data_width(tmp_path):
    d = base()
    d["instances"]["m4"] = {"component": "axi4_mst", "params": {"ID_W": 6}}
    d["instances"]["s4"] = {"component": "axi4_slv", "params": {"ID_W": 4, "DATA_W": 64}}
    d["connections"].append({"from": "m4.m_axi", "to": "s4.s_axi"})
    E = run(tmp_path, d)
    t = msgs(E, "BD-WIDTH-02")
    assert "6-bit IDs" in t and "32-bit data but s4.s_axi has 64-bit data" in t


def test_axi4_link_ok_and_address_width_note(tmp_path):
    d = base()
    d["instances"]["m4"] = {"component": "axi4_mst", "params": {"ID_W": 4}}
    d["instances"]["s4"] = {"component": "axi4_slv", "params": {"ID_W": 6}}
    d["connections"].append({"from": "m4.m_axi", "to": "s4.s_axi"})
    E = run(tmp_path, d)
    assert codes(E) == [] and any(L.kind == "axi4" and L.slave == ("s4", "s_axi") for L in E.links)


# ----------------------------------------------------------------------------------------------- interface types
def test_interface_type_mismatch(tmp_path):
    d = base()
    d["instances"]["src"] = {"component": "axis_src"}
    d["connections"].append({"from": "src.m_axis", "to": "la.s_axil"})
    E = run(tmp_path, d)
    assert "BD-IF-01" in codes(E) and "src.m_axis is axis but la.s_axil is axi4lite" in msgs(E, "BD-IF-01")


def test_master_to_master(tmp_path):
    d = base()
    d["instances"]["m4"] = {"component": "axi4_mst"}
    d["instances"]["m5"] = {"component": "axi4_mst"}
    d["connections"].append({"from": "m4.m_axi", "to": "m5.m_axi"})
    E = run(tmp_path, d)
    assert "BD-IF-02" in codes(E) and "both masters" in msgs(E, "BD-IF-02")


def test_interface_to_port(tmp_path):
    d = base()
    d["connections"].append({"from": "shell.window", "to": "la.sample"})
    E = run(tmp_path, d)
    assert "BD-IF-03" in codes(E)


def test_interconnect_refuses_other_bus_types(tmp_path):
    d = base()
    d["instances"]["s4"] = {"component": "axi4_slv"}
    d["interconnect"][0]["slaves"].append("s4.s_axi")
    E = run(tmp_path, d)
    assert "BD-IF-01" in codes(E) and "s4.s_axi is axi4" in msgs(E, "BD-IF-01")


def test_interrupt_into_a_data_input(tmp_path):
    d = base()
    d["instances"]["src"] = {"component": "axis_src"}
    d["instances"]["snk"] = {"component": "axis_snk"}
    d["connections"] += [{"from": "src.m_axis", "to": "snk.s_axis"}, {"from": "src.irq", "to": "snk.level", "to_bits": [0, 0]},
                         {"const": 0, "to": "snk.level", "to_bits": [7, 1]}, {"from": "dds.tick", "to": "snk.ext_irq"}]
    E = run(tmp_path, d)
    t = msgs(E, "BD-IF-01")
    assert "interrupt src.irq drives snk.level" in t and "snk.ext_irq is an interrupt input, driven by dds.tick" in t


def test_axis_link_and_active_low_reset_automation(tmp_path):
    d = base()
    d["instances"]["src"] = {"component": "axis_src"}
    d["instances"]["snk"] = {"component": "axis_snk"}
    d["connections"] += [{"from": "src.m_axis", "to": "snk.s_axis"}, {"from": "src.irq", "to": "snk.ext_irq"},
                         {"const": 3, "to": "snk.level"}]
    E = run(tmp_path, d)
    assert codes(E) == [], [x.text() for x in E.all_diags()]
    rs = [s for s in E.segs if s.dst == ("box", "snk", "rst_n")]
    assert len(rs) == 1 and rs[0].invert and rs[0].src == ("box", "rst_sync_sys", "rst")


# --------------------------------------------------------------------------------------------------- unconnected
def test_unconnected_required_input(tmp_path):
    d = base()
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    E = run(tmp_path, d)
    assert codes(E) == ["BD-UNCONN-01"] and "la.sample_en (1 bits): all not driven" in msgs(E, "BD-UNCONN-01")


def test_partly_driven_input(tmp_path):
    d = base()
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample"]
    d["connections"].append({"from": "dds.sample", "bits": [7, 0], "to": "la.sample", "to_bits": [7, 0]})
    E = run(tmp_path, d)
    assert "BD-UNCONN-01" in codes(E) and "bits 15:8 not driven" in msgs(E, "BD-UNCONN-01")


def test_unconnected_bus_interface(tmp_path):
    d = base()
    d["interconnect"][0]["slaves"] = ["dds.s_axil"]
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil"}]
    E = run(tmp_path, d)
    assert codes(E) == ["BD-UNCONN-02"] and "la.s_axil is not connected" in msgs(E, "BD-UNCONN-02")


def test_undriven_design_output(tmp_path):
    d = base()
    d["ports"].append({"name": "LED", "dir": "out", "width": 4})
    d["connections"].append({"from": "dds.sample", "bits": [15, 14], "to": "LED", "to_bits": [3, 2]})
    E = run(tmp_path, d)
    assert codes(E) == ["BD-UNCONN-03"] and "LED: bits 1:0 not driven" in msgs(E, "BD-UNCONN-03")


def test_unused_input_and_open_output_are_reported_not_errors(tmp_path):
    d = base()
    d["ports"].append({"name": "SW", "dir": "in", "async": True})
    E = run(tmp_path, d)
    assert codes(E) == [] and codes(E, "warning") == ["BD-OPEN-02"] and "SW is not used" in msgs(E, "BD-OPEN-02")
    assert "dds.phase_o is left open" in msgs(E, "BD-OPEN-01")


# ------------------------------------------------------------------------------------------------ multiple drivers
def test_two_drivers_on_one_input(tmp_path):
    d = base()
    d["connections"].append({"const": 1, "to": "la.sample_en"})
    E = run(tmp_path, d)
    assert codes(E) == ["BD-DRV-01"] and "bit 0 of la.sample_en has two drivers: dds.tick" in msgs(E, "BD-DRV-01")


def test_overlapping_slices(tmp_path):
    d = base()
    d["ports"].append({"name": "LED", "dir": "out", "width": 8})
    d["connections"] += [{"from": "dds.sample", "bits": [15, 10], "to": "LED", "to_bits": [7, 2]},
                         {"const": 0, "to": "LED", "to_bits": [2, 0]}]
    E = run(tmp_path, d)
    assert codes(E) == ["BD-DRV-01"] and "bit 2 of LED" in msgs(E, "BD-DRV-01")


def test_driving_an_output_and_reading_an_input(tmp_path):
    d = base()
    d["connections"] += [{"const": 0, "to": "dds.sample"}, {"from": "la.sample", "to": "TX"}]
    E = run(tmp_path, d)
    t = msgs(E, "BD-DRV-02")
    assert "dds.sample is an output of dds; it cannot be driven" in t and "la.sample is an input of la" in t


def test_slave_with_two_masters(tmp_path):
    d = base()
    d["instances"]["m4"] = {"component": "axi4_mst"}
    d["instances"]["m5"] = {"component": "axi4_mst"}
    d["instances"]["s4"] = {"component": "axi4_slv"}
    d["connections"] += [{"from": "m4.m_axi", "to": "s4.s_axi"}, {"from": "m5.m_axi", "to": "s4.s_axi"}]
    E = run(tmp_path, d)
    assert "BD-DRV-01" in codes(E) and "s4.s_axi has 2 masters" in msgs(E, "BD-DRV-01")


# ----------------------------------------------------------------------------------- clock and reset crossings
def two_domains() -> dict:
    d = base()
    d["ports"].append({"name": "CLK2", "dir": "in", "kind": "clock", "freq_mhz": 75})
    d["clocks"].append({"name": "aux", "port": "CLK2", "reset": "RSTN"})
    for n in d["instances"]:
        d["instances"][n]["domain"] = "sys"
    return d


def test_data_crossing_without_synchroniser(tmp_path):
    d = two_domains()
    d["instances"]["fd"] = {"component": "freq_duty_counter", "domain": "aux"}
    d["instances"]["d2"] = {"component": "dds_awg", "domain": "aux"}
    d["connections"] += [{"from": "dds.sample", "bits": [15, 15], "to": "fd.sig"},       # fd.sig has its own synchroniser
                         {"from": "dds.tick", "to": "d2.tick"}, {"const": 7, "to": "d2.step"}, {"const": 0, "to": "d2.wave"},
                         {"const": 0, "to": "d2.amp_shift"}]
    E = run(tmp_path, d)
    assert codes(E) == ["BD-CDC-01"], [x.text() for x in E.all_diags()]
    assert "dds.tick (domain sys) drives d2.tick (domain aux) with no synchroniser" in msgs(E, "BD-CDC-01")
    xs = graph.crossings(E)
    safe = [x for x in xs if x["to"] == "fd.sig"]
    assert safe and safe[0]["safe"] and "own synchroniser" in safe[0]["synchroniser"]


def test_async_input_without_synchroniser(tmp_path):
    d = base()
    d["ports"].append({"name": "BTN", "dir": "in", "async": True})
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    d["connections"].append({"from": "BTN", "to": "la.sample_en"})
    E = run(tmp_path, d)
    assert codes(E) == ["BD-CDC-02"] and "BTN is asynchronous and drives la.sample_en" in msgs(E, "BD-CDC-02")


def test_async_input_through_sync2_is_fine(tmp_path):
    d = base()
    d["ports"].append({"name": "BTN", "dir": "in", "async": True})
    d["instances"]["sy"] = {"component": "sync2"}
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    d["connections"] += [{"from": "BTN", "to": "sy.d"}, {"from": "sy.q", "to": "la.sample_en"}]
    E = run(tmp_path, d)
    assert codes(E) == []


def test_bus_link_across_domains(tmp_path):
    d = two_domains()
    d["instances"]["la"]["domain"] = "aux"
    E = run(tmp_path, d)
    assert "BD-CDC-03" in codes(E) and "crosses clock domains" in msgs(E, "BD-CDC-03")


def test_reset_from_another_domain(tmp_path):
    d = two_domains()
    d["instances"]["fd"] = {"component": "freq_duty_counter", "domain": "aux"}
    d["connections"] += [{"from": "dds.tick", "to": "fd.sig"}, {"from": "dds.tick", "to": "fd.rst"}]
    E = run(tmp_path, d)
    assert "BD-CDC-01" in codes(E) or "BD-RST-02" in codes(E)
    assert "fd.rst (domain aux)" in msgs(E, "BD-CDC-01") + msgs(E, "BD-RST-02")


def test_reset_polarity_mismatch(tmp_path):
    d = base()
    d["instances"]["snk"] = {"component": "axis_snk"}
    d["instances"]["src"] = {"component": "axis_src"}
    d["connections"] += [{"from": "src.m_axis", "to": "snk.s_axis"}, {"from": "src.irq", "to": "snk.ext_irq"},
                         {"const": 0, "to": "snk.level"}, {"from": "rst_sync_sys.rst", "to": "snk.rst_n"}]
    E = run(tmp_path, d)
    # the reset synchroniser is made by automation after the connections are read: naming it is an unknown endpoint
    assert "BD-REF-01" in codes(E)
    d["connections"][-1] = {"from": "RSTN", "to": "snk.rst_n", "invert": True}
    E = run(tmp_path, d)
    assert "BD-RST-01" in codes(E) and "RSTN is active low, snk.rst_n is active low" in msgs(E, "BD-RST-01")


def test_clock_input_driven_by_data(tmp_path):
    d = base()
    d["connections"].append({"from": "dds.tick", "to": "la.clk"})
    E = run(tmp_path, d)
    assert "BD-CLK-01" in codes(E) and "la.clk is a clock input, driven by dds.tick" in msgs(E, "BD-CLK-01")


def test_ambiguous_domain(tmp_path):
    d = two_domains()
    del d["instances"]["la"]["domain"]
    E = run(tmp_path, d)
    assert "BD-CLK-03" in codes(E) and "instances/la" in msgs(E, "BD-CLK-03")


# ---------------------------------------------------------------------------------------------- the address map
def test_auto_assignment_and_alignment(tmp_path):
    d = base()
    d["address_map"] = {"base": 0x40000800, "ranges": [{"slave": "la.s_axil", "size": 0x2000}]}
    E = run(tmp_path, d)
    assert codes(E) == []
    r = {x.slave: x for x in E.ranges}
    assert r["la.s_axil"].base == 0x40002000 and r["dds.s_axil"].base == 0x40001000   # aligned up, listed first


def test_overlap(tmp_path):
    d = base()
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil", "base": 0x40000000, "size": 0x2000},
                                  {"slave": "la.s_axil", "base": 0x40001000}]
    E = run(tmp_path, d)
    assert codes(E) == ["BD-ADDR-01"] and "la.s_axil [0x40001000, 0x40001fff] overlaps dds.s_axil" in msgs(E, "BD-ADDR-01")


def test_misaligned_base(tmp_path):
    d = base()
    d["address_map"]["ranges"][0]["base"] = 0x40000800
    E = run(tmp_path, d)
    assert "BD-ADDR-03" in codes(E) and "use 0x40000000 or 0x40001000" in msgs(E, "BD-ADDR-03")


def test_hole_is_a_warning(tmp_path):
    d = base()
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil", "base": 0x40000000}, {"slave": "la.s_axil", "base": 0x40008000}]
    E = run(tmp_path, d)
    assert codes(E) == [] and codes(E, "warning") == ["BD-ADDR-02"]
    assert E.holes == [{"xbar": "xbar", "base": 0x40001000, "size": 0x7000}]


def test_outside_the_address_space(tmp_path):
    d = base()
    d["address_map"]["ranges"][0]["base"] = 0xFFFFF000
    d["address_map"]["ranges"][0]["size"] = 0x2000
    E = run(tmp_path, d)
    assert "BD-ADDR-04" in codes(E) or "BD-ADDR-03" in codes(E)


def test_range_for_a_slave_on_no_interconnect(tmp_path):
    d = base()
    d["address_map"]["ranges"].append({"slave": "shell.window"})
    E = run(tmp_path, d)
    assert "BD-ADDR-05" in codes(E)


def test_size_not_a_power_of_two_and_too_small(tmp_path):
    d = base()
    d["address_map"]["ranges"][0]["size"] = 3000
    E = run(tmp_path, d)
    assert "BD-ADDR-06" in codes(E)
    d["address_map"]["ranges"][0]["size"] = 1024
    E = run(tmp_path, d)
    assert codes(E) == [] and "BD-ADDR-07" in codes(E, "warning")


def test_exports_header_and_doc(tmp_path):
    E = run(tmp_path, base())
    h = addrmap.c_header(E)
    assert "#define T_DDS_S_AXIL_BASE 0x40000000u" in h and "#define T_DDS_S_AXIL_STEP_OFFSET 0x000u" in h
    assert "#define T_LA_S_AXIL_BASE 0x40001000u" in h and "#define T_DDS_S_AXIL_SAMPLE_OFFSET 0x010u" in h
    md = addrmap.markdown(E)
    assert "| `dds.s_axil` | `0x40000000` | `0x40000FFF` | 4 KB | by the address editor |" in md


# --------------------------------------------------------------------------------------------------- hierarchy
def test_hierarchy_exports_and_inner_errors_are_prefixed(tmp_path):
    sub = {"schema": M.SCHEMA_ID, "name": "h", "kind": "hierarchy", "ports": [{"name": "y", "dir": "out", "width": 16}],
           "interfaces": [{"name": "s", "export": "d.s_axil"}],
           "instances": {"d": copy.deepcopy(base()["instances"]["dds"])},
           "connections": [{"from": "d.sample", "to": "y"}]}
    d = base()
    del d["instances"]["dds"]
    d["instances"]["hh"] = {"design": "h.yaml"}
    d["connections"] = [c for c in d["connections"] if not c.get("from", "").startswith("dds")]
    d["connections"] += [{"from": "hh.y", "to": "la.sample"}, {"const": 1, "to": "la.sample_en"}]
    d["interconnect"][0]["slaves"] = ["hh.s", "la.s_axil"]
    d["address_map"]["ranges"] = [{"slave": "hh.s"}, {"slave": "la.s_axil"}]
    E = run(tmp_path, d, {"h.yaml": sub})
    assert codes(E) == [], [x.text() for x in E.all_diags()]
    assert E.boxes["hh"].module == "t_h" and E.boxes["hh"].sub.boxes["d"].module == "t_h_d_wrap"
    sub["connections"] = []
    E = run(tmp_path, d, {"h.yaml": sub})
    assert "hh/ports/y" in msgs(E, "BD-UNCONN-03")


def test_hierarchy_recursion(tmp_path):
    sub = {"schema": M.SCHEMA_ID, "name": "h", "kind": "hierarchy", "instances": {"again": {"design": "h.yaml"}}}
    d = base()
    d["instances"]["hh"] = {"design": "h.yaml"}
    E = run(tmp_path, d, {"h.yaml": sub})
    assert "BD-HIER-02" in codes(E)


# ---------------------------------------------------------------------------------------------------- generation
def test_generator_refuses_a_design_with_errors(tmp_path):
    d = base()
    d["connections"].append({"const": 1, "to": "la.sample_en"})
    run(tmp_path, d)
    with pytest.raises(ValueError, match="BD-DRV-01"):
        generate.generate(tmp_path)


def test_manifest_and_graph_of_the_sample():
    man = json.loads((SAMPLE / "gen" / "manifest.json").read_text())
    assert man["summary"] == {"errors": 0, "warnings": 1, "info": 1}
    comps = {c["path"]: c for c in man["components"]}
    assert comps["tone/dds"]["variant"] == "bram" and comps["xbar"]["generated"] and comps["rst_sync_sys"]["generated"]
    g = json.loads((SAMPLE / "gen" / "graph.json").read_text())
    blocks = {b["id"]: b for lv in g["levels"].values() for b in lv["blocks"]}
    assert blocks["tone/dds"]["rtl_path"] == "u_tone/u_dds"
    assert blocks["tone/dds"]["cost"]["measured"]["exact"] is True        # dds_awg bram measured at this very point
    assert any(x["to"] == "rst_sync_sys.rst_n_async" and x["safe"] for x in g["crossings"])
    assert [r["slave"] for r in g["address_map"]["ranges"]] == ["tone.s_dds", "tone.s_fd", "la.s_axil"]


def test_cli_validate_exit_codes(tmp_path, capsys):
    from flow.blockdesign import __main__ as cli
    assert cli.main(["validate", str(SAMPLE)]) == 0
    d = base()
    d["connections"].append({"const": 1, "to": "la.sample_en"})
    run(tmp_path, d)
    assert cli.main(["validate", str(tmp_path)]) == 1
    assert "BD-DRV-01" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------------------ viewer
def test_viewer_draws_every_block_and_fits_its_text():
    from flow.blockdesign import viewer
    g = viewer.load_graph(SAMPLE)
    html = viewer.body(g)
    for lv in g["levels"].values():
        for b in lv["blocks"]:
            assert f'data-id="{b["id"]}"' in html, b["id"]
    for key in g["levels"]:
        nodes, _ = viewer._nodes(g, key)
        for n in nodes:
            for t, cls in n["lines"]:
                px = (7.3 if cls == "bdn" else 6.7) * len(t)          # monospace at 12 px (names) and 11 px
                assert px <= viewer.BW - 12, f"{n['id']}: {t!r} is too long for a block"


def test_hiercheck_catches_a_missing_and_an_extra_block():
    from flow.blockdesign import hiercheck
    g = json.loads((SAMPLE / "gen" / "graph.json").read_text())
    ann = json.loads((ROOT / "results" / "blockdesign" / "b65a_axil_soc" / "build.json").read_text())
    assert hiercheck.check(g, ann["hier"])["pass"]
    lost = [h for h in ann["hier"] if not h["path"].startswith("u_xbar")]
    r = hiercheck.check(g, lost)
    assert not r["pass"] and any("u_xbar (axil_xbar) is in the diagram but not" in m for m in r["mismatches"])
    extra = ann["hier"] + [{"path": "u_tone/u_spare", "module": "sync2", "ref": "sync2"}]
    assert any("u_tone/u_spare" in m for m in hiercheck.check(g, extra)["mismatches"])
    renamed = [dict(h, module="fir") if h["path"] == "u_tone/u_dds/u_ip" else h for h in ann["hier"]]
    assert any("the diagram says dds_awg, the netlist has fir" in m for m in hiercheck.check(g, renamed)["mismatches"])


@pytest.mark.skipif("FDA_E2E" not in __import__("os").environ, reason="browser test: set FDA_E2E=1 (a heavy job; take a slot)")
def test_viewer_in_a_browser(tmp_path):
    import subprocess
    from flow.blockdesign import viewer
    page = viewer.write(SAMPLE, tmp_path / "viewer.html")
    site = ROOT / "site" / "public" / "blockdesign" / "b65a_axil_soc.html"
    r = subprocess.run(["node", str(Path(__file__).with_name("e2e_viewer.js")), f"{page},{site}"], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
