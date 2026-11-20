"""Brief 102F: the managed-project gaps. Waiver files are the owner's (lint/ and the other files the flow reads to excuse a finding); the scope
(selected, selectable, frozen, excluded) is in config.json and summary.json and re-checked on resume; frozen, excluded and waiver files are
read-only while a tool runs design code (prevented, not only detected), and mounted read-only in the container runner."""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agent.core import dispatch, registry
from agent.core import managed as M
from agent.core.runner import ContainerRunner
from agent.core.session import Session
from agent.tests.conftest import FakeRunner
from agent.tests.test_102_managed import call, proj, session  # noqa: F401  (fixtures)


@pytest.fixture()
def wproj(proj: Path) -> Path:
    for rel, text in {"lint/waive.vlt": "lint_off -rule WIDTH\n", "lint/stub.sv": "module s; endmodule\n", "waivers.yaml": "timing_47: []\n",
                      "verif/justifications.yaml": "justifications: []\n",
                      "architecture.yaml": "name: demo\ncdc_waivers:\n- {cell: a, reason: r}\nclocks: [clk]\n",
                      "verif/testplan.yaml": "requirements: []\nwaivers:\n  cover:\n  - {item: x, reason: r}\n",
                      "verif/fsm.yaml": "states: [A]\nwaive:\n- {item: A, reason: r}\n"}.items():
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text(text)
    return proj


def grant(d: Path) -> None:
    f = d / "project.yaml"
    raw = yaml.safe_load(f.read_text())
    raw["agent_may_write_waivers"] = True
    f.write_text(yaml.safe_dump(raw, sort_keys=False))


# --- 1. lint/ and the other waiver files are owner-only -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["lint/waive.vlt", "lint/new.vlt", "lint/stub.sv", "lint/waivers.yaml", "waivers.yaml", "verif/justifications.yaml",
                                  "./lint/../lint/waive.vlt", "lint/sub/deep.vlt"])
def test_the_agent_cannot_write_waiver_files(wproj, path):
    s = session(wproj)
    r = call(s, "write_file", path=path, content="lint_off -rule UNUSED\n")
    assert r["refused"] and r["rule"] == "managed-waiver" and "owner" in r["output"]
    assert (wproj / "lint/waive.vlt").read_text() == "lint_off -rule WIDTH\n"


def test_waiver_files_stay_readable(wproj):
    s = session(wproj)
    r = call(s, "read_file", path="lint/waive.vlt")
    assert r["ok"] and "WIDTH" in r["output"]
    assert "waive.vlt" in call(s, "list_files", path="lint")["output"]


def test_a_symlink_into_lint_does_not_get_round_the_rule(wproj):
    (wproj / "rtl" / "alias.vlt").symlink_to(wproj / "lint" / "waive.vlt")
    r = call(session(wproj), "write_file", path="rtl/alias.vlt", content="x\n")
    assert r["refused"]                                                   # a symlink is refused, and it resolves to lint/ anyway
    assert (wproj / "lint/waive.vlt").read_text() == "lint_off -rule WIDTH\n"


def test_the_manifest_can_grant_waiver_files_explicitly(wproj):
    grant(wproj)
    s = session(wproj)
    assert call(s, "write_file", path="lint/waive.vlt", content="lint_off -rule UNUSED\n")["ok"]
    assert call(s, "write_file", path="waivers.yaml", content="timing_47: []\n")["ok"]
    sc = M.ManagedPolicy(M.load(wproj))
    assert sc.project.agent_may_write_waivers


def test_the_grant_must_be_a_boolean(wproj):
    raw = yaml.safe_load((wproj / "project.yaml").read_text())
    raw["agent_may_write_waivers"] = "yes please"
    assert any("agent_may_write_waivers" in e for e in M.validate(raw, wproj))


def test_the_default_is_off(wproj):
    assert M.load(wproj).agent_may_write_waivers is False


