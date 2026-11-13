"""Adversarial block designs from the independent review of the block-design tools, adopted as regression tests.

Each test is a design that a careless validator gets wrong: a second driver on a bus port by name, a synchroniser
hidden inside a hierarchy, a multi-bit bus through a bit-wise synchroniser, a second clock input, a hand-wired clock
from another domain, a parameter given as a Verilog literal, a long width-propagation chain, address-map edges."""
import copy
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "flow/blockdesign/tests"))
import test_65a_blockdesign as T  # noqa: E402
from flow.blockdesign import model as M, generate  # noqa: E402

stubs = T.stubs
base, run, codes, msgs, two_domains = T.base, T.run, T.codes, T.msgs, T.two_domains


def show(E):
    return [d.text() for d in E.all_diags()]


# ------------------------------------------------------------------ width propagation through hierarchy
def hier_sample(width=16, inner_outw=None):
    sub = {"schema": M.SCHEMA_ID, "name": "h", "kind": "hierarchy",
           "ports": [{"name": "y", "dir": "out", "width": width}],
           "interfaces": [{"name": "s", "export": "d.s_axil"}],
           "instances": {"d": copy.deepcopy(base()["instances"]["dds"])},
           "connections": [{"from": "d.sample", "to": "y"}]}
    if inner_outw:
        sub["instances"]["d"]["params"] = {"OUT_W": inner_outw}
    d = base()
    del d["instances"]["dds"]
    d["instances"]["hh"] = {"design": "h.yaml"}
    d["connections"] = [c for c in d["connections"] if not c.get("from", "").startswith("dds")]
    d["connections"] += [{"from": "hh.y", "to": "la.sample"}, {"const": 1, "to": "la.sample_en"}]
    d["interconnect"][0]["slaves"] = ["hh.s", "la.s_axil"]
    d["address_map"]["ranges"] = [{"slave": "hh.s"}, {"slave": "la.s_axil"}]
    return d, sub


def test_width_hier_boundary_mismatch_inside(tmp_path):
    d, sub = hier_sample(width=12)               # dds.sample is 16 bits by default, the boundary says 12
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert "BD-WIDTH-01" in codes(E)


def test_width_hier_propagates_out_to_parent(tmp_path):
    d, sub = hier_sample(width=12, inner_outw=12)
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert codes(E) == [] and E.boxes["la"].params["WIDTH"] == 12


def test_width_hier_parent_set_contradicts(tmp_path):
    d, sub = hier_sample(width=12, inner_outw=12)
    d["instances"]["la"]["params"] = {"WIDTH": 16}
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert codes(E) == ["BD-WIDTH-01"]


def test_width_long_chain_propagation(tmp_path):
    """A chain of sync2 (q follows d, both [WIDTH-1:0]) longer than the 4 propagation passes."""
    d = base()
    d["instances"]["dds"]["params"] = {"OUT_W": 12}
    n = 6
    for i in range(n):
        d["instances"][f"s{i}"] = {"component": "sync2"}
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample"]
    # wire them in reverse order of listing so each pass moves one step only
    chain = [("dds.sample", "s0.d")] + [(f"s{i}.q", f"s{i+1}.d") for i in range(n - 1)] + [(f"s{n-1}.q", "la.sample")]
    for fr, to in reversed(chain):
        d["connections"].append({"from": fr, "to": to})
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E) == [], "a long chain should propagate (or say why not)"


# ------------------------------------------------------------------ address map
@pytest.mark.parametrize("b1,s1,b2,s2,expect", [
    (0x40000000, 0x1000, 0x40001000, 0x1000, []),                 # touching: no overlap
    (0x40000000, 0x2000, 0x40001000, 0x1000, ["BD-ADDR-01"]),     # inside
    (0x40001000, 0x1000, 0x40000000, 0x2000, ["BD-ADDR-01"]),     # other order
    (0x40000000, 0x1000, 0x40000FFC, 0x4, ["BD-ADDR-01"]),         # last word of the first range
])
def test_addr_boundaries(tmp_path, b1, s1, b2, s2, expect):
    d = base()
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil", "base": b1, "size": s1}, {"slave": "la.s_axil", "base": b2, "size": s2}]
    E = run(tmp_path, d)
    print(show(E))
    assert [c for c in codes(E) if c == "BD-ADDR-01"] == expect


