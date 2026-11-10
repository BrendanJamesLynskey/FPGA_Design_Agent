"""Brief 27B P0: the project checkers, the stage keys, ``project status``, the dashboard and the generator's output.

No simulator here (CI's python job). The generated tests are run on RTL in ``test_27b_contract_tests_rtl.py``.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from project import contract_test, dashboard
from project.expr import ExprError, evaluate
from project.schema import check_contract, check_design, check_project
from project.stages import stage_keys
from project.status import check_evidence, project_status

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "project" / "examples" / "video_median"


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    d = tmp_path / "video_median"
    shutil.copytree(EX, d)
    return d


def _edit_yaml(path: Path, fn: Callable[[Any], None]) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _errors(d: Path) -> list[str]:
    return check_project(d).errors


def _contract(d: Path, m: str) -> Path:
    return d / "modules" / m / "contract.yaml"


def _mod(data: dict[str, Any], name: str) -> dict[str, Any]:
    return next(m for m in data["modules"] if m["name"] == name)


def _iface(data: dict[str, Any], name: str) -> dict[str, Any]:
    return next(f for f in data["interfaces"] if f["name"] == name)


# ---- the worked example ---------------------------------------------------------------------------------------------
def test_the_pilot_example_is_valid() -> None:
    p = check_project(EX)
    assert p.errors == [] and p.warnings == []
    assert sorted(p.contracts) == ["median3x3", "video_src"]


def test_the_example_status_shows_current_stale_and_missing_evidence() -> None:
    st = project_status(EX)
    assert st["valid"] and st["hand_written"] == ["median3x3", "video_src"]
    m = {x["module"]: x for x in st["modules"]}
    assert [s["state"] for s in m["video_src"]["stages"][:4]] == ["pass", "pass", "not-run", "none"]
    assert m["video_src"]["reached"] == 1 and m["video_src"]["reentry"] == 2
    assert m["median3x3"]["stages"][0]["state"] == "stale"
    assert m["median3x3"]["reached"] == -1 and m["median3x3"]["reentry"] == 0
    assert m["median3x3"]["reentry_why"] == "stale evidence"
    assert [a["id"] for a in st["assumptions_open"]] == ["A-1", "A-2"]


def test_the_committed_generated_tests_are_up_to_date() -> None:
    p = check_project(EX)
    for m in p.contracts:
        files = contract_test.generate(_contract(EX, m).read_text(), p.module(m).get("params"))
        for name, text in files.items():
            assert (EX / "modules" / m / "tests" / name).read_text() == text, f"{m}/tests/{name}: run gen-tests again"


def test_generated_tests_cover_the_contract() -> None:
    names = {m: [t for t, _ in contract_test.tests_for(yaml.safe_load(_contract(EX, m).read_text()))]
             for m in ("video_src", "median3x3")}
    assert names["video_src"] == ["contract_ports", "contract_reset", "contract_axis_master_video_out"]
    assert names["median3x3"] == ["contract_ports", "contract_reset", "contract_axis_slave_video_in",
                                  "contract_axis_master_video_out", "contract_latency_0_video_in_video_out",
                                  "contract_throughput_0_video_out"]
    tb = (EX / "modules" / "median3x3" / "tests" / "contract_tb.py").read_text()
    compile(tb, "contract_tb.py", "exec")
    assert "PARAMS = {\"H_TOTAL\": 1650}" in tb


def test_the_generator_refuses_a_bad_contract() -> None:
    text = _contract(EX, "median3x3").read_text().replace("role: slave", "role: sink", 1)
    with pytest.raises(ValueError, match="role must be master or slave"):
        contract_test.generate(text)


# ---- stage keys: what an edit makes stale ----------------------------------------------------------------------------
def _keys(d: Path) -> dict[str, list[str]]:
    p = check_project(d)
    assert not p.errors, p.errors
    return {m: [k["key"] for k in stage_keys(p, m)] for m in p.contracts}


def _first_changed(a: list[str], b: list[str]) -> int | None:
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)


def test_keys_are_stable_and_chained(proj: Path) -> None:
    assert _keys(proj) == _keys(EX)                   # independent of where the project lives
    before = _keys(proj)
    (proj / "modules" / "median3x3" / "rtl").mkdir()
    (proj / "modules" / "median3x3" / "rtl" / "median3x3.sv").write_text("module median3x3; endmodule\n")
    after = _keys(proj)
    assert _first_changed(before["median3x3"], after["median3x3"]) == 2      # stage 2 and every later stage
    assert all(x != y for x, y in zip(before["median3x3"][2:], after["median3x3"][2:]))
    assert before["video_src"] == after["video_src"]


def test_a_latency_edit_restarts_only_that_module_at_stage_0(proj: Path) -> None:
    before = _keys(proj)
    _edit_yaml(_contract(proj, "median3x3"), lambda c: c["latency"][0].update(cycles="H_TOTAL + 3"))
    after = _keys(proj)
    assert _first_changed(before["median3x3"], after["median3x3"]) == 0
    assert before["video_src"] == after["video_src"]


def test_an_interface_edit_reaches_the_other_end_of_the_connection(proj: Path) -> None:
    before = _keys(proj)
    _edit_yaml(_contract(proj, "median3x3"),
               lambda c: _iface(c, "video_in")["tuser"][2].update(meaning="active picture (data enable)"))
    after = _keys(proj)
    assert _first_changed(before["median3x3"], after["median3x3"]) == 0
    assert _first_changed(before["video_src"], after["video_src"]) == 1      # the far end, from its architecture stage


def test_a_clock_plan_edit_restarts_every_module_at_constraints(proj: Path) -> None:
    before = _keys(proj)
    _edit_yaml(proj / "design.yaml", lambda d: d["resets"][1].update(via="xpm_cdc_async_rst"))
    after = _keys(proj)
    for m in before:
        assert _first_changed(before[m], after[m]) == 3


def test_a_requirement_edit_restarts_its_modules_only(proj: Path) -> None:
    before = _keys(proj)
    _edit_yaml(proj / "system" / "requirements.yaml",
               lambda r: next(x for x in r["requirements"] if x["id"] == "S-4").update(text="median of each channel"))
    after = _keys(proj)
    assert _first_changed(before["median3x3"], after["median3x3"]) == 0
    assert before["video_src"] == after["video_src"]


def test_editing_the_spec_makes_hand_written_evidence_stale(proj: Path) -> None:
    spec = proj / "modules" / "video_src" / "spec.md"
    spec.write_text(spec.read_text() + "\nOne more sentence.\n")
    m = {x["module"]: x for x in project_status(proj)["modules"]}
    assert [s["state"] for s in m["video_src"]["stages"][:3]] == ["stale", "stale", "stale"]
    assert m["video_src"]["reentry"] == 0 and m["video_src"]["reached"] == -1


def test_a_failing_current_item_shows_as_fail(proj: Path) -> None:
    p = check_project(proj)
    keys = {k["stage"]: k["key"] for k in stage_keys(p, "video_src")}
    ev_p = proj / "modules" / "video_src" / "evidence" / "status.json"
    ev = json.loads(ev_p.read_text())
    ev["items"][2].update(result="fail")
    ev["items"].append({"stage": "synthesis", "kind": "ooc_timing", "result": "pass", "key": keys["synthesis"],
                        "clock": "clk", "target_mhz": 74.25, "wns_ns": 1.0})
    ev_p.write_text(json.dumps(ev))
    m = {x["module"]: x for x in project_status(proj)["modules"]}["video_src"]
    assert m["stages"][2]["state"] == "fail" and m["stages"][4]["state"] == "pass"
    assert m["reached"] == 1 and m["reentry"] == 2


def test_evidence_items_are_checked(proj: Path) -> None:
    assert check_evidence({"schema": "fpga-design-agent/evidence/v1", "module": "m", "provenance": "flow",
                           "items": [{"stage": "synth", "kind": "x", "result": "ok", "key": "abc"}]}, "m") == [
        "items[0]: stage 'synth' is not one of " + ", ".join(__import__("agent.core.session", fromlist=["x"]).STAGES),
        "items[0]: kind must be one of approval, contract_test, verification, ooc_timing, resources, hil, gates",
        "items[0]: result must be one of pass, fail, not-run",
        "items[0]: key must be the 64-hex stage key (python -m project hash)"]
    (proj / "modules" / "video_src" / "evidence" / "status.json").write_text("{not json")
    st = project_status(proj)
    assert not st["valid"] and any("not valid JSON" in e for e in st["errors"])


# ---- the checkers find what they claim to ----------------------------------------------------------------------------
DESIGN_EDITS: list[tuple[str, Callable[[Any], None], str]] = [
    ("board port name", lambda d: d["board_ports"][4].update(name="VGA_X[3:0]"),
     "VGA_X[3], VGA_X[2], VGA_X[1], VGA_X[0] not in the board's master XDC"),
    ("board port width", lambda d: d["board_ports"][4].update(**{"from": "median3x3.video_out.tdata[23:21]"}),
     "board port VGA_R[3:0]: 4 bits, but median3x3.video_out.tdata[23:21] is 3"),
    ("tuser name", lambda d: d["board_ports"][8].update(**{"from": "median3x3.video_out.tuser.hsync"}),
     "tuser has no bit named hsync"),
    ("electrical type", lambda d: d["board_ports"][3].update(drive="tristate"), "drive (electrical type) must be one of"),
    ("missing crossing", lambda d: _mod(d, "median3x3").update(clocks={"clk": "clk_sys"}, resets={"rst": "rst_sys"}),
     "crosses from clk_pix to clk_sys but declares no crossing"),
    ("needless crossing", lambda d: d["connections"][0].update(crossing={"primitive": "async_fifo"}),
     "declares a crossing but both ends are on clk_pix"),
    ("bad primitive", lambda d: d["connections"][0].update(crossing={"primitive": "two_flops"}),
     "crossing must be {primitive: one of"),
    ("packet length", lambda d: _mod(d, "median3x3").update(params={"H_TOTAL": 1649}), "packet_beats 1650 against 1649"),
    ("param range", lambda d: _mod(d, "median3x3").update(params={"H_TOTAL": 5000}), "outside the contract's allowed"),
    ("clock too fast", lambda d: d["clocks"][1].update(mhz=80), "above the contract's max_mhz 74.25"),
    ("reset polarity", lambda d: d["resets"][1].update(polarity="active_low"), "reset rst is active_high but rst_pix is"),
    ("register crossing", lambda d: _mod(d, "video_src").pop("register_crossings"),
     "register_crossings.PATTERN must name a CDC primitive"),
    ("window overlap", lambda d: _mod(d, "video_src").update(window_base=0x7f), "window offset 0x80 is past 0x7f"),
    ("unbound clock", lambda d: _mod(d, "video_src").update(clocks={"clk2": "clk_pix"}),
     "contract clock clk is not bound to a design clock"),
    ("no board clock pin", lambda d: d["board_ports"].pop(0), "clock clk_sys: no board port drives it"),
    ("shell uart", lambda d: d["board_ports"].pop(2), "the shell's uart_rx is not on a board port"),
    ("unconnected slave", lambda d: d.update(connections=[]), "interface median3x3.video_in (slave) is not connected"),
    ("reset without sync", lambda d: d["resets"][1].pop("via"), "derived from rst_sys in another domain"),
    ("assumption id", lambda d: d["assumptions"][0].update(id="X-1"), "assumptions[0] must be"),
    ("schema", lambda d: d.update(schema="v0"), "schema must be 'fpga-design-agent/project/v1'"),
]


@pytest.mark.parametrize("what,edit,needle", DESIGN_EDITS, ids=[x[0] for x in DESIGN_EDITS])
def test_design_errors_are_found(proj: Path, what: str, edit: Callable[[Any], None], needle: str) -> None:
    _edit_yaml(proj / "design.yaml", edit)
    errs = _errors(proj)
    assert any(needle in e for e in errs), errs


CONTRACT_EDITS: list[tuple[str, str, Callable[[Any], None], str]] = [
    ("missing port", "median3x3", lambda c: c["ports"].pop(4), "port s_axis_video_tdata is missing from the port list"),
    ("port direction", "median3x3", lambda c: c["ports"][3].update(dir="in"), "s_axis_video_tready must be dir out"),
    ("tdata width", "median3x3", lambda c: c["ports"][4].update(width=23), "the interface needs 24"),
    ("field format", "video_src", lambda c: _iface(c, "video_out")["tdata"]["fields"][0].update(format="u7"),
     "format u7 is 7 bits but the field is 8"),
    ("field overlap", "video_src", lambda c: _iface(c, "video_out")["tdata"]["fields"][1].update(bits=[16, 8]),
     "overlap another field"),
    ("tuser mismatch", "median3x3", lambda c: _iface(c, "video_in").update(
        tuser=[{"bit": 0, "name": "vs"}, {"bit": 1, "name": "hs"}, {"bit": 2, "name": "de"}]), "tuser bits differ"),
    ("backpressure", "median3x3", lambda c: _iface(c, "video_in").update(backpressure=True),
     "the sink may hold tready low but the source cannot be stalled"),
    ("gaps", "video_src", lambda c: _iface(c, "video_out").update(source_gaps=True),
     "the source may leave gaps but the sink needs a beat every cycle"),
    ("unknown parameter", "median3x3", lambda c: c["latency"][0].update(cycles="LINES + 2"),
     "LINES is not a declared parameter"),
    ("register port", "video_src", lambda c: c["registers"]["map"][0]["fields"][0].update(port="nope"),
     "port nope is not in the port list"),
    ("register direction", "video_src", lambda c: c["registers"]["map"][1].update(access="RW"),
     "port frame_count must be dir in for access RW"),
    ("register reset", "video_src", lambda c: c["registers"]["map"][0].update(reset=1 << 33), "reset must be an integer"),
    ("reset value", "video_src", lambda c: c["ports"][2].update(reset_value=2), "reset_value must be an integer that fits"),
    ("module name", "video_src", lambda c: c.update(module="vsrc"), "module = 'vsrc' but the directory is modules/video_src"),
]


@pytest.mark.parametrize("what,mod,edit,needle", CONTRACT_EDITS, ids=[x[0] for x in CONTRACT_EDITS])
def test_contract_errors_are_found(proj: Path, what: str, mod: str, edit: Callable[[Any], None], needle: str) -> None:
    _edit_yaml(_contract(proj, mod), edit)
    errs = _errors(proj)
    assert any(needle in e for e in errs), errs


def test_requirement_errors_are_found(proj: Path) -> None:
    _edit_yaml(proj / "system" / "requirements.yaml", lambda r: r["requirements"][0].update(modules=["vga"], proof=["vibes"]))
    errs = _errors(proj)
    assert any("module 'vga' is not in design.yaml" in e for e in errs), errs
    assert any("proof must be a non-empty list" in e for e in errs), errs


def test_the_fixture_contracts_are_valid() -> None:
    for c in sorted((ROOT / "project" / "tests" / "fixtures").glob("*/contract.yaml")):
        assert check_contract(yaml.safe_load(c.read_text()), c.parent.name) == [], c


def test_the_checkers_accept_only_mappings() -> None:
    assert check_design([]) == ["design.yaml must be a YAML mapping at the top level"]
    assert check_contract("x") == ["contract.yaml must be a YAML mapping at the top level"]


def test_expressions_run_no_code() -> None:
    assert evaluate("H_ACTIVE + H_FP * 2 - (3 // 2)", {"H_ACTIVE": 1280, "H_FP": 110}) == 1499
    for bad in ("__import__('os')", "H.real", "[1][0]", "1 if 1 else 2", "2 ** 999"):
        with pytest.raises(ExprError):
            evaluate(bad, {"H": 1})


# ---- the dashboard and the CLI -------------------------------------------------------------------------------------
def test_the_dashboard_is_one_static_page() -> None:
    html = dashboard.page(project_status(EX))
    assert html.startswith("<!doctype html>") and "<script" not in html
    assert not re.search(r"(src|href)=\"https?:", html)
    assert "Hand-written evidence." in html and "nobody has approved" in html
    assert html.count('<rect class="box') == 2
    assert '<rect class="box pass"' in html and '<rect class="box stale"' in html
    assert "video_out → video_in" in html and "A-1" in html and "prefers-color-scheme:dark" in html


def test_the_dashboard_marks_a_failing_module_and_a_crossing(proj: Path) -> None:
    st = project_status(proj)
    st = copy.deepcopy(st)
    st["modules"][0]["stages"][2]["state"] = "fail"
    st["connections"][0]["crossing"] = {"primitive": "async_fifo"}
    html = dashboard.page(st)
    assert '<rect class="box fail"' in html and 'class="edge x"' in html and "async_fifo" in html


def test_cli_status_writes_json_and_html_and_exits_by_validity(proj: Path, tmp_path: Path) -> None:
    out_j, out_h = tmp_path / "st.json", tmp_path / "dash.html"
    r = subprocess.run([sys.executable, "-m", "agent", "project", "status", str(proj), "--json", str(out_j), "--html",
                        str(out_h)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hand-written" in r.stdout and "STALE" in r.stdout
    assert json.loads(out_j.read_text())["project"] == "video_median" and out_h.read_text().startswith("<!doctype")
    _edit_yaml(proj / "design.yaml", lambda d: d["clocks"][1].update(mhz=80))
    r = subprocess.run([sys.executable, "-m", "project", "check", str(proj)], cwd=ROOT, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1 and "INVALID" in r.stdout


def test_cli_hash_matches_the_recorded_keys() -> None:
    r = subprocess.run([sys.executable, "-m", "project", "hash", str(EX), "--json"], cwd=ROOT, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    keys = json.loads(r.stdout)
    ev = json.loads((EX / "modules" / "video_src" / "evidence" / "status.json").read_text())
    assert ev["items"][0]["key"] == keys["video_src"][0]["key"]


def test_cli_gen_tests_writes_both_files(proj: Path) -> None:
    for f in (proj / "modules").glob("*/tests/*"):
        f.unlink()
    r = subprocess.run([sys.executable, "-m", "project", "gen-tests", str(proj), "--module", "median3x3"], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in (proj / "modules" / "median3x3" / "tests").iterdir()) == ["contract_tb.py",
                                                                                         "test_contract_rtl.py"]
    assert not list((proj / "modules" / "video_src" / "tests").iterdir())
