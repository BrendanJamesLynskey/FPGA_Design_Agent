"""The newcomer's first minute (brief 157): what works without the access key, and ``python -m agent doctor``.

Standard library only, on purpose: ``doctor`` and the fallback ``--help`` must run on a checkout that has installed nothing but
``pyyaml`` and ``pyserial`` (and even without those: the doctor then says so).

The access gate (``agent/access``) is a security control. Exactly these things run without a key, each because it prints text, or
reads the user's own design, and does none of the three things the gate protects (call a model, write a design or the run
directory, read private material):

* ``--help`` / ``-h`` at any level (argparse prints and exits before anything else runs);
* ``python -m agent doctor`` (checks that things exist; the private prompts are read only when a valid key is present);
* ``python -m agent models show`` (prints the model table: which endpoint and model each purpose would use; no call is made);
* ``python -m agent resume <design-dir> ... --dry-run`` (reads the design's handover and prints the stage it would re-enter;
  nothing is written, no model is called). ``resume <run-id> --dry-run`` is **not** exempt: for a run id ``--dry-run`` does
  nothing and the run would continue, so it needs the key like every other run.

:func:`ungated` is the single place that decides this; ``agent/tests/test_157_newcomer_cli.py`` proves every other command and
flag combination still stops at the gate, and ``agent/graph``'s ``pickup_cmd`` asks the gate again once it leaves its dry-run
branch, so a mistake here cannot reach a model.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = ROOT / "agent" / "core" / "prompts_pin.json"
SIM_IMAGE = "fda-sim:2"                    # agent/core/runner.py SIM_IMAGE (a test compares the two)
VIVADO_VERSION = "2026.1"                  # flow/version_pin.py DEFAULT_VIVADO_VERSION (a test compares the two)
INSTALL = "pip install -e '.[agent,graph]'    # extras are in pyproject.toml; the README's test install line does not include them"

#: command -> (one-line help, longer description, key). ``key``: "yes" needs FDA_ACCESS_KEY, "no" does not, "part" says which part.
COMMANDS: dict[str, tuple[str, str, str]] = {
    "run": ("a new design from a plain-English spec (calls models; writes runs/ and a design directory)",
            "Build a design from a spec.md: clarify, plan, RTL, tests, constraints, then the Vivado stages. Calls models, writes a run "
            "directory under runs/ and a design directory, and spends money (the model table says on which endpoint: "
            "`python -m agent models show`). Needs the access key.", "yes"),
    "resume": ("continue a run, or change a design the agent made (calls models); `resume <design-dir> ... --dry-run` needs no key",
               "`resume <run-id>` continues a paused or stopped run. `resume <design-dir> \"<change>\"` re-enters the flow at the "
               "stage the change needs. Needs the access key, except `resume <design-dir> ... --dry-run`, which only reads the "
               "design and prints the stage it would re-enter.", "part"),
    "document": ("write the handover for a finished run (calls a model)",
                 "Run the documentation step on a finished run directory. Calls a model. Needs the access key.", "yes"),
    "review": ("review an existing design (read-only; calls a model)",
               "Review RTL you wrote: findings, the understanding the reviewer reached and the verification gap. Writes only "
               "under --out; the design is left unchanged. Calls a model unless --no-judge. Needs the access key.", "yes"),
    "models": ("show (no key) or check (key) the model table",
               "`models show` prints which endpoint, model and options each purpose uses and where each value came from; it makes no "
               "call and needs no key. `models check` validates the table and, with --probe, spends one call per endpoint; it needs "
               "the access key.", "part"),
    "latency": ("the latency loop on a frozen checkout (calls models)", "Needs the access key.", "yes"),
    "improve": ("analyse a design and offer strategies to improve it (calls a model; --choose writes the design's strategy file)",
                "Needs the access key, including with --dry-run (--choose saves strategy.json into the design first).", "yes"),
    "doctor": ("check what this machine is missing before the first run (no key needed)",
               "Checks the Python packages the agent needs, the access key, the private prompts and their pin, the simulator image, "
               "Vivado and the other tool versions, and names each one that is missing with the command that fixes it. Exit "
               "status 0 when nothing the agent cannot run without is missing, else 1. Never prints the key.", "no"),
    "project": ("the project layer (`python -m agent project check|status|hash|gen-tests <dir>`); needs no key except `project spec`",
                "Dispatched before the agent's own command line: `python -m agent project --help` shows its help.", "part"),
}

TOP_DESCRIPTION = """Natural-language spec to a verified AMD FPGA design. Most commands call a model and write a design, so they need the access key."""

TOP_EPILOG = """what works without the access key (FDA_ACCESS_KEY, in the environment or in a git-ignored .env):
  --help at any level           prints help and exits 0
  doctor                        what this machine is missing before a first run
  models show                   the model table; no call is made
  resume <design-dir> "<change>" --dry-run
                                the stage a change would re-enter; reads the design, writes nothing, calls nothing
