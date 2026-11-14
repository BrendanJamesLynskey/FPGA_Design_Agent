"""The joint closure loop: area and power playbooks, the joint planner, the early check after synthesis, the sign-off,
loop-back to an earlier stage and the action log (no Vivado, no model: recorded c13 reports and fakes)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent.graph import closure as cl
from agent.graph import closure_plan as cp
from agent.graph import closure_playbook as pb
from flow.digest.build import digest_build

FX = Path(__file__).parent / "fixtures" / "closure"
C13 = FX / "c13_orig" / "reports"
SPEC = {"top": "c13_hough_lines_top", "clocks": [{"name": "clk", "freq_mhz": 100}]}


@pytest.fixture(scope="module")
def dg():
    d = digest_build(C13)
    d["timing"]["wns_ns"] = 0.6                         # timing met: these tests are about area and power
    d["drc"] = {"errors": 0, "critical_warnings": 0, "warnings": 0, "rules": []}
    d["methodology"] = {"errors": 0, "critical_warnings": 0, "warnings": 2, "rules": []}
    return d


def vec_of(dg, budget=None, g1=True):
    return cl.goal_vector({"pass": g1, "tests": {"t": g1}}, dg, cl.goals_from_spec({**SPEC, "budget": budget or {}}))


# --- playbook ------------------------------------------------------------------------------------------------------

def test_area_strategies_prefer_hard_resources(dg):
    v = vec_of(dg, {"bram": 1})
    assert v["G3"]["met"] is False and pb.over_budget(v) == {"bram_tile": 2.0}
    ids = [s.id for s, _ in pb.applicable("G3", dg, v)]
    assert ids[0] == "a_bram_merge" and "a_lutram" in ids          # keep the data in block RAM first; LUT RAM second
    v2 = vec_of(dg, {"bram": 1, "lut": 3000})                       # LUT over budget too: no room for LUT RAM
    assert "a_lutram" not in [s.id for s, _ in pb.applicable("G3", dg, v2)]


def test_dsp_and_register_strategies(dg):
    d = copy.deepcopy(dg)
    d["utilization"]["dsp"] = 4
    v = vec_of(d, {"dsp": 2})
    assert [s.id for s, _ in pb.applicable("G3", d, v)][:2] == ["a_dsp_share", "a_lut_mult"]
    d["synth"] = {**d["synth"], "ram_in_registers": ["mem"]}
    assert pb.applicable("G3", d, vec_of(d, {"dsp": 2}))[0][0].id == "a_ram"


def test_power_strategies_from_components(dg):
    v = vec_of(dg, {"power_w": 0.14})
    assert v["G4"]["met"] is False
    got = {s.id: why for s, why in pb.applicable("G4", dg, v)}
    assert "p_gate" in got and "p_ce" in got                      # signals + logic are 61 % of c13's dynamic power
    d = copy.deepcopy(dg)
    d["power"]["components"]["Block RAM"] = 0.012
    assert pb.applicable("G4", d, v)[0][0].id == "p_bram_en"
    assert "p_clock" not in got                                   # gated: the spec states no lower clock


def test_checks_strategies(dg):
    d = copy.deepcopy(dg)
    d["methodology"] = {"errors": 0, "critical_warnings": 1, "rules": [
        {"rule": "TIMING-18", "severity": "Critical Warning", "description": "Missing input or output delay", "count": 3}]}
    v = vec_of(d)
    assert v["CHK"]["met"] is False and "TIMING-18" in v["CHK"]["detail"]
    s = pb.applicable("CHK", d, v)[0][0]
    assert s.id == "c_constraints" and s.stage == "constraints"


# --- joint planner -------------------------------------------------------------------------------------------------

def test_joint_plan_one_fix_per_goal(dg):
    d = copy.deepcopy(dg)
    v = vec_of(d, {"bram": 1, "power_w": 0.14})
    p = cp.plan(v, d, SPEC)
    goals = [a["goal"] for a in p["actions"]]
    assert sorted(goals) == ["G3", "G4"] and p["target_stage"] == "rtl"
    assert p["actions"][goals.index("G3")]["id"] == "a_bram_merge"
    kinds = {x["kind"] for x in p["violations"]}
    assert {"over_bram_tile", "power"} <= kinds


def test_joint_plan_skips_conflicting_fixes(dg):
    d = copy.deepcopy(dg)
    d["timing"]["wns_ns"] = -0.4
    v = vec_of(d, {"ff": 1900})                                   # FF over budget and timing failing
    p = cp.plan(v, d, SPEC)
    ids = [a["id"] for a in p["actions"]]
    assert "t_pipeline" not in ids                               # pipelining adds FFs, which are over budget
    assert "ff, which is over budget" in cp.conflict(pb.BY_ID["t_pipeline"], "G2", v, [])
    # two fixes that push a tight resource opposite ways are not combined
    assert "dsp the other way from t_dsp_map" in cp.conflict(pb.BY_ID["a_dsp_share"], "G3", vec_of(d), [pb.BY_ID["t_dsp_map"]])
    # a fix that costs slack is not offered while timing fails
    s = pb.BY_ID["a_lut_mult"]
    assert "slack" in cp.conflict(s, "G3", v, [])


def test_plan_goes_back_to_spec(dg):
    d = copy.deepcopy(dg)
    d["utilization"]["iob"] = 30
    v = vec_of(d, {"io": 20})
    p = cp.plan(v, d, SPEC)
    assert p["target_stage"] == "spec" and [a["id"] for a in p["actions"]] == ["a_io"]
    r = cp.reentry(p)
    assert r["stage"] == 0 and r["note_role"] == "clarify" and "a design that needs" not in r["note"]
    assert set(r) == {"stage", "note", "note_role", "owners"}           # the state shape of agent.graph.pickup.prepare


def test_exhausted_class_is_not_offered(dg):
    v = vec_of(dg, {"bram": 1})
    p = cp.plan(v, dg, SPEC, exhausted={("G3", "bram_merge")})
    assert p["actions"][0]["id"] == "a_lutram"


# --- early check ---------------------------------------------------------------------------------------------------

def _syn(**u):
    base = {"lut": 3000, "ff": 1900, "bram_tile": 2, "dsp": 0, "iob": 20, "carry4": 49}
    return {"ran": True, "utilization": {**base, **u}, "timing": {"wns_ns": -1.0}, "synth": {}}


def test_early_check(dg):
    d = copy.deepcopy(dg)
    d["post_synth"] = {"utilization": {"bram_tile": 2, "dsp": 0, "lut": 3100, "ff": 1919}}
    v = vec_of(d, {"bram": 1})
    acts = [(pb.BY_ID["a_bram_merge"], "G3", "")]
    g = cl.goals_from_spec({**SPEC, "budget": {"bram": 1}})
    e = cl.early_check(_syn(bram_tile=2), d, v, g, acts, None, {})
    assert e["reject"] and "a_bram_merge was to lower bram_tile" in e["reason"]
    assert not cl.early_check(_syn(bram_tile=1), d, v, g, acts, None, {})["reject"]
    # timing after synthesis is an estimate: never a reason to reject
    assert not cl.early_check(_syn(bram_tile=1), d, v, g, acts, None, {})["estimate"]["wns_est_ns"] is None
    # a DSP count over a budget that was met is final after synthesis
    g2 = cl.goals_from_spec({**SPEC, "budget": {"bram": 1, "dsp": 0}})
    e2 = cl.early_check(_syn(bram_tile=1, dsp=2), d, v, g2, acts, None, {})
    assert e2["reject"] and "dsp" in e2["reason"] and e2["worsened"] == ["G3"]
    # new multi-driven nets: the netlist is not the simulated design
    s = _syn(bram_tile=1)
    s["synth"] = {"multi_driven": 2}
    assert cl.early_check(s, d, v, g, acts, None, {"multi_driven": 0})["worsened"] == ["G1"]


# --- the controller ------------------------------------------------------------------------------------------------

class Builds:
    """A fake flow: each full build returns the next utilisation; synthesis-only builds are counted."""

    def __init__(self, dg, brams):
        self.dg, self.brams, self.full, self.synth = dg, list(brams), 0, 0

    def build(self, d):
        x = copy.deepcopy(self.dg)
        x["utilization"]["bram_tile"] = self.brams[min(self.full, len(self.brams) - 1)]
        x["post_synth"] = {"utilization": dict(x["utilization"])}
        self.full += 1
        return x

    def syn(self, d):
        self.synth += 1
        return _syn(bram_tile=self.brams[min(self.full, len(self.brams) - 1)])


def _ws(tmp_path):
    (tmp_path / "rtl").mkdir(parents=True)
    for f in (FX / "c13_orig" / "rtl").glob("*.sv"):
        (tmp_path / "rtl" / f.name).write_text(f.read_text())
    (tmp_path / "design.xdc").write_text("create_clock -period 10 [get_ports clk]\n")
    return cl.Workspace(tmp_path)


def _editor(log=None):
    n = {"i": 0}

    def edit(req):
        n["i"] += 1
        if log is not None:
            log.append(req)
        p = next(p for p in req.files if p.endswith(".sv"))
        return cl.EditResult(files={p: req.files[p] + f"\n// edit {n['i']}\n"}, note="x", usd=0.01, tokens=10, calls=1)
    return edit


def test_joint_loop_closes_area_with_signoff_and_action_log(tmp_path, dg):
    ws = _ws(tmp_path)
    b = Builds(dg, [2, 1, 1])
    reqs = []
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({**SPEC, "budget": {"bram": 1}}), g1=lambda r: {"pass": True, "tests": {"t": True}},
                   build=b.build, editor=_editor(reqs), contract="keep", spec=SPEC, synth=b.syn,
                   signoff=lambda _dg: {"pass": True, "failed": []}, record=tmp_path / "rec", case="t", log=lambda s: None)
    r = c.run()
    assert r["closure_claimed"] and r["accepted"] == 1 and r["strategies"] == [("a_bram_merge", "accept")]
    assert b.synth == 1 and b.full == 2                            # start build, one attempt; sign-off reuses the accepted build
    assert r["signoff"]["pass"] and not r["signoff"]["rebuilt"]
    rows = [json.loads(l) for l in (tmp_path / "rec" / "closure_actions.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["schema"] == cp.SCHEMA
    row = rows[0]
    assert row["actions"][0]["id"] == "a_bram_merge" and row["actions"][0]["hard"] is True
    assert row["features"]["bram_tile_budget_ratio"] == 2.0 and row["result"]["decision"] == "accept"
    assert row["result"]["goals_after"]["G3"]["met"] is True and row["design"]["memories"] >= 1
    assert "rtl/hough.sv" in reqs[0].files and "design.xdc" not in reqs[0].files   # an RTL fix: the XDC is not offered


def test_early_reject_skips_implementation(tmp_path, dg):
    ws = _ws(tmp_path)
    b = Builds(dg, [2])                                            # synthesis keeps showing 2 BRAM tiles
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({**SPEC, "budget": {"bram": 1}}), g1=lambda r: {"pass": True},
                   build=b.build, editor=_editor(), contract="", spec=SPEC, synth=b.syn, max_iter=2,
                   signoff=lambda _dg: {"pass": True, "failed": []}, log=lambda s: None)
    r = c.run()
    assert b.full == 1 and b.synth == 2 and r["early_rejected"] == 2 and not r["closure_claimed"]
    assert "// edit" not in (ws.rtl / "hough.sv").read_text()        # both rejected changes were reverted


def test_signoff_failure_is_not_claimed(tmp_path, dg):
    ws = _ws(tmp_path)
    b = Builds(dg, [2, 1])
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec({**SPEC, "budget": {"bram": 1}}), g1=lambda r: {"pass": True},
                   build=b.build, editor=_editor(), contract="", spec=SPEC, synth=b.syn,
                   signoff=lambda _dg: {"pass": False, "failed": ["bitstream_base"]}, log=lambda s: None)
    r = c.run()
    assert r["all_met"] and not r["closure_claimed"] and "sign-off failed: bitstream_base" in r["stop"]


def test_no_signoff_never_claims(tmp_path, dg):
    b = Builds(dg, [2, 1])
    c = cl.Closure(ws=_ws(tmp_path), goals=cl.goals_from_spec({**SPEC, "budget": {"bram": 1}}), g1=lambda r: {"pass": True},
                   build=b.build, editor=_editor(), contract="", spec=SPEC, log=lambda s: None)
    r = c.run()
    assert r["all_met"] and not r["closure_claimed"] and "sign-off not run" in r["stop"]


def test_signoff_rebuilds_after_a_reverted_attempt(tmp_path, dg):
    """Accepted at iteration 1 (BRAM 1 of 1, power still over), reverted at iteration 2: build/ then holds the reverted
    attempt, so the sign-off must rebuild the accepted files before it reads any gate."""
    ws = _ws(tmp_path)
    seq = iter([(2, 0.150), (1, 0.150), (1, 0.151), (1, 0.130), (1, 0.130)])
    n = {"full": 0}

    def build(d):
        x = copy.deepcopy(dg)
        x["utilization"]["bram_tile"], x["power"]["total_w"] = next(seq)
        n["full"] += 1
        return x
    g = cl.goals_from_spec({**SPEC, "budget": {"bram": 1, "power_w": 0.140}})
    c = cl.Closure(ws=ws, goals=g, g1=lambda r: {"pass": True}, build=build, editor=_editor(), contract="", spec=SPEC,
                   max_iter=3, joint=False, signoff=lambda _dg: {"pass": True, "failed": []}, log=lambda s: None)
    r = c.run()
    assert [d for _, d in r["strategies"]] == ["accept", "revert", "accept"]
    assert r["closure_claimed"] and r["signoff"]["rebuilt"] is False     # the last attempt was accepted: no rebuild
    c2 = cl.Closure(ws=_ws(tmp_path / "b"), goals=g, g1=lambda r: {"pass": True}, build=build, editor=_editor(),
                    contract="", spec=SPEC, signoff=lambda _dg: {"pass": True}, log=lambda s: None)
    assert c2._signoff(None, {"a": "1"}, {"a": "2"})["rebuilt"] is True


def test_loop_stops_with_reentry_for_a_spec_fix(tmp_path, dg):
    d = copy.deepcopy(dg)
    d["utilization"]["iob"] = 30
    c = cl.Closure(ws=_ws(tmp_path), goals=cl.goals_from_spec({**SPEC, "budget": {"io": 20}}), g1=lambda r: {"pass": True},
                   build=lambda _d: copy.deepcopy(d), editor=_editor(), contract="", spec=SPEC, log=lambda s: None)
    r = c.run()
    assert r["stop"].startswith("loop back to the spec stage") and r["reentry"]["stage"] == 0 and r["iterations"] == 0


def test_digest_reads_drc_and_methodology(tmp_path):
    g = json.loads((C13 / "gates.json").read_text())
    g["drc"] = {"errors": 1, "critical_warnings": 0, "warnings": 0,
                "rules": [{"rule": "NSTD-1", "severity": "Error", "description": "Unspecified I/O Standard", "count": 2}]}
    g["methodology"] = {"errors": 0, "critical_warnings": 0, "warnings": 0, "rules": []}
    g["stages"] = {"post_synth": {"ran": True, "utilization": {"bram_tile": 2}, "timing": {"wns_ns": 0.1}}}
    (tmp_path / "gates.json").write_text(json.dumps(g))
    d = digest_build(tmp_path)
    assert d["drc"]["errors"] == 1 and d["post_synth"]["utilization"]["bram_tile"] == 2
    v = cl.goal_vector({"pass": True}, d, cl.goals_from_spec(SPEC))
    assert v["CHK"]["met"] is False and not cl.all_met(v)
    assert pb.applicable("CHK", d, v)[0][0].id == "c_constraints"


# --- review fixes: no closure by a slower clock, and no sign-off on a synthesis-only build ---------------------------

def test_timing_is_judged_at_the_spec_clock(dg):
    d = copy.deepcopy(dg)
    d["timing"]["period_ns"] = 12.0                    # the XDC was slowed to 83 MHz: WNS looks fine
    v = vec_of(d)
    assert v["G2"]["met"] is False and "slower than the spec's 10.0 ns" in v["G2"]["detail"]
    spec = {**SPEC, "clocks": [{"name": "clk", "freq_mhz": 100, "min_freq_mhz": 80}]}
    assert cl.goal_vector({"pass": True}, d, cl.goals_from_spec(spec))["G2"]["met"] is True   # the spec allows 80 MHz


def test_clock_edit_is_reverted(tmp_path, dg):
    ws = _ws(tmp_path)
    assert cl.clock_lines_changed({"design.xdc": "create_clock -period 10 [get_ports clk]\n"},
                                  {"design.xdc": "create_clock -period 12 [get_ports clk]\n"})
    assert not cl.clock_lines_changed({"design.xdc": "create_clock -period 10 x\n"},
                                      {"design.xdc": "create_clock -period 10 x\nset_property IOSTANDARD LVCMOS33 [get_ports a]\n"})
    d = copy.deepcopy(dg)
    d["methodology"] = {"errors": 0, "critical_warnings": 1, "rules": [
        {"rule": "TIMING-18", "severity": "Critical Warning", "description": "Missing input or output delay", "count": 3}]}

    def edit(req):
        assert "design.xdc" in req.files                   # a constraints fix: the XDC is offered
        return cl.EditResult(files={"design.xdc": "create_clock -period 20 [get_ports clk]\n"}, usd=0.0, calls=1)
    c = cl.Closure(ws=ws, goals=cl.goals_from_spec(SPEC), g1=lambda r: {"pass": True}, build=lambda _d: copy.deepcopy(d),
                   editor=edit, contract="", spec=SPEC, max_iter=1, record=tmp_path / "rec", log=lambda s: None)
    r = c.run()
    assert r["strategies"] == [("c_constraints", "revert")] and "-period 10" in (tmp_path / "design.xdc").read_text()
    row = json.loads((tmp_path / "rec" / "closure_actions.jsonl").read_text().splitlines()[0])
    assert row["result"]["outcome"] == "clock_edit" and row["result"]["worsened"] == ["G2"]


def test_gates_signoff_needs_a_routed_build(tmp_path):
    from agent.graph.closure_task import gates_signoff
    b = tmp_path / "build" / "base"
    b.mkdir(parents=True)
    (b / "gates.json").write_text(json.dumps({"pass": True, "gates": {"post_synth_drc_clean": True},
                                              "stages": {"post_synth": {"ran": True}, "post_route": {"ran": False}}}))
    s = gates_signoff(tmp_path)({})
    assert not s["pass"] and "stage post_route not run" in s["failed"]
    (b / "gates.json").write_text(json.dumps({"pass": True, "gates": {"a": True},
                                              "stages": {"post_route": {"ran": True}, "bitstream": {"ran": True}}}))
    assert gates_signoff(tmp_path)({})["pass"]


def test_action_log_outcomes(tmp_path, dg):
    b = Builds(dg, [2])
    c = cl.Closure(ws=_ws(tmp_path), goals=cl.goals_from_spec({**SPEC, "budget": {"bram": 1}}), g1=lambda r: {"pass": True},
                   build=b.build, editor=_editor(), contract="", spec=SPEC, synth=b.syn, max_iter=1,
                   record=tmp_path / "rec", log=lambda s: None)
    c.run()
    row = json.loads((tmp_path / "rec" / "closure_actions.jsonl").read_text().splitlines()[0])
    assert row["result"]["outcome"] == "early_reject" and row["result"]["improved"] == []
    assert row["design"]["rtl_files"] == 3                     # RTL only, not the XDC
