"""Brief 218, part 1: the coverage loop's pure parts and its driver (flow/coverage_loop.py), on recorded-shape evidence and fakes.

Cases: holes parsed from a real Verilator ``coverage.dat`` (through ``flow.verif_gates.merge_code_cov``), from the gate's bin and cover lists and
from a mutation result; when a loop applies at all (only stimulus-owned V3 failures); the plateau rule (no hole closed in two rounds), convergence
and the round limit; what the tests role is shown (the holes, never RTL); the driver closing holes round by round, stopping on a plateau, halting
when the new stimulus breaks V2, and recording bins closed per round and the usage of each."""
from __future__ import annotations

import json
from pathlib import Path

from flow import coverage_loop as CL
from flow import verif_gates as vg


def dat(rows: list[tuple[str, int, str, int]]) -> str:
    """A Verilator coverage.dat body: (file, line, type, hits) rows."""
    out = ["# SystemC::Coverage-3"]
    for f, ln, t, n in rows:
        out.append(f"C '\x01f\x02{f}\x01l\x02{ln}\x01t\x02{t}\x01o\x02sig{ln}\x01page\x02v_{t}/x' {n}")
    return "\n".join(out) + "\n"


def v3(failed: dict[str, list] | None = None, reached: str = "V2", extra_failed: tuple[str, ...] = ()) -> dict:
    """A verif_gates-shaped result: ``failed`` maps a V3 check to its (list) value; everything not named passes."""
    names = ("seeds_run", "all_seeds_pass", "functional_bins_pct", "functional_bins_unhit", "cover_properties_pct", "cover_properties_unhit",
             "line_pct", "toggle_pct", "waivers_without_reason", "mutation_score_pct")
    checks = {n: {"pass": True, "value": [], "threshold": 0} for n in names}
    for k, val in (failed or {}).items():
        checks[k] = {"pass": False, "value": val, "threshold": 0}
    for k in extra_failed:
        checks[k] = {"pass": False, "value": 0, "threshold": 1}
    return {"reached": reached, "stages": {"V3": {"checks": checks}}, "code_coverage_unhit": {}}


# ---- holes ------------------------------------------------------------------------------------------------------------------------------
def test_holes_come_from_a_real_coverage_dat(tmp_path):
    (tmp_path / "seed1").mkdir()
    (tmp_path / "seed1" / "coverage.dat").write_text(dat([("designs/x/rtl/a.sv", 10, "line", 5), ("designs/x/rtl/a.sv", 11, "line", 0),
                                                          ("designs/x/rtl/a.sv", 12, "toggle", 0), ("designs/x/rtl/a.sv", 13, "toggle", 2)]))
    code = vg.merge_code_cov(tmp_path, "designs/x/rtl/")
    verif = {**v3({"line_pct": 50, "toggle_pct": 50}), "code_coverage_unhit": {k: v["unhit"] for k, v in code.items() if k in ("line", "toggle", "branch")}}
    hs = CL.holes_of(verif)
    assert [(h["kind"], h["key"]) for h in hs] == [("line", "line:a.sv:11 sig11"), ("toggle", "toggle:a.sv:12 sig12")]


REF = Path(__file__).parent / "data" / "ref_t1_sim"


def test_holes_from_the_recorded_t1_reference_run():
    """Real Verilator coverage of the committed T1 reference simulation (3 seeds): every line and branch is hit, 111 toggle bits are not."""
    code = vg.merge_code_cov(REF, "designs/t1_dimmer_counter/rtl/")
    assert (code["line"]["hit"], code["line"]["points"], code["branch"]["hit"]) == (36, 36, 28)
    hs = CL.holes_of({"code_coverage_unhit": {k: v["unhit"] for k, v in code.items() if k in ("line", "toggle", "branch")}})
    assert CL.counts(hs) == {"toggle": 111} and len({h["key"] for h in hs}) == 111
    text = CL.brief(hs, 1)
    assert "dimmer_counter.sv:17 an: bits" in text and "(1->0)" in text            # grouped by signal, not 111 lines
    assert text.count("\n- ") <= 12 and "(+" in text                                     # a handful of lines, the rest counted