everything else needs the key and refuses with exit status 2 and one line saying so. Easy to get wrong:
  * `resume <name>` means a run id under runs/ when <name> is not a directory with handover.yaml; for a run id --dry-run does
    nothing and the run continues, so it is not exempt.
  * `--dry-run` on `improve --choose` is not exempt either: it writes the design's strategy.json before it stops.
  * the private prompts are looked for in $FDA_PROMPTS_DIR, else <checkout's parent>/FPGA_Design_Agent_Knowledge/prompts, which
    is the wrong place for a git worktree; `doctor` shows the path it used and whether it matches the pin.
  * `--stop-after N` counts stages from 0: 0 clarify, 1 board-and-device-planning, 2 rtl-design-creation, 3 constraints,
    4 synthesis, 5 implementation, 6 timing-closure, 7 power-closure, 8 drc-closure, 9 configuration-and-debug.
"""

RUN_EPILOG = """examples:
  python -m agent run designs/t1_dimmer_counter/spec.md --board nexys_a7_100t --stop-after 2     # RTL and verification only
  python -m agent models show                                                                    # which models this would spend on

needs the access key and the private prompts (`python -m agent doctor` says what is missing). --stop-after N counts stages from 0:
0 clarify, 1 board-and-device-planning, 2 rtl-design-creation, 3 constraints, 4 synthesis, 5 implementation, 6 timing-closure,
7 power-closure, 8 drc-closure, 9 configuration-and-debug. Stages 0-2 need no Vivado; 3 onward do.
"""

RESUME_EPILOG = """examples:
  python -m agent resume designs/b110_itch_ouch "widen the price field to 64 bits" --dry-run   # which stage would it re-enter; no key
  python -m agent resume <run-id> --reply '{"answer": "yes"}'                        # continue a paused run (key)