def test_addr_misaligned_and_overlap_both(tmp_path):
    d = base()
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil", "base": 0x40000000, "size": 0x1000},
                                  {"slave": "la.s_axil", "base": 0x40000800, "size": 0x2000}]
    E = run(tmp_path, d)
    print(show(E))
    assert "BD-ADDR-03" in codes(E) and "BD-ADDR-01" in codes(E)


def test_addr_auto_placed_after_misaligned_fixed(tmp_path):
    """A misaligned fixed range (error) - auto placement still must not overlap it."""
    d = base()
    d["address_map"] = {"base": 0x40000000, "ranges": [{"slave": "la.s_axil", "base": 0x40000800, "size": 0x1000}]}
    E = run(tmp_path, d)
    r = {x.slave: x for x in E.ranges}
    print(show(E), {k: hex(v.base) for k, v in r.items()})
    a, b = r["dds.s_axil"], r["la.s_axil"]
    assert not (a.base < b.base + b.size and b.base < a.base + a.size)


def test_addr_size_below_wrapper_decode(tmp_path):
    d = base()
    d["address_map"]["ranges"][0]["size"] = 0x400
    E = run(tmp_path, d)
    print(show(E))
    assert "BD-ADDR-07" in codes(E, "warning")


def test_addr_auto_wraps_past_space(tmp_path):
    d = base()
    d["address_map"] = {"base": 0xFFFFF000, "ranges": []}
    E = run(tmp_path, d)
    print(show(E), [(x.slave, hex(x.base)) for x in E.ranges])
    assert "BD-ADDR-04" in codes(E)


def test_addr_hole_below_first_range_reported(tmp_path):
    """A hole between the map base and the first range is not between ranges: report or not, but say."""
    d = base()
    d["address_map"]["ranges"] = [{"slave": "dds.s_axil", "base": 0x40004000}, {"slave": "la.s_axil", "base": 0x40005000}]
    E = run(tmp_path, d)
    print(show(E), E.holes)


# ------------------------------------------------------------------ CDC
def test_cdc_async_input_into_hierarchy_with_sync_inside(tmp_path):
    """BTN (async) into a hierarchy whose port goes straight into a sync2: safe, but is it recognised?"""
    sub = {"schema": M.SCHEMA_ID, "name": "h", "kind": "hierarchy",
           "ports": [{"name": "btn", "dir": "in", "async": True}, {"name": "q", "dir": "out"}],
           "instances": {"sy": {"component": "sync2"}},
           "connections": [{"from": "btn", "to": "sy.d"}, {"from": "sy.q", "to": "q"}]}
    d = base()
    d["ports"].append({"name": "BTN", "dir": "in", "async": True})
    d["instances"]["hh"] = {"design": "h.yaml"}
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    d["connections"] += [{"from": "BTN", "to": "hh.btn"}, {"from": "hh.q", "to": "la.sample_en"}]
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert codes(E) == [], "false alarm: the synchroniser is inside the hierarchy"


def test_cdc_async_input_into_hierarchy_without_sync(tmp_path):
    """BTN (async) into a hierarchy port declared async that feeds a plain data input inside: must be an error."""
    sub = {"schema": M.SCHEMA_ID, "name": "h", "kind": "hierarchy",
           "ports": [{"name": "btn", "dir": "in", "async": True}, {"name": "q", "dir": "out"}],
           "instances": {"sy": {"component": "sync2"}},
           "connections": [{"from": "btn", "to": "sy.rst"}, {"const": 0, "to": "sy.d"}, {"from": "sy.q", "to": "q"}]}
    d = base()
    d["ports"].append({"name": "BTN", "dir": "in", "async": True})
    d["instances"]["hh"] = {"design": "h.yaml"}
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    d["connections"] += [{"from": "BTN", "to": "hh.btn"}, {"from": "hh.q", "to": "la.sample_en"}]
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert any(c.startswith("BD-CDC") or c.startswith("BD-RST") for c in codes(E))


