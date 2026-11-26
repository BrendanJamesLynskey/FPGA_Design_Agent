"""The examples, the pinned setup and the pre-flight (brief 195, following ``_handoff/eval_run_checklist.md``).

The pins are in ``examples.yaml``. A run is allowed only when the installed tools match them; the checks refuse, by name, before any model call or heavy slot:
the Claude Code CLI (version and SHA-256 of the pinned copy that goes first on PATH), Vivado, the knowledge-bank checkout (the commit the prompt pin names), and
the model (never Fable or Opus). ``allow_unpinned`` lets a check that is not a safety rule pass and records it, so the comparison can say the run is not like for like.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
FILE = Path(__file__).resolve().parent / "examples.yaml"
RESULTS = ROOT / "results" / "195_repro_examples"
NAME = re.compile(r"[a-z][a-z0-9_]{1,40}")
FORBIDDEN_MODEL = re.compile(r"fable|opus|anthropic[/:.]", re.I)
PIN_ROOT = Path(os.environ.get("FDA_PIN_DIR") or Path.home() / ".local" / "share" / "fpga_design_agent" / "repro_pins")


class ExampleError(Exception):
    pass


def load(path: Path = FILE) -> dict[str, Any]:
    d = yaml.safe_load(path.read_text())
    if d.get("schema") != "fda-examples/1":
        raise ExampleError("examples.yaml has an unknown schema")
    for e in d["examples"]:
        if not NAME.fullmatch(e["name"]):
            raise ExampleError(f"bad example name {e['name']!r}")
        if "held" in e["task"] or "private" in e["task"]:
            raise ExampleError(f"{e['name']}: an example must be a development task")
    if FORBIDDEN_MODEL.search(str(d["pins"].get("cc_model"))) or FORBIDDEN_MODEL.search(str(d["pins"].get("oracle_cc_model"))):
        raise ExampleError("the pinned models must not be Fable, Opus or an Anthropic model through OpenRouter")
    return d


def get(name: str, reg: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = reg or load()
    for e in reg["examples"]:
        if e["name"] == name:
            return e
    raise ExampleError(f"no example {name!r}; `python -m agent example list` shows them")


def task_dir(e: dict[str, Any]) -> Path:
    p = (ROOT / e["task"]).resolve()
    if not str(p).startswith(str(ROOT / "benchmark")) or not (p / "spec.md").is_file():
        raise ExampleError(f"{e['name']}: the task directory {e['task']} has no spec.md under benchmark/")
    return p


def argv(e: dict[str, Any], pins: dict[str, Any], python: str, max_usd: float | None = None, name: str | None = None) -> list[str]:
    """The ``agent run`` command line of an example, from the pins only. Nothing the user types reaches it except an optional lower cost cap."""
    t = task_dir(e)
    usd = pins["max_usd"] if max_usd is None else min(float(max_usd), float(pins["max_usd"]))
    if usd <= 0:
        raise ExampleError("the cost cap must be above 0")
    rel = lambda p: p.relative_to(ROOT).as_posix()                          # noqa: E731
    return [python, "-m", "agent", "run", rel(t / "spec.md"), "--board", pins["board"], "--name", name or f"ex_{e['name']}",
            "--interview", pins["interview"], "--review", pins["review"], "--hidden-spec", rel(t / "hidden" / "spec.yaml"),
            "--harness", pins["harness"], "--cc-model", pins["cc_model"], "--cc-effort", pins["cc_effort"],
            "--oracle", pins["oracle"], "--oracle-cc-model", pins["oracle_cc_model"], "--verif-level", pins["verif_level"],
            "--harness-arm", str(pins["harness_arm"]), "--docs", pins["docs"], "--profile", pins["profile"], "--hdl", pins["hdl"],
            "--stop-after", str(pins["stop_after"]), "--max-usd", f"{usd:g}"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pinned_cli_dir(pins: dict[str, Any]) -> Path:
    return PIN_ROOT / f"claude-{pins['claude_cli_version']}" / "bin"


def kb_dir() -> Path:
    from agent.core.bank import DEFAULT_BANK
    return Path(DEFAULT_BANK)


def _git_head(d: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def repo_commit() -> str | None:
    return _git_head(ROOT)


def check(pins: dict[str, Any], allow_unpinned: bool = False) -> dict[str, Any]:
    """The pre-flight. Returns ``{"ok": bool, "checks": [..], "env": {...}}``; each check has name, ok, detail, hard (a hard failure is never waived).
    ``env`` is what the child process needs (the pinned CLI first on PATH). Nothing here starts a model or Vivado."""
    out: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, hard: bool = False, **extra: Any) -> None:
        out.append({"name": name, "ok": bool(ok), "detail": detail, "hard": hard, **extra})

    env: dict[str, str] = {}
    # 1. the models are never Fable or Opus
    add("model", not (FORBIDDEN_MODEL.search(pins["cc_model"]) or FORBIDDEN_MODEL.search(pins["oracle_cc_model"])),
        f"{pins['cc_model']} (design), {pins['oracle_cc_model']} (interview oracle); Fable, Opus and Anthropic models through OpenRouter are never used", hard=True)
    # 2. the pinned CLI copy
    d = pinned_cli_dir(pins)
    exe = d / "claude"
    if exe.is_file():
        ver = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        sha = sha256_file(exe)
        ok_v = ver.startswith(pins["claude_cli_version"])
        ok_s = sha == pins["claude_cli_sha256"]
        add("claude_cli", ok_v and ok_s, f"pinned copy {exe}: version {ver or '?'}, sha256 {sha[:12]} (pinned {pins['claude_cli_version']}, {pins['claude_cli_sha256'][:12]})",
            hard=not ok_v, installed=ver, sha256=sha)
        if ok_v:
            env["PATH"] = f"{d}:{os.environ.get('PATH', '')}"
    else:
        add("claude_cli", False, f"no pinned copy at {exe}: copy the installed {pins['claude_cli_version']} binary there as a real file "
                                 f"(cp ~/.local/share/claude/versions/{pins['claude_cli_version']} {exe}); the updater prunes old versions, a symlink can vanish", hard=True)
    # 3. Vivado
    try:
        from flow import version_pin as VP
        vp = Path(VP.vivado_path())
        want = pins["vivado_version"]
        have = vp.is_file()
        match = f"/{want}/" in str(vp)
        add("vivado", have and match, f"{vp} ({'present' if have else 'MISSING'}); pinned {want}", hard=True, installed=str(vp))
    except Exception as e:                                                  # noqa: BLE001
        add("vivado", False, f"could not resolve Vivado: {type(e).__name__}", hard=True)
    # 4. the knowledge bank at the commit the prompt pin names
    try:
        from agent.core import prompts
        pin = prompts.read_pin()
        want_kb = pin.get("kb_commit")
        kb = kb_dir()
        head = _git_head(kb)
        ok_kb = bool(head) and head == want_kb
        add("knowledge_bank", ok_kb,
            f"checkout {kb} is at {str(head)[:12]}; the prompt pin names {str(want_kb)[:12]}"
            + ("" if ok_kb else f". Fix: git -C <knowledge repo> worktree add --detach <dir> {want_kb} and export FDA_KNOWLEDGE=<dir>"),
            hard=False, installed=head, pinned=want_kb)
    except Exception as e:                                                  # noqa: BLE001
        add("knowledge_bank", False, f"could not read the prompt pin: {type(e).__name__}", hard=True)
    waived = [c["name"] for c in out if not c["ok"] and not c["hard"] and allow_unpinned]
    ok = all(c["ok"] or c["name"] in waived for c in out)
    return {"ok": ok, "checks": out, "env": env, "unpinned_waived": waived}
