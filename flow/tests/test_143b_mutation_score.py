"""Brief 143b: the blind mutant generator, the score arithmetic, the formal equivalence filter and the trace_v1 `mutation` reader."""
import inspect
import json
from pathlib import Path

import pytest
import yaml

from flow import mutation_blind as B
from flow import mutation_equiv as E
from flow import mutation_score as S
from flow import trace_v1 as T

RTL = """module m (input logic clk, input logic rst, input logic [3:0] a, input logic en, output logic [3:0] q, output logic hit);
    logic [3:0] r;
    // a comment with == and + that must not be mutated
    assign hit = (r == 4'd9) && en;
    assign q = r;
    always_ff @(posedge clk) begin
        if (rst) r <= 4'd0;
        else if (en) r <= r + a;
    end
endmodule
"""


@pytest.fixture()
def rtl(tmp_path):
    f = tmp_path / "m.sv"
    f.write_text(RTL)
    return f


# ---- the generator is blind and reproducible ----------------------------------------------------------------------------------

def test_generator_takes_rtl_and_a_seed_only():
    """No parameter can carry a test, a model or a bench into the generator."""
    assert list(inspect.signature(B.generate).parameters) == ["files", "seed", "count", "operators"]


def test_same_inputs_give_the_same_mutants_and_the_seed_changes_them(rtl):
    a, b = B.generate([rtl], 7, 4), B.generate([rtl], 7, 4)
    assert a == b and a["seed"] == 7 and a["rtl_sha256"]
    names = lambda g: [m["name"] for m in g["mutants"]]
    assert names(B.generate([rtl], 1, 3)) != names(B.generate([rtl], 2, 3)) or B.generate([rtl], 1, None)["candidates"] <= 3


def test_comments_and_declarations_are_not_mutated(rtl):
    for m in B.candidates([rtl]):
        assert "comment" not in m["old_line"] and not m["old_line"].startswith(("module", "input"))


def test_a_mutant_changes_exactly_one_line_and_is_refused_when_the_text_moved(rtl):
    pool = B.candidates([rtl])
    assert pool
    for m in pool:
        new = B.apply(m, RTL)
        assert new is not None and new != RTL
        assert sum(1 for x, y in zip(RTL.splitlines(), new.splitlines()) if x != y) == 1
    drifted = RTL.replace("r == 4'd9", "r == 4'd8")
    eq = [m for m in pool if m["class"] == "eq_to_ne"][0]
    assert B.apply(eq, drifted) is None


def test_operator_classes_are_present(rtl):
    classes = {m["class"] for m in B.candidates([rtl])}
    assert {"eq_to_ne", "and_to_or", "plus_to_minus", "const_plus1", "const_minus1"} <= classes


def test_ternary_arms_are_swapped_with_brackets_respected(tmp_path):
    f = tmp_path / "t.sv"
    f.write_text("module t;\n    assign y = c ? {1'b1, a} : f(b, d);\nendmodule\n")
    sw = [m for m in B.candidates([f]) if m["class"] == "ternary_swap"]
    assert len(sw) == 1 and "    assign y = c ? f(b, d) : {1'b1, a};" in B.apply(sw[0], f.read_text())


def test_llm_proposals_are_validated_and_the_prompt_holds_only_rtl(rtl):
    good = {"file": "m.sv", "old": "r <= r + a;", "new": "r <= r - a;", "why": "sign"}
    ok, bad = B.load_llm_proposals(json.dumps([good, {**good, "old": "nowhere"}, {"file": "x.sv", "old": "a", "new": "b"}, {**good, "new": good["old"]}]), [rtl])
    assert len(ok) == 1 and ok[0]["class"] == "llm_proposed" and len(bad) == 3
    assert B.apply(ok[0], RTL).count("r - a") == 1
    prompt = B.llm_prompt([rtl])
    assert "module m" in prompt and "test" in prompt.lower() and "cocotb" not in prompt
    assert B.load_llm_proposals("not json", [rtl])[0] == []