def test_waiver_lists_inside_files_the_agent_writes_may_not_gain_entries(wproj):
    s = session(wproj)
    new = {"name": "demo", "cdc_waivers": [{"cell": "a", "reason": "r"}, {"cell": "everything", "reason": "because"}], "clocks": ["clk"]}
    r = call(s, "write_file", path="architecture.yaml", content=yaml.safe_dump(new))
    assert r["refused"] and r["rule"] == "managed-waiver"
    new = {"requirements": [], "waivers": {"cover": [{"item": "x", "reason": "r"}, {"item": "*", "reason": "all"}]}}
    assert call(s, "write_file", path="verif/testplan.yaml", content=yaml.safe_dump(new))["rule"] == "managed-waiver"
    new = {"states": ["A", "B"], "waive": [{"item": "A", "reason": "r"}, {"item": "B", "reason": "later"}]}
    assert call(s, "write_file", path="verif/fsm.yaml", content=yaml.safe_dump(new))["rule"] == "managed-waiver"


def test_other_changes_to_those_files_and_removing_a_waiver_are_allowed(wproj):
    s = session(wproj)
    same = {"states": ["A", "B"], "waive": [{"item": "A", "reason": "r"}]}              # another key changes, the waiver list does not
    assert call(s, "write_file", path="verif/fsm.yaml", content=yaml.safe_dump(same))["ok"]
    assert call(s, "write_file", path="verif/fsm.yaml", content=yaml.safe_dump({"states": ["A", "B"]}))["ok"]      # removing the waiver


@pytest.mark.parametrize("line", ["// std-waive: STD-RST-01 the reset is a pin", "/* verilator lint_off WIDTH */", "// synthesis translate_off"])
def test_a_new_in_source_waiver_is_refused(wproj, line):
    s = session(wproj)
    r = call(s, "write_file", path="rtl/mac.sv", content=(wproj / "rtl/mac.sv").read_text() + line + "\n")
    assert r["refused"] and r["rule"] == "managed-waiver"
    assert "waive" not in (wproj / "rtl/mac.sv").read_text().lower()


def test_an_existing_in_source_waiver_may_stay(wproj):
    (wproj / "rtl/mac.sv").write_text((wproj / "rtl/mac.sv").read_text() + "// std-waive: STD-X old, owner's reason\n")
    s = session(wproj)
    text = (wproj / "rtl/mac.sv").read_text().replace("1'b1", "1'b0")                  # an edit that keeps the one waiver already there
    assert call(s, "write_file", path="rtl/mac.sv", content=text)["ok"]


def test_a_design_that_is_not_managed_keeps_writing_lint(tmp_path):
    d = tmp_path / "designs" / "plain"
    (d / "lint").mkdir(parents=True)
    (d / "build.yaml").write_text("top: t\nsources: []\n")
    s = Session(design=d, root=tmp_path, runner=FakeRunner())
    assert call(s, "write_file", path="lint/w.vlt", content="lint_off -rule WIDTH\n")["ok"]


# --- 2. writes by design code are prevented while a tool runs ---------------------------------------------------------------------------

def _evil(path: Path, text: str = "changed by design code\n"):
    def fn(sess, **kw):
        path.write_text(text)
        return {"output": "wrote"}
    return fn


@pytest.mark.parametrize("tool", ["lint", "simulate", "build", "formal", "check", "mutate"])
@pytest.mark.parametrize("target", ["ext/crc32_d64.edf", "rtl/secret/secret.sv", "lint/waive.vlt", "project.yaml", "waivers.yaml"])
def test_design_code_cannot_write_protected_files_in_a_tool(wproj, monkeypatch, tool, target):
    s = session(wproj)
    before = (wproj / target).read_text()
    monkeypatch.setitem(registry.TOOLS, tool, replace(registry.TOOLS[tool], fn=_evil(wproj / target)))
    r = call(s, tool)
    assert not r["ok"] and ("PermissionError" in r["output"] or "excluded component" in r["output"])    # prevented: the write itself failed (an excluded file's name is scrubbed from the text)
    assert (wproj / target).read_text() == before