def test_cdc_multibit_bus_through_sync2(tmp_path):
    """A 16-bit sample from sys crosses into aux through sync2 (WIDTH propagated to 16): bit-wise synchroniser on a bus."""
    d = two_domains()
    d["instances"]["sy"] = {"component": "sync2", "domain": "aux"}
    d["instances"]["la2"] = {"component": "logic_analyser", "domain": "aux", "params": {"ADDR_W": 8}}
    d["connections"] += [{"from": "dds.sample", "to": "sy.d"}, {"from": "sy.q", "to": "la2.sample"},
                         {"const": 1, "to": "la2.sample_en"}, {"const": 0, "to": "la2.win_addr"}, {"const": 0, "to": "la2.win_wr"},
                         {"const": 0, "to": "la2.win_rd"}, {"const": 0, "to": "la2.win_wdata"}]
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E) == ["BD-CDC-04"], show(E)
    assert "16 bits of dds.sample (domain sys)" in msgs(E, "BD-CDC-04")


def test_cdc_bus_through_sync2_bit_by_bit_is_accepted(tmp_path):
    """Independent level bits, each connected on its own, may use the bit-wise synchroniser."""
    d = two_domains()
    d["instances"]["sy"] = {"component": "sync2", "domain": "aux", "params": {"WIDTH": 2}}
    d["instances"]["la2"] = {"component": "logic_analyser", "domain": "aux", "params": {"ADDR_W": 8, "WIDTH": 2}}
    d["connections"] += [{"from": "dds.sample", "bits": [0, 0], "to": "sy.d", "to_bits": [0, 0]},
                         {"from": "dds.sample", "bits": [1, 1], "to": "sy.d", "to_bits": [1, 1]},
                         {"from": "sy.q", "to": "la2.sample"},
                         {"const": 1, "to": "la2.sample_en"}, {"const": 0, "to": "la2.win_addr"}, {"const": 0, "to": "la2.win_wr"},
                         {"const": 0, "to": "la2.win_rd"}, {"const": 0, "to": "la2.win_wdata"}]
    E = run(tmp_path, d)
    assert "BD-CDC-04" not in codes(E) + codes(E, "warning"), show(E)


def test_cdc_second_clock_input_silently_tied(tmp_path):
    """A component with second clock inputs (eth_mac_rgmii clk90, rgmii_rx_clk) left unconnected: only its first clock
    is tied, and each other clock is reported as unconnected."""
    d = base()
    d["instances"]["mac"] = {"component": "eth_mac_rgmii"}
    E = run(tmp_path, d)
    segs = [s for s in E.segs if s.dst[1] == "mac" and s.auto == "clock"]
    assert [s.dst[2] for s in segs] == ["clk"]
    un = msgs(E, "BD-UNCONN-01")
    assert "mac.clk90" in un and "mac.rgmii_rx_clk" in un and "second clock input" in un


def test_cdc_second_clock_wired_by_hand_is_accepted(tmp_path):
    d = base()
    d["ports"].append({"name": "CLK90", "dir": "in", "kind": "clock", "freq_mhz": 100})
    d["instances"]["mac"] = {"component": "eth_mac_rgmii"}
    d["connections"].append({"from": "CLK90", "to": "mac.clk90"})
    E = run(tmp_path, d)
    assert "mac.clk90" not in msgs(E, "BD-UNCONN-01") and "BD-CLK-02" not in codes(E)


def test_cdc_hand_wired_clock_from_another_domain(tmp_path):
    """d2 says domain sys but is clocked by CLK2 (aux): refused, so the sys-to-aux crossing cannot hide."""
    d = two_domains()
    d["instances"]["d2"] = {"component": "dds_awg", "domain": "sys"}
    d["connections"] += [{"from": "CLK2", "to": "d2.clk"}, {"from": "dds.tick", "to": "d2.tick"}, {"const": 7, "to": "d2.step"},
                         {"const": 0, "to": "d2.wave"}, {"const": 0, "to": "d2.amp_shift"}]
    E = run(tmp_path, d)
    assert "BD-CLK-02" in codes(E) and "the clock of domain aux" in msgs(E, "BD-CLK-02"), show(E)


