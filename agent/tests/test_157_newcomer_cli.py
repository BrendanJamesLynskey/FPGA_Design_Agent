"""Brief 157: the newcomer's first minute. ``--help``, ``models show``, ``resume <design-dir> --dry-run`` and ``doctor`` work without the
access key; every command that calls a model, writes a design or reads private material still stops at the gate.

The CLI is run in a subprocess with the key removed from the environment and the checkout's ``.env`` hidden (a developer's local
``.env`` would otherwise supply a key). Keys here are made up; the real key is never read or written."""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent import access, newcomer

pytestmark = pytest.mark.access_gate
ROOT = Path(__file__).resolve().parents[2]
DESIGN = "designs/b110_itch_ouch"                    # a committed design with handover.yaml and AGENT.md
GATE_MSG = "access key required"

_DRIVER = ("import sys, agent.access as a\n"
           "a.ENV_FILE = a.ROOT / 'no-such.env'\n"
           "from agent.__main__ import main\n"
           "sys.exit(main(sys.argv[1:]))\n")


def cli(*args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("FDA_ACCESS_KEY", "FDA_PROMPTS_DIR")}
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", _DRIVER, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def tree(d: Path) -> dict:
    return {str(p.relative_to(d)): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(d.rglob("*")) if p.is_file()}


def test_the_gate_is_armed_here():
    assert access.KEYS_FILE.is_file(), "these tests prove refusals, so the committed keys file must exist"


# --- what runs without the key ---------------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [["--help"], ["-h"], ["run", "--help"], ["resume", "--help"], ["document", "--help"], ["review", "--help"],
                                  ["models", "--help"], ["latency", "--help"], ["improve", "--help"], ["doctor", "--help"]])
def test_help_exits_0_without_a_key(argv):
    r = cli(*argv)
    assert r.returncode == 0, r.stderr
    assert GATE_MSG not in r.stderr and r.stdout.strip()


def test_help_says_what_needs_the_key_and_what_a_user_could_guess_wrong():
    top = cli("--help").stdout
    for word in ("what works without the access key", "doctor", "models show", "--dry-run", "FDA_PROMPTS_DIR", "git worktree", "--stop-after",
                 "improve --choose", "run id"):
        assert word in top, word
    run = cli("run", "--help").stdout
    assert "0 clarify" in run and "2 rtl-design-creation" in run and "Vivado" in run
    res = cli("resume", "--help").stdout
    assert "design directory" in res and "no key" in res and "run id" in res and "stage 0" in res
    assert all(n in top for n in newcomer.COMMANDS)             # every command is listed, project and doctor included


def test_models_show_exits_0_without_a_key_and_names_the_models():
    r = cli("models", "show")
    assert r.returncode == 0, r.stderr
    assert "openrouter" in r.stdout and "table hash" in r.stdout
    j = cli("models", "show", "--json")
    assert j.returncode == 0 and json.loads(j.stdout)


def test_design_dry_run_exits_0_without_a_key_and_writes_nothing():
    d = ROOT / DESIGN
    before = tree(d)
    runs = (ROOT / "runs").exists() and sorted(p.name for p in (ROOT / "runs").iterdir())
    r = cli("resume", DESIGN, "widen the price field", "--dry-run")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["resume"] == "dry run" and "entry" in rep and rep["design"].endswith("b110_itch_ouch")
    assert tree(d) == before                                     # nothing written into the design
    assert ((ROOT / "runs").exists() and sorted(p.name for p in (ROOT / "runs").iterdir())) == runs      # no run directory made


def test_doctor_runs_without_a_key_and_exits_1_while_something_is_missing():
    r = cli("doctor", "--no-probe")
    assert r.returncode in (0, 1) and "access_key" in r.stdout and "prompts_path" in r.stdout and GATE_MSG not in r.stderr
    j = json.loads(cli("doctor", "--no-probe", "--json").stdout)
    assert "access_key" in j["missing_required"]                 # the cli() helper removed the key


# --- what still stops at the gate --------------------------------------------------------------------------------

GATED = [
    ["run", "spec.md"], ["run", "spec.md", "--stop-after", "0"], ["run", "spec.md", "--interview", "oracle", "--hidden-spec", "h.md"],
    ["resume", "someid"], ["resume", "someid", "--dry-run"], ["resume", "someid", "change", "--dry-run"], ["resume", "someid", "--rewind", "2"],
    ["resume", "no_such_dir/handover.yaml", "--dry-run"],                       # a name that is not a design directory is a run id
    ["resume", DESIGN, "widen the price field"], ["resume", DESIGN], ["resume", DESIGN, "x", "--stop-after", "2"],
    ["document", "rundir"], ["review", DESIGN], ["review", DESIGN, "--no-judge"],
    ["models", "check"], ["models", "check", "--probe"],
    ["latency", "--arm", "A0", "some_checkout"], ["improve", DESIGN, "use fewer LUTs"], ["improve", DESIGN, "use fewer LUTs", "--analyse-only"],
    ["improve", DESIGN, "x", "--choose", "1"], ["improve", DESIGN, "x", "--choose", "1", "--dry-run"],
]


