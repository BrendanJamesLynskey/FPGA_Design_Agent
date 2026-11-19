"""Brief 105A: the three constraint rules the owner approved on 2026-11-19 (flow/constraint_gates.py).

1. CFGBVS-1/2 are a gate failure only for a board whose configuration voltage is confirmed in its board file; the flow sets the two
   properties for such a board; an unconfirmed board stays advisory.
2. A blanket ``set_clock_groups -asynchronous`` is flagged for owner review and can never block.
3. ``SIM_ASSERT_CHK`` is 1 on every xpm_cdc instance the repo owns; a source check (advisory) finds one that is not.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from flow import checks as C
from flow import constraint_gates as CG
from flow import gates, prepare

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data"
CONFIRMED = "nexys_video"          # Digilent's vendor XDC sets CFGBVS VCCO and CONFIG_VOLTAGE 3.3 (source: XDC)
UNCONFIRMED = "arty_a7_100t"       # assumed 3.3 V, the schematic was not read (status: unconfirmed)


# ---- helpers -----------------------------------------------------------------------------------------------------------
def _drc(rows: list[tuple[str, str, str]]) -> str:
    head = ("Report DRC\n\n1. REPORT SUMMARY\n-----------------\n+------+----------+-------------+--------+\n"
            "| Rule | Severity | Description | Checks |\n+------+----------+-------------+--------+\n")
    body = "".join(f"| {r} | {s} | {d} | 1 |\n" for r, s, d in rows)
    return head + body + "+------+----------+-------------+--------+\n\n2. REPORT DETAILS\n-----------------\n"


CFGBVS_1 = ("CFGBVS-1", "Warning", "Missing CFGBVS and CONFIG_VOLTAGE Design Properties")
CFGBVS_2 = ("CFGBVS-2", "Critical Warning", "CONFIG_VOLTAGE Design Property is not set correctly")


def _clock_interaction(pairs: list[tuple[str, str, str, int]]) -> str:
    """A report_clock_interaction table with the real column layout (16 columns, two header rows, dashed rule)."""
    w = [30, 30, 11, 7, 7, 11, 9, 15, 11, 7, 7, 11, 9, 15, 19, 23]
    names1 = ["", "", "WNS", "", "", "TNS Failing", "TNS Total", "WNS Path", "WHS", "", "", "THS Failing", "THS Total", "WHS Path", "Clock-Pair", "Inter-Clock"]
    names2 = ["From Clock", "To Clock", "Clock Edges", "WNS(ns)", "TNS(ns)", "Endpoints", "Endpoints", "Requirement(ns)", "Clock Edges", "WHS(ns)",
              "THS(ns)", "Endpoints", "Endpoints", "Requirement(ns)", "Classification", "Constraints"]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(n) for c, n in zip(cells, w)).rstrip() + "\n"
    out = "Clock Interaction Report\n\nClock Interaction Table\n-----------------------\n\n" + line(names1) + line(names2)
    out += "  ".join("-" * n for n in w) + "\n"
    for a, b, cons, n in pairs:
        cells = [a, b, "rise - rise", "3.87", "0.00", "0", str(n), "10.00", "rise - rise", "0.03", "0.00", "0", str(n), "0.00",
                 "Clean" if cons in ("Timed", "Partial False Path") else "Ignored", cons]
        if cons not in ("Timed", "Partial False Path"):          # an ignored pair prints no slack, as in the real report
            cells = [a, b, "", "", "", "0", str(n), "", "", "", "", "0", str(n), "", "Ignored", cons]
        out += line(cells)
    return out + "\n"


def _build(tmp: Path, board: str | None, drc_text: str, ci_text: str | None = None) -> Path:
    """A routed build directory: the T1 good reports, with this drc.rpt (and clock interaction report) and a prepare.json naming the board."""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in DATA.glob("good_*.rpt"):
        n = f.name.replace("good_", "")
        if any(k in n for k in ("_synth", "_rtl", "_place", "board_env", "qor")):
            continue
        (tmp / n).write_text(f.read_text())
    (tmp / "drc.rpt").write_text(drc_text)
    (tmp / "t1_dimmer_counter_top.bit").write_bytes(b"\0" * 16)
    if ci_text is not None:
        (tmp / "clock_interaction_route.rpt").write_text(ci_text)
    (tmp / "prepare.json").write_text(json.dumps({"top": "t1_dimmer_counter_top", "variant": "base", "board": board, "files": []}))
    return tmp


def _evaluate(tmp: Path, xdc: Path | None = None) -> dict:
    """gates.evaluate reads the design's XDCs from prepare.json ``files`` (paths relative to the repo root); an absolute path joins unchanged."""
    if xdc is not None:
        prep = json.loads((tmp / "prepare.json").read_text())
        prep["files"] = [str(xdc)]
        (tmp / "prepare.json").write_text(json.dumps(prep))
    return gates.evaluate(tmp)


