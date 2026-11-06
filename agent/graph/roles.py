"""Sub-agent separation, enforced in code (brief 05b).

Each sub-agent works through a :class:`RoleJail`, a path jail that narrows what the design-directory jail allows:

- ``model`` (the **blind golden model**): reads only ``spec.yaml``; writes only ``model.py``. No RTL, no tests.
- ``tests`` (the **test writer**): reads ``spec.yaml`` and ``model.py``; writes ``tests/`` and ``verif/``. No RTL.
- ``rtl`` (the **RTL writer** and the later implementation stages): reads the design (and ``@shell/``); never the
  hidden full spec or the oracle's material, which live outside the design directory and are never mounted.
- ``clarify``: reads ``spec.md``; writes ``spec.yaml``.

The role's prompt is built from files read through the same jail (:func:`role_inputs`), so a test can prove
exactly what each sub-agent was given.
"""

from __future__ import annotations

import fnmatch
from dataclasses import replace
from pathlib import Path

from agent.core.security import PathJail, SecurityError
from agent.core.session import Session

ROLES: dict[str, dict[str, tuple[str, ...]]] = {
    "clarify": {"read": ("spec.md", "spec.yaml", "data/*"), "write": ("spec.yaml",)},
    "model": {"read": ("spec.yaml", "model.py", "data/*"), "write": ("model.py",)},      # its own output, to edit on a repair
    "tests": {"read": ("spec.yaml", "model.py", "data/*", "tests/*", "verif/*", "probes.yaml", "BRINGUP.md", "hw_checks.py"),
              "write": ("tests/*", "verif/*", "hw_checks.py")},       # hw_checks.py: stage 9 bring-up checks, against the model
    "rtl": {"read": ("*",), "write": ("rtl/*", "build.yaml", "design.xdc", "probes.yaml", "BRINGUP.md",
                                      "ARCHITECTURE.md", "architecture.yaml", "hw_checks.py", "lint/*", "BUILD_NOTE.md")},
}
#: tool names each role may call at all (on top of the stage's own list)
ROLE_TOOLS = {"clarify": {"read_file", "write_file", "list_files", "search_docs", "load_skill"},
              "model": {"read_file", "write_file"},
              "tests": {"read_file", "write_file", "list_files", "search_docs", "load_skill", "formal"},
              "rtl": None}                                      # None: whatever the stage allows


#: what the test writer may read of ``@shell/`` (read-only): the frame protocol and the host classes it must import
TESTS_SHELL_VIEW = ("PROTOCOL.md", "host/protocol.py", "host/fpga_shell.py")


class RoleJail(PathJail):
    def __init__(self, base: PathJail, role: str):
        super().__init__(base.root, base.write_deny, base.shell_root if role in ("rtl", "tests") else None)
        self.role, self.rules = role, ROLES[role]
        if role == "tests":     # brief 05g: the test shell's protocol and host classes (what the hw tests import), not its RTL
            self.READ_ONLY_ENTRIES = TESTS_SHELL_VIEW

    def _ok(self, rel: str, pats: tuple[str, ...]) -> bool:
        return any(fnmatch.fnmatch(rel, p) for p in pats)

    def resolve(self, rel: str, write: bool = False) -> Path:
        real = super().resolve(rel, write)
        if self.shell_root is not None and (real == self.shell_root or self.shell_root in real.parents):
            return real                                        # rtl role, read-only shell view
        inside = str(real.relative_to(self.root)) if real != self.root else "."
        if inside == "." and not write:
            return real
        if write and self.role == "rtl" and inside in ("architecture.yaml", "ARCHITECTURE.md") \
                and (self.root / "build" / "approvals" / "architecture.json").is_file():
            raise SecurityError("role", f"{inside} is approved and frozen; a change goes back to the architecture stage "
                                        f"for a new approval (brief 05d)")
        if not self._ok(inside, self.rules["write" if write else "read"]):
            raise SecurityError("role", f"the {self.role} sub-agent may not {'write' if write else 'read'} {inside}")
        return real


def role_session(s: Session, role: str) -> Session:
    """A view of ``s`` for one sub-agent: same design, runner, audit and budget; a narrowed jail."""
    v = replace(s, jail=RoleJail(s.jail, role))
    v.audit, v.hw = s.audit, s.hw
    return v


def role_inputs(s: Session, role: str, previous: bool = False) -> dict[str, str]:
    """The files a sub-agent's first prompt carries, read through its own jail. ``previous`` (a repair visit) adds
    the role's own earlier output, which it edits: ``model.py`` for the model writer, ``tests/`` and ``verif/``
    for the test writer. Never anything the role may not read."""
    want = {"clarify": ["spec.md", "spec.yaml"], "model": ["spec.yaml"], "tests": ["spec.yaml", "model.py"],
            "rtl": ["spec.yaml", "ARCHITECTURE.md"]}[role]
    j = RoleJail(s.jail, role)
    if role == "tests" and s.stage == "configuration-and-debug":      # stage 9: the bring-up files (probe names, guide)
        want = want + ["probes.yaml", "BRINGUP.md", "hw_checks.py"] + sorted(
            str(p.relative_to(s.design)) for p in (s.design / "tests").glob("test_*_hw.py"))
    if previous and role == "model":
        want = want + ["model.py"]
    if previous and role == "tests":
        want = want + sorted(str(p.relative_to(s.design)) for d in ("tests", "verif")
                             for p in (s.design / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                             and p.name != "__init__.py" and p.stat().st_size < 60_000)
    if role == "tests" and (s.design / "verif" / "checkers" / "v_macros.svh").is_file():
        want = want + ["verif/checkers/v_macros.svh"]       # 05i: the macros the tests role declares assertions with
    out = {}
    for f in want:
        p = j.resolve(f)
        if p.is_file():
            out[f] = p.read_text()
    if role == "tests":                  # brief 05g: the shell's protocol and host classes, read-only, for the bench and the hw tests
        refs = ["PROTOCOL.md"] + (["host/fpga_shell.py", "host/protocol.py"] if s.stage == "configuration-and-debug" else [])
        for f in refs:
            try:
                p = j.resolve("@shell/" + f)
            except SecurityError:
                continue
            if p.is_file():
                out["shell_ref/" + f] = p.read_text()
    return out
