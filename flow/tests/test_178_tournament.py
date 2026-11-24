"""Brief 178: the tournament's ranking, memory admission, report parser and Tcl. No Vivado is run."""
from pathlib import Path

from flow import tournament as t

TS = """Design Timing Summary
| ---------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------
      {w}        0.000                      0                  100        0.227        0.000                      0                  100
"""
UT = "| Slice LUTs*  |  {l} |     0 |     63400 |  0.10 |\n| Slice Registers |  {f} |     0 |    126800 |  0.10 |\n| DSPs |  2 |     0 |   240 |  0.8 |\n"


def cand(i, w, lut=100, ff=100, lv=5, order=0, status="ok"):
    return {"id": i, "wns_ns": w, "lut": lut, "ff": ff, "levels": lv, "order": order, "status": status}


def test_score_key_buckets_wns_then_area_then_default_first():
    cs = [cand("default", 0.50, order=0), cand("small", 0.52, lut=80, order=2), cand("fast", 0.80, lut=300, order=1), cand("bad", None, status="error: x", order=3)]
    r = t.rank(cs, 1)
    assert [c["id"] for c in r] == ["fast", "default", "small", "bad"] or [c["id"] for c in r][0] == "fast"
    # 0.50 and 0.52 share a 0.05 ns bucket: area decides, so "small" (80 LUT) beats "default"
    assert [c["id"] for c in r].index("small") < [c["id"] for c in r].index("default")
    assert r[-1]["id"] == "bad" and "run failed" in r[-1]["dropped_because"]
    assert r[0]["kept"] and not r[1]["kept"] and "behind rank 1" in r[1]["dropped_because"]


def test_complete_tie_keeps_the_default():
    r = t.rank([cand("a", 0.5, order=1), cand("default", 0.5, order=0)], 1)
    assert r[0]["id"] == "default"


def test_may_launch_rules():
    assert t.may_launch([], 2.0, 11.0)[0]                       # 2 + 8 = 10 <= 11
    assert not t.may_launch([2.0], 2.0, 11.0)[0]                # 4 + 8 = 12 > 11
    assert not t.may_launch([2.0] * 4, 2.0, 99.0)[0]            # never more than 4
    assert t.may_launch([2.0] * 3, 2.0, 99.0)[0]
    ok, why = t.may_launch([], 3.0, 99.0)                       # a child above 2 GiB is not light class
    assert not ok and "light class" in why


def test_run_children_never_exceeds_limit_and_admits_by_memory():
    live, peak = [], [0]

    class P:
        def __init__(self, cmd, **k):
            self.n = 0
            live.append(self)
            peak[0] = max(peak[0], len([p for p in live if p.poll() is None]))

        def poll(self):
            self.n += 1
            return None if self.n < 3 else 0

    jobs = [{"tcl": Path(f"/x{i}.tcl"), "log": Path(f"/x{i}.log")} for i in range(7)]
    t.run_children(jobs, 2.0, 4, poll_s=0, launch=P, avail=lambda: 99.0)
    assert len(live) == 7 and peak[0] <= 4
    live.clear(); peak[0] = 0
    jobs = [{"tcl": Path(f"/y{i}.tcl"), "log": Path(f"/y{i}.log")} for i in range(4)]
    t.run_children(jobs, 2.0, 4, poll_s=0, launch=P, avail=lambda: 12.5)   # 2 children fit: 2+2+8 = 12 <= 12.5, a third needs 14
    assert len(live) == 4 and peak[0] <= 2


def test_parse_reports(tmp_path):
    (tmp_path / "utilization.rpt").write_text(UT.format(l=120, f=80))
    (tmp_path / "timing_summary.rpt").write_text(TS.format(w="-0.213"))
    (tmp_path / "worst_path.rpt").write_text("    Logic Levels:           7  (CARRY4=3 LUT2=2)\n")
    (tmp_path / "done.txt").write_text("41\n")
    r = t.parse(tmp_path)
    assert (r["status"], r["lut"], r["ff"], r["dsp"], r["wns_ns"], r["whs_ns"], r["levels"], r["runtime_s"]) == ("ok", 120, 80, 2, -0.213, 0.227, 7, 41)
    (tmp_path / "error.txt").write_text("boom\nmore")
    assert t.parse(tmp_path)["status"] == "error: boom"


def test_synth_tcl_one_thread_ooc_and_options(tmp_path):
    spec = {"part": "xc7a100tcsg324-1", "top": "adder", "clock_ns": 5.0, "files": ["/a.sv"], "generics": {"WIDTH": 32}, "fanout_nets": ["u/n1"]}
    c = next(m for m in t.SYNTH_MENU if m["id"] == "perf_retime")
    s = t.synth_tcl(spec, c, tmp_path)
    assert "synth.maxThreads 1" in s and "-mode out_of_context -directive PerformanceOptimized -retiming -generic WIDTH=32" in s
    f = t.synth_tcl(spec, next(m for m in t.SYNTH_MENU if m["id"] == "fanout_nets"), tmp_path)
    assert "MAX_FANOUT 50" in f


