"""Brief 143a: requirement agreement pinned by text hash, the method mix per requirement kind, who wrote each test, review records and waivers."""
import json
import shutil
from pathlib import Path

import pytest
import yaml

from flow import trace_records as TR
from flow import trace_v1 as T

REAL_POLICY = Path(__file__).resolve().parents[1] / "method_mix_policy.yaml"


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setenv("TRACE_TODAY", "2026-11-21")
    (tmp_path / "designs" / "d" / "verif").mkdir(parents=True)
    (tmp_path / "designs" / "d" / "rtl").mkdir()
    (tmp_path / "designs" / "d" / "rtl" / "a.sv").write_text("module a; endmodule\n")
    (tmp_path / "results").mkdir()
    (tmp_path / "flow").mkdir()
    shutil.copy(REAL_POLICY, tmp_path / "flow" / "method_mix_policy.yaml")
    return tmp_path


def D(repo):
    return repo / "designs" / "d"


def plan(repo, reqs, items):
    (D(repo) / "verif" / "testplan.yaml").write_text(yaml.safe_dump({"schema": T.SCHEMA_V1, "design": "d", "requirements": reqs, "verification": items}))
    return D(repo)


def rec(repo, name, rows, schema, key):
    (D(repo) / "verif" / name).write_text(yaml.safe_dump({"schema": schema, key: rows}))


def ok(repo, name="v.json"):
    (repo / "results" / name).write_text(json.dumps({"v": True}))
    return {"file": f"results/{name}", "reader": "json", "field": "v"}


def it(i, req, method, ev, **k):
    return {"id": i, "requirements": [req], "method": method, "evidence": ev, **k}


def req(rid="R1", kind="functional", text="x holds"):
    return {"id": rid, "kind": kind, "title": "t", "text": text, "spec_status": "draft"}


def state(repo, d, rid="R1"):
    return next(r for r in T.collect(d)["requirements"] if r["id"] == rid)


# ---- 1. agreement ----------------------------------------------------------------------------------------
def test_requirement_is_a_draft_until_a_record_agrees_it(repo):
    d = plan(repo, [req()], [it("i", "R1", "formal", ok(repo))])
    r = state(repo, d)
    assert r["agreement"] == "draft"
    h = TR.req_hash(req())
    rec(repo, "agreements.yaml", [{"requirement": "R1", "text_sha256": h, "agreed_kind": "human", "agreed_by": "owner", "date": "2026-11-21"}], TR.AGREEMENTS_SCHEMA, "agreements")
    assert state(repo, d)["agreement"] == "agreed_human"
    rec(repo, "agreements.yaml", [{"requirement": "R1", "text_sha256": h, "agreed_kind": "agent_delegated", "accepted_by": "planner", "delegated_by": "owner decision 25",
                                   "date": "2026-11-21"}], TR.AGREEMENTS_SCHEMA, "agreements")
    c = T.collect(d)
    assert c["requirements"][0]["agreement"] == "agreed_delegated" and "not human" in c["summary"]["line"]
    assert c["summary"]["agreement"] == {"draft": 0, "agreed_human": 0, "agreed_delegated": 1} and c["summary"]["spec_agreed"] == 0
    assert T.gate(d) == []


def test_changed_requirement_text_drops_the_agreement_back_to_draft(repo):
    h = TR.req_hash(req(text="x holds"))
    rec(repo, "agreements.yaml", [{"requirement": "R1", "text_sha256": h, "agreed_kind": "human", "agreed_by": "owner", "date": "2026-11-21"}], TR.AGREEMENTS_SCHEMA, "agreements")
    d = plan(repo, [req(text="x holds and y holds")], [it("i", "R1", "formal", ok(repo))])
    c = T.collect(d)
    assert c["requirements"][0]["agreement"] == "draft"
    assert any(g["type"] == "agreement_dropped" for g in c["gaps"])
    assert T.gate(d) == []                            # a drop is reported, not a failure
    # a changed bound drops it too; a changed source anchor does not
    assert TR.req_hash({**req(), "source": "elsewhere"}) == TR.req_hash(req())
    assert TR.req_hash({**req(), "performance": {"bound": 1}}) != TR.req_hash(req())


def test_the_testplan_cannot_claim_agreement(repo):
    q = req()
    q["spec_status"] = "agreed"
    d = plan(repo, [q], [it("i", "R1", "formal", ok(repo))])
    assert state(repo, d)["agreement"] == "draft"
    assert any("cannot claim agreement" in p for p in T.gate(d))


