"""Brief 143c: formal rigour. The judge is tested on synthetic records (no sby needed); one end-to-end test runs sby on a tiny
harness with a vacuous assertion, an over-constrained one and a good one; and the repo's own proofs must all have an accepting,
fresh record."""

from __future__ import annotations

import copy
import json
import shutil
import textwrap
from pathlib import Path

import pytest
import yaml

from flow import formal_rigour as fr


def chk(label, flavor="assert", src=None, taut=False):
    return {"flavor": flavor, "label": label, "src": src or f"h.sv:{sum(map(ord, label)) % 900}", "id": label, "tautology": taut}


def task(mode, depth, checks, status="PASS", covers=None, failed=None):
    t = {"mode": mode, "depth": depth, "status": status, "seconds": 1.0, "checks": checks, "covers": covers or {}}
    if failed:
        t["failed_asserts"] = failed
    return t


def record(tasks):
    return {"schema": fr.SCHEMA, "sby": "x/none.sby", "tasks": tasks, "sources": {}}


GOOD_SIDE = {"sanity": ["c_main"], "depth": {"bmc": {"enough": True, "why": "the longest path is 4 clocks"}}}


def good_tasks():
    asserts = [chk("a_one"), chk("a_two")]
    covers = [chk("a_one__ante", "cover"), chk("a_two__ante", "cover"), chk("c_main", "cover")]
    return {"bmc": task("bmc", 10, asserts + [chk("m", "assume")]),
            "cover": task("cover", 12, covers, covers={c["id"]: {"reached": True, "step": 3} for c in covers})}


def j(tasks, side=GOOD_SIDE):
    return fr.judge(record(tasks), Path("/nonexistent/none.sby"), copy.deepcopy(side))


def status_of(res):
    return {a["id"]: a["status"] for a in res["assertions"]}


def test_bounded_and_justified_is_bounded_not_pass():
    r = j(good_tasks())
    assert status_of(r) == {"a_one": "bounded", "a_two": "bounded"}
    assert r["verdict"] == "bounded" and not r["reasons"], r["reasons"]
    assert all(a["bound"] == 10 and a["justified"] for a in r["assertions"])


def test_unjustified_bounded_fails():
    r = j(good_tasks(), {"sanity": ["c_main"]})
    assert r["verdict"] == "fail"
    assert r["summary"]["bounded_unjustified"] == 2
    assert any("depth justification" in x for x in r["reasons"])
    r = j(good_tasks(), {"sanity": ["c_main"], "depth": {"bmc": {"why": "x"}}})      # enough: must say yes or no
    assert r["verdict"] == "fail"


def test_not_enough_is_a_justification():
    r = j(good_tasks(), {"sanity": ["c_main"], "depth": {"bmc": {"enough": False, "why": "the counter wraps after 1000 clocks"}}})
    assert r["verdict"] == "bounded"
    assert all(a["enough"] is False for a in r["assertions"])


def test_proved_when_a_prove_task_passes():
    t = good_tasks()
    t["prove"] = task("prove", 5, t["bmc"]["checks"])
    r = j(t, {"sanity": ["c_main"], "depth": {"bmc": {"enough": True, "why": "y"}}})
    assert status_of(r) == {"a_one": "proved", "a_two": "proved"}
    assert r["verdict"] == "pass"


def test_missing_antecedent_cover_is_vacuous():
    t = good_tasks()
    t["cover"]["checks"] = [c for c in t["cover"]["checks"] if c["id"] != "a_two__ante"]
    r = j(t)
    assert status_of(r)["a_two"] == "vacuous" and r["verdict"] == "fail"


def test_unreached_antecedent_cover():
    t = good_tasks()
    t["cover"]["covers"]["a_one__ante"] = {"reached": False, "step": None}
    r = j(t)
    assert status_of(r)["a_one"] == "unreachable-cover" and r["verdict"] == "fail"


def test_antecedent_first_reached_after_the_bmc_depth_is_unreachable_in_the_bound():
    t = good_tasks()
    t["cover"]["covers"]["a_one__ante"] = {"reached": True, "step": 10}        # bmc depth is 10: it checks steps 0..9
    r = j(t)
    assert status_of(r)["a_one"] == "unreachable-cover" and "stops at depth 10" in next(a for a in r["assertions"] if a["id"] == "a_one")["detail"]
    assert r["verdict"] == "fail"
    t["cover"]["covers"]["a_one__ante"] = {"reached": True, "step": 9}
    assert status_of(j(t))["a_one"] == "bounded"
    t["prove"] = task("prove", 5, t["bmc"]["checks"])                           # a k-induction proof has no depth to fall short of
    t["cover"]["covers"]["a_one__ante"] = {"reached": True, "step": 40}
    assert status_of(j(t))["a_one"] == "proved"


