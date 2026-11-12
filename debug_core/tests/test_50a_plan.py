"""Brief 50A: request intent -> plan: values, trigger patterns, window, packing, cuts, schema, probes.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from debug_core.plan import (PlanError, compile_condition, make_plan, merge_patterns, parse_value, probes_yaml, render,
                             validate)
from debug_core.rtl_index import RtlIndex
from flow.prepare import pack_probes

T1 = Path("designs/t1_dimmer_counter")

COUNT_WRITE = {"probes": ["count"], "trigger": {"combine": "AND", "conditions": [
    {"signal": "win_wr", "op": "==", "value": 1}, {"signal": "addr", "op": "==", "value": "0x80"}]},
    "pre": 16, "post": 32, "setup": [{"op": "write", "register": "COUNT", "value": 3}],
    "stimulus": [{"op": "write", "register": "COUNT", "value": "0x1234"}], "readback": [{"op": "read", "register": "COUNT"}]}


@pytest.mark.parametrize("v,w,bits", [(5, 4, "0101"), ("0x80", 8, "10000000"), ("0x8?", 8, "1000XXXX"),
                                      ("0b1x0", 3, "1X0"), ("'A'", 8, "01000001"), ("8'hA5", 8, "10100101"),
                                      ("42", 8, "00101010"), ("0x0080", 8, "10000000")])
def test_parse_value(v, w, bits) -> None:
    assert parse_value(v, w) == bits


@pytest.mark.parametrize("v,w", [(256, 8), ("0x180", 8), ("abc", 8), (None, 4), (-1, 4)])
def test_parse_value_refuses(v, w) -> None:
    with pytest.raises(PlanError):
        parse_value(v, w)


def test_compile_conditions() -> None:
    assert compile_condition("rise", None, 1) == "R"
    assert compile_condition("fall", None, 1) == "F"
    assert compile_condition("change", None, 1) == "B"
    assert compile_condition("!=", 1, 1) == "0"
    assert compile_condition("<", 64, 8) == "00XXXXXX"
    assert compile_condition("<=", 15, 8) == "0000XXXX"
    for op, v, w in (("rise", None, 8), ("!=", 0, 16), ("<", 100, 8), (">", 3, 8), (">=", 128, 8)):
        with pytest.raises(PlanError) as e:
            compile_condition(op, v, w)
        assert "use" in str(e.value) or "trigger on" in str(e.value)     # every refusal proposes what would work
    assert merge_patterns("1XX0", "X1X0") == "11X0"
    with pytest.raises(PlanError):
        merge_patterns("1XXX", "0XXX")


def test_count_write_plan() -> None:
    p = make_plan(T1, COUNT_WRITE, "capture count when the shell writes COUNT")
    assert not p["errors"] and not validate(p, "plan")
    assert [x["label"] for x in p["probes"]] == ["win_wr", "addr", "count"]
    assert [c["pattern"] for c in p["trigger"]["conditions"]] == ["1", "10000000"]
    assert p["clock"] == {"domain": "CLK100MHZ", "net": "CLK100MHZ_IBUF_BUFG", "mhz": 100.0}
    assert p["window"] == {"pre": 16, "post": 1007, "depth": 1024, "position": 16, "requested": {"pre": 16, "post": 32}}
    assert [(pt["group"], pt["width"]) for pt in p["ports"]] == [("flags", 1), ("data", 24)]
    assert p["setup"][0] == {"op": "write", "register": "COUNT", "value": 3, "address": 0x80}
    assert p["stimulus"][0]["value"] == 0x1234 and p["readback"][0]["address"] == 0x80
    assert p["fit"]["bram36_estimate"] == 1 and p["fit"]["ok"]
    text = render(p)
    assert "Probe set" in text and "buildable" in text and "win_wr == 1 AND addr == 0x80" in text


def test_probeset_ignores_run_time_settings() -> None:
    a = make_plan(T1, COUNT_WRITE)
    b = make_plan(T1, {**COUNT_WRITE, "pre": 100, "trigger": {"combine": "AND", "conditions": [
        {"signal": "win_wr", "op": "rise"}, {"signal": "addr", "op": "==", "value": 0x81}]}})
    assert a["probeset"] == b["probeset"]
    c = make_plan(T1, {**COUNT_WRITE, "probes": ["count", "led"]})
    assert c["probeset"] != a["probeset"]


def test_probes_yaml_is_what_the_flow_packs_the_same_way() -> None:
    p = make_plan(T1, COUNT_WRITE)
    data = yaml.safe_load(probes_yaml(p))
    assert data["ila"]["clock_net"] == "CLK100MHZ_IBUF_BUFG" and data["ila"]["depth"] == 1024
    ports = pack_probes(data["probes"], clock_net=data["ila"]["clock_net"])
    assert [[s["name"] for s in pt["slices"]] for pt in ports] == [[s["label"] for s in pt["slices"]] for pt in p["ports"]]
    assert [[s["offset"] for s in pt["slices"]] for pt in ports] == [[s["offset"] for s in pt["slices"]] for pt in p["ports"]]
    bad = make_plan(T1, {"probes": ["nope"], "trigger": {"combine": "AND", "conditions": []}})
    with pytest.raises(PlanError):
        probes_yaml(bad)


def test_unresolvable_names_are_errors_with_suggestions() -> None:
    p = make_plan(T1, {"probes": ["UART byte", "cnt", "duty_eff"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "fifo overflow", "op": "rise"}]}, "pre": 200, "post": 50})
    what = {e["what"]: e for e in p["errors"]}
    assert "signal 'fifo overflow'" in what and "signal 'cnt'" in what and "signal 'duty_eff'" in what
    assert "u_shell.u_rx.cnt" in what["signal 'cnt'"]["candidates"]
    assert "u_dut.duty" in what["signal 'duty_eff'"]["suggestions"]
    assert not p["fit"]["ok"] and "NOT BUILDABLE" in render(p)


def test_multi_bit_or_and_magnitude_are_refused_with_a_proposal() -> None:
    p = make_plan(T1, {"probes": ["led"], "trigger": {"combine": "OR", "conditions": [
        {"signal": "count", "op": "==", "value": 5}, {"signal": "phase", "op": "==", "value": 3}]}})
    assert [e["what"] for e in p["errors"]] == ["trigger OR"]
    m = make_plan(T1, {"probes": ["led"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "phase", "op": ">", "value": 3}]}})
    assert [e["what"] for e in m["errors"]] == ["trigger on 'phase' > 3"]
    ok = make_plan(T1, {"probes": ["count"], "trigger": {"combine": "OR", "conditions": [
        {"signal": "win_wr", "op": "rise"}, {"signal": "press_clear", "op": "rise"}]}})
    assert not ok["errors"]


def test_window_and_block_ram_cuts() -> None:
    p = make_plan(T1, {"probes": ["led", "count"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "phase", "op": "==", "value": 0}]}, "pre": 0, "post": 200000})
    e = {x["what"]: x for x in p["errors"]}
    assert e["window"]["proposal"] == {"pre": 0, "post": 131071}
    assert "block RAM" in e and e["block RAM"]["proposal"].get("or_depth") or e["block RAM"]["proposal"].get("depth")
    q = make_plan(T1, {"probes": ["led", "count"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "phase", "op": "==", "value": 0}]}, "pre": 1000, "post": 3000}, bram_budget=2)
    br = next(x for x in q["errors"] if x["what"] == "block RAM")
    assert br["proposal"]["keep"][0] == "u_dut.phase"            # the trigger probe is kept by any cut


def test_port_limit_cut_keeps_trigger_probes() -> None:
    p = make_plan(T1, COUNT_WRITE, max_ports=1)
    e = next(x for x in p["errors"] if x["what"] == "ports")
    assert "limit is 1" in e["why"] and "u_shell.u_core.win_wr" in e["proposal"]["keep"]


SRC2 = """
module top2 (input logic clk_a, input logic clk_b, input logic d, output logic qa, output logic qb);
  always_ff @(posedge clk_a) qa <= d;
  always_ff @(posedge clk_b) qb <= d;