# ---- rule 1: CFGBVS / CONFIG_VOLTAGE -----------------------------------------------------------------------------------
def test_confirmed_boards_are_exactly_those_whose_file_cites_a_source() -> None:
    seen = {}
    for b in sorted((ROOT / "boards").glob("*/board.yaml")):
        cfg = CG.board_config(b.parent.name)
        raw = (yaml.safe_load(b.read_text()) or {}).get("config")
        if raw is None:
            assert cfg is None
            continue
        # every config block says which: a source (confirmed) or a status (assumed), never neither
        assert bool(raw.get("source")) != bool(raw.get("status")), f"{b.parent.name}: config needs source or status, not both or neither"
        seen[b.parent.name] = cfg["confirmed"]
    assert {n for n, c in seen.items() if c} == {"basys3", "arty_s7_50", "nexys_video"}
    assert not seen["nexys_a7_100t"] and not seen["arty_a7_100t"] and not seen["genesys2"]


def test_confirmed_board_with_the_property_missing_fails_and_with_it_set_passes(tmp_path: Path) -> None:
    bad = _evaluate(_build(tmp_path / "b", CONFIRMED, _drc([CFGBVS_1])))
    assert bad["gates"]["config_voltage_declared"] is False and bad["gates"]["drc_clean"] is True     # the Warning does not trip drc_clean
    assert bad["pass"] is False and bad["first_failed_stage"] == "post_route"
    assert bad["stages"]["post_route"]["config_voltage"]["rows"] == ["CFGBVS-1 (Warning) x1"]
    good = _evaluate(_build(tmp_path / "g", CONFIRMED, _drc([])))
    assert good["gates"]["config_voltage_declared"] is True and good["pass"] is True


def test_cfgbvs_2_also_fails_a_confirmed_board(tmp_path: Path) -> None:
    r = _evaluate(_build(tmp_path / "x", CONFIRMED, _drc([CFGBVS_2])))
    assert r["gates"]["config_voltage_declared"] is False


def test_an_unconfirmed_board_stays_advisory(tmp_path: Path) -> None:
    r = _evaluate(_build(tmp_path / "u", UNCONFIRMED, _drc([CFGBVS_1])))
    assert "config_voltage_declared" not in r["gates"] and r["pass"] is True
    assert r["stages"]["post_route"]["config_voltage"]["applies"] is False
    n = _evaluate(_build(tmp_path / "n", None, _drc([CFGBVS_1])))          # no board at all: as today
    assert "config_voltage_declared" not in n["gates"] and n["pass"] is True


def test_the_flow_sets_the_properties_for_a_confirmed_board_only(tmp_path: Path) -> None:
    f = prepare.board_config_xdc(CONFIRMED, tmp_path)
    assert f is not None and f.name == "board_config.xdc"
    lines = [ln for ln in f.read_text().splitlines() if not ln.startswith("#")]
    assert lines == ["set_property CFGBVS VCCO [current_design]", "set_property CONFIG_VOLTAGE 3.3 [current_design]"]
    (tmp_path / "o").mkdir()
    assert prepare.board_config_xdc(UNCONFIRMED, tmp_path / "o") is None and not list((tmp_path / "o").iterdir())
    assert prepare.board_config_xdc("kr260", tmp_path / "o") is None and prepare.board_config_xdc(None, tmp_path / "o") is None


