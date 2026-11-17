"""Brief 95: the board catalogue. Every board file parses and cites its sources, no two ports share a pin unless the file says so,
the trust labels never exceed their evidence, the smoke designs are regenerated from the board files, and a request picks its board."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import boards as agent_boards  # noqa: E402
from flow import board_catalogue as cat  # noqa: E402
from flow import prepare  # noqa: E402
from tools import board_pins_import as imp  # noqa: E402
from tools import board_smoke as smoke  # noqa: E402
from tools.inventory_check import parse_xdc  # noqa: E402

BOARDS = ROOT / "boards"
CAT = cat.load()
V2 = [b for b, e in CAT.items() if not e.get("legacy")]
LEGACY = [b for b, e in CAT.items() if e.get("legacy")]


def y(board: str) -> dict:
    return yaml.safe_load((BOARDS / board / "board.yaml").read_text())


def master(board: str) -> dict[str, tuple[str, str]]:
    b = y(board)
    return parse_xdc((BOARDS / board / b["master_xdc"]).read_text())[0] if b.get("master_xdc") else {}


def test_catalogue_is_consistent():
    assert cat.problems() == []


def test_legacy_boards_are_the_two_that_predate_v2():
    assert sorted(LEGACY) == ["kr260", "nexys_a7_100t"]


def test_every_board_directory_is_in_the_catalogue():
    assert {p.parent.name for p in BOARDS.glob("*/board.yaml")} == set(CAT)


@pytest.mark.parametrize("board", V2)
def test_board_file_parses_and_cites_sources(board):
    b = y(board)
    assert b["schema"] == "fpga-design-agent/board/v2" and b["name"] == board
    for k in ("display_name", "vendor", "family", "part", "sources", "clock", "facts", "hardware_use", "thermal"):
        assert b.get(k) not in (None, {}, []), f"{board}: {k} is missing"
    ids = set(b["sources"])
    for sid, s in b["sources"].items():
        assert s.get("title") and s.get("version") and s.get("url"), f"{board}: source {sid} lacks title, version or url"
    def cites(where: str, node: dict):
        if node.get("status") in ("unconfirmed", "none", "assumption"):
            assert node.get("reason"), f"{board}: {where} is {node['status']} with no reason"
        if node.get("status") in ("unconfirmed", "assumption") and not node.get("source"):
            return
        assert node.get("source"), f"{board}: {where} has no source"
        assert set(node["source"]) <= ids, f"{board}: {where} cites {set(node['source']) - ids}, not in sources"
    for f in b["facts"]:
        assert f.get("item"), f"{board}: a fact has no item"
        if f.get("status") == "unconfirmed":
            assert f.get("reason"), f"{board}: fact {f['item']!r} is unconfirmed with no reason"
        else:
            assert f.get("value") and f.get("source"), f"{board}: fact {f['item']!r} needs a value and a source"
            assert set(f["source"]) <= ids, f"{board}: fact {f['item']!r} cites a source that is not listed"
    cites("clock", b["clock"])
    if b.get("uart"):
        cites("uart", b["uart"])
    for k in ("config", "thermal"):
        if b.get(k) and b[k].get("status"):
            assert b[k].get("reason"), f"{board}: {k} is {b[k]['status']} with no reason"
    # a board nobody owns says so, so the agent never programs it
    assert "owned" in b["hardware_use"] and b["hardware_use"].get("rule")


@pytest.mark.parametrize("board", V2)
def test_master_xdc_pins_clocks_and_resources(board):
    b = y(board)
    src = b["master_xdc_source"]
    assert src["kind"] in ("vendor_copy", "derived", "none")
    if src["kind"] == "none":
        assert b["master_xdc"] is None and src["reason"] and not CAT[board]["targetable"], f"{board}: no master XDC but targetable"
        return
    ports = master(board)
    assert ports, f"{board}: the master XDC parses to no ports"
    if src["kind"] == "vendor_copy":
        assert (BOARDS / board / "LICENSE-digilent-xdc.txt").is_file(), f"{board}: a vendor copy needs its licence text beside it"
        assert src["commit"] and src["licence"] and src["repo"]
    else:
        spec = yaml.safe_load((ROOT / src["spec"]).read_text())
        assert spec["board"] == board and spec["out"] == f"boards/{board}/{b['master_xdc']}"
        for s in spec["sources"]:
            assert re.fullmatch(r"[0-9a-f]{64}", s["sha256"]) and s["url"].startswith("https://") and s["licence"]
    # the clock, UART and smoke resources are ports of the master XDC
    c = b["clock"]
    if c.get("port"):
        assert c["port"] in ports and ports[c["port"]][0] == c["pin"], f"{board}: clock {c['port']} is not on pin {c['pin']} in the master XDC"
        if c.get("differential"):
            assert ports[c["port_n"]][0] == c["pin_n"]
        if c.get("period_ns_in_vendor_xdc"):
            assert abs(1000 / c["period_ns_in_vendor_xdc"] - c["freq_mhz"]) < 0.5, f"{board}: clock frequency disagrees with the vendor's create_clock"
    for k in ("fpga_rx", "fpga_tx"):
        u = (b.get("uart") or {}).get(k)
        if u:
            assert ports[u["port"]][0] == u["pin"]
    for name, target in (b.get("resources") or {}).items():
        for p in (target if isinstance(target, list) else [target]):
            assert p in ports, f"{board}: resource {name} names {p}, not a port of the master XDC"


@pytest.mark.parametrize("board", [b for b in CAT if master(b)])
def test_no_pin_clash_unless_declared(board):
    ports = master(board)
    by_pin: dict[str, list[str]] = {}
    for p, (pin, _s) in ports.items():
        by_pin.setdefault(pin, []).append(p)
    clash = {k: sorted(v) for k, v in by_pin.items() if len(v) > 1}
    declared = {a["pin"]: sorted(a["ports"]) for a in (y(board).get("pin_aliases") or {}).get("pins", [])}
    if board in LEGACY:
        assert clash == {}, f"{board}: pins shared by two ports: {clash}"
        return
    assert clash == declared, f"{board}: pin sharing {clash} is not what pin_aliases declares ({declared})"


@pytest.mark.parametrize("board", [b for b in V2 if master(b)])
def test_io_standards_are_known_to_vivado(board):
    stds = {s for _p, s in master(board).values()}
    known = {"LVCMOS12", "LVCMOS15", "LVCMOS18", "LVCMOS25", "LVCMOS33", "LVDS", "LVDS_25", "TMDS_33", "DIFF_SSTL12", "DIFF_SSTL15", "DIFF_SSTL135",
             "SSTL15", "SSTL135", "SSTL12", "DIFF_HSUL_12", "HSUL_12", "LVDS_25", "DIFF_SSTL15_T_DCI", "DIFF_SSTL135_T_DCI", "LVCMOS18_JEDEC", "MIPI_DPHY_DCI"}
    assert stds <= known, f"{board}: I/O standards {stds - known} are not in the checked list"


def test_pins_import_spec_reproduces_committed_xdc():
    """With the source files in $FDA_BOARD_SOURCES (named by source id) every derived XDC must equal what its spec produces."""
    d = os.environ.get("FDA_BOARD_SOURCES")
    if not d:
        pytest.skip("set FDA_BOARD_SOURCES to a directory of the source files, named by source id, to run the reproduction check")
    for spec in sorted(BOARDS.glob("*/pins_import.yaml")):
        assert imp.main([str(spec), "--source-dir", d, "--check"]) == 0, spec


def test_pins_import_parsers(tmp_path):
    dict_style = "#set_property -dict { PACKAGE_PIN W5   IOSTANDARD LVCMOS33 } [get_ports clk]\n#set_property -dict { PACKAGE_PIN V17 IOSTANDARD LVCMOS33 } [get_ports {sw[0]}]\n"
    old_style = "set_property PACKAGE_PIN T22 [get_ports {LD0}];\nset_property IOSTANDARD LVCMOS33 [get_ports {LD0}];\nset_property PACKAGE_PIN Y9 [get_ports {GCLK}];\n"
    xml = '<pin index="0" name ="a_0" iostandard="LVCMOS12" loc="AB1"/>\n<pin index="1" name ="b" loc="C3"/>'
    assert imp.parse_xdc(dict_style) == [("clk", "W5", "LVCMOS33"), ("sw[0]", "V17", "LVCMOS33")]
    assert imp.parse_xdc(old_style) == [("LD0", "T22", "LVCMOS33"), ("GCLK", "Y9", None)]
    assert imp.parse_board_store_xml(xml) == [("a_0", "AB1", "LVCMOS12"), ("b", "C3", None)]
    src = tmp_path / "SRC"
    src.write_text(xml)
    spec = {"board": "t", "title": "t", "sources": [{"id": "SRC", "url": "https://x/y", "sha256": hashlib.sha256(xml.encode()).hexdigest(),
                                                     "format": "board-store-xml", "licence": "l", "use": "u"}],
            "rename": [["^a_(\\d)$", "led[\\1]"]]}
    text = imp.build(spec, tmp_path)
    assert "[get_ports { led[0] }]" in text and "Left out because no source gives its I/O standard" in text and "b on C3" in text
    spec["sources"][0]["sha256"] = "0" * 64
    with pytest.raises(SystemExit):
        imp.build(spec, tmp_path)


# ---- trust labels -------------------------------------------------------------------------------------------------

def test_trust_is_computed_from_evidence_and_never_declared_above_it(monkeypatch):
    for b, e in CAT.items():
        assert e["trust"] == cat.computed_trust(b, e), b
    fake = {k: dict(v) for k, v in CAT.items()}
    fake["basys3"]["trust"] = "built"                       # no smoke record behind it
    monkeypatch.setattr(cat, "load", lambda: fake)
    assert any("above the evidence" in p for p in cat.problems())
    fake["basys3"]["trust"] = "hardware"
    assert any("basys3" in p and "above the evidence" in p for p in cat.problems())


def test_a_smoke_record_must_match_the_committed_xdc(tmp_path, monkeypatch):
    b = "basys3"
    assert smoke.has_smoke(b)
    ok, why = cat.smoke_evidence(b)
    if not ok:
        assert why in ("no smoke record",) or "gate" in why or "hash" in why
    # a record whose hash is wrong never proves 'built'
    monkeypatch.setattr(cat, "ROOT", tmp_path)
    monkeypatch.setattr(cat, "BOARDS", tmp_path / "boards")
    (tmp_path / "boards" / b / "smoke").mkdir(parents=True)
    (tmp_path / "boards" / b / "smoke" / "design.xdc").write_text("x")
    rec = tmp_path / "results" / "95_boards" / b
    rec.mkdir(parents=True)
    good = {"board": b, "passed": True, "xdc_sha256": hashlib.sha256(b"x").hexdigest(),
            "gates": {"post_route_timing": True, "drc": True, "methodology": True, "bitstream": True}}
    (rec / "smoke.json").write_text(json.dumps(good))
    assert cat.smoke_evidence(b) == (True, "")
    for bad in ({"xdc_sha256": "0" * 64}, {"passed": False}, {"gates": {**good["gates"], "drc": False}}, {"board": "other"}):
        (rec / "smoke.json").write_text(json.dumps({**good, **bad}))
        assert cat.smoke_evidence(b)[0] is False, bad


def test_built_boards_have_a_smoke_design_or_listed_builds():
    for b, e in CAT.items():
        if e["trust"] == "built":
            assert cat.built_ok(b, e)[0], b


def test_hardware_label_only_for_the_boards_the_owner_has():
    assert {b for b, e in CAT.items() if e["trust"] == "hardware"} <= {"nexys_a7_100t", "kr260", "zedboard", "adalm_pluto"}


# ---- the smoke designs ----------------------------------------------------------------------------------------------

SMOKE = [b for b in CAT if (BOARDS / b / "smoke").is_dir()]


@pytest.mark.parametrize("board", SMOKE)
def test_smoke_files_are_regenerated_from_the_board_file(board):
    assert smoke.main(["check", board]) == 0


@pytest.mark.parametrize("board", [b for b in V2 if smoke.has_smoke(b)])
def test_smoke_constraints_use_only_the_boards_pins(board):
    """The generated XDC's every pin and standard is the master XDC's for the same name, and every I/O port is constrained."""
    p = smoke.plan(board)
    xdc = smoke.make_xdc(board, p)
    mine, _ = parse_xdc(xdc)
    ms = master(board)
    names = {v: k for k, v in ms.items()}
    for port, (pin, std) in mine.items():
        assert pin in {v[0] for v in ms.values()}, f"{board}: {port} on {pin} is not a pin of the master XDC"
    used = sorted(pin for pin, _s in mine.values())
    assert len(used) == len(set(used)), f"{board}: the smoke design uses a pin twice"
    top = smoke.make_top(board, p)
    for port in mine:
        base = re.sub(r"\[\d+\]$", "", port)
        assert re.search(rf"\b{base}\b", top), f"{board}: constrained port {base} is not in the top"
    clocks = re.findall(r"create_clock .*-period ([\d.]+)", xdc)
    assert len(clocks) == 1 and abs(1000 / float(clocks[0]) - p["y"]["clock"]["freq_mhz"]) < 0.01


def test_smoke_uart_pins_are_the_boards_uart():
    for b in V2:
        if smoke.has_smoke(b):
            p = smoke.plan(b)
            u = p["y"].get("uart") or {}
            if p["uart"]:
                assert p["y"]["resources"]["uart_rx"] == u["fpga_rx"]["port"] and p["y"]["resources"]["uart_tx"] == u["fpga_tx"]["port"]


# ---- picking the board from a request ------------------------------------------------------------------------------

@pytest.mark.parametrize("text,board", [
    ("Build me a counter on the Nexys A7-100T", "nexys_a7_100t"), ("for my PYNQ-Z2", "pynq_z2"), ("AUP-ZU3 please", "aup_zu3"),
    ("a ZedBoard design", "zedboard"), ("the Basys 3", "basys3"), ("Cora Z7-07S", "cora_z7_07s"), ("Arty S7-50", "arty_s7_50"),
    ("on a Kria KR260", "kr260"), ("zybo z7-20 board", "zybo_z7_20")])
def test_a_request_names_one_board(text, board):
    assert cat.resolve(text) == (board, [])


@pytest.mark.parametrize("text,cands", [
    ("the Arty A7", ["arty_a7_100t", "arty_a7_35t"]), ("Zybo Z7", ["zybo_z7_10", "zybo_z7_20"]),
    ("a Basys 3 or a PYNQ-Z2", ["basys3", "pynq_z2"])])
def test_an_ambiguous_request_is_not_guessed(text, cands):
    assert cat.resolve(text) == (None, cands)


def test_an_unknown_board_is_not_guessed():
    assert cat.resolve("a Lattice ECP5 board") == (None, [])


def test_every_alias_resolves_to_its_board_or_is_ambiguous_with_it():
    for b, e in CAT.items():
        for a in [b, e["display"], *e.get("aliases", [])]:
            got, cands = cat.resolve(a)
            assert got == b or b in cands, (a, got, cands)


def test_board_arg_accepts_ids_and_requests_and_refuses_the_rest():
    assert agent_boards.board_arg("nexys_a7_100t") == "nexys_a7_100t"
    assert agent_boards.board_arg("the Basys 3") == "basys3"
    with pytest.raises(argparse.ArgumentTypeError, match="more than one"):
        agent_boards.board_arg("arty a7")
    with pytest.raises(argparse.ArgumentTypeError, match="no board named"):
        agent_boards.board_arg("a Lattice board")
    with pytest.raises(argparse.ArgumentTypeError, match="cannot target"):
        agent_boards.board_arg("kv260")


def test_commands_that_only_read_a_design_accept_a_board_the_agent_cannot_target():
    assert agent_boards.board_name("kr260") == "kr260"             # `document` and `resume` of the hand-written KR260 designs keep working
    assert agent_boards.board_name("the kv260") == "kv260"
    with pytest.raises(argparse.ArgumentTypeError, match="more than one"):
        agent_boards.board_name("arty a7")


def test_the_agent_cli_takes_a_request_for_its_board():
    r = subprocess.run([sys.executable, "-m", "agent", "run", "x.md", "--board", "arty a7"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2 and "names more than one board" in r.stderr


# ---- the flow still finds the board of a part-only build.yaml ---------------------------------------------------------

def test_a_part_only_build_yaml_still_finds_its_board():
    assert prepare.board_for({"part": "xc7a100tcsg324-1"}) == "nexys_a7_100t"      # the Arty A7-100T shares this part
    assert prepare.board_for({"part": "xck26-sfvc784-2LV-c"}) == "kr260"           # so does the KV260
    assert prepare.board_for({"part": "xc7z020clg400-1", "board": "pynq_z2"}) == "pynq_z2"
    assert prepare.board_for({"part": "xc7z020clg400-1"}) is None                  # two boards, none the default


def test_the_trust_table_is_current():
    assert cat.TABLE.read_text() == cat.table(), "docs/board_catalogue.md is stale: python3 flow/board_catalogue.py table --write"


def test_every_board_file_still_works_with_the_constraints_tool():
    from agent.core import constraints as con
    for b in CAT:
        if master(b):
            assert con.resource_catalogue(BOARDS / b), b