# ---- the score arithmetic --------------------------------------------------------------------------------------------------------

def row(name, status, verdict=None, fb=None):
    r = {"name": name, "status": status}
    if verdict:
        r["formal"] = {"verdict": verdict}
    if fb:
        r["formal_bench"] = fb
    return r


def test_score_headline_before_after_and_worst_case():
    rows = ([row(f"k{i}", "killed") for i in range(8)] + [row("e1", "survived", "equivalent"), row("e2", "survived", "equivalent"), row("r1", "survived", "not_equivalent"),
            row("u1", "survived", "undecided"), row("t1", "timed_out"), row("i1", "invalid")])
    s = S.summarise(rows, False)
    assert (s["killed"], s["equivalent"], s["real_survivors"], s["undecided"], s["bench_timed_out"], s["invalid"]) == (8, 2, 1, 1, 1, 1)
    assert s["score_pct"] == round(100 * 8 / 9, 2)                                 # killed / (killed + real survivors)
    assert s["score_worst_case_pct"] == round(100 * 8 / 11, 2)                     # undecided and the timeout counted against the bench
    assert s["score_before_filter_pct"] == round(100 * 8 / 13, 2)                  # equivalents, the undecided one and the timeout all count as not killed
    assert s["evaluated"] == 13


def test_a_formal_bench_kill_is_counted_apart_from_simulation_kills():
    rows = [row("k", "killed"), row("f", "survived", "not_equivalent", fb="killed"), row("r", "survived", "not_equivalent", fb="passed")]
    s = S.summarise(rows, True)
    assert (s["killed_by_simulation"], s["killed_by_formal_bench"], s["killed"], s["real_survivors"]) == (1, 1, 2, 1)
    assert s["score_pct"] == round(100 * 2 / 3, 2) and s["score_simulation_only_pct"] == round(100 / 3, 2)


def test_a_timeout_is_never_a_kill():
    s = S.summarise([row("t", "timed_out"), row("u", "survived", "undecided")], False)
    assert s["killed"] == 0 and s["score_pct"] is None and s["score_worst_case_pct"] == 0.0


# ---- the formal filter -----------------------------------------------------------------------------------------------------------

def test_module_renaming_is_whole_word():
    assert E.rename_modules("module a; b #(1) u(); endmodule // a_b", ["a", "b"]) == "module a_mut; b_mut #(1) u(); endmodule // a_b"


def test_the_miter_wrapper_asserts_every_output_and_qualifies_data_by_valid():
    ports = [{"name": "clk", "dir": "input", "width": 1}, {"name": "rst", "dir": "input", "width": 1}, {"name": "d", "dir": "output", "width": 8}, {"name": "v", "dir": "output", "width": 1},
             {"name": "rdy", "dir": "output", "width": 1}]
    w = E.wrapper_sv("t", {"W": 8}, ports, {"clocks": ["clk"], "reset": {"port": "rst", "clock": "clk", "cycles": 2, "active": 1}, "qualifiers": {"d": "v"}, "assume": ["!v || g_rdy"]})
    assert "t #(.W(8)) gold" in w and "t_mut #(.W(8)) mut" in w
    assert "assert (g_v == m_v && (!g_v || g_d == m_d))" in w and "assert (g_rdy == m_rdy)" in w and "assume (!v || g_rdy)" in w and "assume (rst[0] == 1'b1)" in w


needs_sby = pytest.mark.skipif(E.suite_bin() is None, reason="the OSS CAD Suite is not installed")

COUNTER = """module cnt (input logic clk, input logic rst, input logic en, output logic [2:0] q, output logic wrap);
    logic [2:0] r;
    assign q = r;
    assign wrap = (r == 3'd7);
    always_ff @(posedge clk) begin
        if (rst) r <= 3'd0;
        else if (en) r <= r + 3'd1;
    end
endmodule
"""
TARGET = {"top": "cnt", "clocks": ["clk"], "reset": {"port": "rst", "clock": "clk", "cycles": 2, "active": 1}, "qualifiers": {}, "assume": []}