def test_a_design_xdc_with_another_value_is_reported(tmp_path: Path) -> None:
    xdc = tmp_path / "design.xdc"
    xdc.write_text("set_property CFGBVS VCCO [current_design]\nset_property CONFIG_VOLTAGE 1.8 [current_design]\n")
    r = _evaluate(_build(tmp_path / "m", CONFIRMED, _drc([])), xdc)
    names = [w["name"] for w in r["stages"]["post_route"]["warnings"]]
    assert "config_voltage_differs_from_board" in names and r["pass"] is True          # a warning: the board file's value is the one built


def test_drc_check_in_the_registry_blocks_only_on_a_confirmed_board(tmp_path: Path) -> None:
    for board, blocking in ((CONFIRMED, True), (UNCONFIRMED, False)):
        d = tmp_path / board
        (d / "build" / "base").mkdir(parents=True)
        (d / "build" / "base" / "drc.rpt").write_text(_drc([CFGBVS_1]))
        (d / "build" / "base" / "prepare.json").write_text(json.dumps({"board": board}))
        (d / "build" / "base" / "timing_summary.rpt").write_text("x")
        r = C.CHECKS["drc"].run(C.Ctx(design=d, scope="route"))
        f = [x for x in r["findings"] if x["code"] == "CFGBVS-1"]
        assert len(f) == 1 and f[0]["blocking"] is blocking


# ---- rule 2: blanket asynchronous clock groups -------------------------------------------------------------------------
HUB = "dbg_hub/inst/BSCANID.u_xsdbm_id/SWITCH_N_EXT_BSCAN.bscan_inst/SERIES7_BSCAN.bscan_inst/TCK"
BLANKET_XDC = """create_clock -period 10 [get_ports clk_a]
create_clock -period 8 [get_ports clk_b]
set_clock_groups -asynchronous \\
    -group [get_clocks clk_a] \\
    -group [get_clocks clk_b]
"""
ONE_PAIR_XDC = "set_max_delay -datapath_only -from [get_clocks clk_a] -to [get_clocks clk_b] 10\n"


def test_report_parser_reads_the_real_column_layout() -> None:
    rows = CG.parse_clock_pairs(_clock_interaction([("clk_a", "clk_b", "Asynchronous Groups", 86), ("clk_a", "clk_a", "Timed", 4349)]))
    assert rows[0] == {"from": "clk_a", "to": "clk_b", "constraints": "Asynchronous Groups", "endpoints": 86}
    assert rows[1]["constraints"] == "Timed" and rows[1]["endpoints"] == 4349
    fixture = (ROOT / "flow/tests/fixtures/ila_ip_exceptions/ila_ip_base/clock_interaction_route.rpt").read_text()
    real = CG.parse_clock_pairs(fixture)                       # a report Vivado 2026.1 wrote (the debug hub's own pairs)
    assert len(real) == 4 and {r["constraints"] for r in real} == {"Timed", "Max Delay Datapath Only", "Partial False Path"}


def test_asynchronous_group_over_a_pair_with_paths_is_flagged_never_blocking(tmp_path: Path) -> None:
    ci = _clock_interaction([("clk_a", "clk_a", "Timed", 100), ("clk_a", "clk_b", "Asynchronous Groups", 86), ("clk_b", "clk_a", "Asynchronous Groups", 12)])
    xdc = tmp_path / "design.xdc"
    xdc.write_text(BLANKET_XDC)
    r = _evaluate(_build(tmp_path / "a", CONFIRMED, _drc([]), ci), xdc)
    w = [x for x in r["stages"]["post_route"]["warnings"] if x["name"] == "async_clock_groups_review"]
    assert {x["code"] for x in w} == {"XDC-ASYNC-PATHS", "XDC-ASYNC-ALL"} and sum(x["code"] == "XDC-ASYNC-PATHS" for x in w) == 2
    assert r["pass"] is True and all(v is True for v in r["gates"].values())      # advisory: every gate still passes