def test_sidecar_maps_an_assertion_to_a_shared_cover():
    t = good_tasks()
    t["cover"]["checks"] = [c for c in t["cover"]["checks"] if c["id"] != "a_two__ante"] + [chk("shared", "cover")]
    t["cover"]["covers"]["shared"] = {"reached": True, "step": 1}
    r = j(t, {**GOOD_SIDE, "antecedents": {"a_t*": "shared"}})
    assert status_of(r)["a_two"] == "bounded"


def test_constant_true_assertion_is_vacuous():
    t = good_tasks()
    t["bmc"]["checks"].append(chk("a_taut", taut=True))
    r = j(t)
    assert status_of(r)["a_taut"] == "vacuous"


def test_unlabelled_assertion_is_vacuous():
    t = good_tasks()
    t["bmc"]["checks"].append({"flavor": "assert", "label": None, "src": "h.sv:99", "id": "h.sv:99", "tautology": False})
    assert status_of(j(t))["h.sv:99"] == "vacuous"


def test_sanity_cover_missing_or_unreached():
    assert j(good_tasks(), {"depth": GOOD_SIDE["depth"]})["verdict"] == "fail"
    t = good_tasks()
    t["cover"]["covers"]["c_main"] = {"reached": False, "step": None}
    r = j(t)
    assert r["verdict"] == "fail" and any("over-constrain" in x or "unreachable" in x for x in r["reasons"])


def test_no_cover_task_no_sidecar_failing_task():
    t = good_tasks()
    del t["cover"]
    assert "no cover task" in " ".join(j(t)["reasons"])
    assert "no sidecar" in " ".join(fr.judge(record(good_tasks()), Path("/nonexistent/none.sby"), None)["reasons"])
    t = good_tasks()
    t["bmc"]["status"] = "FAIL"
    t["bmc"]["failed_asserts"] = ["a_one"]
    r = j(t)
    assert status_of(r)["a_one"] == "failed" and r["verdict"] == "fail"


def test_stale_record(tmp_path):
    sby = tmp_path / "p.sby"
    sby.write_text("[tasks]\nbmc\n")
    rec = record(good_tasks())
    rec["sources"] = {str(sby): "0" * 64}
    r = fr.judge(rec, sby, copy.deepcopy(GOOD_SIDE))
    assert any("stale" in x for x in r["reasons"])


def test_trace_v1_hook(monkeypatch):
    ok = {"sby": "a.sby", "verdict": "pass", "summary": {"proved": 3}, "reasons": []}
    bd = {"sby": "b.sby", "verdict": "bounded", "summary": {"proved": 0}, "reasons": []}
    bad = {"sby": "c.sby", "verdict": "fail", "summary": {}, "reasons": ["2 assertion(s) vacuous: a, b"]}
    for verdicts, want in (([ok], "pass"), ([ok, bd], "bounded"), ([ok, bad], "fail")):
        it = {"rigour": ["x.sby"] * len(verdicts)}
        res = {"status": "pass", "detail": "junit"}
        it_v = iter(verdicts)
        monkeypatch.setattr(fr, "judge_job", lambda p, _i=it_v: next(_i))
        fr.apply_to_item(it, res)
        assert res["status"] == want, res
    res = {"status": "fail", "detail": "x"}
    fr.apply_to_item({"rigour": ["x.sby"]}, res)                     # a failing item is left alone
    assert res["status"] == "fail" and "rigour" not in res
    res = {"status": "pass", "detail": "x"}
    fr.apply_to_item({}, res)                                        # no field: untouched
    assert res == {"status": "pass", "detail": "x"}


def test_read_covers_and_checks(tmp_path):
    log = textwrap.dedent("""\
        SBY 1 [w] engine_0: ##   0:00:00  Reached cover statement in step 7 at top: dut.u.c_a (a.sv:3.1-3.20)
        SBY 1 [w] engine_0: ##   0:00:00  Unreached cover statement at top: dut.u.c_b (a.sv:4.1-4.20)
        SBY 1 [w] engine_0: ##   0:00:00  Reached cover statement in step 2 at top: check_a_sv_9_cover_1 (a.sv:9.1-9.20)
        """)
    c = fr.read_covers(log)
    assert c["c_a"] == {"reached": True, "step": 7} and c["a.sv:3"]["reached"]
    assert c["c_b"]["reached"] is False
    assert c["a.sv:9"]["step"] == 2
    il = tmp_path / "d.il"
    il.write_text(textwrap.dedent("""\
        module \\top
          attribute \\src "a.sv:5.5-5.30"
          cell $check $pub@1  # \\A_X
            parameter \\FLAVOR "assert"
          end
          attribute \\src "a.sv:6.5-6.30"
          cell $check $pub@2  # \\C_X
            parameter \\FLAVOR "cover"
          end
          attribute \\src "a.sv:7.5-7.30"
          cell $check $pub@3
            parameter \\FLAVOR "assume"
          end
        end
        """))
    (tmp_path / "a.sv").write_text("\n" * 4 + "A_X: assert (a || 1'b1);\n")
    cs = fr.read_checks(il, tmp_path)
    assert [(x["flavor"], x["id"]) for x in cs] == [("assert", "A_X"), ("cover", "C_X"), ("assume", "a.sv:7")]
    assert cs[0]["tautology"] is True                    # the statement text at the recorded coordinates holds `|| 1'b1`


