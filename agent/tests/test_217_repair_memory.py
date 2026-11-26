"""Brief 217: repair records, retrieval by exact evidence, and the check suite over MCP. No model is called."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from mcp import Client

from agent.graph import repair_memory as rm
from agent.mcp_server.checks import READ_ONLY_TOOLS, build_checks_server, copy_design, skills_markdown

ROOT_DIR = "/home/x/runs/p3/p3_crc_engine"
LINT_SUPPLIED = (
    f"%Warning-UNUSEDSIGNAL: {ROOT_DIR}/data/jtag_bus.sv:20:21: Signal is not used: 'tdo'\n"
    "                       : ... note: In instance 'crc32_top.u_jtag'\n"
    "   20 |     logic tck, tdi, tdo, sel, shift, capture, update;\n"
    f"%Warning-UNUSEDSIGNAL: {ROOT_DIR}/data/jtag_bus.sv:41:18: Bits of signal are not used: 'cmd_s'[45]\n"
    "%Error: Exiting due to 2 warning(s)\n"
    "FDA-CON-8 spec.yaml declares port jtag_bus internal: h_we, but the top module crc32_top has no port jtag_bus internal: h_we.\n")
LINT_OWN = f"%Warning-UNUSEDSIGNAL: {ROOT_DIR}/rtl/crc32_top.sv:12:9: Signal is not used: 'spare'\n%Error: Exiting due to 1 warning(s)\n"


def ev_lint(text: str) -> dict:
    return {"lint": {"ok": False, "text": text}, "contract": {"ok": True}, "simulate": {"ok": True}, "verif": {"reached": "V2"}, "verif_level": "V2"}


def design(tmp_path: Path, rtl: str, name: str = "d1") -> Path:
    d = tmp_path / name
    (d / "rtl").mkdir(parents=True, exist_ok=True)
    (d / "rtl" / "top.sv").write_text(rtl)
    (d / "spec.yaml").write_text("name: crc32_top\nports:\n  - {name: jtag_bus, interface: jtag_bus}\n")
    return d


# --- the evidence keys --------------------------------------------------------------------------------------------------------------------------

def test_lint_keys_separate_supplied_from_own_findings_and_name_the_rule_ids():
    ks = {rm.key_tuple(k) for k in rm.evidence_keys(ev_lint(LINT_SUPPLIED))}
    assert ("lint", "VL-UNUSEDSIGNAL", "supplied: Signal is not used") in ks
    assert ("lint", "VL-UNUSEDSIGNAL", "supplied: Bits of signal are not used") in ks
    assert ("lint", "FDA-CON-8", "default") in ks
    own = {rm.key_tuple(k) for k in rm.evidence_keys(ev_lint(LINT_OWN))}
    assert own == {("lint", "VL-UNUSEDSIGNAL", "own: Signal is not used")}       # same warning code, a different class: a different key


def test_simulate_and_standards_keys():
    ev = {"lint": {"ok": True}, "contract": {"ok": True}, "standards_fails": ["STD-CDC-01 architecture.yaml:1: crossings[0]: inline_in jtag_bus is not a module"],
          "simulate": {"ok": False, "first_failure": {"test": "t", "message": ["AssertionError: q: rtl 0x1 model 0x2"], "cause": []},
                       "first_check": {"kind": "assertion", "signal": "h_rdata"}}, "verif": {"reached": "V2"}, "verif_level": "V2"}
    ks = {rm.key_tuple(k) for k in rm.evidence_keys(ev)}
    assert ("standards", "STD-CDC-01", "default") in ks and ("simulate", "AssertionError", "mismatch:h_rdata") in ks
    stop = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": False, "first_check": {"kind": "sim_stop", "class": "no-clock-edge", "message": "m"}},
            "verif": {"reached": "V2"}, "verif_level": "V2"}
    assert {rm.key_tuple(k) for k in rm.evidence_keys(stop)} == {("simulate", "SIM-STOP", "no-clock-edge")}


# --- record creation ----------------------------------------------------------------------------------------------------------------------------

def test_a_failing_gate_that_passes_after_an_edit_leaves_a_record(tmp_path):
    d = design(tmp_path, "module top; logic spare; endmodule\n")
    run = tmp_path / "run"
    st, written = rm.step(run, d, "run-A", None, ev_lint(LINT_OWN), False, 1)
    assert not written and [rm.key_tuple(k) for k in st["keys"]] == [("lint", "VL-UNUSEDSIGNAL", "own: Signal is not used")]
    (d / "rtl" / "top.sv").write_text("module top; /* verilator lint_off UNUSEDSIGNAL */ logic spare; endmodule\n")
    st2, written = rm.step(run, d, "run-A", st, {}, True, 2, repair_note="I waived the signal.")
    assert st2["keys"] == [] and len(written) == 1
    r = written[0]
    assert r["trigger"]["finding_id"] == "VL-UNUSEDSIGNAL" and r["provenance"] == "agent-repair" and r["produced_by"] != "human"
    assert r["fix"]["files"] == ["rtl/top.sv"] and "+module top; /* verilator lint_off" in r["fix"]["diff"]
    assert r["run_id"] == "run-A" and "all stage-2 gates" in r["constraints_preserved"] and r["agent_note"].startswith("I waived")
    assert json.loads((run / "repair_memory" / "records" / f"{r['id']}.json").read_text())["id"] == r["id"]
    assert rm.valid(r)


def test_no_record_when_no_file_changed_or_the_key_still_fails(tmp_path):
    d = design(tmp_path, "module top; endmodule\n")
    run = tmp_path / "run"
    st, _ = rm.step(run, d, "r", None, ev_lint(LINT_OWN), False, 1)
    st2, written = rm.step(run, d, "r", st, ev_lint(LINT_OWN), False, 2)       # nothing changed, same failure
    assert not written and st2["keys"]
    (d / "rtl" / "top.sv").write_text("module top; wire x; endmodule\n")
    _, written = rm.step(run, d, "r", st2, ev_lint(LINT_OWN), False, 3)       # edited but the same key still fails: not repaired
    assert not written


# --- retrieval by exact evidence ------------------------------------------------------------------------------------------------------------------

def rec(fid="VL-UNUSEDSIGNAL", cls="supplied: Signal is not used", gate="lint", run="r1", diff="+x", fam="f", stamp="2026-11-26 10:00:00"):
    t = {"gate": gate, "finding_id": fid, "signature_class": cls, "first_line": "l"}
    return {"schema": rm.SCHEMA, "id": f"{run}-{fid}-{abs(hash(diff)) % 999}", "provenance": rm.PROVENANCE, "produced_by": "agent", "trigger": t, "role": "rtl",
            "mechanism": "m", "fix": {"files": ["rtl/a.sv"], "diff": diff}, "run_id": run, "design_family": fam, "stamp": stamp, "constraints_preserved": []}


def test_retrieval_is_exact_on_all_three_fields_and_capped():
    keys = [{"gate": "lint", "finding_id": "VL-UNUSEDSIGNAL", "signature_class": "supplied: Signal is not used", "line": ""}]
    pool = [rec(diff=f"+d{i}", run=f"r{i}") for i in range(5)]
    pool += [rec(cls="own: Signal is not used"), rec(fid="VL-WIDTH"), rec(gate="standards"), rec(cls="supplied: Signal is not used", diff="+d1", run="dup")]
    got = rm.retrieve(pool, keys)
    assert len(got) == rm.MAX_INJECT == 3
    assert all(r["trigger"]["finding_id"] == "VL-UNUSEDSIGNAL" and r["trigger"]["signature_class"] == "supplied: Signal is not used" for r in got)
    assert len({r["fix"]["diff"] for r in got}) == 3                     # one record per distinct fix


def test_no_match_on_a_different_signature_even_with_similar_text():
    keys = [{"gate": "lint", "finding_id": "VL-UNUSEDSIGNAL", "signature_class": "own: Signal is not used", "line": "unused signal tdo"}]
    pool = [rec(cls="supplied: Signal is not used"), rec(fid="VL-UNUSEDPARAM", cls="own: Signal is not used"), rec(gate="constants", cls="own: Signal is not used")]
    assert rm.retrieve(pool, keys) == []                                  # text similarity never counts
    assert rm.with_memory({"rtl": ["lint text"]}, []) == {"rtl": ["lint text"]}


def test_same_family_first_then_newest_and_held_out_runs_are_excluded():
    keys = [{"gate": "lint", "finding_id": "VL-UNUSEDSIGNAL", "signature_class": "supplied: Signal is not used", "line": ""}]
    pool = [rec(run="old", diff="+1", fam="other", stamp="2026-11-01"), rec(run="new", diff="+2", fam="other", stamp="2026-11-20"), rec(run="mine", diff="+3", fam="same", stamp="2026-10-01")]
    assert [r["run_id"] for r in rm.retrieve(pool, keys, family="same")] == ["mine", "new", "old"]
    assert [r["run_id"] for r in rm.retrieve(pool, keys, exclude_runs=("mine", "new"))] == ["old"]


def test_records_marked_human_or_without_provenance_are_refused(tmp_path):
    good, human, none = rec(run="g"), {**rec(run="h"), "produced_by": "human"}, {k: v for k, v in rec(run="n").items() if k != "provenance"}
    d = tmp_path / "repairs"
    d.mkdir()
    for r in (good, human, none):
        (d / f"{r['run_id']}.json").write_text(json.dumps(r))
    assert [r["run_id"] for r in rm.load_records(d)] == ["g"]


def test_memory_text_goes_to_the_owning_role_only():
    r = rec()
    out = rm.with_memory({"rtl": ["a"], "tests": ["b"]}, [r])
    assert "[repair memory" in out["rtl"][-1] and "VL-UNUSEDSIGNAL" in out["rtl"][-1] and out["tests"] == ["b"]
    assert len(rm.memory_text([r], "rtl")) < 2200


# --- the check suite over MCP -------------------------------------------------------------------------------------------------------------------

def test_the_mcp_checks_server_lists_only_read_only_tools_and_answers_a_call(session, tmp_path):
    bank = tmp_path / "bank"
    (bank / "family" / "artix7" / "io" / "demo-skill").mkdir(parents=True)
    (bank / "family" / "artix7" / "io" / "demo-skill" / "SKILL.md").write_text('---\nname: demo-skill\ndescription: "when to load it"\naxis: family\nsection: io\n---\nbody text\n')

    async def go():
        async with Client(build_checks_server(session, bank)) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            lc = await c.call_tool("list_checks", {})
            files = await c.call_tool("list_files", {})
            wr = await c.call_tool("write_file", {"path": "rtl/evil.sv", "content": "x"})
            sk = await c.call_tool("skills_markdown", {"name": "demo-skill"})
            idx = await c.call_tool("skills_markdown", {})
            return names, lc, files, wr, sk, idx
    names, lc, files, wr, sk, idx = anyio.run(go)
    assert set(names) == set(READ_ONLY_TOOLS) | {"list_checks", "skills_markdown"}
    assert not {"write_file", "build", "program", "simulate", "board_constraints", "stage_note"} & set(names)
    assert not lc.is_error and "cdc:" in lc.content[0].text and "lint:" in lc.content[0].text
    assert not files.is_error and "spec.yaml" in files.content[0].text
    assert wr.is_error and wr.structured_content["rule"] == "unknown-tool" and not (session.design / "rtl" / "evil.sv").exists()
    assert "body text" in sk.content[0].text and "| demo-skill | family | io |" in idx.content[0].text


def test_the_server_works_on_a_copy_and_leaves_the_folder_alone(wd, tmp_path):
    (wd / ".git").mkdir()
    (wd / ".git" / "x").write_text("x")
    c = copy_design(wd, tmp_path / "copy_parent") if (tmp_path / "copy_parent").mkdir() is None else None
    assert c != wd and (c / "spec.yaml").is_file() and not (c / ".git").exists()


def test_skills_markdown_without_a_bank_tool_is_not_listed(session):
    async def go():
        async with Client(build_checks_server(session, None)) as c:
            return [t.name for t in (await c.list_tools()).tools]
    assert "skills_markdown" not in anyio.run(go)


# --- the arm in the graph -------------------------------------------------------------------------------------------------------------------------

def test_stage2_plan_injects_matching_records_only_with_the_arm_and_records_the_retrieval(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from agent.graph import run as G
    d = design(tmp_path, "module top; endmodule\n")
    (d / "model.py").write_text("class Model: pass\n")
    (d / "tests").mkdir()
    (d / "tests" / "test_top_rtl.py").write_text("")
    runs = tmp_path / "run"
    runs.mkdir()
    bank = tmp_path / "bank"
    (bank / "repairs").mkdir(parents=True)
    (bank / "repairs" / "a.json").write_text(json.dumps(rec(run="past")))
    (bank / "repairs" / "b.json").write_text(json.dumps(rec(cls="own: Signal is not used", run="other")))
    logged: list = []
    monkeypatch.setattr(G, "log_routing_event", lambda rt, event, **kw: logged.append((event, kw)))
    keys = rm.evidence_keys(ev_lint(LINT_SUPPLIED))
    keys = [k for k in keys if k["finding_id"] == "VL-UNUSEDSIGNAL" and k["signature_class"].endswith("Signal is not used")]
    state = {"owners": {"rtl": ["[lint] text"]}, "rm": {"keys": keys, "visit": 1}}
    mk = lambda arms: SimpleNamespace(cfg=SimpleNamespace(arms=arms), design=d, run_dir=runs, run_id="now", visit=2,  # noqa: E731
                                      session=SimpleNamespace(bank=SimpleNamespace(root=bank)))
    off = G.stage2_plan(mk(("H1",)), state)
    assert off["rtl"] == ["[lint] text"] and not logged                                   # off by default: no text, no retrieval record
    on = G.stage2_plan(mk(("H1", "R4")), state)
    assert on["rtl"][0] == "[lint] text" and "[repair memory" in on["rtl"][1] and "run past" in on["rtl"][1] and "run other" not in on["rtl"][1]
    ev = [kw for e, kw in logged if e == "repair_memory_retrieval"][0]
    assert ev["pool"] == 2 and len(ev["offered"]) == 1
    assert json.loads((runs / "repair_memory" / "retrievals.jsonl").read_text().splitlines()[0])["offered_runs"] == ["past"]
    none = G.stage2_plan(mk(("R4",)), {"owners": {"rtl": ["x"]}, "rm": {"keys": [], "visit": 1}})
    assert none["rtl"] == ["x"]                                                           # no keys, nothing injected