def test_impl_tcl_directives(tmp_path):
    s = t.impl_tcl(tmp_path / "x.dcp", next(m for m in t.IMPL_MENU if m["id"] == "extra_timing"), tmp_path)
    assert "place_design -directive ExtraTimingOpt" in s and s.count("phys_opt_design") == 2
    d = t.impl_tcl(tmp_path / "x.dcp", next(m for m in t.IMPL_MENU if m["id"] == "default"), tmp_path)
    assert "-directive" not in d and "route_design" in d


def test_candidates_skip_and_default_always_first(tmp_path):
    spec = {"name": "d"}
    cs = t.synth_candidates(spec, ["perf"])
    assert [c["id"] for c in cs] == ["default", "perf"]
    t.synth_candidates(spec, None)
    assert any(s["id"] == "fanout_nets" for s in spec["_skipped"])


def test_score_joins_outcome(tmp_path):
    import json
    rec = {"design": "d", "candidates": [{"id": "a", "wns_ns": 0.1}, {"id": "b", "wns_ns": 0.5}, {"id": "c", "wns_ns": 0.3}]}
    p = tmp_path / "r.json"; p.write_text(json.dumps(rec))
    s = t.score(str(p), {"a": 0.2, "b": 0.1, "c": 0.4})
    assert s["n"] == 3 and s["early_best"] == "b" and s["routed_best"] == "c" and not s["early_best_is_routed_best"]


def test_triage_post_thresholds_and_decision():
    assert t.triage_post(0.8)["class"] == "easy" and t.triage_post(0.1)["class"] == "marginal" and t.triage_post(-0.5)["class"] == "hard"
    assert t.triage_post(None)["class"] == "unknown"
    spec = {"part": "xck26-sfvc784-2LV-c", "clock_ns": 1.4, "function": "nosuchfn"}
    d = t.triage(spec)
    assert d["decision"] == "unknown" and "default synthesis" in d["next"]
    assert t.triage(spec, 0.9, True)["decision"] == "easy"                    # the post-synthesis signal overrides an unknown pre signal


def test_triage_pre_uses_nearest_rows(tmp_path):
    ds = tmp_path / "d.csv"
    ds.write_text("source,row_id,clock_ns,rt_wns\n" + "".join(f"arith,f/v/k26/P{i},2.0,0.0\n" for i in range(4)))   # Fmax 500 MHz
    assert t.triage_pre({"part": "xck26", "clock_ns": 1.5, "function": "f"}, ds)["class"] == "hard"       # 667 MHz target
    assert t.triage_pre({"part": "xck26", "clock_ns": 2.6, "function": "f"}, ds)["class"] == "easy"       # 385 MHz
    assert t.triage_pre({"part": "xck26", "clock_ns": 2.0, "function": "f"}, ds)["class"] == "hard"       # exactly at Fmax


def test_run_children_falls_back_to_one_child_when_the_gate_never_admits():
    """Brief 178b: with MemAvailable below peak + 8 GiB the gate refuses for ever; after the grace period one child runs alone, one at a time."""
    live, peak, msgs = [], [0], []

    class P:
        def __init__(self, cmd, **k):
            self.n = 0
            live.append(self)
            peak[0] = max(peak[0], len([p for p in live if p.poll() is None]))

        def poll(self):
            self.n += 1
            return None if self.n < 2 else 0

    jobs = [{"tcl": Path(f"/z{i}.tcl"), "log": Path(f"/z{i}.log")} for i in range(3)]
    t.run_children(jobs, 2.0, 4, poll_s=0, launch=P, avail=lambda: 5.0, fallback_after_s=0.0, log=msgs.append)
    assert len(live) == 3 and peak[0] == 1 and msgs
    live.clear()
    t.run_children(jobs[:1], 4.0, 1, poll_s=0, launch=P, avail=lambda: 5.5, fallback_after_s=0.0, log=msgs.append)   # 4 + 1 <= 5.5: runs
    assert len(live) == 1


def test_synth_peak_by_part():
    assert t.synth_peak_g({"part": "xc7a100tcsg324-1"}) == 2.0
    assert t.synth_peak_g({"part": "xck26-sfvc784-2LV-c"}) == 4.0
    assert t.synth_peak_g({"part": "xck26-sfvc784-2LV-c", "synth_peak_g": 3}) == 3.0