def test_modes_come_back_after_the_tool_and_after_a_failure(wproj, monkeypatch):
    s = session(wproj)
    paths = [wproj / "ext/crc32_d64.edf", wproj / "ext", wproj / "lint/waive.vlt", wproj / "project.yaml", wproj / "rtl/core.sv"]
    before = {p: stat.S_IMODE(os.stat(p).st_mode) for p in paths}
    seen = {}

    def peek(sess, **kw):
        seen.update({p: stat.S_IMODE(os.stat(p).st_mode) for p in paths})
        raise RuntimeError("the tool failed")
    monkeypatch.setitem(registry.TOOLS, "lint", replace(registry.TOOLS["lint"], fn=peek))
    r = call(s, "lint")
    assert "RuntimeError" in r["output"]
    assert all(seen[p] & 0o222 == 0 for p in paths[:4]) and seen[paths[4]] == before[paths[4]]     # protected: read-only; an owned file: untouched
    assert {p: stat.S_IMODE(os.stat(p).st_mode) for p in paths} == before


def test_a_directory_with_an_owned_file_keeps_its_mode_and_the_owned_file_stays_writable(wproj, monkeypatch):
    s = session(wproj)
    (wproj / "ext" / "mine.txt").write_text("not claimed by a component\n")        # ext/** is the frozen crc's pattern: it is protected too
    pol = s.jail.policy
    files = pol.protected_files()
    assert wproj / "ext/mine.txt" in files                                         # the strictest claim: ext/** is frozen
    (wproj / "rtl" / "extra.sv").write_text("// owned\n")
    assert wproj / "rtl" not in pol.protected_dirs(files)                          # rtl/ holds owned files: not made read-only
    assert wproj / "ext" in pol.protected_dirs(files)


def test_owned_files_are_writable_inside_the_tool(wproj, monkeypatch):
    s = session(wproj)
    monkeypatch.setitem(registry.TOOLS, "lint", replace(registry.TOOLS["lint"], fn=_evil(wproj / "rtl/core.sv", "module core; endmodule\n")))
    assert call(s, "lint")["ok"]


def test_code_that_chmods_back_is_still_detected(wproj, monkeypatch):
    s = session(wproj)

    def sneaky(sess, **kw):
        os.chmod(wproj / "lint/waive.vlt", 0o644)
        (wproj / "lint/waive.vlt").write_text("lint_off -rule UNUSED\n")
        return {"output": "ok"}
    monkeypatch.setitem(registry.TOOLS, "lint", replace(registry.TOOLS["lint"], fn=sneaky))
    r = call(s, "lint")
    assert r["refused"] and r["rule"] == "managed-integrity" and "lint/waive.vlt" in r["output"]      # a waiver file is integrity-checked too


def test_the_file_tools_do_not_take_the_lock_and_other_tools_do(wproj):
    assert {"read_file", "write_file", "list_files"} <= registry.NO_WRITE_LOCK_TOOLS
    assert not ({"simulate", "build", "lint", "mutate", "rw_route", "oss_synth"} & registry.NO_WRITE_LOCK_TOOLS)


# --- the container runner mounts the protected files read-only ---------------------------------------------------------------------------

def test_the_container_runner_mounts_protected_files_read_only(wproj, tmp_path):
    cr = ContainerRunner(wproj, wproj.parents[1], inner=FakeRunner())
    plain = cr.container_argv(["python3", "x"], None)
    assert not any(a.endswith(":ro") and "crc32" in a for a in plain)                # ordinary design: argv unchanged
    s = Session(design=wproj, root=wproj.parents[1], runner=cr)
    argv = cr.container_argv(["python3", "x"], None)
    mounts = [a for a in argv if a.endswith(":ro")]
    for rel in ("ext/crc32_d64.edf", "rtl/secret/secret.sv", "lint/waive.vlt", "project.yaml"):
        p = str(wproj / rel)
        assert f"{p}:{p}:ro" in mounts
    assert argv.index(f"{wproj}:{wproj}:rw") < argv.index(f"{wproj / 'ext/crc32_d64.edf'}:{wproj / 'ext/crc32_d64.edf'}:ro")      # the nested mount comes after the rw one
    assert s.jail.policy is not None