`--dry-run` is for a design directory only. A request with no keyword the classifier knows (for example "use fewer LUTs") re-enters at
stage 0, a full re-run: the dry run shows that before anything is spent; pass --kind or --from-stage to choose the stage yourself.
"""

#: Python modules that belong to an extra in pyproject.toml, by extra. ``find_spec`` only: nothing is imported.
EXTRAS: dict[str, dict[str, str]] = {
    "agent": {"jsonschema": "jsonschema", "mcp": "mcp"},
    "graph": {"langgraph": "langgraph", "langgraph.checkpoint.sqlite": "langgraph-checkpoint-sqlite", "deepagents": "deepagents",
              "langchain_openai": "langchain-openai"},
}
BASE = {"yaml": "pyyaml", "serial": "pyserial"}


def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _version(dist: str) -> str:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return "?"


# --- the gate exemptions ---------------------------------------------------------------------------------------

def is_design_resume(run_id: str) -> bool:
    """``resume <x>`` picks up a design (rather than a run id) when <x> is a directory holding handover.yaml: the one test, used by
    both the dispatcher and the exemption, so they cannot disagree."""
    return (Path(run_id) / "handover.yaml").is_file()


def ungated(a) -> str | None:
    """Why this parsed command line may run without the access key, or None (it needs the key). The only list of exemptions."""
    cmd = getattr(a, "cmd", None)
    if cmd == "models" and getattr(a, "action", None) == "show":
        return "models show: prints the model table; no model call, nothing written, no private file read"
    if cmd == "resume" and getattr(a, "dry_run", False) and is_design_resume(getattr(a, "run_id", "")):
        return "resume <design-dir> --dry-run: reads the design's handover and prints the entry stage; nothing is written, no model is called"
    return None


def help_requested(args: list[str]) -> bool:
    for x in args:
        if x == "--":
            return False
        if x in ("-h", "--help"):
            return True
    return False


def fallback_help() -> str:
    rows = "\n".join(f"  {n:<9} {h}" for n, (h, _l, _k) in COMMANDS.items())
    return f"usage: python -m agent [-h] command ...\n\n{TOP_DESCRIPTION}\n\ncommands:\n{rows}\n\n{TOP_EPILOG}"


def _missing_modules() -> dict[str, list[str]]:
    return {ex: [d for m, d in mods.items() if not _have(m)] for ex, mods in EXTRAS.items()}


def without_extras(args: list[str], err: ImportError) -> int:
    """The full command line could not be built because a package of an extra is missing. ``--help`` still answers (exit 0) with the
    command table and what to install; any other use is gated first (the key decides, as always), then says what is missing."""
    miss = {k: v for k, v in _missing_modules().items() if v}
    what = "; ".join(f"{k} extra: {', '.join(v)}" for k, v in miss.items()) or f"module {getattr(err, 'name', '?')}"
    if help_requested(args):
        print(fallback_help())
        print(f"note: the full help of each command needs the agent extras, which are not all installed here (missing {what}).\n"
              f"      {INSTALL}\n      python -m agent doctor    # lists everything else that is missing")
        return 0
    first = next((x for x in args[1:] if not x.startswith("-")), "")
    runs_nothing = args[:2] == ["models", "show"] or (args[:1] == ["resume"] and "--dry-run" in args and is_design_resume(first))
    if not runs_nothing:                                   # these two would have run without a key had the extras been here
        from agent.access import require_or_exit
        require_or_exit("python -m agent")
    print(f"python -m agent: not installed here: {what}. {INSTALL}. `python -m agent doctor` lists everything that is missing.", file=sys.stderr)
    return 2


def missing_extra(a, err: ImportError) -> int:
    """A command that is allowed to run needed a package that is not installed: say which, not a traceback."""
    miss = {k: v for k, v in _missing_modules().items() if v}
    what = "; ".join(f"{k} extra: {', '.join(v)}" for k, v in miss.items()) or f"module {getattr(err, 'name', '?')}"
    print(f"python -m agent {getattr(a, 'cmd', '')}: not installed here: {what}. {INSTALL}. `python -m agent doctor` lists everything "
          "that is missing.", file=sys.stderr)
    return 2


# --- doctor ----------------------------------------------------------------------------------------------------

class Check:
    """One line of the report. ``level``: required (the agent cannot run without it), recommended (a stage or a feature needs it),
    optional (a route you may not use). ``ok`` None = not checked here (said in the detail)."""

    def __init__(self, id: str, level: str, ok: bool | None, detail: str, fix: str = ""):
        self.id, self.level, self.ok, self.detail, self.fix = id, level, ok, detail, fix

    def line(self) -> str:
        tag = "n/a    " if self.ok is None else "ok     " if self.ok else ("MISSING" if self.level == "required" else "missing")
        tail = f"  Fix: {self.fix}" if self.ok is False and self.fix else ""
        return f"[{tag}] {self.id}: {self.detail}{tail}"

    def as_dict(self) -> dict:
        return {"id": self.id, "level": self.level, "ok": self.ok, "detail": self.detail, "fix": self.fix}


def prompts_location(env: dict | None = None) -> tuple[Path, str]:
    """Where the private prompts are looked for, and why: the same rule as ``agent.core.prompts.prompts_dir`` (a test compares them)."""
    env = os.environ if env is None else env
    if env.get("FDA_PROMPTS_DIR"):
        return Path(env["FDA_PROMPTS_DIR"]), "FDA_PROMPTS_DIR"
    if env.get("FDA_KNOWLEDGE"):
        return Path(env["FDA_KNOWLEDGE"]) / "prompts", "FDA_KNOWLEDGE"
    return ROOT.parent / "FPGA_Design_Agent_Knowledge" / "prompts", "default: the sibling FPGA_Design_Agent_Knowledge of this checkout"


def vivado_path(env: dict | None = None) -> str:
    """The same rule as ``flow.version_pin.vivado_path`` (a test compares them)."""
    env = os.environ if env is None else env
    if env.get("VIVADO"):
        return env["VIVADO"]
    return f"/opt/Xilinx/{env.get('FDA_VIVADO_VERSION') or VIVADO_VERSION}/Vivado/bin/vivado"


def _run_version(cmd: list[str], runner: Callable, timeout: int = 20) -> str:
    try:
        r = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return "version not readable"
    out = ((r.stdout or "") + " " + (r.stderr or "")).strip().splitlines()
    return out[0].strip()[:100] if out else "version not readable"


def run_checks(*, env: dict | None = None, probe: bool = True, which: Callable = shutil.which, runner: Callable = subprocess.run,
               key_ok: Callable[[], str | None] | None = None) -> list[Check]:
    env = os.environ if env is None else env
    out: list[Check] = []
    v = sys.version_info
    out.append(Check("python", "required", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}" + ("" if v >= (3, 10) else " (3.10 or newer is required)"),
                     "use Python 3.10 or newer (CI uses 3.12)"))
    miss = [d for m, d in BASE.items() if not _have(m)]
    out.append(Check("base_packages", "required", not miss, "pyyaml, pyserial" + (f"; not installed: {', '.join(miss)}" if miss else " installed"),
                     "pip install pyyaml pyserial"))
    for ex, why in (("agent", "the agent core and its MCP server"), ("graph", "the Deep Agents graph that runs the stages")):
        m = [d for mod, d in EXTRAS[ex].items() if not _have(mod)]
        out.append(Check(f"{ex}_extra", "required", not m,
                         f"{why}: " + (f"not installed: {', '.join(m)}" if m else ", ".join(f"{d} {_version(d)}" for d in EXTRAS[ex].values())),
                         INSTALL))
    # the key: never printed; the entry's name only when it matches
    from agent import access
    entry = key_ok() if key_ok else _key_entry(access, env)
    keyed = entry is not None
    if access.load_entries() is None:
        out.append(Check("access_key", "required", True, "the gate is not armed here (agent/access/keys.json is absent): no key needed"))
        keyed = True
    elif entry:
        out.append(Check("access_key", "required", True, f"FDA_ACCESS_KEY accepted (entry '{entry}')"))
    else:
        has = bool((env.get("FDA_ACCESS_KEY") or "").strip() or access.read_dotenv(access.ENV_FILE))
        out.append(Check("access_key", "required", False,
                         "FDA_ACCESS_KEY is " + ("set but not accepted (wrong, revoked or expired)" if has else "not set (environment or .env)"),
                         "the owner gives each user a key; put FDA_ACCESS_KEY=... in the environment or in a git-ignored .env at the repo root "
                         "(see .env.example). Without a key only --help, doctor, models show and resume <design-dir> --dry-run run"))
    # the private prompts: where they are looked for, and the pin
    pdir, how = prompts_location(env)
    try:
        pin = json.loads(PIN_FILE.read_text())
    except (OSError, ValueError):
        pin = {}
    mf = pdir / "MANIFEST.json"
    out.append(Check("prompts_path", "required", mf.is_file(), f"{pdir} ({how})" + ("" if mf.is_file() else "; no MANIFEST.json there"),
                     "check out the private FPGA_Design_Agent_Knowledge repository (read access is the owner's to give) and set FDA_PROMPTS_DIR "
                     "to its prompts/ directory; a git worktree needs this because the default is a sibling of the checkout"))
    want = pin.get("manifest_sha256")
    commit = str(pin.get("kb_commit") or "")[:12]
    if not mf.is_file():
        out.append(Check("prompts_pin", "required", False, f"pinned to private commit {commit or 'none'}; cannot be compared (no manifest)",
                         "make prompts_path point at the checkout of that commit"))
    elif not keyed:
        out.append(Check("prompts_pin", "required", None, f"pinned to private commit {commit or 'none'}; the manifest is compared only when a "
                                                          "valid key is present (it is private material)"))
    else:
        import hashlib
        got = hashlib.sha256(mf.read_bytes()).hexdigest()
        ok = (not want) or got == want or env.get("FDA_PROMPTS_UNPINNED") == "1"
        out.append(Check("prompts_pin", "required", ok, f"pinned to private commit {commit or 'none'}; manifest "
                         + ("matches the pin" if ok else f"hash {got[:12]} is not the pinned {str(want)[:12]}"),
                         "check out the private repository at the pinned commit (FDA_PROMPTS_UNPINNED=1 skips the comparison, for prompt development only)"))
    # the sandbox image and the other tools
    docker = which("docker")
    if not docker:
        out.append(Check("sim_image", "recommended", False, f"docker not found; the image {SIM_IMAGE} runs the agent's own test code in isolation",
                         f"install Docker, then: docker build -t {SIM_IMAGE} agent/container (without it a run falls back to the host, and a run with a "
                         "hidden spec refuses)"))
    elif not probe:
        out.append(Check("sim_image", "recommended", None, f"docker at {docker}; the image {SIM_IMAGE} was not probed (--no-probe)"))
    else:
        r = None
        try:
            r = runner([docker, "image", "inspect", SIM_IMAGE], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
        have = bool(r and r.returncode == 0)
        out.append(Check("sim_image", "recommended", have, f"image {SIM_IMAGE} " + ("present" if have else "not present (or the docker daemon is not reachable)"),
                         f"docker build -t {SIM_IMAGE} agent/container   (the agent's own test code runs there; without it a run falls back to the host)"))
    vp = vivado_path(env)
    vexists = Path(vp).is_file() or bool(which("vivado") and not env.get("VIVADO"))
    if not vexists:
        out.append(Check("vivado", "recommended", False, f"Vivado not found at {vp}",
                         f"install Vivado {VIVADO_VERSION} under /opt/Xilinx, or set VIVADO=<path to the binary>. Stages 0-2 (clarify, plan, RTL and "
                         "verification) run without it; synthesis onward does not"))
    else:
        exe = vp if Path(vp).is_file() else (which("vivado") or vp)
        ver = _run_version([exe, "-version"], runner, 90) if probe else "not probed (--no-probe)"
        m = re.search(r"v(\d{4}\.\d)", ver)
        pinned = bool(m and m.group(1) == (env.get("FDA_VIVADO_VERSION") or VIVADO_VERSION))
        out.append(Check("vivado", "recommended", pinned if probe else None, f"{exe}: {ver}" + ("" if pinned or not probe else f" (published numbers use {VIVADO_VERSION})"),
                         f"the flow is pinned to Vivado {VIVADO_VERSION}"))
    tools = (("claude_cli", "recommended", "claude", ["claude", "--version"],
              "install Claude Code; the default model table sends spectest, review and doc purposes to it (python -m agent models show)"),
             ("iverilog", "recommended", "iverilog", ["iverilog", "-V"], "apt install iverilog (host simulation; the image has its own)"),
             ("verilator", "optional", "verilator", ["verilator", "--version"], "apt install verilator, or use the image (coverage and lint)"),
             ("yosys", "optional", "yosys", ["yosys", "-V"], "needed for the structural checks and formal proofs (not installed by apt on every OS)"),
             ("ghdl", "optional", "ghdl", ["ghdl", "--version"], "apt install ghdl, only for --hdl vhdl"))
    for id_, level, exe, cmd, fix in tools:
        p = which(exe)
        if not p:
            out.append(Check(id_, level, False, f"{exe} not found", fix))
        else:
            out.append(Check(id_, level, True, f"{p}: " + (_run_version(cmd, runner) if probe else "not probed (--no-probe)")))
    return out


def _key_entry(access, env: dict) -> str | None:
    entries = access.load_entries()
    if entries is None:
        return None
    return access.match(access.read_key(dict(env), access.ENV_FILE), entries)


def doctor_main(argv: list[str], *, out=None, **kw) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m agent doctor", description=COMMANDS["doctor"][1],
                                 epilog="Levels: MISSING = the agent cannot run without it (exit status 1); missing = a stage or feature needs it; "
                                        "n/a = not checked (the line says why). Needs no access key; the private prompt manifest is compared "
                                        "only when a valid key is present, and the key is never printed.")
    ap.add_argument("--json", action="store_true", help="the checks as JSON")
    ap.add_argument("--no-probe", action="store_true", help="locate tools but run none of them (no docker call, no vivado -version)")
    a = ap.parse_args(argv)
    out = out or sys.stdout
    checks = run_checks(probe=not a.no_probe, **kw)
    bad = [c for c in checks if c.level == "required" and c.ok is False]
    if a.json:
        print(json.dumps({"checks": [c.as_dict() for c in checks], "missing_required": [c.id for c in bad]}, indent=1), file=out)
    else:
        for c in checks:
            print(c.line(), file=out)
        print(("\nnot ready: " + ", ".join(c.id for c in bad)) if bad else "\nready: nothing the agent cannot run without is missing", file=out)
    return 1 if bad else 0