def test_single_child_stage_uses_the_real_memory_reading_and_no_light_gate():
    """Brief 178c: place and route passed avail=lambda: 99.0 (a stub, logged as 'MemAvailable 99.0 G') and a 4 G child was refused by the light-class gate."""
    live, msgs = [], []

    class P:
        def __init__(self, cmd, **k):
            live.append(self)

        def poll(self):
            return 0

    jobs = [{"tcl": Path("/y.tcl"), "log": Path("/y.log")}]
    t.run_children(jobs, 4.0, 1, poll_s=0, launch=P, avail=lambda: 5.5, log=msgs.append)
    assert len(live) == 1 and not msgs                      # admitted at once, no 'gate refused' message
    live.clear()
    clock = iter(range(0, 10**7, 4000))                     # the clock jumps over an hour per call: with 2 G free the one-hour error fires
    orig = t.time.time
    t.time.time = lambda: next(clock)
    try:
        try:
            t.run_children(jobs, 4.0, 1, poll_s=0, launch=P, avail=lambda: 2.0, log=msgs.append)
            raised = False
        except SystemExit:
            raised = True
    finally:
        t.time.time = orig
    assert raised and not live



# ---- brief 178e: the two-step mode -------------------------------------------------------------------------------------------------
def _strategies(tmp_path, monkeypatch):
    import json
    p = tmp_path / "vs.json"
    p.write_text(json.dumps({"impl": {"Area_Explore": {"opt": "ExploreArea"}, "Performance_Explore": {"opt": "Explore", "place": "Explore", "route": "Explore"},
                                      "Performance_BalanceSLLs": {"place": "SSI_BalanceSLLs"}, "Performance_NetDelay_high": {"opt": "Default", "place": "ExtraNetDelay_high"},
                                      "Congestion_SpreadLogic_high": {"place": "AltSpreadLogic_high"}}}))
    monkeypatch.setattr(t, "STRATEGIES", p)


def test_performance_menu_is_default_plus_performance_sets_without_slr_only(tmp_path, monkeypatch):
    _strategies(tmp_path, monkeypatch)
    assert t.performance_menu() == ["default", "amd:Performance_Explore", "amd:Performance_NetDelay_high"]
    monkeypatch.setattr(t, "STRATEGIES", tmp_path / "missing.json")
    assert t.performance_menu() == ["default"]


def test_two_step_pick_keeps_default_on_identical_netlists_and_takes_better_retime():
    d, r = cand("default", -0.9, lut=116, ff=196, order=0), cand("retime", -0.9, lut=116, ff=196, order=8)
    assert t.two_step_pick([r, d, cand("altroute", 0.5, order=3)])["id"] == "default"          # a tie, and a third candidate step 1 never looks at
    assert t.two_step_pick([cand("default", -0.19, lut=510, ff=117, order=0), cand("retime", 0.15, lut=501, ff=197, order=8)])["id"] == "retime"
    assert t.two_step_pick([cand("default", -0.5, order=0), cand("retime", None, status="error: x", order=8)])["id"] == "default"


def test_run_two_step_stops_at_the_first_set_that_meets_timing(tmp_path, monkeypatch):
    _strategies(tmp_path, monkeypatch)
    monkeypatch.setattr(t, "WORK", tmp_path / "work")
    monkeypatch.setattr(t, "take_slot", lambda text, wait_s=0: tmp_path / "lock")
    monkeypatch.setattr(t, "release_slot", lambda lock, prefix: None)
    monkeypatch.setattr(t, "vivado", lambda: "/x/2026.1/Vivado/bin/vivado")
    wns = {"default": -0.3, "retime": -0.1, "amd_Performance_Explore": 0.02, "amd_Performance_NetDelay_high": 0.5}
    ran = []

    def fake(jobs, peak, n, **k):                                   # writes the reports a Vivado run would, from the run directory's name
        for j in jobs:
            wd = j["tcl"].parent
            key = wd.name.split("_", 1)[1] if wd.parent.name.startswith("impl") else wd.name
            w = wns.get(key, wns.get(wd.name, -0.3))
            (wd / "utilization.rpt").write_text(UT.format(l=100, f=50))
            (wd / "timing_summary.rpt").write_text(TS.format(w=w))
            (wd / "done.txt").write_text("7\n")
            ran.append(wd.name)

    monkeypatch.setattr(t, "run_children", fake)
    spec = {"name": "d", "part": "xc7a100tcsg324-1", "top": "x", "clock_ns": 5.0, "files": ["/a.sv"]}
    rec = t.run_two_step(spec, take=False, stop_at_pass=True)
    assert rec["two_step"]["step1_pick"] == "retime"                                           # -0.1 beats -0.3
    impl = [r for r in ran if r.startswith("retime_")]
    assert impl == ["retime_default", "retime_amd_Performance_Explore"]                         # stopped at the first WNS >= 0, NetDelay_high never ran
    assert rec["winner"] == "retime/amd:Performance_Explore"
    assert any("stopped early" in s["reason"] for s in spec["_skipped"])
    assert rec["two_step"]["step1_cpu_s"] == 14 and rec["two_step"]["step2_cpu_s"] == 14