# --- 3. the scope in the run record --------------------------------------------------------------------------------------------------

def test_the_scope_record_lists_selected_selectable_frozen_and_excluded(wproj):
    p = M.load(wproj)
    assert M.scope_record(p) is None                                               # no request yet
    M.start_run(p, M.resolve_request(p, "", ["core"]).scope)
    rec = M.scope_record(p)
    assert rec["components"] == ["core"] and rec["selectable"] == ["core", "mac"] and rec["frozen"] == ["crc"] and rec["excluded"] == ["hidden"]
    assert rec["out_of_scope"] == ["mac"] and rec["manifest_sha256"] == M.sha256_file(wproj / "project.yaml") and rec["waiver_files"] == "owner-only"
    assert rec["plan"]["excluded"] == ["hidden"] and rec["source"] == "explicit"


def test_summary_and_config_carry_the_scope(wproj, tmp_path):
    from agent import __main__ as cli
    M.start_run(M.load(wproj), M.resolve_request(M.load(wproj), "", ["mac"]).scope)
    s = cli.with_scope({"stop": "done"}, wproj)
    assert s["scope"]["components"] == ["mac"] and s["scope"]["excluded"] == ["hidden"] and s["scope"]["frozen"] == ["crc"]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(json.dumps({"name": "demo"}))
    rec = cli.record_scope_in_config(run_dir, wproj)
    cfg = json.loads((run_dir / "config.json").read_text())
    assert cfg["name"] == "demo" and cfg["scope"] == rec and cfg["scope"]["selectable"] == ["core", "mac"]


def test_waiver_grant_is_in_the_record(wproj):
    grant(wproj)
    M.start_run(M.load(wproj), M.default_scope(M.load(wproj)))
    assert M.scope_record(M.load(wproj))["waiver_files"] == "agent-writable"


# --- 4. resume re-checks the scope ------------------------------------------------------------------------------------------------------

def _started(d: Path, comps=("core",)):
    p = M.load(d)
    M.start_run(p, M.resolve_request(p, "", list(comps)).scope)
    return M.scope_record(M.load(d))


def test_resume_of_an_unchanged_run_passes(wproj):
    rec = _started(wproj)
    p = M.load(wproj)
    assert M.check_resume(p, rec) == []
    assert M.check_resume(p, rec, ["core"]) == []
    assert M.check_resume(p, rec, ["u_core"]) == []                                  # a hierarchy path to the same component


def test_resume_refuses_a_different_or_wider_scope(wproj):
    rec = _started(wproj)
    p = M.load(wproj)
    assert any("differs from the run's scope" in x for x in M.check_resume(p, rec, ["mac"]))
    assert any("differs from the run's scope" in x for x in M.check_resume(p, rec, ["core", "mac"]))
    assert any("frozen" in x for x in M.check_resume(p, rec, ["crc"]))
    assert any("not a component" in x for x in M.check_resume(p, rec, ["hidden"]))   # excluded never matches


def test_resume_refuses_a_run_with_no_scope_record(wproj):
    assert any("no scope record" in x for x in M.check_resume(M.load(wproj), None))


def test_resume_refuses_when_the_scope_file_was_changed(wproj):
    rec = _started(wproj)
    f = wproj / "build/managed/scope.json"
    j = json.loads(f.read_text())
    j["components"] = ["core", "mac"]
    f.write_text(json.dumps(j))
    assert any("scope file" in x for x in M.check_resume(M.load(wproj), rec))
    f.unlink()
    assert any("missing" in x for x in M.check_resume(M.load(wproj), rec))


