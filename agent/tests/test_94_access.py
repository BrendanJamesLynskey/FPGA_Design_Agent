"""Brief 94: the access gate. Keys here are made up for the test; the real key is never read or written."""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent import access
from agent.core import security
from tools.access import set_key_hash

pytestmark = pytest.mark.access_gate
ROOT = Path(__file__).resolve().parents[2]
TODAY = dt.date(2026, 11, 16)
KEY = "test-key-aaaaaaaaaaaaaaaaaaaa"


def _entry(name, key, **kw):
    salt = "00112233445566778899aabbccddeeff"
    return {"name": name, "salt": salt, "sha256": access.hash_key(key, salt), "expires": None, "enabled": True, **kw}


def _keys(tmp_path, *entries):
    f = tmp_path / "keys.json"
    f.write_text(json.dumps({"version": 1, "entries": list(entries)}))
    return f


def _req(tmp_path, entries, env, **kw):
    return access.require("t", env=env, env_file=tmp_path / "none.env", keys_file=_keys(tmp_path, *entries), **kw)


def test_right_wrong_empty_and_no_key(tmp_path):
    e = [_entry("owner", KEY)]
    assert _req(tmp_path, e, {"FDA_ACCESS_KEY": KEY}) == "owner"
    for env in ({"FDA_ACCESS_KEY": "wrong"}, {"FDA_ACCESS_KEY": ""}, {}):
        with pytest.raises(access.AccessDenied) as x:
            _req(tmp_path, e, env)
        assert "FDA_ACCESS_KEY" in str(x.value) and ".env.example" in str(x.value) and KEY not in str(x.value)


def test_key_from_dotenv(tmp_path):
    envf = tmp_path / ".env"
    envf.write_text(f"# c\nFDA_ACCESS_KEY='{KEY}'\n")
    assert access.require("t", env={}, env_file=envf, keys_file=_keys(tmp_path, _entry("owner", KEY))) == "owner"


def test_unarmed_when_file_absent(tmp_path, capsys):
    assert access.require("t", env={}, keys_file=tmp_path / "absent.json") is None


def test_named_entries_and_attribution(tmp_path):
    e = [_entry("owner", KEY), _entry("alice", "alice-key-bbbbbbbbbbbbbbbb")]
    assert _req(tmp_path, e, {"FDA_ACCESS_KEY": "alice-key-bbbbbbbbbbbbbbbb"}) == "alice"
    assert access.CURRENT == "alice"


def test_expiry(tmp_path):
    e = [_entry("alice", KEY, expires="2026-11-16")]
    assert _req(tmp_path, e, {"FDA_ACCESS_KEY": KEY}, today=TODAY) == "alice"          # the last day still works
    with pytest.raises(access.AccessDenied):
        _req(tmp_path, e, {"FDA_ACCESS_KEY": KEY}, today=TODAY + dt.timedelta(days=1))


def test_revocation_with_the_tool(tmp_path):
    f = tmp_path / "keys.json"
    envf = tmp_path / "alice.env"
    envf.write_text(f"FDA_ACCESS_KEY={KEY}\n")
    assert set_key_hash.main(["--name", "alice", "--env-file", str(envf), "--expires", "2027-01-31"], keys_file=f) == 0
    ents = json.loads(f.read_text())["entries"]
    assert ents[0]["name"] == "alice" and ents[0]["expires"] == "2027-01-31" and KEY not in f.read_text()
    assert access.match(KEY, ents, TODAY) == "alice"
    assert set_key_hash.main(["--revoke", "alice"], keys_file=f) == 0
    ents = json.loads(f.read_text())["entries"]
    assert ents[0]["enabled"] is False and access.match(KEY, ents, TODAY) is None
    assert set_key_hash.main(["--revoke", "nobody"], keys_file=f) == 1
    # replacing keeps one entry per name and draws a new salt
    old = ents[0]["salt"]
    set_key_hash.main(["--name", "alice", "--env-file", str(envf)], keys_file=f)
    ents = json.loads(f.read_text())["entries"]
    assert len(ents) == 1 and ents[0]["salt"] != old and ents[0]["enabled"]


def test_the_key_is_redacted(monkeypatch):
    monkeypatch.setenv("FDA_ACCESS_KEY", KEY)
    assert KEY not in security.redact(f"error with {KEY} inside")


