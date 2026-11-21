"""Brief 125: Lean as an evidence tier of the traceability matrix (flow/lean_tier.py, `formal_lean` in flow/trace_v1.py).

What these tests stand for: a Lean proof is shown in the matrix only as strongly as it is. The statement is the specification and only a human approves
it; an approved statement that changes fails the gate; the axiom tier, the RTL link and where the build status came from are always visible; the result
never depends on the machine (CI has no Lean). Cosmetic changes (comments, renaming, whitespace) in a theorem never count as a different statement.
"""
import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from flow import lean_tier as LT
from flow import trace_v1 as T

REPO = Path(__file__).resolve().parents[2]
needs_lean = pytest.mark.skipif(not LT.toolchain_available(), reason="the Lean toolchain (elan) is not installed; CI runs without it")
needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="Icarus Verilog is not installed")

SPEC = """namespace Foo
def f (n : Nat) : Nat := n + 1
theorem f_pos (n : Nat) : 0 < f n := by
  sorry
theorem f_ne (n : Nat) : f n ≠ 0 := by
  sorry
end Foo
"""


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A tiny repository: one design, one Lean project with two theorems, one RTL file."""
    for m in (T, LT):
        monkeypatch.setattr(m, "ROOT", tmp_path)
    (tmp_path / "designs" / "d" / "verif").mkdir(parents=True)
    (tmp_path / "designs" / "d" / "rtl").mkdir()
    (tmp_path / "designs" / "d" / "rtl" / "a.sv").write_text("\n".join(f"line {i}" for i in range(1, 21)) + "\n")
    lean = tmp_path / "formal" / "lean"
    (lean / "Foo").mkdir(parents=True)
    (lean / "tools").mkdir()
    shutil.copy(REPO / "formal" / "lean" / "tools" / "statements.py", lean / "tools" / "statements.py")
    (lean / "Foo" / "Spec.lean").write_text(SPEC)
    (lean / "Foo" / "CrossCheck.lean").write_text("import Foo.Spec\n")
    (lean / "lakefile.toml").write_text('name = "foo"\n')
    (lean / "lean-toolchain").write_text("leanprover/lean4:v4.36.0\n")
    return tmp_path


LINK = {"kind": "transcription_tested", "source": [{"file": "designs/d/rtl/a.sv", "lines": "3-5"}], "transcribed_in": "Foo/Spec.lean",
        "crosscheck": {"file": "formal/lean/Foo/CrossCheck.lean", "reference": "an independent reference"}}


def make_plan(repo, link=None, items=None, extra_item=None):
    it = {"id": "V1", "requirements": ["R1"], "method": "formal_lean", "title": "f is positive", "lean": {"module": "Foo.Spec", "theorem": "Foo.f_pos"},
          "rtl_link": copy.deepcopy(link or LINK), **(extra_item or {})}
    d = {"schema": T.SCHEMA_V1, "design": "d", "requirements": [{"id": "R1", "kind": "functional", "title": "r", "text": "t", "spec_status": "draft"}],
         "verification": items or [it]}
    (repo / "designs" / "d" / "verif" / "testplan.yaml").write_text(yaml.safe_dump(d))
    return repo / "designs" / "d"


def record(repo, tier="kernel_only", ok=True, axioms=None, theorem="Foo.f_pos"):
    """A hand-made record with the hashes a real `lean-record` would pin (the build itself is not run here)."""
    project = "formal/lean"
    f = LT.frozen(project, "Foo.Spec", theorem)
    rec = {"schema": LT.RECORD_SCHEMA, "toolchain": "leanprover/lean4:v4.36.0", "build_ok": ok, "files": LT.project_files(project),
           "theorems": {theorem: {"module": "Foo.Spec", "build_ok": ok, "axioms": axioms if axioms is not None else ["propext"], "tier": tier,
                                  "statement_sha256": f["statement_sha256"], "definitions_sha256": f["definitions_sha256"]}},
           "rtl_sources": {LT.source_key(s): LT.source_hash(s) for s in LINK["source"]}}
    p = LT.record_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec))
    return rec


def approve(repo, item="V1", theorem="Foo.f_pos", kind="human", **over):
    f = LT.frozen("formal/lean", "Foo.Spec", theorem)
    a = {"item": item, "theorem": theorem, "statement_sha256": f["statement_sha256"], "definitions_sha256": f["definitions_sha256"], "approved_by": "A. Person",
         "approver_kind": kind, "date": "2026-11-22", **over}
    (repo / "designs" / "d" / "verif" / "lean_approvals.yaml").write_text(yaml.safe_dump({"schema": LT.APPROVAL_SCHEMA, "approvals": [a]}))


def item_of(c, iid="V1"):
    return next(i for i in c["items"] if i["id"] == iid)


# ---- statuses --------------------------------------------------------------------------------------------
def test_an_unapproved_statement_is_shown_as_such_and_is_not_verification(repo):
    d = make_plan(repo)
    record(repo)
    c = T.collect(d)
    i = item_of(c)
    assert i["status"] == "unapproved" and "statement not approved" in i["detail"]
    assert c["requirements"][0]["state"] == "unapproved"
    assert c["summary"]["by_state"].get("verified", 0) == 0
    assert any(g["type"] == "lean_statement_unapproved" and not g["gate"] for g in c["gaps"])
    assert "statement not approved" in c["summary"]["line"]
    assert T.gate(d) == []                       # not approved is a report, not a CI failure


def test_a_human_approval_makes_it_pass_with_its_tier_and_source_visible(repo):
    d = make_plan(repo)
    record(repo)
    approve(repo)
    c = T.collect(d)
    i = item_of(c)
    assert i["status"] == "pass" and i["lean"]["approved_by"] == "A. Person" and i["lean"]["build_source"] == "recorded build (not re-run)"
    assert c["requirements"][0]["state"] == "verified"
    assert c["requirements"][0]["lean_transcription_only"] is True
    md = T.render_md(c, repo / "designs" / "d" / "verif")
    assert "kernel only; transcription tested; recorded build" in md and "not of the RTL itself" in md


def test_a_compiled_decision_procedure_is_a_lower_tier_and_sorry_or_a_foreign_axiom_fails(repo):
    d = make_plan(repo)
    approve(repo)
    record(repo, tier="compiled_decision_procedure", axioms=["propext", "Foo.f_pos._native.bv_decide.ax_1_1"])
    i = item_of(T.collect(d))
    assert i["status"] == "pass" and i["lean"]["tier"] == "compiled_decision_procedure"
    assert "kernel plus a compiled decision procedure" in T.render_md(T.collect(d), repo / "designs" / "d" / "verif")
    record(repo, tier="unsound", axioms=["sorryAx"])
    assert item_of(T.collect(d))["status"] == "fail"
    assert LT.tier_of(["sorryAx"]) == "unsound" and LT.tier_of(["propext", "Classical.choice", "Quot.sound"]) == "kernel_only"
    assert LT.tier_of(["x._native.bv_decide.ax_12_3"]) == "compiled_decision_procedure" and LT.tier_of(["Foo.myAxiom"]) == "unsound"


def test_a_failed_build_fails_and_a_missing_record_is_not_run(repo):
    d = make_plan(repo)
    assert item_of(T.collect(d))["status"] == "not_run"
    record(repo, ok=False, tier=None)
    assert item_of(T.collect(d))["status"] == "fail"


def test_the_rtl_link_tiers_are_shown_distinctly(repo):
    texts = set()
    for kind in ("model_only", "transcription_untested", "transcription_tested"):
        link = {"kind": kind, **({k: v for k, v in LINK.items() if k != "kind"} if kind != "model_only" else {})}
        if kind == "transcription_untested":
            link.pop("crosscheck")
        d = make_plan(repo, link=link)
        record(repo)
        approve(repo)
        i = item_of(T.collect(d))
        assert i["lean"]["rtl_link"] == kind
        texts.add(i["lean"]["rtl_link_text"])
        if kind != "model_only":
            assert T.gate(d) == []
    assert texts == {LT.RTL_LINK_TEXT[k] for k in ("model_only", "transcription_untested", "transcription_tested")}
    assert "proof of the transcription, transcription tested" in texts


# ---- staleness -------------------------------------------------------------------------------------------
def test_stale_when_the_lean_files_the_statement_or_the_transcribed_rtl_lines_change(repo):
    d = make_plan(repo)
    record(repo)
    approve(repo)
    assert item_of(T.collect(d))["status"] == "pass"
    rtl = repo / "designs" / "d" / "rtl" / "a.sv"
    keep = rtl.read_text()
    rtl.write_text(keep.replace("line 4", "line four"))
    i = item_of(T.collect(d))
    assert i["status"] == "stale" and "transcribed RTL lines changed" in i["stale_because"]
    rtl.write_text(keep.replace("line 12", "line twelve"))               # outside the transcribed lines 3-5
    assert item_of(T.collect(d))["status"] == "pass"
    rtl.write_text(keep)
    p = repo / "formal" / "lean" / "Foo" / "CrossCheck.lean"
    p.write_text(p.read_text() + "-- touched\n")
    i = item_of(T.collect(d))
    assert i["status"] == "stale" and "Lean files changed since the recorded build" in i["stale_because"]


# ---- the frozen statement --------------------------------------------------------------------------------
def test_a_changed_approved_statement_fails_the_gate_but_a_comment_or_whitespace_does_not(repo):
    d = make_plan(repo)
    record(repo)
    approve(repo)
    p = repo / "formal" / "lean" / "Foo" / "Spec.lean"
    p.write_text(SPEC.replace("theorem f_pos (n : Nat) : 0 < f n", "-- a comment\ntheorem f_pos   (n : Nat) :\n    0 < f n"))
    assert T.gate(d) == []
    p.write_text(SPEC.replace("0 < f n", "0 ≤ f n"))                       # a weaker statement
    probs = T.gate(d)
    assert len(probs) == 1 and probs[0].startswith("lean_frozen_statement_changed") and "the statement is the specification" in probs[0]
    assert item_of(T.collect(d))["status"] == "fail"
    p.write_text(SPEC.replace("n + 1", "n + 2"))                            # a definition the statement rests on
    probs = T.gate(d)
    assert len(probs) == 1 and "definitions" in probs[0]


def test_an_unapproved_statement_may_change_freely_and_only_goes_stale(repo):
    d = make_plan(repo)
    record(repo)
    (repo / "formal" / "lean" / "Foo" / "Spec.lean").write_text(SPEC.replace("0 < f n", "0 ≤ f n"))
    assert T.gate(d) == []
    assert item_of(T.collect(d))["status"] == "stale"


def test_no_agent_can_approve_through_the_testplan_or_as_a_non_human(repo):
    d = make_plan(repo, extra_item={"approved_by": "Sonnet"})
    assert any("approved_by" in p and "refused" in p for p in T.gate(d))
    d = make_plan(repo, extra_item={"lean": {"module": "Foo.Spec", "theorem": "Foo.f_pos", "approved": True}})
    assert any("refused" in p for p in T.gate(d))
    d = make_plan(repo)
    record(repo)
    approve(repo, kind="agent")
    assert any("approver_kind must be human" in p for p in T.gate(d))
    approve(repo, item="V-NOT-THERE")
    assert any("unknown item" in p for p in T.gate(d))
    assert item_of(T.collect(d))["status"] == "unapproved"                 # an approval for another item approves nothing here


def test_the_gate_names_a_missing_theorem_a_missing_crosscheck_and_an_unreadable_source(repo):
    d = make_plan(repo, extra_item={"lean": {"module": "Foo.Spec", "theorem": "Foo.nope"}})
    assert any("not found" in p for p in T.gate(d))
    bad = copy.deepcopy(LINK)
    bad["crosscheck"]["file"] = "formal/lean/Foo/Missing.lean"
    assert any("cross-check" in p for p in T.gate(make_plan(repo, link=bad)))
    bad = copy.deepcopy(LINK)
    bad["source"] = [{"file": "designs/d/rtl/a.sv", "lines": "19-40"}]
    assert any("cannot be read" in p for p in T.gate(make_plan(repo, link=bad)))
    assert any("must name the RTL" in p for p in T.gate(make_plan(repo, link={"kind": "transcription_untested", "transcribed_in": "x"})))
    assert any("rtl_link" in p for p in T.gate(make_plan(repo, link={"kind": "magic"})))


# ---- where the status comes from -------------------------------------------------------------------------
def test_recorded_mode_never_runs_lake_and_live_without_the_toolchain_is_not_run(repo, monkeypatch):
    d = make_plan(repo)
    record(repo)

    def boom(*a, **k):
        raise AssertionError("lake must not run in recorded mode")
    monkeypatch.setattr(LT, "build_live", boom)
    assert item_of(T.collect(d, "recorded"))["status"] == "unapproved"
    monkeypatch.setattr(LT, "lake_path", lambda: None)
    assert item_of(T.collect(d, "live"))["status"] == "not_run"
    assert item_of(T.collect(d, "auto"))["lean"]["build_source"] == "recorded build (not re-run)"        # no toolchain: auto falls back to the record


def test_auto_uses_a_live_build_when_the_toolchain_is_present(repo, monkeypatch):
    d = make_plan(repo)
    record(repo)
    monkeypatch.setattr(LT, "toolchain_available", lambda: True)
    monkeypatch.setattr(LT, "build_live", lambda project, pairs: {"build_ok": True, "theorems": {"Foo.f_pos": {"module": "Foo.Spec", "build_ok": True, "axioms": [], "tier": "kernel_only"}}})
    i = item_of(T.collect(d, "auto"))
    assert i["lean"]["build_source"] == "lake build (live)" and i["status"] == "unapproved"


def test_the_statement_report_writes_nothing_and_shows_both_hashes(repo):
    d = make_plan(repo)
    it = T.load(d)["verification"][0]
    out = LT.statement_report(d, it)
    f = LT.frozen("formal/lean", "Foo.Spec", "Foo.f_pos")
    assert f["statement_sha256"] in out and f["definitions_sha256"] in out and "Nothing in this repository writes that file" in out
    assert not (d / "verif" / "lean_approvals.yaml").exists()


# ---- brief 135: a delegated acceptance is not a human approval ----------------------------------------------
def delegate(repo, item="V1", theorem="Foo.f_pos", **over):
    f = LT.frozen("formal/lean", "Foo.Spec", theorem)
    a = {"item": item, "theorem": theorem, "statement_sha256": f["statement_sha256"], "definitions_sha256": f["definitions_sha256"],
         "accepted_by": "planner (Session A)", "delegated_by": "owner decision 23", "approver_kind": "agent_delegated", "date": "2026-11-21", **over}
    a = {k: v for k, v in a.items() if v is not None}
    (repo / "designs" / "d" / "verif" / "lean_approvals.yaml").write_text(yaml.safe_dump({"schema": LT.APPROVAL_SCHEMA, "approvals": [a]}))


def test_a_delegated_acceptance_passes_but_is_shown_and_counted_apart_from_a_human_approval(repo):
    d = make_plan(repo)
    record(repo)
    delegate(repo)
    c = T.collect(d)
    i = item_of(c)
    assert i["status"] == "pass" and i["lean"]["approver_kind"] == "agent_delegated" and i["lean"]["accepted_by"] == "planner (Session A)"
    assert "accepted by planner (Session A) on the owner's delegation (owner decision 23)" in i["detail"] and "not a human approval" in i["detail"]
    assert "approved by a human" not in i["detail"]
    r = c["requirements"][0]
    assert r["state"] == "verified" and r["rests_on_delegated"] is True
    s = c["summary"]
    assert s["lean"]["delegated"] == 1 and s["lean"]["approved"] == 0 and s["verified_on_delegated"] == 1
    assert "1 verified, of which 1 rest on delegated acceptances" in s["line"]
    md = T.render_md(c, repo / "designs" / "d" / "verif")
    assert "statement accepted on delegation, not a human approval" in md and "rests on a delegated acceptance" in md
    assert T.gate(d) == []


def test_a_human_approval_is_shown_as_human_and_is_not_counted_as_delegated(repo):
    d = make_plan(repo)
    record(repo)
    approve(repo)
    c = T.collect(d)
    assert "proved; statement approved by a human (A. Person)" in item_of(c)["detail"]
    s = c["summary"]
    assert s["lean"]["approved"] == 1 and s["lean"]["delegated"] == 0 and s["verified_on_delegated"] == 0
    assert "of which" not in s["line"].split("Lean proof")[0]
    assert "statement approved by a human" in T.render_md(c, repo / "designs" / "d" / "verif")


def test_the_frozen_statement_gate_applies_to_a_delegated_acceptance_too(repo):
    d = make_plan(repo)
    record(repo)
    delegate(repo)
    (repo / "formal" / "lean" / "Foo" / "Spec.lean").write_text(SPEC.replace("0 < f n", "0 ≤ f n"))
    assert any(p.startswith("lean_frozen_statement_changed") and "planner (Session A) accepted it" in p for p in T.gate(d))


def test_a_delegated_entry_must_name_who_and_on_whose_delegation_and_never_says_approved_by(repo):
    d = make_plan(repo)
    record(repo)
    delegate(repo, delegated_by=None)
    assert any("lacks delegated_by" in p for p in T.gate(d))
    delegate(repo, approved_by="owner")
    assert any("never approved_by" in p for p in T.gate(d))
    approve(repo, accepted_by="planner")
    assert any("not accepted_by" in p for p in T.gate(d))


def test_no_agent_can_set_a_delegated_acceptance_through_the_testplan(repo):
    for k in ("accepted_by", "delegated_by"):
        d = make_plan(repo, extra_item={k: "planner"})
        assert any(k in p and "refused" in p for p in T.gate(d))
    d = make_plan(repo, extra_item={"lean": {"module": "Foo.Spec", "theorem": "Foo.f_pos", "approver_kind": "agent_delegated"}})
    assert any("refused" in p for p in T.gate(d))


# ---- the committed repository ----------------------------------------------------------------------------
def test_committed_lean_items_pass_the_gate_and_the_record_is_not_stale():
    for d in T.v1_designs():
        c = T.collect(d)
        lean = [i for i in c["items"] if i["method"] == "formal_lean"]
        assert T.gate(d) == []
        for i in lean:
            assert i["status"] in ("pass", "unapproved"), (i["id"], i["status"], i.get("stale_because"), i["detail"])
            assert i["lean"]["build_source"] == "recorded build (not re-run)"
            assert i["lean"]["tier"] in ("kernel_only", "compiled_decision_procedure")


def test_the_committed_plans_carry_the_124_theorems_and_the_gray_lemma():
    """The gray-code theorems are b96's (rate_match_gp); the checksum theorems are b119's (tcp_fast), moved there by brief 133."""
    def lean_items(design):
        return [i for i in T.collect(REPO / "designs" / design)["items"] if i["method"] == "formal_lean"]
    b96, b119 = lean_items("b96_kr260_10g"), lean_items("b119_tcp_fast")
    assert {i["lean"]["theorem"] for i in b96} == {"Gray.gray_step", "Gray.gray2bin_bin2gray", "Gray.bin2gray_gray2bin", "Gray.gray_sample"}
    assert {i["lean"]["theorem"] for i in b119} == {"Cksum.rtl_ip_correct", "Cksum.rtl_ip_receiver", "Cksum.rtl_tcp_correct", "Cksum.ocSum_toNat",
                                                    "Cksum.incUpdate_correct", "Cksum.incUpdate_zero_corner"}
    kinds = {i["lean"]["rtl_link"] for i in b96 + b119}
    assert kinds == {"transcription_tested", "model_only"}                       # no RTL-generated model exists, and none is claimed


def test_the_lean_files_tag_the_ids_of_the_plan_that_owns_them():
    """A `req:` tag in a doc comment of formal/lean must be a requirement id of the b96 or b119 testplan (brief 133 renamed the checksum tags)."""
    import re
    ids = {r["id"] for d in ("b96_kr260_10g", "b119_tcp_fast") for r in T.load(REPO / "designs" / d)["requirements"]}
    tags = set()
    for f in ("Gray/Spec.lean", "Cksum/Spec.lean"):
        tags |= set(re.findall(r"req:\s*(\S+)", (REPO / "formal" / "lean" / f).read_text().replace("-/", " ")))
    assert tags and tags <= ids, tags - ids


def test_every_lean_theorem_the_plan_names_is_in_the_committed_record():
    rec = LT.load_record()
    assert rec and rec["schema"] == LT.RECORD_SCHEMA and rec["build_ok"] is True
    for d in T.v1_designs():
        for it in T.load(d)["verification"]:
            if it.get("method") == "formal_lean":
                assert it["lean"]["theorem"] in rec["theorems"], it["id"]


# ---- the toolchain-dependent parts (skipped without Lean; CI does not have it) ------------------------------
@needs_lean
def test_a_live_build_agrees_with_the_committed_record():
    rec = LT.load_record()
    pairs = sorted((v["module"], k) for k, v in rec["theorems"].items())
    b = LT.build_live("formal/lean", pairs)
    assert b["build_ok"]
    for k, v in rec["theorems"].items():
        assert b["theorems"][k]["axioms"] == v["axioms"] and b["theorems"][k]["tier"] == v["tier"], k
    assert LT.project_files("formal/lean") == rec["files"]
    assert b["lean_version"].startswith("Lean (version 4.36.0")


@needs_lean
def test_the_matrix_is_the_same_whether_the_status_is_read_from_the_record_or_built_live():
    d = REPO / "designs" / "b96_kr260_10g"
    rec = {i["id"]: (i["status"], i["lean"]["tier"]) for i in T.collect(d, "recorded")["items"] if i["method"] == "formal_lean"}
    live = {i["id"]: (i["status"], i["lean"]["tier"]) for i in T.collect(d, "live")["items"] if i["method"] == "formal_lean"}
    assert rec == live


@needs_iverilog
def test_the_gray_crosscheck_file_is_what_the_simulation_writes_today():
    spec = importlib.util.spec_from_file_location("crosscheck_gray", REPO / "formal" / "lean" / "tools" / "crosscheck_gray.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.render(8) == (REPO / "formal" / "lean" / "Gray" / "CrossCheck.lean").read_text()


# ---- the proof driver ------------------------------------------------------------------------------------
def _driver(monkeypatch):
    sys.path.insert(0, str(REPO / "formal" / "lean" / "tools"))
    spec = importlib.util.spec_from_file_location("lean_prove_driver", REPO / "formal" / "lean" / "tools" / "prove.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import agent.access
    import agent.models
    monkeypatch.setattr(agent.access, "require_or_exit", lambda *a, **k: None)
    return m, agent.models


class _Stub:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def entry(self, purpose, *a, **k):
        assert purpose == "proof"
        return type("E", (), {"endpoint": "claude_code", "model": "stub-model", "options": {"effort": "medium"}})()

    def text(self, purpose, *a, **k):
        assert purpose == "proof"

        def llm(system, user):
            self.calls.append((system, user))
            return self.replies.pop(0)
        return llm


def test_the_driver_rejects_an_edited_statement_without_building_and_records_the_round(tmp_path, monkeypatch):
    m, models = _driver(monkeypatch)
    spec = (REPO / "formal" / "lean" / "Gray" / "Spec.lean").read_text()
    edited = spec.replace("(hn : 0 < n)", "(hn : 1 < n)", 1)               # a weakened statement
    stub = _Stub(["```lean\n" + edited + "```"])
    monkeypatch.setattr(models, "resolver_for", lambda purpose, **k: (_ for _ in ()).throw(AssertionError) if purpose != "proof" else stub)
    monkeypatch.setattr(sys, "argv", ["prove.py", "--module", "Gray.Spec", "--theorem", "gray_step", "--out", str(tmp_path / "o"), "--rounds", "1"])
    assert m.main() == 1
    res = json.loads((tmp_path / "o" / "result.json").read_text())
    assert res["purpose"] == "proof" and res["solved"] is False and res["first_try_ok"] is False and res["rounds_used"] == 1
    assert res["rounds"][0]["statement_errors"] and res["rounds"][0]["build_s"] == 0.0
    assert "Prove these theorems: gray_step" in stub.calls[0][1] and "statements are the specification" in stub.calls[0][0]


def test_the_driver_refuses_an_unknown_theorem(tmp_path, monkeypatch):
    m, models = _driver(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["prove.py", "--module", "Gray.Spec", "--theorem", "nope", "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit, match="no such theorem"):
        m.main()


@needs_lean
def test_the_driver_feeds_the_checker_back_and_stops_when_it_builds(tmp_path, monkeypatch):
    m, models = _driver(monkeypatch)
    spec = (REPO / "formal" / "lean" / "Gray" / "Spec.lean").read_text()
    broken = spec.replace("end Gray", "theorem broken : 1 = 2 := by\n  decide\nend Gray")        # a helper that does not build (only a decision on a false goal)
    stub = _Stub(["```lean\n" + broken + "```", "```lean\n" + spec + "```"])
    monkeypatch.setattr(models, "resolver_for", lambda purpose, **k: stub)
    monkeypatch.setattr(sys, "argv", ["prove.py", "--module", "Gray.Spec", "--theorem", "gray_step", "--out", str(tmp_path / "o"), "--rounds", "3"])
    rc = m.main()
    res = json.loads((tmp_path / "o" / "result.json").read_text())
    assert res["rounds"][0]["build_ok"] is False and res["rounds"][0]["errors"] >= 1 and "Lean reported" in stub.calls[1][1]
    assert rc == 0 and res["solved"] is True and res["rounds_used"] == 2 and res["first_try_ok"] is False
    assert (tmp_path / "o" / "proved_Gray.Spec.lean").exists()


# ---- the model table and CI without Lean --------------------------------------------------------------------
def test_the_proof_purpose_is_sonnet_on_the_subscription_and_a_default_does_not_move_it():
    from agent.models import build_table
    t = build_table()
    e = t.entry("proof")
    assert (e.kind, e.model) == ("claude_code", "claude-sonnet-5-5") and e.options["timeout_s"] == 1500


def test_the_committed_matrices_are_written_from_the_record_so_they_do_not_depend_on_the_machine():
    out = T.outputs(T.v1_designs())
    for p, text in out.items():
        assert p.read_text() == text, p
    assert "recorded build" in out[REPO / "designs" / "b96_kr260_10g" / "verif" / "matrix.md"]