def test_holes_from_bins_cover_properties_and_mutants():
    verif = v3({"functional_bins_unhit": ["t1.op.kind:CLEAR", "t1.clock.mix:WRITE"], "cover_properties_unhit": ["C_X"]})
    mut = {"survivor_text": ["a.sv:7 '==' replaced by '!='"], "timed_out_text": ["b.sv:9 '+' replaced by '-'"]}
    hs = CL.holes_of(verif, mut)
    assert CL.counts(hs) == {"bin": 2, "cover": 1, "mutant": 2}
    assert {h["key"] for h in hs} >= {"bin:t1.op.kind:CLEAR", "cover:C_X", "mutant:a.sv:7 '==' replaced by '!='", "mutant:timeout:b.sv:9 '+' replaced by '-'"}
    assert all(h["text"] for h in hs)


def test_a_loop_applies_only_when_the_tests_own_every_failed_check():
    assert CL.stimulus_only(v3({"functional_bins_unhit": ["a:b"], "functional_bins_pct": 50}))
    assert CL.stimulus_only(v3({"mutation_score_pct": 40}))
    assert not CL.stimulus_only(v3({"functional_bins_unhit": ["a:b"]}, extra_failed=("seeds_run",)))       # a seed count is not stimulus
    assert not CL.stimulus_only(v3({"functional_bins_unhit": ["a:b"]}, reached="V1"))                      # V2 first
    assert not CL.stimulus_only(v3({}))                                                                      # nothing failed
    assert not CL.stimulus_only(None)


def test_diff_names_what_closed_and_what_opened():
    a = [{"key": "bin:x"}, {"key": "bin:y"}]
    b = [{"key": "bin:y"}, {"key": "bin:z"}]
    assert CL.diff(a, b) == {"closed": ["bin:x"], "opened": ["bin:z"]}


# ---- the stop rule ----------------------------------------------------------------------------------------------------------------------
def rnd(closed: int, after: int = 3) -> dict:
    return {"closed": [f"k{i}" for i in range(closed)], "holes_after": [f"h{i}" for i in range(after)]}


def test_stop_rules():
    assert CL.stop_reason([rnd(1)]) is None
    assert CL.stop_reason([rnd(2), rnd(0)]) is None                            # one empty round is not a plateau
    assert CL.stop_reason([rnd(0), rnd(0)]) == "plateau"                       # two in a row is
    assert CL.stop_reason([rnd(1), rnd(0), rnd(0)]) == "plateau"
    assert CL.stop_reason([rnd(1, after=0)]) == "converged"
    assert CL.stop_reason([rnd(1), rnd(1), rnd(1)]) == "rounds"                # progress, but the limit
    assert CL.stop_reason([rnd(1), rnd(1)], max_rounds=2) == "rounds"
    assert CL.stop_reason([rnd(0, after=0)]) == "converged"                    # convergence wins over a plateau


# ---- what the role is shown -------------------------------------------------------------------------------------------------------------
def test_the_brief_names_the_holes_and_never_the_rtl():
    hs = CL.holes_of(v3({"functional_bins_unhit": ["t1.op.kind:CLEAR"]}), {"survivor_text": ["a.sv:7 '==' replaced by '!='"]})
    text = CL.brief(hs, 2, history=[{"round": 1, "closed": ["x"], "opened": []}])
    assert text.startswith("COVERAGE ROUND 2") and CL.round_of_brief(text) == 2
    assert "t1.op.kind:CLEAR" in text and "a.sv:7" in text and "Earlier rounds: round 1 closed 1" in text
    assert "Do not change the assertions" in text
    assert "module " not in text and "always" not in text                      # no RTL text


def test_a_long_brief_counts_what_it_leaves_out():
    hs = [{"kind": "bin", "key": f"bin:b{i}", "text": f"functional bin b{i} was never hit"} for i in range(60)]
    text = CL.brief(hs, 1, limit=10)
    assert text.count("- functional bin") == 10 and "(+50 more" in text


