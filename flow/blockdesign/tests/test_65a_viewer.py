"""The block-design viewer's text and data: one vocabulary for the counts, the check card, hex values, the scope line."""
from __future__ import annotations

import json
import re

from flow.blockdesign import viewer
from flow.blockdesign import model as M

DESIGN = M.ROOT / "designs" / "b65a_axil_soc"


def _g():
    return viewer.enrich(json.loads((DESIGN / "gen" / "graph.json").read_text()), DESIGN)


def _with_build(g, check):
    g = json.loads(json.dumps(g))
    g["build"] = {"tool": "2026.1", "wns_ns": 1.0, "gates_pass": True, "build_id": "x"}
    g["check"] = check
    return g


def test_counts_come_from_the_graph():
    g = _g()
    total, top, inside = viewer.count_blocks(g)
    assert total == sum(len(lv["blocks"]) for lv in g["levels"].values())
    assert viewer.count_text(g) == f"blocks ({top} at the top, {inside['tone']} inside tone)"
    html = viewer.body(g)
    assert f'<div class="n">{total}</div>' in html
    assert f"{top} blocks" in html          # the top diagram's aria-label uses the same word
    assert f"{inside['tone']} blocks" in html


def test_check_text_says_what_was_checked():
    t = viewer.check_text({"pass": True, "matched": 14, "expected": 14})
    assert "14 include the generated wrappers" in t and "RTL instances" in t and "links" not in t
    t = viewer.check_text({"pass": True, "matched": 14, "expected": 14, "edges_matched": 6, "edges_expected": 7,
                           "edges_not_visible": ["tone/dds -> tone/fd: through logic"], "ranges_checked": 3})
    assert "6 of 7 links between blocks found as nets" in t and "1 not compared" in t and "3 address ranges" in t
    assert viewer.check_text({"pass": False, "matched": 13, "expected": 14}).startswith("MISMATCH")
    assert "matches the netlist" not in viewer.body(_with_build(_g(), {"pass": True, "matched": 14, "expected": 14}))


def test_scope_line_is_data_not_typed():
    g = _g()
    assert "not yet built" in viewer.scope_line(g)
    s = viewer.scope_line(_with_build(g, None))
    assert "AXI4-Lite only" in s and "one 100 MHz clock domain" in s and "Vivado 2026.1" in s
    g2 = _with_build(g, None)
    g2["domains"][0]["freq_mhz"] = 125
    assert "125 MHz" in viewer.scope_line(g2)


def test_hex_params_stay_hex_and_slices_are_named():
    g = _g()
    shell = next(b for b in g["levels"][""]["blocks"] if b["id"] == "shell")
    assert next(p for p in shell["params"] if p["name"] == "DESIGN_ID")["shown"] == "0x42363541"
    labels = [L["label"] for L in g["levels"]["tone"]["links"]]
    assert any(l.startswith("sample bit 15 (inverted) -> sig") for l in labels)


def test_page_defines_terms_and_has_no_brief_numbers():
    html = viewer.body(_g())
    assert "<code>ip_lib</code>" in html and "UART test shell" in html
    assert not re.search(r"\bbrief\b", re.sub(r"<[^>]+>", " ", html), re.I)


def test_diagram_shows_ports_addresses_arrows_and_rail():
    svg = viewer.svg_level(_g(), "", "wide")
    for needle in ("s_dds 0x40000000 4 KB", "s_fd 0x40001000 4 KB", "hole 0x40002000", "UART_TXD_IN", "CLK100MHZ", "32b", "bda-bus", "bdl-clk", "bdl-rst"):
        assert needle in svg, needle
    assert "max-width" not in svg                 # fills the column; no pixel cap
    assert viewer.svg_level(_g(), "", "narrow").count("bdblk") >= 6


def test_links_table_names_ports():
    html = viewer.body(_g())
    assert "<code>tone.s_dds</code>" in html and "<code>tone.s_fd</code>" in html and "<code>xbar.m0</code>" in html