def _pair(tmp_path, new_src):
    a, b = tmp_path / "o" / "cnt.sv", tmp_path / "m" / "cnt.sv"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text(COUNTER)
    b.write_text(new_src)
    return [a], [b]


@needs_sby
def test_an_equivalent_mutant_is_proved_and_a_real_difference_is_found(tmp_path):
    o, m = _pair(tmp_path, COUNTER.replace("r == 3'd7", "r >= 3'd7"))                # a 3-bit counter: == 7 and >= 7 are the same
    v = E.classify(o, m, TARGET, {"params": {}}, bmc_depth=12, bmc_s=60, prove_s=90)
    assert v["verdict"] == "equivalent", v
    (tmp_path / "x").mkdir()
    o, m = _pair(tmp_path / "x", COUNTER.replace("r + 3'd1", "r + 3'd2"))
    v = E.classify(o, m, TARGET, {"params": {}}, bmc_depth=12, bmc_s=60, prove_s=90)
    assert v["verdict"] == "not_equivalent" and v["bmc_status"] == "FAIL", v


# ---- the trace_v1 reader ---------------------------------------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    (tmp_path / "designs" / "d" / "verif").mkdir(parents=True)
    (tmp_path / "designs" / "d" / "rtl").mkdir()
    (tmp_path / "designs" / "d" / "rtl" / "a.sv").write_text("module a; endmodule\n")
    (tmp_path / "results").mkdir()
    return tmp_path


def record(repo, **k):
    rtl = repo / "designs" / "d" / "rtl" / "a.sv"
    rec = {"schema": S.SCHEMA, "rtl_dir": "designs/d/rtl", "rtl": {"a.sv": S.sha(rtl)}, "filter": {"method": "miter"}, "generator": {"seed": 3}, "evaluated": 30, "killed": 28,
           "real_survivors": 1, "equivalent": 2, "undecided": 0, "bench_timed_out": 0, "invalid": 0, "score_pct": 96.55, "score_worst_case_pct": 96.55,
           "score_before_filter_pct": 90.3, "killed_by_simulation": 28, "killed_by_formal_bench": 0} | k
    (repo / "results" / "mut.json").write_text(json.dumps(rec))


def collect(repo, floor, on="item"):
    req = {"id": "R1", "kind": "functional", "title": "t", "text": "t", "source": "s", "spec_status": "draft"}
    it = {"id": "V1", "requirements": ["R1"], "method": "coverage_bin", "evidence": {"file": "results/mut.json", "reader": "mutation"}}
    (it if on == "item" else req)["mutation_floor"] = floor
    (repo / "designs" / "d" / "verif" / "testplan.yaml").write_text(yaml.safe_dump({"schema": T.SCHEMA_V1, "design": "d", "requirements": [req], "verification": [it]}))
    c = T.collect(repo / "designs" / "d")
    return c["items"][0], c["requirements"][0]


def test_a_requirement_can_bind_a_mutation_floor(repo):
    record(repo)
    i, r = collect(repo, {"score_pct": 95, "min_mutants": 20}, on="requirement")
    assert i["status"] == "pass" and r["state"] == "verified" and "96.55%" in i["detail"] and i["mutation"]["real_survivors"] == 1
    i, r = collect(repo, {"score_pct": 99})
    assert i["status"] == "fail" and "below the floor" in i["detail"] and r["state"] == "fail"


def test_the_floor_also_limits_undecided_timeouts_and_unfiltered_records(repo):
    record(repo, undecided=2)
    assert collect(repo, {"score_pct": 90})[0]["status"] == "fail"
    assert collect(repo, {"score_pct": 90, "max_undecided": 2})[0]["status"] == "pass"
    record(repo, bench_timed_out=1)
    assert "timeouts" in collect(repo, {"score_pct": 90})[0]["detail"]
    record(repo, filter={"method": "none"})
    assert "not filtered" in collect(repo, {"score_pct": 90})[0]["detail"]
    record(repo, evaluated=10)
    assert "fewer than 20" in collect(repo, {"score_pct": 90, "min_mutants": 20})[0]["detail"]


