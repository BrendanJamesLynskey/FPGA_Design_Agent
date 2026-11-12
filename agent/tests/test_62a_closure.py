"""Brief 62A: report digests, the design-time plan, the goal vector and the closure controller (no Vivado, no model)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from agent.graph import closure as cl
from agent.graph import closure_playbook as pb
from flow import timing_plan as tp
from flow.digest import power, synth, timing, utilization
from flow.digest.build import digest_build, digest_text

FX = Path(__file__).parent / "fixtures" / "closure"
C13 = FX / "c13_orig" / "reports"
MODEL = FX / "delay_model_test.yaml"


@pytest.fixture(scope="module")
def dg():
    return digest_build(C13)


# --- digests ------------------------------------------------------------------------------------------------------

def test_c13_critical_path(dg):
    p = dg["setup_path"]
    assert p["slack_ns"] == -0.166 and p["data_path_ns"] == 10.165 and p["logic_levels"] == 13
    assert p["levels_by_type"] == {"CARRY4": 7, "LUT4": 2, "LUT5": 2, "LUT6": 2}
    assert p["source_reg"] == {"instance": "u_regs/u_core", "signal": "k", "bit": 2}
    assert p["dest_reg"]["signal"] == "rho_r" and p["dest_reg"]["bit"] == 15
    assert [n["fanout"] for n in p["nets"]][:2] == [103, 8]
    f = dg["setup_features"]
    assert f["lut_arith"] and f["high_fanout"] and not f["dsp_on_path"] and f["same_instance"]
    assert dg["timing"]["period_ns"] == 10.0 and dg["timing"]["wns_ns"] == -0.166


def test_hold_path_parses():
    h = timing.parse_paths((C13 / "timing_worst_hold.rpt").read_text())
    assert h and h[0]["kind"] == "hold" and h[0]["met"]


def test_utilization_and_power(dg):
    rows = utilization.parse_hier((C13 / "utilization_hier.rpt").read_text())
    assert rows[0]["lut"] == 3069 and rows[0]["ramb36"] == 2
    assert dg["hier_modules"]["u_regs/u_core"] == "hough"
    assert dg["util_top"]["lut"][0]["path"] == "u_regs/u_core" and dg["util_top"]["lut"][0]["lut"] == 2699
    comp = power.parse_components((C13 / "power.rpt").read_text())
    assert comp["Total"] == 0.15 and comp["Static Power"] == 0.114
    hier = power.parse_hierarchy((C13 / "power.rpt").read_text())
    assert hier[0] == {"name": "c13_hough_lines_top", "depth": 0, "power_w": 0.036} and hier[2]["name"] == "u_core"
    text = digest_text(dg, "G2")
    assert text.startswith("TIMING: WNS -0.166") and "RTL signal k" in text and "DSP 0/240" in text


def test_synth_scan():
    log = ("WARNING: [Synth 8-327] inferring latch for variable 'q_reg' [x.sv:3]\n"
           "WARNING: [Synth 8-4767] Trying to implement RAM 'mem_reg' in registers. Block RAM or DRAM implementation is not possible\n")
    s = synth.scan(log)
    assert s == {"latches": ["q_reg"], "ram_in_registers": ["mem_reg"], "clean": False}
    assert synth.scan("INFO: nothing")["clean"]


# --- goals and the vector ------------------------------------------------------------------------------------------

def test_goal_defaults_and_vector(dg):
    spec = {"clocks": [{"name": "sys", "freq_mhz": 100}], "budget": {"dsp": 4}}
    g = cl.goals_from_spec(spec)
    assert g["G3"]["budget"]["dsp"] == 4 and g["G3"]["budget"]["lut"] == 63400 * 0.8
    assert "default 80 %" in g["G3"]["why"]["lut"] and g["G4"]["power_w"] == 2.0
    v = cl.goal_vector({"pass": True, "tests": {"a": True}}, dg, g)
    assert v["G1"]["met"] and not v["G2"]["met"] and v["G3"]["met"] and v["G4"]["met"] and v["G5"]["met"] is None
    assert v["G2"]["shortfall"] == pytest.approx(0.0166)
    assert cl.choose_goal(v) == "G2"


def test_g3_over_budget_and_latch(dg):
    g = cl.goals_from_spec({"clocks": [{"freq_mhz": 100}], "budget": {"lut": 2000}})
    v = cl.goal_vector({"pass": True}, dg, g)
    assert not v["G3"]["met"] and v["G3"]["shortfall"] == pytest.approx(3069 / 2000 - 1, abs=1e-4)
    d2 = copy.deepcopy(dg)
    d2["synth"] = {"latches": ["x"], "ram_in_registers": [], "clean": False}
    v2 = cl.goal_vector({"pass": True}, d2, cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}))
    assert not v2["G3"]["met"] and "latches" in v2["G3"]["detail"]


def _vec(wns, ff=2000, g1=True, ffb=126800 * 0.8):
    g = cl.goals_from_spec({"clocks": [{"freq_mhz": 100}], "budget": {"ff": ffb}})
    dgx = {"ran": True, "timing": {"wns_ns": wns, "whs_ns": 0.04, "period_ns": 10.0}, "gates": {},
           "utilization": {"lut": 3000, "ff": ff, "bram_tile": 2, "dsp": 0, "iob": 20}, "power": {"total_w": 0.15, "junction_c": 40}}
    return cl.goal_vector({"pass": g1}, dgx, g)


def test_judge():
    assert cl.judge(_vec(-0.166), _vec(-0.05))[0] == "accept"
    assert cl.judge(_vec(-0.166), _vec(0.3, ff=2100))[0] == "accept"           # FFs up but still inside the budget
    assert cl.judge(_vec(-0.166), _vec(-0.3))[0] == "revert"
    assert cl.judge(_vec(-0.166), _vec(-0.166))[0] == "revert"                 # no progress
    d, imp, wor = cl.judge(_vec(-0.166, ffb=2050), _vec(0.1, ff=2100, ffb=2050))
    assert d == "revert" and wor == ["G3"] and imp == ["G2"]                  # timing bought with a broken area budget


# --- the playbook ---------------------------------------------------------------------------------------------------

def test_playbook_c13_order(dg):
    v = cl.goal_vector({"pass": True}, dg, cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}))
    ids = [s.id for s, _ in pb.applicable("G2", dg, v)]
    assert ids[:3] == ["t_dsp_map", "t_pipeline", "t_fanout"]
    assert "t_exception" not in ids                                           # no multicycle protocol in the spec
    ids2 = [s.id for s, _ in pb.applicable("G2", dg, v, plan_fails=["plan: x"])]
    assert ids2[0] == "t_plan_map"
    v0 = cl.goal_vector({"pass": True}, dg, cl.goals_from_spec({"clocks": [{"freq_mhz": 100}], "budget": {"dsp": 0}}))
    assert "t_dsp_map" not in [s.id for s, _ in pb.applicable("G2", dg, v0)]   # no DSP headroom: not offered
    assert pb.applicable("G3", dg, v) == []                                    # area strategies are 62B


# --- the controller -------------------------------------------------------------------------------------------------

class FakeBuild:
    def __init__(self, base, wns_seq):
        self.base, self.wns, self.n = base, list(wns_seq), 0

    def __call__(self, d):
        x = copy.deepcopy(self.base)
        x["timing"]["wns_ns"] = self.wns[min(self.n, len(self.wns) - 1)]
        self.n += 1
        return x


def _ws(tmp_path):
    (tmp_path / "rtl").mkdir()
    for f in (FX / "c13_orig" / "rtl").glob("*.sv"):
        (tmp_path / "rtl" / f.name).write_text(f.read_text())
    return cl.Workspace(tmp_path)


def _editor(seq):
    it = iter(seq)

    def edit(req):
        tag = next(it)
        assert "rtl/hough.sv" in req.files and "c13_hough_lines_top" not in "".join(req.files)   # only the path's file
        txt = req.files["rtl/hough.sv"] + f"\n// edit {tag}\n"
        return cl.EditResult(files={"rtl/hough.sv": txt}, note=f"edit {tag}", usd=0.01, tokens=100, calls=1)
    return edit


def test_closure_closes_and_records(tmp_path, dg):
    ws = _ws(tmp_path)
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}), g1=lambda r: {"pass": True, "tests": {"t": True}},
                   build=FakeBuild(dg, [-0.166, 0.35]), editor=_editor([1]), contract="keep ports", record=tmp_path / "rec",
                   log=lambda s: None)
    r = c.run()
    assert r["all_met"] and r["iterations"] == 1 and r["accepted"] == 1 and r["strategies"] == [("t_dsp_map", "accept")]
    hist = [json.loads(l) for l in (tmp_path / "rec" / "history.jsonl").read_text().splitlines()]
    assert hist[1]["delta"]["G2"]["wns_ns"] == pytest.approx(0.516) and "+// edit 1" in hist[1]["diff"]
    assert "// edit 1" in (ws.rtl / "hough.sv").read_text()


def test_closure_reverts_and_stalls(tmp_path, dg):
    ws = _ws(tmp_path)
    orig = (ws.rtl / "hough.sv").read_text()
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}), g1=lambda r: {"pass": True},
                   build=FakeBuild(dg, [-0.166, -0.3, -0.2, -0.4, -0.5, -0.6, -0.7, -0.8, -0.9, -1, -1, -1, -1, -1]),
                   editor=_editor(range(100)), contract="", max_iter=20, stall_n=2, log=lambda s: None)
    r = c.run()
    assert not r["all_met"] and r["accepted"] == 0 and (ws.rtl / "hough.sv").read_text() == orig      # every change reverted
    classes = [pb.BY_ID[s].cls for s, _ in r["strategies"]]
    assert all(classes.count(k) == 2 for k in set(classes))                     # the stall rule: two tries per class
    assert r["stop"] == "goal G2 not met; strategy classes exhausted"
    assert r["unmet_text"][0].startswith("goal G2 not met; best value {'wns_ns': -0.166")


def test_closure_g1_failure_retries_then_reverts(tmp_path, dg):
    ws = _ws(tmp_path)
    calls = {"g1": 0}

    def g1(_r):
        calls["g1"] += 1
        return {"pass": calls["g1"] == 1, "tests": {"t": calls["g1"] == 1}, "detail": "assert failed"}
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}), g1=g1, build=FakeBuild(dg, [-0.166]),
                   editor=_editor(range(10)), contract="", max_iter=1, log=lambda s: None)
    r = c.run()
    h = c.history[1]
    assert h["decision"] == "revert" and h["g1_retries"] == 1 and h["worsened"] == ["G1"]
    assert r["llm_calls"] == 2 and "// edit" not in (ws.rtl / "hough.sv").read_text()


def test_closure_refuses_without_g1(tmp_path, dg):
    c = cl.Closure(ws=_ws(tmp_path), goals=cl.goals_from_spec({"clocks": [{"freq_mhz": 100}]}), g1=lambda r: {"pass": False},
                   build=FakeBuild(dg, [0]), editor=_editor([]), contract="", log=lambda s: None)
    assert c.run()["stop"].startswith("G1 fails at the start")


def test_parse_reply():
    t = "x\n=== FILE: rtl/a.sv ===\n```systemverilog\nmodule a; endmodule\n```\n=== FILE: rtl/zz.sv ===\n```\nno\n```\nNOTE: one clock"
    files, note = cl.parse_reply(t, {"rtl/a.sv"})
    assert files == {"rtl/a.sv": "module a; endmodule\n"} and note == "one clock"


def test_contract_from_spec():
    spec = yaml.safe_load((Path(__file__).parents[2] / "benchmark/course/tasks/c13_hough_lines/hidden/spec.yaml").read_text())
    assert "BUSY is high for about 17 clocks" in cl.contract_from_spec(spec)


# --- the design-time plan -------------------------------------------------------------------------------------------

C13_ARCH = {
    "clock_domains": [{"name": "sys", "clock": "CLK100MHZ", "freq_mhz": 100}],
    "datapaths": [{"name": "rho", "clock": "sys", "instance": "u_regs/u_core", "ops": [
        {"name": "angle_table", "op": "table", "index_bits": 4, "width": 9},
        {"name": "x_cos", "op": "mul", "a_bits": 9, "b_bits": 9},
        {"name": "y_sin", "op": "mul", "a_bits": 9, "b_bits": 9, "parallel": True},
        {"name": "sum", "op": "add", "bits": 19, "inputs": 3},
        {"name": "shift", "op": "shift"},
        {"name": "offset", "op": "add", "bits": 16}]}],
}


def test_plan_c13_puts_multiplies_on_dsp():
    p = tp.plan(C13_ARCH, tp.load_model(path=MODEL))
    d = p["datapaths"][0]
    res = {o["name"]: o["resource"] for o in d["ops"]}
    assert res["x_cos"] == "dsp" and res["y_sin"] == "dsp" and res["sum"] == "carry" and p["planned"]["dsp"] == 2
    assert d["fits"] and all(s["est_ns"] <= d["budget_ns"] for s in d["stages"]) and d["budget_ns"] == 7.0
    assert d["unpipelined_est_ns"] > 10.0 and d["latency_cycles"] >= 2
    assert "dsp_mul_p2" in {o["template"] for o in d["ops"]}
    assert "stage 1" in tp.plan_text(p) and "DSP48E1" in tp.plan_text(p)


def test_plan_fallbacks_and_forced_latency():
    arch = {"clock_domains": [{"name": "s", "freq_mhz": 100}], "datapaths": [{"name": "d", "latency_fixed": 1, "ops": [
        {"name": "small", "op": "mul", "a_bits": 3, "b_bits": 12},
        {"name": "big", "op": "mul", "a_bits": 16, "b_bits": 16},
        {"name": "mem", "op": "memory", "depth": 1024, "width": 16},
        {"name": "tiny", "op": "memory", "depth": 16, "width": 8},
        {"name": "dl", "op": "delay", "depth": 12, "width": 4}]}]}
    p = tp.plan(arch, tp.load_model(path=MODEL), budget={"dsp": 0})
    ops = {o["name"]: o for o in p["datapaths"][0]["ops"]}
    assert ops["small"]["resource"] == "lut" and "too small" in ops["small"]["reason"]
    assert ops["big"]["resource"] == "lut" and "budget exhausted" in ops["big"]["reason"]
    assert ops["mem"]["resource"] == "bram" and ops["tiny"]["resource"] == "lutram" and ops["dl"]["resource"] == "srl"
    assert any("fixes the latency at 1" in x for x in p["problems"])


def test_check_datapaths_and_architecture_hook():
    from flow.architecture import check_architecture
    assert tp.check_datapaths({"datapaths": [{"name": "a", "ops": [{"name": "m", "op": "divide"}]}]})
    assert tp.check_datapaths({"datapaths": [{"name": "a", "ops": [{"name": "m", "op": "mul", "map": "lut"}]}]}) == [
        "datapaths[a].ops[m]: a map override needs a reason"]
    errs = check_architecture({"datapaths": "x"})
    assert "'datapaths' must be a list" in errs


def test_plan_check_after_synthesis_fails_c13_reference(tmp_path):
    p = tp.plan(C13_ARCH, tp.load_model(path=MODEL))
    rows = utilization.parse_hier((C13 / "utilization_hier.rpt").read_text())
    g = json.loads((C13 / "gates.json").read_text())
    fails = tp.check_post_synth(p, g["utilization"], rows)
    assert len(fails) == 1 and "instance u_regs/u_core has 0 DSP48E1" in fails[0] and "2 multiplies" in fails[0]
    rows[4]["dsp"] = 2                                         # the u_core row: as if the multiplies had mapped
    assert tp.check_post_synth(p, g["utilization"], rows) == []


def test_calibration_row(dg):
    p = tp.plan(C13_ARCH, tp.load_model(path=MODEL))
    rows = tp.compare_post_route(p, dg["setup_path"])
    assert rows and rows[0]["datapath"] == "rho" and rows[0]["measured_ns"] == pytest.approx(10.262) and rows[0]["miss"]


def test_plan_design_writes_files(tmp_path):
    (tmp_path / "architecture.yaml").write_text(yaml.safe_dump(C13_ARCH))
    r = tp.plan_design(tmp_path, tp.load_model(path=MODEL))
    assert r["ok"] and (tmp_path / tp.PLAN_MD).is_file() and tp.load_plan(tmp_path)["planned"]["dsp"] == 2
    (tmp_path / "architecture.yaml").write_text(yaml.safe_dump({"clock_domains": C13_ARCH["clock_domains"]}))
    assert tp.plan_design(tmp_path, tp.load_model(path=MODEL)) == {"ok": True, "problems": [], "plan": None}


def test_stage_hooks():
    from agent.graph.stages import MACHINE, classify, exit_check
    st = MACHINE[4]
    gates = {"stages": {"post_synth": {"ran": True, "gates": {"post_synth_drc_clean": True}}}}
    ok, why = exit_check(st, {"gates_base": gates, "standards": {"rules": []}, "plan_fails": ["plan: instance x has 0 DSP48E1"]})
    assert not ok and "plan: instance x has 0 DSP48E1" in why
    assert classify(st, why) == "rtl"
    ok2, _ = exit_check(st, {"gates_base": gates, "standards": {"rules": []}})
    assert ok2