def test_audit_records_the_name_not_the_key(tmp_path, monkeypatch):
    from agent.core.session import Session
    monkeypatch.setattr(access, "CURRENT", "alice")
    monkeypatch.setattr(access, "_TEST_BYPASS", True)   # this test is about the audit log, not admission: once
    monkeypatch.setenv("FDA_ACCESS_KEY", KEY)           # keys.json is committed, the test key is (rightly) refused
    d = tmp_path / "d"
    d.mkdir()
    s = Session(design=d)
    s.audit.log({"note": f"leak attempt {KEY}"})
    log = (d / "build" / "audit.jsonl").read_text()
    assert '"entry": "alice"' in log and KEY not in log


def test_arm_config_never_holds_the_key(monkeypatch, tmp_path):
    from agent.claude_code_arm import arm
    monkeypatch.setenv("FDA_ACCESS_KEY", KEY)
    rt = type("R", (), {"design": tmp_path, "cfg": type("C", (), {"board": "b", "skill_routing": "off"})()})()
    cfg = arm.mcp_config(rt, {"role": "rtl", "stage": "s", "file_tools": [], "core_tools": []})
    assert KEY not in json.dumps(cfg) and cfg["mcpServers"]["fda"]["env"]["FDA_ACCESS_KEY"] == "${FDA_ACCESS_KEY}"


# --- every entry point calls the gate -------------------------------------------------------------------

#: Scripts that import the agent package but do not run the agent (no model, no tools); each with its reason.
NOT_RUNNING_THE_AGENT = {
    "tools/access/set_key_hash.py": "manages the key file; reads the key to hash it",
    "agent/tools/harness_audit.py": "builds the harness over a stub client; no model, no tools",
    "results/36_skill_routing/measure.py": "an old measurement script under results/ (frozen record)",
    "debug_core/demo_t1.py": "a demo that replays recorded calls",
    "designs/b58a_trigger/host/nl_rule.py": "a host-side tool using only the model client",
    "flow/requirements_report.py": "reads a design's run records and writes its requirements report (brief 210); no model, no tools",
    "tools/requirements_rescore.py": "re-scores recorded interview questions with the risk rules (brief 210); read only; no model, no tools",
    "flow/doccheck.py": "documentation checker", "flow/mutate.py": "mutation tool", "flow/standards_check.py": "lint-like checker",
    "flow/tests/test_55_vhdl_rtl.py": "a test module", "flow/tests/fixtures/timing_exceptions/make_table.py": "fixture generator",
    "tools/vhdl_translate.py": "translator",
    "tools/vhdl_parity_probe.py": "measures which readers of the RTL read VHDL (brief 153); imports the spec-test module for its RTL list only; no model, no tools", "benchmark/drills/lib/grade_io.py": "grader", "benchmark/drills/lib/grade_constraints.py": "grader",
    "tools/board_smoke.py": "writes a smoke design from a board file through the constraints writer; no model, no tools (brief 95)",
    "flow/managed_import.py": "import checks of a managed project's netlists (brief 102); no model, no tools",
    "flow/managed_rtl_import.py": "import checks of a managed project's third-party RTL blocks (brief 102 stage 3); no model, no tools",
    "flow/managed_placed.py": "import check and placement evidence of a managed project's placed-and-routed block (brief 102, stage 2); no model, no tools",
    "flow/prepare.py": "writes a build directory's Tcl; reads the managed-project manifest only to check build coverage (brief 102)",
    "site/export.py": "site build", "site/build.py": "site build", "agent/tests/test_mcp.py": "a test module",
}
GATED_NAMES = ("require_or_exit", "require", "_gate")


def _is_script(tree: ast.Module) -> bool:
    for n in tree.body:
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and "__main__" in ast.dump(n.test):
            return True
    return False


def _imports_agent(tree: ast.Module) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "agent":
            return True
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "agent" for a in n.names):
            return True
    return False


def _calls_gate(tree: ast.Module) -> bool:
    return any(isinstance(n, ast.Call) and (getattr(n.func, "id", None) in GATED_NAMES or getattr(n.func, "attr", None) in GATED_NAMES)
               for n in ast.walk(tree))