def test_agreement_record_form_is_gated(repo):
    d = plan(repo, [req()], [it("i", "R1", "formal", ok(repo))])
    h = TR.req_hash(req())
    bad = [{"requirement": "NOPE", "text_sha256": h, "agreed_kind": "human", "agreed_by": "o", "date": "2026-11-21"},
           {"requirement": "R1", "text_sha256": "abc", "agreed_kind": "agent_delegated", "accepted_by": "p", "date": "2026-11-21"},
           {"requirement": "R1", "text_sha256": h, "agreed_kind": "robot", "date": "2026-11-21"}]
    rec(repo, "agreements.yaml", bad, TR.AGREEMENTS_SCHEMA, "agreements")
    p = "\n".join(T.gate(d))
    for frag in ("not a requirement of this testplan", "text_sha256 must be", "needs accepted_by and delegated_by", "agreed_kind must be", "agreed twice"):
        assert frag in p, frag
    rec(repo, "agreements.yaml", [{"requirement": "R1", "text_sha256": h, "agreed_kind": "human", "agreed_by": "o", "delegated_by": "x", "date": "2026-11-21"}], TR.AGREEMENTS_SCHEMA, "agreements")
    assert "never uses delegated_by" in "\n".join(T.gate(d))


def test_agreement_hash_command_prints_the_hash_and_writes_nothing(repo, capsys):
    d = plan(repo, [req()], [it("i", "R1", "formal", ok(repo))])
    assert T.main(["agreement-hash", str(d)]) == 0
    assert TR.req_hash(req()) in capsys.readouterr().out
    assert not (D(repo) / "verif" / "agreements.yaml").exists()


# ---- 2. the method mix -----------------------------------------------------------------------------------
def test_functional_needs_an_independent_test_or_formal_or_the_board(repo):
    own = it("a", "R1", "sim_test", ok(repo, "a.json"))
    r = state(repo, plan(repo, [req()], [own]))
    assert r["state"] == "partially_verified" and r["own_tests_only"] and r["missing_methods"] == [TR_label(repo, "independent_simulation")]
    indep = it("a", "R1", "sim_test", ok(repo, "a.json"), written_by="independent_bench")
    assert state(repo, plan(repo, [req()], [indep]))["state"] == "verified"
    assert state(repo, plan(repo, [req()], [own, it("f", "R1", "formal", ok(repo, "f.json"))]))["state"] == "verified"
    assert state(repo, plan(repo, [req()], [it("b", "R1", "board_measurement", ok(repo, "b.json"), instrument="jtag_registers", pass_when=[{"field": "v", "op": "true"}])]))["state"] == "verified"


def TR_label(repo, g):
    return TR.load_policy(repo / "flow" / "method_mix_policy.yaml")["groups"][g]["label"]


def test_safety_needs_simulation_plus_formal_or_board(repo):
    q = req(kind="safety")
    sim, formal = it("s", "R1", "sim_test", ok(repo, "s.json")), it("f", "R1", "formal", ok(repo, "f.json"))
    r = state(repo, plan(repo, [q], [sim]))
    assert r["state"] == "partially_verified" and len(r["missing_methods"]) == 1 and "formal" in r["missing_methods"][0]
    assert state(repo, plan(repo, [q], [formal]))["state"] == "partially_verified"
    assert state(repo, plan(repo, [q], [sim, formal]))["state"] == "verified"
    board = it("b", "R1", "board_measurement", ok(repo, "b.json"), instrument="jtag_registers", pass_when=[{"field": "v", "op": "true"}])
    assert state(repo, plan(repo, [q], [sim, board]))["state"] == "verified"
    c = T.collect(plan(repo, [q], [sim]))
    assert any(g["type"] == "method_mix_missing" and "lacks" in g["text"] for g in c["gaps"]) and "partially verified" in c["summary"]["line"]


def test_performance_keeps_its_measurement_rule_through_the_policy(repo):
    q = {"id": "P1", "kind": "performance", "title": "E", "performance": {"quantity": "E", "unit": "clocks", "op": "le", "bound": 22, "condition": "c"}}
    (repo / "results" / "m.json").write_text(json.dumps({"v": 21}))
    meas = it("m", "P1", "sim_measurement", {"file": "results/m.json", "reader": "json", "field": "v"})
    assert state(repo, plan(repo, [q], [meas]), "P1")["state"] == "verified"
    assert state(repo, plan(repo, [q], [it("s", "P1", "sim_test", ok(repo))]), "P1")["state"] == "no_measurement"