# ---- the driver -------------------------------------------------------------------------------------------------------------------------
class Fake:
    """A design whose holes shrink as the role 'writes' stimulus: ``plan`` lists the holes open after each rerun."""

    def __init__(self, plan: list[list[str]], files=("tests/t.py",)):
        self.plan, self.i, self.briefs, self.files = plan, 0, [], files
        self.now = [CL._hole("bin", k, k) for k in plan[0]]
        self.spent = 100.0

    def read_holes(self):
        return list(self.now)

    def ask(self, brief, n):
        self.briefs.append(brief)
        self.spent += 50
        return {"ok": True, "files": list(self.files)}

    def rerun(self):
        self.i += 1
        self.now = [CL._hole("bin", k, k) for k in self.plan[min(self.i, len(self.plan) - 1)]]


def drive(tmp_path, plan, **kw):
    f = Fake(plan)
    s = CL.run_loop(tmp_path, read_holes=f.read_holes, ask_tests=f.ask, rerun=f.rerun, spent=lambda: f.spent, **kw)
    return f, s


def test_holes_close_round_by_round_until_converged(tmp_path):
    f, s = drive(tmp_path, [["a", "b", "c"], ["c"], []])
    assert (s["rounds"], s["stop"], s["holes_start"], s["holes_end"], s["closed_of_start"]) == (2, "converged", 3, 0, 3)
    log = CL.read_log(tmp_path)
    assert [r["closed"] for r in log] == [["bin:a", "bin:b"], ["bin:c"]]                 # bins closed per round
    assert [r["usage"] for r in log] == [50.0, 50.0] and s["usage"] == 100.0           # and what each round cost
    assert "COVERAGE ROUND 1" in f.briefs[0] and "COVERAGE ROUND 2" in f.briefs[1]


def test_a_plateau_stops_the_loop_after_two_empty_rounds(tmp_path):
    f, s = drive(tmp_path, [["a", "b"], ["a", "b"], ["a", "b"], ["a"]])
    assert s["stop"] == "plateau" and s["rounds"] == 2 and s["holes_end"] == 2 and len(f.briefs) == 2


def test_the_round_limit_stops_a_loop_that_keeps_closing(tmp_path):
    f, s = drive(tmp_path, [list("abcdefgh"), list("bcdefgh"), list("cdefgh"), list("defgh"), list("efgh")], max_rounds=3)
    assert s["stop"] == "rounds" and s["rounds"] == 3 and s["closed_of_start"] == 3


def test_no_holes_means_no_round(tmp_path):
    f, s = drive(tmp_path, [[]])
    assert s["stop"] == "converged" and s["rounds"] == 0 and f.briefs == [] and CL.read_log(tmp_path) == []


def test_a_new_hole_that_appears_is_counted_as_opened_not_hidden(tmp_path):
    f, s = drive(tmp_path, [["a"], ["b"], ["b"], ["b"]])
    log = CL.read_log(tmp_path)
    assert log[0]["closed"] == ["bin:a"] and log[0]["opened"] == ["bin:b"] and s["opened_total"] == 1


def test_a_role_that_cannot_run_ends_the_loop_with_its_reason(tmp_path):
    f = Fake([["a"], []])
    s = CL.run_loop(tmp_path, read_holes=f.read_holes, rerun=f.rerun,
                    ask_tests=lambda b, n: {"ok": False, "error": "budget: stage usd limit reached"})
    assert s["stop"].startswith("tests_role: budget") and s["rounds"] == 1 and s["holes_end"] == 1 and f.i == 0       # no rerun after a failed call


def test_stimulus_that_breaks_v2_halts_the_loop(tmp_path):
    f = Fake([["a", "b"], ["a"]])
    s = CL.run_loop(tmp_path, read_holes=f.read_holes, ask_tests=f.ask, rerun=f.rerun, halt=lambda: "the new stimulus broke V2")
    assert s["stop"] == "the new stimulus broke V2" and s["holes_end"] == 2 and s["closed_of_start"] == 0
    assert json.loads(CL.log_path(tmp_path).read_text().splitlines()[-1])["stop"] == "the new stimulus broke V2"


def test_the_summary_line_reads_in_plain_words(tmp_path):
    _, s = drive(tmp_path, [["a", "b"], ["b"], ["b"], ["b"]])
    assert CL.summary_line(s) == "coverage loop: 3 round(s), stopped on plateau; holes 2 -> 1 (1 of the first 2 closed, 0 opened)"