@pytest.mark.parametrize("argv", GATED, ids=[" ".join(a)[:60] for a in GATED])
def test_every_other_command_still_stops_at_the_gate(argv, tmp_path):
    runs = (ROOT / "runs").exists() and sorted(p.name for p in (ROOT / "runs").iterdir())
    r = cli(*argv)
    assert r.returncode == 2 and GATE_MSG in r.stderr, (r.returncode, r.stderr[-300:])
    assert len(r.stderr.strip().splitlines()) == 1
    assert ((ROOT / "runs").exists() and sorted(p.name for p in (ROOT / "runs").iterdir())) == runs


def test_a_wrong_key_does_not_open_the_exempt_or_the_gated(tmp_path):
    r = cli("run", "spec.md", extra_env={"FDA_ACCESS_KEY": "not-the-key"})
    assert r.returncode == 2 and GATE_MSG in r.stderr and "not-the-key" not in r.stderr + r.stdout


def test_the_only_ungated_command_lines_are_the_documented_two():
    """A grid over every command, action, dry-run flag and run-id kind: exactly models show and design dry-run are exempt."""
    exempt = []
    cmds = ["run", "resume", "document", "review", "models", "latency", "improve", "doctor", "project", "other"]
    for cmd, action, dry, rid in itertools.product(cmds, [None, "show", "check"], [False, True], ["someid", DESIGN]):
        a = SimpleNamespace(cmd=cmd, action=action, dry_run=dry, run_id=rid)
        if newcomer.ungated(a):
            exempt.append((cmd, action, dry, rid))
    assert exempt
    for c, a, d, rid in exempt:
        assert (c == "models" and a == "show") or (c == "resume" and d and rid == DESIGN), (c, a, d, rid)
    assert {e[0] for e in exempt} == {"models", "resume"}