endmodule
"""


def test_two_clock_domains_are_cut_to_the_trigger_domain(tmp_path: Path) -> None:
    f = tmp_path / "top2.sv"
    f.write_text(SRC2)
    idx = RtlIndex.from_files([f], "top2")
    p = make_plan(T1, {"probes": ["qb"], "trigger": {"combine": "AND", "conditions": [{"signal": "qa", "op": "rise"}]}},
                  index=idx)
    e = next(x for x in p["errors"] if x["what"] == "clock domains")
    assert e["proposal"]["keep_domain"] == "clk_a" and e["proposal"]["drop"] == ["qb"]


def test_unknown_register_in_stimulus() -> None:
    p = make_plan(T1, {**COUNT_WRITE, "stimulus": [{"op": "write", "register": "FIFO_CTRL", "value": 1}]})
    e = next(x for x in p["errors"] if x["what"].startswith("stimulus"))
    assert "COUNT" in e["suggestions"]


def test_intent_schema_is_enforced() -> None:
    with pytest.raises(PlanError):
        make_plan(T1, {"probes": "count", "trigger": {"combine": "AND", "conditions": []}})
    with pytest.raises(PlanError):
        make_plan(T1, {"probes": [], "trigger": {"combine": "XOR", "conditions": []}})


def test_find_build_reuses_a_build_that_holds_the_probes(tmp_path: Path) -> None:
    import json as _json
    from debug_core.build import find_build
    big = make_plan(T1, {**COUNT_WRITE, "probes": ["count", "led"]})
    small = make_plan(T1, {"probes": ["count"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "win_wr", "op": "rise"}]}, "pre": 4, "post": 8})
    for p in (big, small):
        p["design"] = str(tmp_path)
    assert find_build(small) is None
    b = tmp_path / "build" / "debug" / big["probeset"] / "build" / "ila"
    b.mkdir(parents=True)
    (b.parents[1] / "plan.json").write_text(_json.dumps(big))
    (b / "prepare.json").write_text(_json.dumps({"top": "top"}))
    assert find_build(small) is None                       # not finished: no bitstream yet
    for f in ("top.bit", "top.ltx", "probe_map.txt"):
        (b / f).write_text("x")
    ov, labels = find_build(small)
    assert ov.name == big["probeset"] and labels == {"win_wr": "win_wr", "count": "count"}
    deep = make_plan(T1, {**small_intent(), "pre": 3000, "post": 3000})
    deep["design"] = str(tmp_path)
    assert find_build(deep) is None                        # the build is only 1024 deep


def small_intent() -> dict:
    return {"probes": ["count"], "trigger": {"combine": "AND", "conditions": [{"signal": "win_wr", "op": "rise"}]}}