def test_cdc_hand_wired_clock_of_own_domain_is_fine(tmp_path):
    d = two_domains()
    d["instances"]["d2"] = {"component": "dds_awg", "domain": "aux"}
    d["connections"] += [{"from": "CLK2", "to": "d2.clk"}, {"const": 1, "to": "d2.tick"}, {"const": 7, "to": "d2.step"},
                         {"const": 0, "to": "d2.wave"}, {"const": 0, "to": "d2.amp_shift"}]
    E = run(tmp_path, d)
    assert codes(E) == [], show(E)


# ------------------------------------------------------------------ multiple drivers
def test_double_driver_iface_port_and_link(tmp_path):
    """la.s_axil is on the crossbar; a const also drives one of its ports by name: refused, never dropped."""
    d = base()
    d["connections"].append({"const": 0, "to": "la.s_axil_awvalid"})
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E) == ["BD-IF-03"] and "la.s_axil_awvalid belongs to the bus interface la.s_axil" in msgs(E, "BD-IF-03")


def test_bus_port_read_by_name_refused(tmp_path):
    d = base()
    d["connections"] = [c for c in d["connections"] if c.get("to") != "la.sample_en"]
    d["connections"].append({"from": "la.s_axil_awready", "to": "la.sample_en"})
    E = run(tmp_path, d)
    assert codes(E) == ["BD-IF-03"], show(E)


def test_double_driver_through_hierarchy_export(tmp_path):
    d, sub = hier_sample()
    d["connections"].append({"const": 0, "to": "hh.s_awvalid"})
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert codes(E) == ["BD-IF-03"] and "hh.s_awvalid belongs to the bus interface hh.s" in msgs(E, "BD-IF-03")


def test_double_driver_inside_hierarchy_output(tmp_path):
    d, sub = hier_sample()
    sub["connections"].append({"const": 0, "to": "y", "to_bits": [3, 0]})
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert "BD-DRV-01" in codes(E)


def test_hierarchy_used_twice_drives_same_parent_input(tmp_path):
    d, sub = hier_sample()
    d["instances"]["h2"] = {"design": "h.yaml"}
    d["interconnect"][0]["slaves"].append("h2.s")
    d["connections"].append({"from": "h2.y", "to": "la.sample"})
    E = run(tmp_path, d, {"h.yaml": sub})
    print(show(E))
    assert "BD-DRV-01" in codes(E)


# ------------------------------------------------------------------ interface roles
def test_role_swap_on_interconnect(tmp_path):
    d = base()
    d["interconnect"][0]["masters"] = ["la.s_axil"]
    d["interconnect"][0]["slaves"] = ["host.m_axil", "dds.s_axil"]
    E = run(tmp_path, d)
    print(show(E))
    assert "BD-IF-02" in codes(E)


def test_role_slave_to_master_reversed_text(tmp_path):
    """Connection written slave -> master: legal (the model orders it)."""
    d = base()
    d["connections"] = [c for c in d["connections"] if c.get("from") != "shell.window"]
    d["connections"].append({"from": "host.window", "to": "shell.window"})
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E) == []


def test_role_window_slave_to_slave(tmp_path):
    d = base()
    d["connections"].append({"from": "host.window", "to": "la.window"})
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E)          # la.window is consumed by its wrapper: unknown endpoint, or slave-to-slave


def test_hierarchy_export_of_master_used_as_slave(tmp_path):
    sub = {"schema": M.SCHEMA_ID, "name": "hm", "kind": "hierarchy",
           "interfaces": [{"name": "m", "export": "b.m_axil"}, {"name": "w", "export": "b.window"}],
           "instances": {"b": {"component": "bd_win_axil_master"}}}
    d = base()
    d["instances"]["hm"] = {"design": "hm.yaml"}
    d["interconnect"][0]["slaves"].append("hm.m")
    d["connections"].append({"from": "hm.w", "to": "la.sample"})
    E = run(tmp_path, d, {"hm.yaml": sub})
    print(show(E))
    assert "BD-IF-02" in codes(E)


# ------------------------------------------------------------------ parameter expressions
def test_param_expression_clog2_given_as_string(tmp_path):
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": "$clog2(256)"}
    E = run(tmp_path, d)
    assert codes(E) == [] and E.boxes["la"].params["ADDR_W"] == 8