def test_defence_in_depth_if_the_exemption_were_wrong():
    """Force ``ungated`` to say yes to everything: the commands that call models still stop, inside themselves."""
    code = ("import sys, agent.access as a, agent.newcomer as n\n"
            "a.ENV_FILE = a.ROOT / 'no-such.env'\n"
            "n.ungated = lambda ns: 'forced'\n"
            "from agent.__main__ import main\n"
            "sys.exit(main(sys.argv[1:]))\n")
    env = {k: v for k, v in os.environ.items() if k != "FDA_ACCESS_KEY"}
    for argv in (["resume", DESIGN, "widen the price field"], ["models", "check", "--probe"]):
        r = subprocess.run([sys.executable, "-c", code, *argv], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 2 and GATE_MSG in r.stderr, (argv, r.stderr[-300:])


def test_main_still_gates_and_asks_ungated_first():
    tree_ = ast.parse((ROOT / "agent" / "__main__.py").read_text())
    f = next(n for n in tree_.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    src = ast.unparse(f)
    assert "require_or_exit" in src and "newcomer.ungated" in src
    assert src.index("newcomer.ungated(a)") < src.index("require_or_exit('python -m agent')") < src.index("_run_main")
    for fn in ("pickup_cmd", "models_cmd"):                       # the commands the exemptions touch gate themselves past the exempt branch
        g = next(n for n in tree_.body if isinstance(n, ast.FunctionDef) and n.name == fn)
        assert "require_or_exit" in ast.unparse(g), fn


# --- the fallback help, and doctor -------------------------------------------------------------------------------

def test_help_still_exits_0_when_an_extra_is_missing_and_other_use_is_gated():
    code = ("import sys, agent.access as a, agent.__main__ as m\n"
            "a.ENV_FILE = a.ROOT / 'no-such.env'\n"
            "def boom():\n    raise ModuleNotFoundError('no jsonschema', name='jsonschema')\n"
            "m.build_parser = boom\n"
            "sys.exit(m.main(sys.argv[1:]))\n")
    env = {k: v for k, v in os.environ.items() if k != "FDA_ACCESS_KEY"}
    h = subprocess.run([sys.executable, "-c", code, "run", "--help"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert h.returncode == 0 and "commands:" in h.stdout and "pip install" in h.stdout
    g = subprocess.run([sys.executable, "-c", code, "run", "spec.md"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert g.returncode == 2 and GATE_MSG in g.stderr
    m = subprocess.run([sys.executable, "-c", code, "models", "show"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert m.returncode == 2 and "not installed here" in m.stderr and GATE_MSG not in m.stderr


class _Run:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def _fake_runner(cmd, **kw):
    return _Run(0, "fake 1.0\n")


def test_doctor_names_each_missing_prerequisite(monkeypatch, tmp_path):
    monkeypatch.setattr(newcomer, "_have", lambda m: False)                       # a bare runner: no package at all
    cs = newcomer.run_checks(env={}, which=lambda x: None, runner=_fake_runner, key_ok=lambda: None)
    miss = {c.id for c in cs if c.ok is False}
    for want in ("base_packages", "agent_extra", "graph_extra", "access_key", "prompts_path", "prompts_pin", "sim_image", "vivado",
                 "claude_cli", "iverilog", "verilator", "yosys", "ghdl"):
        assert want in miss, want
    text = "\n".join(c.line() for c in cs)
    assert "jsonschema" in text and "langgraph" in text and "FDA_PROMPTS_DIR" in text and "fda-sim:2" in text and "2026.1" in text
    assert all(c.fix for c in cs if c.ok is False)
    out = []
    rc = newcomer.doctor_main(["--no-probe"], out=SimpleNamespace(write=out.append, flush=lambda: None), env={}, which=lambda x: None,
                              key_ok=lambda: None)
    assert rc == 1 and "not ready:" in "".join(out)


def test_doctor_never_prints_the_key_and_reads_the_manifest_only_with_a_valid_key(monkeypatch, tmp_path):
    key = "doctor-test-key-zzzzzzzzzzzzzz"
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    (pdir / "MANIFEST.json").write_text('{"version": 1, "prompts": {}}')
    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps({"kb_commit": "a" * 40, "manifest_sha256": hashlib.sha256((pdir / "MANIFEST.json").read_bytes()).hexdigest()}))
    monkeypatch.setattr(newcomer, "PIN_FILE", pin)
    env = {"FDA_ACCESS_KEY": key, "FDA_PROMPTS_DIR": str(pdir)}
    nokey = {c.id: c for c in newcomer.run_checks(env=env, probe=False, which=lambda x: None, key_ok=lambda: None)}
    assert nokey["prompts_path"].ok is True and nokey["prompts_pin"].ok is None and "only when a valid key" in nokey["prompts_pin"].detail
    withkey = {c.id: c for c in newcomer.run_checks(env=env, probe=False, which=lambda x: None, key_ok=lambda: "alice")}
    assert withkey["prompts_pin"].ok is True and "alice" in withkey["access_key"].detail
    pin.write_text(json.dumps({"kb_commit": "a" * 40, "manifest_sha256": "0" * 64}))
    bad = {c.id: c for c in newcomer.run_checks(env=env, probe=False, which=lambda x: None, key_ok=lambda: "alice")}
    assert bad["prompts_pin"].ok is False
    for cs in (nokey, withkey, bad):
        assert key not in json.dumps([c.as_dict() for c in cs.values()])


def test_doctor_agrees_with_the_agents_own_rules(monkeypatch, tmp_path):
    """The doctor is stdlib-only, so it repeats three rules; these compare them with the code that really decides."""
    from agent.core import prompts, runner
    from flow import version_pin
    for env in ({}, {"FDA_PROMPTS_DIR": str(tmp_path / "p")}, {"FDA_KNOWLEDGE": str(tmp_path / "kb")}):
        for k in ("FDA_PROMPTS_DIR", "FDA_KNOWLEDGE"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        if "FDA_KNOWLEDGE" in env:
            continue                                                  # DEFAULT_BANK is fixed at import: compared below without it
        assert newcomer.prompts_location(dict(os.environ))[0] == prompts.prompts_dir()
    assert newcomer.prompts_location({"FDA_KNOWLEDGE": "/x"})[0] == Path("/x/prompts")
    assert newcomer.SIM_IMAGE == runner.SIM_IMAGE and newcomer.VIVADO_VERSION == version_pin.DEFAULT_VIVADO_VERSION
    for env in ({}, {"VIVADO": "/v/vivado"}, {"FDA_VIVADO_VERSION": "2025.2"}):
        assert newcomer.vivado_path(env) == version_pin.vivado_path(env)
    assert newcomer.PIN_FILE == prompts.PIN_FILE


def test_readme_has_a_start_here_row_for_each_newcomer_command():
    text = (ROOT / "README.md").read_text()
    assert "python -m agent doctor" in text and "models show" in text and "--dry-run" in text