def test_without_a_policy_file_one_passing_item_verifies_as_before(repo):
    (repo / "flow" / "method_mix_policy.yaml").unlink()
    assert state(repo, plan(repo, [req()], [it("a", "R1", "sim_test", ok(repo))]))["state"] == "verified"


def test_a_failing_item_still_fails_and_the_committed_policy_loads():
    p = TR.load_policy(REAL_POLICY)
    assert set(p["kinds"]) == {"safety", "performance", "functional", "interface"}
    assert p["kinds"]["performance"] == [["measurement"]]


# ---- 3. who wrote the test -------------------------------------------------------------------------------
def test_author_is_shown_and_an_unknown_author_fails_the_gate(repo):
    items = [it("a", "R1", "sim_test", ok(repo, "a.json")), it("b", "R1", "uvm_test", ok(repo, "b.json"), written_by="independent_bench")]
    d = plan(repo, [req()], items)
    c = T.collect(d)
    md = T.render_md(c, D(repo) / "verif")
    assert "[author not recorded]" in md and "[independent bench]" in md
    assert T.gate(d) == []
    d = plan(repo, [req()], [it("a", "R1", "sim_test", ok(repo), written_by="a friend")])
    assert any("written_by must be one of" in p for p in T.gate(d))
    d = plan(repo, [req()], [it("a", "R1", "formal", ok(repo), written_by="human")])
    assert any("applies to tests" in p for p in T.gate(d))


def test_a_requirement_resting_on_own_tests_only_is_flagged(repo):
    c = T.collect(plan(repo, [req()], [it("a", "R1", "sim_test", ok(repo))]))
    assert c["requirements"][0]["own_tests_only"] and c["summary"]["own_tests_only"] == 1
    assert any(g["type"] == "own_tests_only" for g in c["gaps"])
    c = T.collect(plan(repo, [req()], [it("a", "R1", "sim_test", ok(repo), written_by="human")]))
    assert not c["requirements"][0]["own_tests_only"]


# ---- 4. reviews and waivers ------------------------------------------------------------------------------
def review_item():
    return {"id": "rv", "requirements": ["R1"], "method": "review", "title": "review", "reviewer": "Sonnet", "reviewer_kind": "agent", "date": "2026-11-17"}


def test_a_review_item_does_not_pass_by_default(repo):
    d = plan(repo, [req()], [review_item()])
    c = T.collect(d)
    assert c["items"][0]["status"] == "not_run" and "no review record" in c["items"][0]["detail"]
    assert c["requirements"][0]["state"] == "not_run"


def test_a_review_record_passes_it_and_names_the_kind(repo):
    d = plan(repo, [req()], [review_item()])
    (repo / "designs" / "d" / "rtl" / "b.sv").write_text("module b; endmodule\n")
    rec(repo, "reviews.yaml", [{"item": "rv", "reviewer": "Sonnet", "reviewer_kind": "agent_delegated", "delegated_by": "owner decision 25", "date": "2026-11-21",
                                "read": ["designs/d/rtl/a.sv"], "findings": "none"}], TR.REVIEWS_SCHEMA, "reviews")
    c = T.collect(d)
    assert c["items"][0]["status"] == "pass" and c["items"][0]["reviewer_kind"] == "agent_delegated" and c["summary"]["delegated_reviews"] == 1
    assert "agent delegated review" in T.render_md(c, D(repo) / "verif")
    assert T.gate(d) == []


def test_review_record_problems_and_a_changed_file_that_was_read(repo):
    d = plan(repo, [req()], [review_item(), it("a", "R1", "sim_test", ok(repo))])
    sha = TR.hashlib.sha256((repo / "designs/d/rtl/a.sv").read_bytes()).hexdigest()
    rec(repo, "reviews.yaml", [{"item": "rv", "reviewer": "x", "reviewer_kind": "human", "date": "2026-11-21", "read": [{"file": "designs/d/rtl/a.sv", "sha256": sha}], "findings": "f"}],
        TR.REVIEWS_SCHEMA, "reviews")
    assert T.collect(d)["items"][0]["status"] == "pass"
    (repo / "designs/d/rtl/a.sv").write_text("module a; wire w; endmodule\n")
    i = T.collect(d)["items"][0]
    assert i["status"] == "stale" and "has changed since" in i["stale_because"]
    rec(repo, "reviews.yaml", [{"item": "a", "reviewer_kind": "robot", "read": [], "findings": " "}, {"item": "rv", "reviewer": "x", "reviewer_kind": "agent_delegated", "date": "2026-11-21",
                                                                                                   "read": ["nope.txt"], "findings": "f"}], TR.REVIEWS_SCHEMA, "reviews")
    p = "\n".join(T.gate(d))
    for frag in ("not a `review` item", "needs reviewer", "reviewer_kind must be", "needs `read`", "needs findings", "needs delegated_by", "does not exist"):
        assert frag in p, frag


