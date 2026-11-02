"""The security layer of the agent core: enforced in code, so the model cannot talk its way past it.

Four pieces, all used by :func:`agent.core.registry.dispatch` before and after every tool runs:

- :class:`PathJail`: every file tool is confined to the design directory (``..`` and symlinks are
  resolved before the check); the build outputs (``build/``) are read-only to the agent, so it cannot forge
  a gate result.
- argument validation against each tool's JSON schema (``additionalProperties: false``), so the agent can
  only ever ask for the fixed commands the tools build: it never sends free-form Tcl or shell.
- :class:`HardwarePolicy`: a per-session budget of hardware actions; flash and configuration memory are
  refused here as well as in ``flow/program.py``.
- :func:`redact` and :class:`AuditLog`: no key, token or cable serial reaches the model's context, a trace
  or the audit log; every call and every refusal is logged to ``build/audit.jsonl``.

``redact`` follows the HW Design Space Agent's tracer (BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6,
``src/hw_dse/agent/trace.py``, MIT): environment values of credential-looking names plus well-known key
shapes. It adds private-key blocks, bearer tokens, GitHub tokens and the local board file's cable serial.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import jsonschema

_KEY_SHAPES = re.compile(
    r"(sk-or-v1-[A-Za-z0-9]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abp]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16})")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)
_SECRET_NAME = re.compile(r"(API_KEY|_TOKEN|_SECRET|PASSWORD|PASSWD)$", re.IGNORECASE)
EXTRA_SECRETS: set[str] = set()          # values registered at runtime (for example the cable serial)


class SecurityError(Exception):
    """A tool call was refused by the security layer; ``rule`` names the rule, the message says why."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule


def _secret_values() -> list[str]:
    vals = {v for k, v in os.environ.items() if _SECRET_NAME.search(k) and v and len(v) >= 8}
    vals |= {v for v in EXTRA_SECRETS if v and len(v) >= 4}
    return sorted(vals, key=len, reverse=True)


def redact(text: str) -> str:
    for v in _secret_values():
        text = text.replace(v, "[REDACTED]")
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    return _KEY_SHAPES.sub("[REDACTED]", text)


