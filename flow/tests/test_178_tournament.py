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
    assert t.triage_pre({"part": "xck26", "clock_ns": 2.2, "function": "f"}, ds)["class"] == "easy"       # 455 MHz
    assert t.triage_pre({"part": "xck26", "clock_ns": 2.0, "function": "f"}, ds)["class"] == "hard"       # exactly at Fmax
