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
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SIM", "VIVADO", "HW_SERVER", "MEM_MAX", "MIN_AVAIL_GB",
            "HW_MIN_AVAIL_GB", "FDA_BOARDS_FILE", "VERILATOR_ROOT", "PYTHONPATH", "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS", "PORT_VERILATORS", "USER", "LOGNAME")
OPT = Path.home() / ".local" / "opt"


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


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP}
    path = env.get("PATH", "/usr/bin:/bin")
    for d in (OPT / "verilator-5048" / "bin", OPT / "formal-deb" / "bin", OPT / "formal-deb" / "usr" / "bin"):
        if d.is_dir() and str(d) not in path:
            path = f"{d}:{path}"
    env["PATH"] = path
    env.update(extra or {})
    return env


class LocalRunner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        t0 = time.monotonic()
        try:
            p = subprocess.run(argv, cwd=cwd, env=scrubbed_env(env), capture_output=True, text=True,
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