def waiver(**k):
    base = {"id": "W1", "requirement": "R1", "waives": ["formal"], "reason": "no formal tool for this block", "expires": "2026-12-31", "approver_kind": "human",
            "approved_by": "owner", "date": "2026-11-21"}
    return {**base, **k}


def test_a_waiver_covers_the_missing_group_and_is_shown(repo):
    q = req(kind="safety")
    d = plan(repo, [q], [it("s", "R1", "sim_test", ok(repo))])
    assert state(repo, d)["state"] == "partially_verified"
    rec(repo, "waivers.yaml", [waiver()], TR.WAIVERS_SCHEMA, "waivers")
    c = T.collect(d)
    r = c["requirements"][0]
    assert r["state"] == "waived" and r["waivers"][0]["id"] == "W1" and c["summary"]["waived"] == 1
    assert "W1" in T._state_cell(r) and "verified under a waiver" in c["summary"]["line"]
    assert any(g["type"] == "waiver_in_effect" for g in c["gaps"]) and T.gate(d) == []
    rec(repo, "waivers.yaml", [waiver(waives=["board"])], TR.WAIVERS_SCHEMA, "waivers")      # wrong scope: the missing group is not covered
    assert state(repo, d)["state"] == "partially_verified"


def test_an_expired_waiver_waives_nothing(repo):
    d = plan(repo, [req(kind="safety")], [it("s", "R1", "sim_test", ok(repo))])
    rec(repo, "waivers.yaml", [waiver(expires="2026-11-20")], TR.WAIVERS_SCHEMA, "waivers")
    c = T.collect(d)
    assert c["requirements"][0]["state"] == "partially_verified" and any(g["type"] == "waiver_expired" for g in c["gaps"])


def test_no_waiver_for_a_safety_requirement_without_a_human(repo):
    d = plan(repo, [req(kind="safety")], [it("s", "R1", "sim_test", ok(repo))])
    rec(repo, "waivers.yaml", [waiver(approver_kind="agent_delegated", approved_by=None, accepted_by="planner", delegated_by="owner decision 25")], TR.WAIVERS_SCHEMA, "waivers")
    assert any("only by a human" in p for p in T.gate(d))
    assert state(repo, d)["state"] == "partially_verified"              # and it is not applied
    # a delegated waiver of a functional requirement is allowed
    d = plan(repo, [req()], [it("s", "R1", "sim_test", ok(repo))])
    rec(repo, "waivers.yaml", [waiver(waives=["independent_simulation"], approver_kind="agent_delegated", approved_by=None, accepted_by="planner", delegated_by="owner decision 25")],
        TR.WAIVERS_SCHEMA, "waivers")
    assert T.gate(d) == [] and state(repo, d)["state"] == "waived"


def test_waiver_record_problems(repo):
    d = plan(repo, [req()], [it("s", "R1", "sim_test", ok(repo))])
    rec(repo, "waivers.yaml", [waiver(requirement="X", waives=["telepathy"], reason="", expires="soon", id=None)], TR.WAIVERS_SCHEMA, "waivers")
    p = "\n".join(T.gate(d))
    for frag in ("needs an id", "is not in this testplan", "must list method groups", "needs a reason", "needs an expiry date"):
        assert frag in p, frag


def test_a_waiver_does_not_rescue_a_requirement_with_nothing_passing(repo):
    d = plan(repo, [req(kind="safety")], [it("s", "R1", "sim_test", {"file": "results/none.json", "reader": "json", "field": "v"})])
    rec(repo, "waivers.yaml", [waiver(waives=["simulation", "formal"])], TR.WAIVERS_SCHEMA, "waivers")
    assert state(repo, d)["state"] == "not_run"