def redact_obj(o: Any) -> Any:
    """:func:`redact` applied to every string in a JSON-like structure."""
    if isinstance(o, str):
        return redact(o)
    if isinstance(o, dict):
        return {redact(str(k)): redact_obj(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [redact_obj(v) for v in o]
    return o


# --- the path jail ---------------------------------------------------------------------------------

class PathJail:
    """Resolve agent-supplied paths and refuse anything outside ``root``.

    ``write_deny`` lists top-level names under ``root`` that are read-only for the agent (default
    ``build``: tool outputs). Hidden files at the top level (``.git``, ``.env``) are never writable."""

    MAX_WRITE_BYTES = 1_000_000

    #: Read-only views outside the design (owner, 2026-11-01): the test shell's RTL and protocol. A path
    #: starting with the prefix resolves under the repo; only the listed entries (files or directories) are
    #: visible, and every write is refused.
    READ_ONLY_PREFIX = "@shell/"
    READ_ONLY_ENTRIES = ("rtl", "PROTOCOL.md", "host/protocol.py")

    def __init__(self, root: Path, write_deny: tuple[str, ...] = ("build",), shell_root: Path | None = None):
        self.root = Path(os.path.realpath(root))
        self.write_deny = write_deny
        self.shell_root = Path(os.path.realpath(shell_root)) if shell_root else None

    def _resolve_shell(self, rel: str, write: bool) -> Path:
        if write:
            raise SecurityError("path-jail", "the test shell (@shell/) is read-only for the agent")
        if self.shell_root is None:
            raise SecurityError("path-jail", "no read-only shell view in this session")
        real = Path(os.path.realpath(self.shell_root / rel[len(self.READ_ONLY_PREFIX):]))
        for e in self.READ_ONLY_ENTRIES:
            allowed = Path(os.path.realpath(self.shell_root / e))
            if real == allowed or allowed in real.parents:
                return real
        if real == self.shell_root:
            return real                               # listing @shell/ itself shows only the allowed entries
        raise SecurityError("path-jail", f"path {rel!r} is not in the read-only shell view "
                                         f"({', '.join(self.READ_ONLY_ENTRIES)})")

    #: first components of the design's own layout; '/<one of these>/...' is the Deep Agents virtual style
    VIRTUAL_TOPS = ("spec.md", "spec.yaml", "model.py", "tests", "verif", "rtl", "lint", "build.yaml", "design.xdc",
                    "probes.yaml", "ARCHITECTURE.md", "BRINGUP.md", "hw_checks.py", "BUILD_NOTE.md")

    def canonical(self, rel: str) -> str:
        """ONE path convention for every harness (05c follow-up): tool paths are relative to the design directory.
        The prompts also show the repo-relative design path (build.yaml needs it) and the Deep Agents virtual
        '/model.py' style, so both are accepted and mapped to the design-relative path; the result is still
        resolved and jailed below, so this widens nothing."""
        repo = Path(__file__).resolve().parents[2]
        try:
            pre = self.root.relative_to(repo).as_posix()
        except ValueError:
            pre = ""
        r = rel
        if pre:
            if r.lstrip("/") == pre:
                return "."
            for cand in (pre + "/", "/" + pre + "/"):
                if r.startswith(cand):
                    return r[len(cand):] or "."
        absolute = Path(r).is_absolute()
        if absolute and Path(r).parts[1:2] and Path(r).parts[1] in self.VIRTUAL_TOPS:
            return r.lstrip("/")                         # virtual '/model.py' -> design-relative 'model.py'
        return r

    def resolve(self, rel: str, write: bool = False) -> Path:
        if not isinstance(rel, str) or not rel or "\x00" in rel:
            raise SecurityError("path-jail", "empty or invalid path")
        if rel.startswith(self.READ_ONLY_PREFIX) or rel == self.READ_ONLY_PREFIX.rstrip("/"):
            return self._resolve_shell(rel if rel.endswith("/") or "/" in rel else rel + "/", write)
        if rel.startswith("~"):
            raise SecurityError("path-jail", f"path {rel!r} is outside the design directory")
        rel = self.canonical(rel)
        cand = Path(rel)
        full = cand if cand.is_absolute() else self.root / cand
        real = Path(os.path.realpath(full))          # resolves '..' and every symlink on the way
        try:
            inside = real.relative_to(self.root)
        except ValueError:
            raise SecurityError("path-jail", f"path {rel!r} resolves outside the design directory") from None
        if write:
            top = inside.parts[0] if inside.parts else ""
            if not inside.parts:
                raise SecurityError("path-jail", "cannot write the design directory itself")
            if top in self.write_deny:
                raise SecurityError("path-jail", f"{top}/ is read-only for the agent (tool outputs)")
            if top.startswith("."):
                raise SecurityError("path-jail", f"hidden path {top!r} is not writable")
            if os.path.lexists(full) and os.path.islink(full):
                raise SecurityError("path-jail", "refusing to write through a symlink")
        return real


# --- schema validation -------------------------------------------------------------------------------

def validate_args(schema: dict[str, Any], args: dict[str, Any]) -> None:
    try:
        jsonschema.validate(args, schema, cls=jsonschema.Draft202012Validator)
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "(arguments)"
        raise SecurityError("arguments", f"{loc}: {e.message}") from None


# --- hardware policy -----------------------------------------------------------------------------------

FLASH_WORDS = re.compile(r"flash|qspi|spi_?flash|write_cfgmem|program_hw_cfgmem|cfgmem|\.mcs|\.bin\b|sd\s*card", re.I)
HW_COST = {"program": 1, "bringup": 2}


class HardwarePolicy:
    """A per-session budget for hardware actions. Cost: ``program`` 1, ``bringup`` 2 (it programs twice)."""

    def __init__(self, budget: int = 6):
        self.budget = budget
        self.used = 0

    def charge(self, action: str) -> None:
        cost = HW_COST[action]
        if self.used + cost > self.budget:
            raise SecurityError("hardware-budget", f"hardware action budget exhausted ({self.used} of {self.budget} used, "
                                                  f"{action} costs {cost})")
        self.used += cost


# --- the audit log ---------------------------------------------------------------------------------------

class AuditLog:
    """Append-only JSONL of every tool call: time, stage, tool, arguments, result summary, refusals."""

    def __init__(self, path: Path | None):
        self.path = path
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, rec: dict[str, Any]) -> dict[str, Any]:
        rec = redact_obj({"t": round(time.time(), 3), **rec})
        with self._lock:
            self.records.append(rec)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(rec, default=str) + "\n")
        return rec

    def refusals(self) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("refused")]
