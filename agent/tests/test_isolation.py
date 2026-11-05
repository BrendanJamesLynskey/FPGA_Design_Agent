"""Agent-written test code runs in a container with no network and only the design directory writable
(owner decision 2026-11-01). These tests check the command the ContainerRunner builds; the live run is in
the 05b report (it needs Docker and the fda-sim image, which CI does not have)."""

import sys
from pathlib import Path

from agent.core.runner import SIM_IMAGE, ContainerRunner, RunResult
from agent.core.session import ROOT


class _Spy:
    def __init__(self):
        self.calls = []

    def run(self, kind, argv, cwd, env=None, timeout=600):
        self.calls.append((kind, argv, env))
        return RunResult(0, "", "", 0.0)


def _argv():
    spy = _Spy()
    d = ROOT / "designs" / "t1_dimmer_counter"
    cr = ContainerRunner(d, ROOT, inner=spy)
    cr.run("simulate", [sys.executable, "-m", "pytest", "-q"], ROOT, {"SIM": "icarus"})
    cr.run("lint", ["verilator", "--lint-only"], ROOT)
    return spy.calls, d


def test_simulate_runs_in_container_without_network_or_privilege():
    calls, d = _argv()
    kind, argv, env = calls[0]
    assert argv[:3] == ["docker", "run", "--rm"] and env is None
    joined = " ".join(argv)
    for flag in ("--network none", "--cap-drop ALL", "--security-opt no-new-privileges", "--read-only"):
        assert flag in joined
    assert "--user" in argv and not argv[argv.index("--user") + 1].startswith("0:")
    assert "SIM=icarus" in argv and argv[-5:] == [SIM_IMAGE, "python3", "-m", "pytest", "-q"]


def test_only_the_design_is_writable_and_nothing_else_is_mounted():
    calls, d = _argv()
    argv = calls[0][1]
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    rw = [m for m in mounts if m.endswith(":rw")]
    assert rw == [f"{d}:{d}:rw"]
    allowed_ro = {"flow", "shell", "designs/__init__.py"}
    for m in mounts:
        if m.endswith(":ro"):
            assert any(m.startswith(f"{ROOT}/{a}:") for a in allowed_ro), m
    assert not any(str(Path.home()) + ":" in m or ".config" in m or ".ssh" in m for m in mounts)
    assert not any(a.startswith("OPENROUTER") or "KEY" in a for a in argv)


def test_other_kinds_are_not_containerised():
    calls, _ = _argv()
    assert calls[1][1] == ["verilator", "--lint-only"]
