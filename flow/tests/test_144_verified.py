"""Brief 144: the verification record (flow/verified.py, docs/verified.md).

The committed VERIFIED.md and verified.json of every design, arithmetic function and IP-library entry equal what the generator writes now (the CI check),
the label rules behave as documented, a field a 143 brief has not added counts as not met, no record carries a board or deploy command, and the READMEs
and AGENT.md carry the label."""
import json
from pathlib import Path

import pytest

from flow import verified as V

ROOT = V.ROOT
ENTRIES = V.entries()


def test_every_entry_has_a_current_record():
    assert ENTRIES, "no entries found"
    assert V.check(ENTRIES) == []


def test_manifest_hashes_match_the_files():
    for d in ENTRIES:
        rec = json.loads((d / "verified.json").read_text())
        for p, h in rec["manifest"].items():
            f = ROOT / p
            assert (V.sha(f) if f.is_file() else "absent") == h, f"{d.name}: {p}"


def test_a_changed_manifest_hash_is_a_difference():
    rec = V.record(ROOT / "designs" / "b119_tcp_fast")
    k = next(iter(rec["manifest"]))
    other = dict(rec, manifest=dict(rec["manifest"], **{k: "0" * 64}))
    assert V.norm(V.render_md(rec)) != V.norm(V.render_md(other))
    assert V.norm(V.render_json(rec)) != V.norm(V.render_json(other))


def test_the_commit_is_the_only_field_not_compared():
    rec = V.record(ROOT / "designs" / "b119_tcp_fast")
    other = dict(rec, git_commit="deadbeef")
    assert V.norm(V.render_md(rec)) == V.norm(V.render_md(other))
    assert V.norm(V.render_json(rec)) == V.norm(V.render_json(other))


def _req(rid, state="verified", status="draft"):
    return {"id": rid, "state": state, "agreement": {"status": status}}


def _crits(**over):
    base = {k: V.crit(k, "met", "") for k, _ in V.CRITERIA}
    for k, v in over.items():
        base[k] = V.crit(k, v, "x", ["R1"])
    return list(base.values())


def test_label_verified_only_when_every_criterion_is_met():
    reqs = [_req("R1")]
    assert V.label_of(_crits(), reqs) == ("verified", "verified")
    kind, text = V.label_of(_crits(agreement="unmet"), reqs)
    assert kind == "verified_except" and text.startswith("verified except:") and "not agreed" in text


def test_a_criterion_not_yet_measured_counts_as_not_met():
    kind, text = V.label_of(_crits(mutation="not_measured"), [_req("R1")])
    assert kind == "verified_except" and "mutation floor not yet measured" in text


def test_label_not_verified_when_a_requirement_fails_or_none_passes():
    assert V.label_of(_crits(), [_req("R1"), _req("R2", state="fail")])[0] == "not_verified"
    assert V.label_of(_crits(), [_req("R1", state="not_run")])[0] == "not_verified"


def test_agreement_kinds_are_counted_apart_and_a_testplan_cannot_claim_it():
    assert V.agreement({"spec_status": "draft"})["status"] == "draft"
    assert V.agreement({"spec_status": "agreed"})["status"] == "unrecorded"
    h = V.agreement({"agreement": {"kind": "human", "by": "owner", "date": "2026-11-22"}})
    d = V.agreement({"agreement": {"kind": "agent_delegated", "by": "planner", "date": "2026-11-22"}})
    assert h["status"] == "agreed_human" and d["status"] == "agreed_delegated" and "delegated" in d["text"]


def test_143_fields_are_read_when_the_collector_supplies_them():
    c = {"items": [{"id": "i", "method": "formal", "status": "pass"}], "mutation": {"score": 0.9, "floor": 0.8, "met": True},
         "formal_rigour": {"met": False, "detail": "2 vacuous"}, "fresh_run": {"differs": []}}
    reqs = [dict(_req("R1", status="agreed_human"), method_mix={"met": True})]
    by = {k["id"]: k for k in V.criteria(c, reqs)}
    assert by["mutation"]["state"] == "met" and by["formal_rigour"]["state"] == "unmet" and by["fresh"]["state"] == "met"
    assert by["method_mix"]["state"] == "met" and by["agreement"]["state"] == "met"


def test_no_record_lists_a_board_or_deploy_command():
    for d in ENTRIES:
        for c in json.loads((d / "verified.json").read_text())["reproduce"]:
            assert not V.DENY.search(c["cmd"]), f"{d.name}: {c['cmd']}"
    assert V.DENY.search("flow/run_vivado.sh designs/x") and V.DENY.search("python flow/bringup.py x")


def test_a_directory_without_a_testplan_is_not_assessed():
    rec = V.record(ROOT / "ip_lib" / "crc32_step")
    assert rec["label_kind"] == "not_assessed" and rec["declared"]["source"] == "ip.yaml"


def test_readmes_and_agent_hand_over_carry_the_label():
    for d in ENTRIES:
        label = json.loads((d / "verified.json").read_text())["label"]
        if d.parent.name == "designs":
            assert f"**Verification: {label}.**" in (d / "README.md").read_text(), d.name
            assert f"verified: {label}" in (d / "AGENT.md").read_text(), d.name
        elif d.parent.name == "ip_lib":
            assert f"**Verification: {label}.**" in (d / "README.md").read_text(), d.name


def test_every_design_and_ip_entry_is_covered():
    names = {d.relative_to(ROOT).as_posix() for d in ENTRIES}
    for p in (ROOT / "designs").iterdir():
        if p.is_dir() and not p.name.startswith(("_", ".")):
            assert f"designs/{p.name}" in names
    for p in (ROOT / "ip_lib").glob("*/ip.yaml"):
        assert f"ip_lib/{p.parent.name}" in names