def test_clean_case_per_crossing_exception_and_hub_pairs_are_not_flagged(tmp_path: Path) -> None:
    ci = _clock_interaction([("clk_a", "clk_a", "Timed", 100), ("clk_a", "clk_b", "Max Delay Datapath Only", 86),
                             (HUB, "clk_a", "Asynchronous Groups", 20), ("clk_a", HUB, "Asynchronous Groups", 20)])
    xdc = tmp_path / "design.xdc"
    xdc.write_text(ONE_PAIR_XDC)
    r = _evaluate(_build(tmp_path / "c", CONFIRMED, _drc([]), ci), xdc)
    assert [x for x in r["stages"]["post_route"]["warnings"] if x["name"] == "async_clock_groups_review"] == []


def test_group_over_every_clock_is_flagged_even_with_no_pair_rows() -> None:
    ci = _clock_interaction([("clk_a", "clk_a", "Timed", 1), ("clk_b", "clk_b", "Timed", 1)])
    f = CG.async_group_findings(ci, [BLANKET_XDC])
    assert [x["code"] for x in f] == ["XDC-ASYNC-ALL"]
    # a group that leaves one of three clocks out is not "every clock" (and no pair row is Asynchronous Groups here)
    ci3 = _clock_interaction([("clk_a", "clk_a", "Timed", 1), ("clk_b", "clk_b", "Timed", 1), ("clk_c", "clk_c", "Timed", 1)])
    assert CG.async_group_findings(ci3, [BLANKET_XDC]) == []
    # wildcards and the one-line forms are read too
    wild = "set_clock_groups -asynchronous -group {clk_a*} -group {clk_b*}"
    assert [x["code"] for x in CG.async_group_findings(ci, [wild])] == ["XDC-ASYNC-ALL"]
    assert CG.async_group_findings(ci, ["# set_clock_groups -asynchronous -group clk_a -group clk_b"]) == []      # a comment is not a command
    assert CG.async_group_findings(ci, ["set_clock_groups -logically_exclusive -group clk_a -group clk_b"]) == []


def test_no_async_finding_is_ever_blocking() -> None:
    ci = _clock_interaction([("clk_a", "clk_b", "Asynchronous Groups", 5)])
    assert all(f["blocking"] is False for f in CG.async_group_findings(ci, [BLANKET_XDC]))
    r = C.CHECKS["constraint_scope"]
    assert r.codes == {"constraint_scope": ("XDC-ASYNC-PATHS", "XDC-ASYNC-ALL")}


# ---- rule 3: XPM SIM_ASSERT_CHK ---------------------------------------------------------------------------------------
def test_xpm_source_check_finds_zero_and_missing_but_not_one_or_async_rst_or_comments() -> None:
    t = """
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SIM_ASSERT_CHK(0)) u0 (.src_clk(a));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .SIM_ASSERT_CHK(1)) u1 (.src_clk(a));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3)) u2 (.src_clk(a));
    xpm_cdc_sync_rst u3 (.src_rst(a));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(3)) u4 (.src_arst(a));
    // xpm_cdc_array_single #(.SIM_ASSERT_CHK(0)) u5 (.a);
    /* xpm_cdc_handshake #(.SIM_ASSERT_CHK(0)) u6 (.a); */
    initial $display("xpm_cdc_single #(.SIM_ASSERT_CHK(0)) u7 (");
    xpm_cdc_handshake #(.SIM_ASSERT_CHK(P_SIM)) u8 (.a);
    """
    f = CG.xpm_sim_findings(t, "x.sv")
    assert [(x["macro"], x["value"]) for x in f] == [("xpm_cdc_single", "0"), ("xpm_cdc_pulse", None), ("xpm_cdc_sync_rst", None),
                                                     ("xpm_cdc_handshake", "P_SIM")]
    assert all(x["blocking"] is False and x["where"].startswith("x.sv:") for x in f)


def test_xpm_check_is_in_the_registry_advisory_and_reads_the_builds_sources(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "build.yaml").write_text("top: t\nsources: [d/rtl/t.sv]\n")
    (d / "rtl" / "t.sv").write_text("module t; xpm_cdc_single #(.SIM_ASSERT_CHK(0)) u (.src_clk(1'b0)); endmodule\n")
    r = C.CHECKS["xpm_sim"].run(C.Ctx(design=d, scope="rtl", root=tmp_path))
    assert [f["code"] for f in r["findings"]] == ["XPM-SIM-01"] and not r["findings"][0]["blocking"]
    (d / "rtl" / "t.sv").write_text("module t; xpm_cdc_single #(.SIM_ASSERT_CHK(1)) u (.src_clk(1'b0)); endmodule\n")
    assert C.CHECKS["xpm_sim"].run(C.Ctx(design=d, scope="rtl", root=tmp_path))["findings"] == []