def test_parse_sby(tmp_path):
    p = tmp_path / "j.sby"
    p.write_text(textwrap.dedent("""\
        [tasks]
        safety_bmc safety bmc
        cover safety cover
        [options]
        multiclock on
        bmc: mode bmc
        bmc: depth 40
        cover: mode cover
        cover: depth 60
        [engines]
        smtbmc z3
        [script]
        prep -top t
        [files]
        a.sv
        ../b.sv
        """))
    i = fr.parse_sby(p)
    assert i["tasks"] == {"safety_bmc": {"mode": "bmc", "depth": 40}, "cover": {"mode": "cover", "depth": 60}}
    assert [f.name for f in i["files"]] == ["a.sv", "b.sv"]


# ---- end to end: needs sby ----------------------------------------------------------------------------------------------
TOY_RTL = """\
module toy (input logic clk, input logic req, input logic [1:0] mode, output logic [3:0] n, output logic ack);
    always_ff @(posedge clk) begin
        ack <= req && mode == 2'd1;
        if (req && mode == 2'd1) n <= n + 4'd1; else n <= 4'd0;
    end
endmodule
"""
TOY_HARNESS = """\
module toy_fv (input logic clk, input logic req, input logic [1:0] mode);
    logic [3:0] n; logic ack;
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    toy dut (.*);
    always_comb assume (mode != 2'd3);                      // a wrong assumption would use mode == 3 and mode != 3 together
    always_ff @(posedge clk) if (f_past) begin
        a_good: assert (!ack || $past(req));                // reachable guard
        if (mode == 2'd3) begin
            a_vacuous: assert (n == 4'd9);                  // guard excluded by the assumption: never checked
        end
        a_taut: assert (ack || 1'b1);
        c_ack: cover (ack);
        a_good__ante: cover (ack);
        a_vacuous__ante: cover (mode == 2'd3);
        a_taut__ante: cover (ack);
    end
endmodule
"""
TOY_SBY = """\
[tasks]
bmc
cover
[options]
bmc: mode bmc
bmc: depth 6
cover: mode cover
cover: depth 6
[engines]
smtbmc z3
[script]
read_verilog -formal -sv toy.sv
read_verilog -formal -sv toy_fv.sv
prep -top toy_fv
[files]
toy.sv
toy_fv.sv
"""


@pytest.mark.skipif(not fr.pinned_oss_cad(), reason="the pinned OSS CAD Suite (FDA_OSS_CAD or ~/.local/opt/oss-cad-suite) is not installed")
def test_end_to_end_vacuity_is_found(tmp_path):
    d = tmp_path / "job"
    d.mkdir()
    (d / "toy.sv").write_text(TOY_RTL)
    (d / "toy_fv.sv").write_text(TOY_HARNESS)
    (d / "toy.sby").write_text(TOY_SBY)
    side = {"sanity": ["c_ack"], "depth": {"bmc": {"enough": True, "why": "the toy has a one-clock pipeline; depth 6 is 6 times that"}}}
    (d / "toy.rigour.yaml").write_text(yaml.safe_dump(side))
    rec = fr.run(d / "toy.sby", work_root=tmp_path / "w")
    r = fr.judge(rec, d / "toy.sby", side)
    st = status_of(r)
    assert st["a_good"] == "bounded", r
    assert st["a_vacuous"] == "unreachable-cover", r      # the assumption removes the guard's state: the assertion never fires
    assert st["a_taut"] == "vacuous", r
    assert r["verdict"] == "fail"
    assert r["sanity"]["c_ack"] is not None


# ---- the repo's own proofs --------------------------------------------------------------------------------------------------
def test_every_shipped_proof_has_a_sidecar_and_an_accepting_fresh_record():
    jobs = fr.tracked_sby()
    assert len(jobs) >= 14, [fr.rel(p) for p in jobs]
    bad = {}
    for p in jobs:
        v = fr.judge_job(p)
        if v["verdict"] == "fail":
            bad[fr.rel(p)] = v["reasons"][:2]
    assert not bad, json.dumps(bad, indent=1)