def test_param_hex_string(tmp_path):
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": "8'h8"}
    E = run(tmp_path, d)
    assert codes(E) == [] and E.boxes["la"].params["ADDR_W"] == 8


def test_param_hex_string_out_of_range(tmp_path):
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": "8'hff"}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-01"] and "ADDR_W=255" in msgs(E, "BD-PARAM-01")


def test_param_string_that_is_not_a_number(tmp_path):
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": "eight"}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-01"] and "not an integer" in msgs(E, "BD-PARAM-01")


def test_param_bool(tmp_path):
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": True}
    E = run(tmp_path, d)
    print(show(E))
    assert codes(E)


def test_param_out_of_space_via_derived_clock(tmp_path):
    d = base()
    d["ports"][0]["freq_mhz"] = 0.05        # 50 kHz: CLKS_PER_BIT rounds to 0
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-01"] and "CLKS_PER_BIT=0" in msgs(E, "BD-PARAM-01"), show(E)


def test_param_derived_outside_space(tmp_path):
    d = base()
    d["ports"][0]["freq_mhz"] = 0.4        # CLKS_PER_BIT rounds to 3: below the shell's 4
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-01"] and "CLKS_PER_BIT=3" in msgs(E, "BD-PARAM-01"), show(E)


def test_generate_writes_a_literal_parameter_as_a_number():
    """A parameter given as a Verilog literal reaches the HDL as its value, never as a quoted string."""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(dir=REPO / "flow" / "blockdesign" / "tests"))
    try:
        d = base()
        d["instances"]["la"]["params"] = {"ADDR_W": "8'h8"}
        run(tmp, d)
        top = next(v for k, v in generate.generate(tmp).items() if k.endswith("t_la_wrap.sv"))
        assert ".ADDR_W(8)" in top and "8'h8\"" not in top
    finally:
        shutil.rmtree(tmp)


def test_unlinked_window_tied_off_port_by_port_is_generated():
    """A bus interface on no link may be tied off port by port; every tie reaches the generated RTL."""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(dir=REPO / "flow" / "blockdesign" / "tests"))
    try:
        d = base()
        d["instances"]["la2"] = {"component": "logic_analyser", "params": {"ADDR_W": 8}}
        d["connections"] += [{"from": "dds.sample", "to": "la2.sample"}, {"const": 1, "to": "la2.sample_en"},
                             {"const": 3, "to": "la2.win_addr"}, {"const": 0, "to": "la2.win_wr"}, {"const": 0, "to": "la2.win_rd"},
                             {"const": 0, "to": "la2.win_wdata"}]
        E = run(tmp, d)
        assert codes(E) == [], show(E)
        top = next(v for k, v in generate.generate(tmp).items() if k.endswith("t_top.sv"))
        for line in ("assign la2__win_addr = 7'd3;", "assign la2__win_wr = 1'd0;", "assign la2__win_rd = 1'd0;"):
            assert line in top
    finally:
        shutil.rmtree(tmp)


def test_unlinked_window_partly_tied_reports_the_rest():
    d = base()
    d["instances"]["la2"] = {"component": "logic_analyser", "params": {"ADDR_W": 8}}
    d["connections"] += [{"from": "dds.sample", "to": "la2.sample"}, {"const": 1, "to": "la2.sample_en"},
                         {"const": 0, "to": "la2.win_wr"}]
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        E = run(Path(t), d)
    assert "la2.win_addr" in msgs(E, "BD-UNCONN-01") and "BD-UNCONN-02" not in codes(E)


@pytest.mark.parametrize("text", ["8.5", "3.99", "0x10", "1e1"])
def test_param_python_syntax_is_refused(tmp_path, text):
    """A parameter string must be Verilog: a real number or a C-style 0x10 is refused, not truncated or converted."""
    d = base()
    d["instances"]["la"]["params"] = {"ADDR_W": text}
    E = run(tmp_path, d)
    assert codes(E) == ["BD-PARAM-01"] and "not an integer" in msgs(E, "BD-PARAM-01"), show(E)