#: snapshots of earlier variants of a design (recorded experiments; their text is the record, so they keep the value they were built with)
SNAPSHOT_DIRS = ("pre96c", "lat_agent_both", "lat_agent_cdc", "lat_hand_ref")


def test_every_live_xpm_cdc_instance_the_repo_owns_sets_sim_assert_chk_1() -> None:
    """The repo-wide sweep: every instance in a live design, IP or rig source. Test inputs (flow/tests, flow/checks/seeded), recorded
    benchmark artifacts and results are not live sources; variant snapshots are listed in SNAPSHOT_DIRS."""
    bad, n = [], 0
    for sub in ("designs", "ip_lib", "hil", "shell", "showcase", "project", "agent"):
        for f in (ROOT / sub).rglob("*"):
            if f.suffix not in (".sv", ".v", ".svh") or any(p in SNAPSHOT_DIRS for p in f.parts) or "node_modules" in f.parts:
                continue
            if "sim" in f.parts and f.name == "xpm_models.sv":
                continue                                  # the Icarus stand-in modules define the macros; they are not instances
            text = f.read_text(errors="replace")
            n += len(re.findall(r"(?<![\w.$])xpm_cdc_(?:single|array_single|sync_rst|pulse|gray|handshake)\b\s*#", CG._strip_comments(text)))
            bad += [f"{f.relative_to(ROOT)}:{x['where'].split(':')[-1]} {x['macro']}" for x in CG.xpm_sim_findings(text, str(f))]
    assert n >= 80, f"the sweep found only {n} instances; the scan is broken"
    assert not bad, bad


def test_every_variant_snapshot_is_still_a_snapshot() -> None:
    """The exemption above is for recorded variants only: each has a variant.json or is the pre-96C reference."""
    base = ROOT / "designs" / "b96_kr260_10g"
    for n in SNAPSHOT_DIRS:
        assert (base / n).is_dir()


def test_a_status_of_any_kind_makes_a_board_unconfirmed(tmp_path: Path) -> None:
    for status in ("assumed", "tbd", None, ""):
        b = tmp_path / "boards" / "x"
        b.mkdir(parents=True, exist_ok=True)
        (b / "board.yaml").write_text(yaml.safe_dump({"config": {"cfgbvs": "VCCO", "config_voltage": 3.3, "source": ["XDC"], "status": status}}))
        assert CG.board_config("x", tmp_path)["confirmed"] is False
    (b / "board.yaml").write_text(yaml.safe_dump({"config": {"cfgbvs": "VCCO", "config_voltage": 3.3, "source": ["XDC"]}}))
    assert CG.board_config("x", tmp_path)["confirmed"] is True


def test_the_real_vivado_report_of_the_probe_without_the_property() -> None:
    """results/105A_constraint_gates/reports/probe_b/drc.rpt is Vivado 2026.1's own report_drc on the Nexys Video smoke design with the two
    lines missing: CFGBVS-1 is a Warning, so drc_clean passes; the rule fails it for the confirmed board and leaves an unconfirmed one."""
    rows = gates.parse_rule_table((ROOT / "results/105A_constraint_gates/reports/probe_b/drc.rpt").read_text())
    assert [(r["rule"], r["severity"]) for r in rows] == [("CFGBVS-1", "Warning")]
    assert CG.cfgbvs_verdict(rows, CG.board_config(CONFIRMED))["ok"] is False
    assert CG.cfgbvs_verdict(rows, CG.board_config(UNCONFIRMED))["ok"] is True
    clean = gates.parse_rule_table((ROOT / "results/105A_constraint_gates/reports/probe_a/drc.rpt").read_text())
    assert clean == [] and CG.cfgbvs_verdict(clean, CG.board_config(CONFIRMED))["ok"] is True