def test_a_record_for_other_rtl_is_not_evidence(repo):
    record(repo)
    (repo / "designs" / "d" / "rtl" / "a.sv").write_text("module a; wire x; endmodule\n")
    i, _ = collect(repo, {"score_pct": 90})
    assert i["status"] in ("fail", "stale") and ("RTL changed" in i["detail"] or i.get("stale_because"))


def test_an_item_without_a_floor_fails_loudly(repo):
    record(repo)
    req = {"id": "R1", "kind": "functional", "title": "t", "text": "t", "source": "s", "spec_status": "draft"}
    it = {"id": "V1", "requirements": ["R1"], "method": "coverage_bin", "evidence": {"file": "results/mut.json", "reader": "mutation"}}
    (repo / "designs" / "d" / "verif" / "testplan.yaml").write_text(yaml.safe_dump({"schema": T.SCHEMA_V1, "design": "d", "requirements": [req], "verification": [it]}))
    assert "mutation_floor" in T.collect(repo / "designs" / "d")["items"][0]["detail"]


def test_committed_records_are_well_formed():
    root = Path(__file__).resolve().parents[2] / "results"
    for p in sorted([*(root / "143b_mutation").glob("*.json"), *(root / "152_b96_mutation").glob("*.json")]):
        r = json.loads(p.read_text())
        assert r["schema"] == S.SCHEMA and r["generator"]["blind_to_tests"] is True and r["generator"]["seed"] is not None
        assert r["killed"] + r["survived_after_bench"] + r["bench_timed_out"] + r["invalid"] == r["generator"]["sampled"] + r["generator"]["llm_proposals_valid"]
        assert r["survived_after_bench"] == r["equivalent"] + r["real_survivors"] + r["undecided"]
        assert r["timeout_policy"] and r["rows"] and all(x["status"] in ("killed", "survived", "timed_out", "invalid") for x in r["rows"])


# ---- brief 152 ----------------------------------------------------------------------------------------------------------------

def test_the_floor_can_bind_the_worst_case(repo):
    """Brief 152: floor = worst case >= 90 % over >= 30 evaluated mutants (the planner's floor for a design's bench)."""
    floor = {"score_pct": 90, "worst_case_pct": 90, "min_mutants": 30}
    record(repo, score_worst_case_pct=93.1)
    assert collect(repo, floor)[0]["status"] == "pass"
    record(repo, score_worst_case_pct=80.0)
    i = collect(repo, floor)[0]
    assert i["status"] == "fail" and "worst-case score 80.0% is below the floor 90%" in i["detail"]
    record(repo, evaluated=29)
    assert "fewer than 30" in collect(repo, floor)[0]["detail"]


def test_the_formal_bench_still_finds_the_survivors_copy(tmp_path):
    """Brief 143b deleted a survivor's directory at the end of the filter, so the design's own formal bench never ran on it (record: killed_by_formal_bench 0 for a mutant that its
    assertion p6c catches in 2 s). The directories now live until drop_mutant_dirs."""
    d = tmp_path / "s1"
    d.mkdir()
    seen = []
    target = {"rtl_dir": tmp_path / "rtl", "rtl_files": ["a.sv"], "configs": [{"label": "c", "params": {}}], "formal_bench": lambda p: seen.append(p.is_dir()) or "killed"}
    rows = [{"name": "s1", "status": "survived", "formal": {"verdict": "not_equivalent"}}]
    S.formal_bench_kills(target, rows, tmp_path, log=lambda *a, **k: None)
    assert seen == [True] and rows[0]["formal_bench"] == "killed"
    assert "rmtree" not in inspect.getsource(S.filter_survivors)
    S.drop_mutant_dirs(rows, tmp_path)
    assert not d.exists()