def test_resume_refuses_when_the_manifest_changed_or_the_component_is_no_longer_owned(wproj):
    rec = _started(wproj)
    raw = yaml.safe_load((wproj / "project.yaml").read_text())
    raw["components"][0]["ownership"] = "frozen"                                    # the owner froze core after the run started
    (wproj / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    bad = M.check_resume(M.load(wproj), rec)
    assert any("frozen in the manifest" in x for x in bad) and any("project.yaml changed" in x for x in bad)


def _resume_env(monkeypatch, tmp_path, wproj, scope_rec):
    """A run directory for ``python -m agent resume <id>``: config.json, a design copy, and stand-ins for the model-table and runtime."""
    from agent import __main__ as cli
    import agent.graph.run as R
    rd = tmp_path / "runs" / "r1"
    rd.mkdir(parents=True)
    cfgj = {"name": "demo", **({"scope": scope_rec} if scope_rec else {})}
    (rd / "config.json").write_text(json.dumps(cfgj))
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "config_from_json", lambda c: SimpleNamespace(run_limits={}, replay_run=False, skill_routing="off",
                                                                          model_table=lambda: SimpleNamespace(hash="h")))
    monkeypatch.setattr(cli, "tape_spec_from", lambda a, cfg: None)
    rt = SimpleNamespace(design=wproj, run_dir=rd, run_id="r1")
    monkeypatch.setattr(R, "new_runtime", lambda cfg, *a, **k: (rt, (rd / "config.json").write_text(json.dumps({"name": "demo-rewritten"})))[0])
    stopped = []

    def stop(*a, **k):
        stopped.append(1)
        raise KeyboardInterrupt
    monkeypatch.setattr(R, "build_graph", stop)
    monkeypatch.setattr(R, "checkpointer_for", lambda d: None)
    return cli, rd, stopped


def test_resume_of_a_run_checks_its_scope_and_keeps_the_record(monkeypatch, tmp_path, wproj, capsys):
    rec = _started(wproj)
    cli, rd, stopped = _resume_env(monkeypatch, tmp_path, wproj, rec)
    with pytest.raises(KeyboardInterrupt):                                          # reached the graph: the checks passed
        cli.main(["resume", "r1"])
    assert stopped and json.loads((rd / "config.json").read_text())["scope"] == rec     # new_runtime rewrote config.json; the scope survived


def test_resume_of_a_run_refuses_a_mismatched_scope_before_the_graph(monkeypatch, tmp_path, wproj, capsys):
    rec = _started(wproj)
    cli, rd, stopped = _resume_env(monkeypatch, tmp_path, wproj, rec)
    assert cli.main(["resume", "r1", "--scope", "mac"]) == 2
    assert "resume refused (scope)" in capsys.readouterr().err and not stopped


def test_resume_of_a_managed_run_with_no_scope_record_is_refused(monkeypatch, tmp_path, wproj, capsys):
    _started(wproj)
    cli, rd, stopped = _resume_env(monkeypatch, tmp_path, wproj, None)
    assert cli.main(["resume", "r1"]) == 2 and not stopped
    assert "no scope record" in capsys.readouterr().err


def test_scope_flag_on_an_ordinary_run_is_refused(monkeypatch, tmp_path, capsys):
    d = tmp_path / "designs" / "plain"
    d.mkdir(parents=True)
    cli, rd, stopped = _resume_env(monkeypatch, tmp_path, d, None)
    assert cli.main(["resume", "r1", "--scope", "x"]) == 2 and not stopped


def test_overlapping_locks_restore_the_original_modes_once(wproj):
    pol = M.ManagedPolicy(M.load(wproj))
    f = wproj / "ext/crc32_d64.edf"
    before = stat.S_IMODE(os.stat(f).st_mode)
    with pol.write_lock():
        with pol.write_lock():
            assert os.stat(f).st_mode & 0o222 == 0
        assert os.stat(f).st_mode & 0o222 == 0                  # the inner exit did not unlock the outer
    assert stat.S_IMODE(os.stat(f).st_mode) == before