def test_trace_v1_item_with_rigour():
    """collect() on a tiny plan: the same passing evidence is pass, bounded or fail depending on what the rigour record of its jobs says."""
    from flow import trace_v1 as t
    d = fr.ROOT / "build" / "t143c_trace" / "x"            # collect() wants the design under the repo root; build/ is not tracked
    shutil.rmtree(d.parent, ignore_errors=True)
    (d / "verif").mkdir(parents=True)

    def verdict(rigour):
        plan = {"schema": t.SCHEMA_V1, "design": "x", "requirements": [{"id": "R1", "kind": "functional", "title": "t", "text": "t", "source": "s", "spec_status": "draft"}],
                "verification": [{"id": "V1", "requirements": ["R1"], "method": "formal", "title": "f", "evidence": {"file": "README.md", "reader": "exists"}, "rigour": rigour}]}
        (d / "verif" / "testplan.yaml").write_text(yaml.safe_dump(plan))
        return next(i for i in t.collect(d)["items"] if i["id"] == "V1")

    proved = verdict(["designs/t1_dimmer_counter/verif/formal/debounce.sby"])
    assert proved["status"] == "pass" and proved["rigour"][0]["verdict"] == "pass"
    bounded = verdict(["designs/t1_dimmer_counter/verif/formal/debounce.sby", "designs/b58a_trigger/verif/formal/mac_rx.sby"])
    assert bounded["status"] == "bounded" and "justification" in bounded["detail"]
    no_record = verdict(["flow/tests/fixtures/trace53/mini/verif/formal/mini.sby"])        # a job with no record and no sidecar
    assert no_record["status"] == "fail" and "formal rigour" in no_record["detail"]
    plain = verdict(None)
    assert plain["status"] == "pass" and "rigour" not in plain
    shutil.rmtree(d.parent, ignore_errors=True)


# ---- mutation --------------------------------------------------------------------------------------------------------------
def test_derive_sby_keeps_the_task_options():
    from flow import formal_mutation as fm
    p = fr.ROOT / "designs" / "b96_kr260_10g" / "verif" / "formal" / "rm_gp.sby"
    t = fm.derive_sby(p, "safety_bmc", "bmc", 24, "m.il")
    assert "mode bmc" in t and "depth 24" in t and "multiclock on" in t and "read_rtlil m.il" in t and "smtbmc boolector" in t
    assert "depth 40" not in t and "mode prove" not in t and "-D FV_PROGRESS" not in t


@pytest.mark.skipif(not fr.pinned_oss_cad(), reason="the pinned OSS CAD Suite (FDA_OSS_CAD or ~/.local/opt/oss-cad-suite) is not installed")
def test_mutation_run_on_a_small_proof(tmp_path):
    from flow import formal_mutation as fm
    r = fm.run(fr.ROOT / "designs" / "b58a_trigger" / "verif" / "formal" / "mac_rx.sby", "bmc", "bmc", 8, 3, 1, "a:src=*mac_rx.sv*", tmp_path, 300)
    assert r["control"] == "PASS" and r["summary"]["mutants"] == 3
    assert {m["result"] for m in r["mutants"]} <= {"killed", "survived"}
    assert all(m["rtl"] for m in r["mutants"]), "each mutant is reported with the RTL line it sits on"
    assert r["summary"]["killed"] + r["summary"].get("survived", 0) == 3


def test_a_psl_model_from_the_ghdl_plugin_is_read_by_label_and_its_dot_cover_pairs(tmp_path):
    """The GHDL plugin writes no source attribute, names the antecedent cover of a PSL implication `<label>.cover`, and the instance path of a cover in a
    generate scope in the log holds a space (brief 202)."""
    il = tmp_path / "design.il"
    il.write_text('module \\top\n  cell $cover $pub@1 # \\steps.cover\n    connect \\EN 1\'1\n  end\n  cell $assert $pub@2 # \\steps\n    connect \\EN 1\'1\n  end\nend\n')
    checks = fr.read_checks(il, tmp_path)
    assert {(c["flavor"], c["id"]) for c in checks} == {("cover", "steps.cover"), ("assert", "steps")}
    log = ("Reached cover statement in step 4 at top: steps.cover\n"
           "Reached cover statement in step 5 at top.\\genblk1.g_a[1].u : deep__ante\n"
           "Unreached cover statement at top: never__ante\n")
    cov = fr.read_covers(log)
    assert cov["steps.cover"] == {"reached": True, "step": 4}
    assert cov["deep__ante"]["reached"] and cov["deep__ante"]["step"] == 5
    assert cov["never__ante"]["reached"] is False
