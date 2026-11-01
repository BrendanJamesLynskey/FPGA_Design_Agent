"""Run the fixed commands the tools build. Three runners share one interface:

- :class:`LocalRunner` runs the command in a subprocess with a scrubbed environment (no key or token is
  passed down; agent-written tests run as host code, so this matters) and a timeout.
- :class:`RecordingRunner` wraps another runner and records every run (argv, result, files the run wrote that
  later tools read) into an episode fixture.
- :class:`RecordedRunner` replays those records with no tools installed: CI runs a whole agent episode this way.
  It checks that the argv the core builds is the argv recorded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SIM", "VIVADO", "HW_SERVER", "MEM_MAX", "MIN_AVAIL_GB",
            "HW_MIN_AVAIL_GB", "FDA_BOARDS_FILE", "VERILATOR_ROOT", "PYTHONPATH", "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS", "PORT_VERILATORS", "USER", "LOGNAME", "LD_LIBRARY_PATH", "YOSYS_DATDIR")


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    seconds: float
    files: dict[str, str] = field(default_factory=dict)      # small files the run produced (recorded runs)


class Runner(Protocol):
    def run(self, kind: str, argv: list[str], cwd: Path, env: dict[str, str] | None = None,
            timeout: float = 600) -> RunResult: ...


TOOLS_FILE = Path(os.environ.get("FDA_TOOLS_FILE", Path.home() / ".config" / "fpga_design_agent" / "tools.yaml"))

# How to get each external tool the core runs by bare name (shown in the error when it is missing).
INSTALL_HINTS = {
    "verilator": "Verilator 5.x: no root needed; extract a release into ~/.local/opt and add to "
                 "~/.config/fpga_design_agent/tools.yaml:  path: [<VERILATOR_ROOT>/bin]  env: {VERILATOR_ROOT: ...}",
    "iverilog": "Icarus Verilog: install it, or add its bin directory to tools.yaml 'path'",
    "yosys": "Yosys/SymbiYosys (OSS CAD Suite): unpack into ~/.local/opt and add its bin directory to tools.yaml 'path'",
}


class ToolMissing(FileNotFoundError):
    """An external tool the core needs is not on the configured PATH."""

    def __init__(self, name: str, path: str):
        self.name = name
        super().__init__(f"tool {name!r} not found (searched PATH plus {TOOLS_FILE} 'path'). "
                         f"Install: {INSTALL_HINTS.get(name, 'install it and add its bin directory to tools.yaml')}")


def load_tools_config(f: Path | None = None) -> dict[str, Any]:
    """The local tools file (outside the repo): ``path`` (dirs put first on PATH) and ``env`` (variables set
    for every run, e.g. ``VERILATOR_ROOT``). ``~`` and ``$HOME`` are expanded. Missing file: empty config."""
    import yaml
    f = f or TOOLS_FILE
    if not f.is_file():
        return {"path": [], "env": {}}
    data = yaml.safe_load(f.read_text()) or {}
    ex = lambda v: os.path.expandvars(os.path.expanduser(str(v)))  # noqa: E731
    return {"path": [ex(d) for d in data.get("path", []) or []],
            "env": {str(k): ex(v) for k, v in (data.get("env") or {}).items()}}


def scrubbed_env(extra: dict[str, str] | None = None, tools: dict[str, Any] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP}
    tools = load_tools_config() if tools is None else tools
    env.update(tools.get("env", {}))
    if tools.get("path"):
        env["PATH"] = os.pathsep.join([*tools["path"], env.get("PATH", os.defpath)])
    env.update(extra or {})
    return env


def resolve_tool(argv0: str, env: dict[str, str]) -> str:
    """A bare tool name resolved on the run's PATH; a path is returned unchanged. Raises ToolMissing."""
    if os.sep in argv0:
        return argv0
    found = shutil.which(argv0, path=env.get("PATH", os.defpath))
    if not found:
        raise ToolMissing(argv0, env.get("PATH", ""))
    return found


class LocalRunner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        t0 = time.monotonic()
        full_env = scrubbed_env(env)
        argv = [resolve_tool(argv[0], full_env), *argv[1:]]
        try:
            p = subprocess.run(argv, cwd=cwd, env=full_env, capture_output=True, text=True,
                               timeout=timeout, errors="replace")
            rc, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = 124, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), \
                f"timed out after {timeout} s"
        return RunResult(rc, out, err, round(time.monotonic() - t0, 2))


class RecordingRunner:
    """Wrap ``inner``; remember each run. ``capture`` lists relative paths (under cwd) to store with the run."""

    def __init__(self, inner: Runner, capture: dict[str, list[str]] | None = None):
        self.inner = inner
        self.capture = capture or {}
        self.records: list[dict[str, Any]] = []

    def run(self, kind, argv, cwd, env=None, timeout=600):
        res = self.inner.run(kind, argv, cwd, env, timeout)
        files = {}
        for rel in self.capture.get(kind, []):
            p = cwd / rel
            if p.is_file() and p.stat().st_size < 200_000:
                files[rel] = p.read_text(errors="replace")
        res.files = files
        self.records.append({"kind": kind, "argv": [os.path.basename(argv[0]) if i == 0 else a for i, a in enumerate(argv)],
                             "returncode": res.returncode, "stdout": res.stdout[-6000:], "stderr": res.stderr[-2000:],
                             "seconds": res.seconds, "files": files})
        return res


class RecordedRunner:
    """Replay recorded runs in order; refuse a run whose kind or argv differs from the recording."""

    def __init__(self, records: list[dict[str, Any]]):
        self.records = list(records)
        self.i = 0

    def run(self, kind, argv, cwd, env=None, timeout=600):
        if self.i >= len(self.records):
            raise AssertionError(f"replay: unexpected extra run {kind} {argv}")
        r = self.records[self.i]
        self.i += 1
        shown = [os.path.basename(argv[0]) if i == 0 else a for i, a in enumerate(argv)]
        assert r["kind"] == kind, f"replay: run {self.i} was {r['kind']} when recorded, now {kind}"
        assert [_norm(a) for a in r["argv"]] == [_norm(a) for a in shown], \
            f"replay: argv changed: recorded {r['argv']}, now {shown}"
        for rel, text in r.get("files", {}).items():
            p = cwd / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        return RunResult(r["returncode"], r["stdout"], r["stderr"], r["seconds"], r.get("files", {}))


def _norm(a: str) -> str:
    """Paths in recorded argv are repo-relative placeholders: compare the last two path parts only."""
    return "/".join(a.split("/")[-2:]) if a.startswith("/") else a