def test_every_entry_point_calls_the_gate():
    skip = {"results", "site", ".venv", "build", "runs", "node_modules"}
    missing = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if set(rel.split("/")) & skip and rel not in NOT_RUNNING_THE_AGENT:
            continue
        if "/tests/" in rel and rel not in NOT_RUNNING_THE_AGENT or rel.startswith("designs/") and rel not in NOT_RUNNING_THE_AGENT:
            continue
        try:
            tree = ast.parse(p.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        if _is_script(tree) and (_imports_agent(tree) or rel.startswith("agent/")) and rel not in NOT_RUNNING_THE_AGENT:
            if not _calls_gate(tree):
                missing.append(rel)
    assert not missing, f"entry points that run the agent must call agent.access.require_or_exit: {missing}"


def test_run_creation_and_the_arm_are_gated():
    for rel, fn in (("agent/graph/run.py", "new_runtime"), ("agent/claude_code_arm/arm.py", "run_subagent_cc")):
        tree = ast.parse((ROOT / rel).read_text())
        f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
        assert _calls_gate(ast.Module(body=f.body, type_ignores=[])), f"{rel}:{fn}"


def test_armed_cli_refuses_without_key_and_unarmed_runs(tmp_path):
    """A subprocess of the real CLI: with a keys file present and no key it exits 2 with one line; the repo as committed
    (no keys file yet, or the owner's key in the environment) runs."""
    keys = ROOT / "agent" / "access" / "keys.json"
    if keys.is_file():
        env = {k: v for k, v in os.environ.items() if k != "FDA_ACCESS_KEY"}
        r = subprocess.run([sys.executable, "-m", "agent", "run", str(tmp_path / "nospec.md")], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        if (ROOT / ".env").is_file():
            pytest.skip("a local .env supplies a key")
        assert r.returncode == 2 and "FDA_ACCESS_KEY" in r.stderr and len(r.stderr.strip().splitlines()) == 1
    else:
        r = subprocess.run([sys.executable, "-m", "agent", "run", str(tmp_path / "nospec.md")], cwd=ROOT,
                           capture_output=True, text=True)
        assert "gate not armed" in r.stderr


def test_the_ci_secret_matches_the_committed_hash():
    """Runs only where the secret is present (not on forks) and the gate is armed: catches a secret that does not
    match the committed entries."""
    if not access.KEYS_FILE.is_file():
        pytest.skip("gate not armed")
    if not os.environ.get("FDA_ACCESS_KEY"):
        pytest.skip("FDA_ACCESS_KEY is not set here (fork pull request or a local run without the key)")
    assert access.require("ci") is not None


def test_dotenv_comments_and_malformed_expiry(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"FDA_ACCESS_KEY={KEY} # my key\n")
    assert access.read_dotenv(f) == KEY
    e = _entry("alice", KEY, expires="not-a-date")
    assert access.match(KEY, [e], TODAY) is None          # closed, no traceback


def test_session_oracle_and_project_spec_are_gated():
    for rel, fn in (("agent/core/session.py", "__post_init__"), ("agent/claude_code_arm/oracle.py", "cc_oracle"),
                    ("project/cli.py", "_spec")):
        tree = ast.parse((ROOT / rel).read_text())
        f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
        assert _calls_gate(ast.Module(body=f.body, type_ignores=[])), f"{rel}:{fn}"


# --- brief 157: what runs without a key, and nothing more -------------------------------------------------------

def test_only_help_doctor_models_show_and_design_dry_run_run_without_a_key():
    """The exemptions are one function (``agent.newcomer.ungated``); a command line outside the documented two is refused. The
    command lines themselves, run for real, are in ``test_157_newcomer_cli.py``."""
    from types import SimpleNamespace
    from agent import newcomer
    yes = {("models", "show", False, "x"), ("models", "show", True, "x"), ("resume", None, True, "designs/b110_itch_ouch"),
           ("resume", "show", True, "designs/b110_itch_ouch"), ("resume", "check", True, "designs/b110_itch_ouch")}
    for cmd in ("run", "resume", "document", "review", "models", "latency", "improve", "project", "doctor"):
        for action in (None, "show", "check"):
            for dry in (False, True):
                for rid in ("x", "designs/b110_itch_ouch"):
                    got = newcomer.ungated(SimpleNamespace(cmd=cmd, action=action, dry_run=dry, run_id=rid)) is not None
                    want = (cmd, action, dry, rid) in yes or (cmd == "models" and action == "show") or \
                           (cmd == "resume" and dry and rid == "designs/b110_itch_ouch")
                    assert got == want, (cmd, action, dry, rid)


def test_a_model_calling_function_is_still_gated_inside_when_main_lets_a_command_through():
    for rel, fn in (("agent/__main__.py", "pickup_cmd"), ("agent/__main__.py", "models_cmd")):
        tree = ast.parse((ROOT / rel).read_text())
        f = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
        assert _calls_gate(ast.Module(body=f.body, type_ignores=[])), f"{rel}:{fn}"
