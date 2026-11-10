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
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SIM", "VIVADO", "HW_SERVER", "MEM_MAX", "MIN_AVAIL_GB",
            "HW_MIN_AVAIL_GB", "FDA_BOARDS_FILE", "VERILATOR_ROOT", "PYTHONPATH", "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS", "PORT_VERILATORS", "FDA_HEAVY_LOCK", "USER", "LOGNAME", "LD_LIBRARY_PATH", "YOSYS_DATDIR")


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
    uid_dir = Path(f"/run/user/{os.getuid()}")             # the build runs under systemd-run --user: it needs the user bus
    if "XDG_RUNTIME_DIR" not in env and uid_dir.is_dir():  # (a launcher that lost these made every Vivado build fail
        env["XDG_RUNTIME_DIR"] = str(uid_dir)              #  with "Failed to connect to bus" in 05c2's Opus run)
    if "DBUS_SESSION_BUS_ADDRESS" not in env and (uid_dir / "bus").exists():
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={uid_dir / 'bus'}"
    env.update(tools.get("env", {}))
    if tools.get("path"):
        env["PATH"] = os.pathsep.join([*tools["path"], env.get("PATH", os.defpath)])
    env.update(extra or {})
    return env


def tool_available(name: str) -> bool:
    """Whether ``name`` is on the PATH the agent's tools run with (the local tools file included)."""
    return shutil.which(name, path=scrubbed_env().get("PATH", os.defpath)) is not None


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
        # own session/process group: on a timeout the whole group is killed. subprocess.run(timeout=) kills only the
        # direct child, so a timed-out flow/run_vivado.sh left its Vivado (in the systemd scope) running (QR1, verified)
        proc = subprocess.Popen(argv, cwd=cwd, env=full_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                errors="replace", start_new_session=True, stdin=subprocess.DEVNULL)
        try:
            out, err = proc.communicate(timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                out, _ = proc.communicate(timeout=15)       # partial output; a grandchild that left the group may hold the pipes
            except subprocess.TimeoutExpired:
                out = ""
            rc, err = 124, f"timed out after {timeout} s"
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
        if kind in ("import_check", "lint-icarus"):       # derived pre-checks (07a2 fix 3, fix 5 D), not recorded steps; recordings predate them
            return RunResult(0, "", "", 0.0)
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


# --- isolation for agent-written test code (owner decision 2026-11-01) ---------------------------------------

#: Default image: Ubuntu 24.04, Python 3.12, cocotb 2.0.1, Icarus 12.0, Verilator 5.048 (agent/container/Dockerfile).
SIM_IMAGE = "fda-sim:2"          # built from agent/container/Dockerfile (docker build -t fda-sim:2 agent/container)
#: Unchanged from fda-sim:1: the T1 Verilator coverage run peaked at 0.8 GiB and 13 MB of build tmpfs (05m): see docs/agent_core.md.
DEFAULT_MEMORY, DEFAULT_BUILD_TMPFS = "3g", "1g"


class ContainerRunner:
    """Run the kinds that execute agent-written code (default: ``simulate``) in a container: no network, all
    capabilities dropped, no new privileges, the host user's uid/gid (never root inside), a read-only root
    filesystem, and only these mounts: the design directory read-write, the repo's trusted ``flow/``,
    ``shell/`` and ``designs/__init__.py`` read-only, and a tmpfs over the repo's ``build/`` (sim scratch) and
    ``/tmp``. No home directory, no keys, no other design. Other kinds go to ``inner`` unchanged.

    The engine is Docker 29 via the docker group (the daemon itself runs as root; podman is not installed).
    The argv is the same one the core builds, so replay fixtures do not change."""

    def __init__(self, design: Path, root: Path, inner: Runner | None = None, kinds: tuple[str, ...] = ("simulate", "contract", "import_check"),
                 image: str = SIM_IMAGE, engine: str = "docker", memory: str = DEFAULT_MEMORY,
                 build_tmpfs: str = DEFAULT_BUILD_TMPFS):
        self.design, self.root = Path(os.path.realpath(design)), Path(os.path.realpath(root))
        self.inner = inner or LocalRunner()
        self.kinds, self.image, self.engine, self.memory = kinds, image, engine, memory
        self.build_tmpfs = build_tmpfs

    def container_argv(self, argv: list[str], env: dict[str, str] | None, name: str | None = None) -> list[str]:
        import sys
        r = str(self.root)
        cmd = [self.engine, "run", "--rm", *(["--name", name] if name else []), "--network", "none", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--read-only", "--user", f"{os.getuid()}:{os.getgid()}",
               "--memory", self.memory, "--pids-limit", "512",
               "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", f"{r}/build:rw,exec,size={self.build_tmpfs}",
               "-v", f"{self.design}:{self.design}:rw",
               "-v", f"{r}/flow:{r}/flow:ro", "-v", f"{r}/shell:{r}/shell:ro",
               "-v", f"{r}/designs/__init__.py:{r}/designs/__init__.py:ro",
               "-w", r, "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PYTHONPATH={r}"]
        for k, v in (env or {}).items():
            cmd += ["-e", f"{k}={v}"]
        prog = "python3" if argv[0] == sys.executable or os.path.basename(argv[0]).startswith("python") else argv[0]
        return [*cmd, self.image, prog, *argv[1:]]

    def run(self, kind, argv, cwd, env=None, timeout=600):
        if kind not in self.kinds:
            return self.inner.run(kind, argv, cwd, env, timeout)
        name = f"fda-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        res = self.inner.run(kind, self.container_argv(argv, env, name), cwd, None, timeout)
        if res.returncode == 124:           # timed out: killing the docker client leaves the container running, so remove it by name
            subprocess.run([self.engine, "rm", "-f", name], capture_output=True, timeout=60)
        return res


def container_available(engine: str = "docker", image: str = SIM_IMAGE) -> bool:
    """True if the engine runs and the image is present locally (no pull: pulling needs the network)."""
    try:
        p = subprocess.run([engine, "image", "inspect", image], capture_output=True, timeout=30)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


_IMAGE_VERILATOR: dict[tuple[str, str], tuple[int, int] | None] = {}


def image_verilator_version(engine: str = "docker", image: str = SIM_IMAGE) -> tuple[int, int] | None:
    """Verilator's (major, minor) inside the sandbox image, or None (no Verilator in it, or no engine). The image is
    probed once per process and the answer cached: an image does not change under a running graph."""
    import re
    key = (engine, image)
    if key not in _IMAGE_VERILATOR:
        v = None
        try:
            p = subprocess.run([engine, "run", "--rm", "--network", "none", "--entrypoint", "verilator", image, "--version"],
                               capture_output=True, text=True, timeout=120)
            m = re.search(r"Verilator\s+(\d+)\.(\d+)", p.stdout) if p.returncode == 0 else None
            v = (int(m.group(1)), int(m.group(2))) if m else None
        except (OSError, subprocess.SubprocessError):
            pass
        _IMAGE_VERILATOR[key] = v
    return _IMAGE_VERILATOR[key]
