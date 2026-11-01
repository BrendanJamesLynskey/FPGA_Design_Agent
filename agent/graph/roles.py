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
    "clarify": {"read": ("spec.md", "spec.yaml"), "write": ("spec.yaml",)},
    "model": {"read": ("spec.yaml",), "write": ("model.py",)},
    "tests": {"read": ("spec.yaml", "model.py", "tests/*", "verif/*"), "write": ("tests/*", "verif/*")},
    "rtl": {"read": ("*",), "write": ("rtl/*", "build.yaml", "design.xdc", "probes.yaml", "BRINGUP.md",
                                      "ARCHITECTURE.md", "hw_checks.py", "lint/*", "BUILD_NOTE.md")},
}
#: tool names each role may call at all (on top of the stage's own list)
ROLE_TOOLS = {"clarify": {"read_file", "write_file", "list_files", "search_docs", "load_skill"},
              "model": {"read_file", "write_file"},
              "tests": {"read_file", "write_file", "list_files", "search_docs", "load_skill"},
              "rtl": None}                                      # None: whatever the stage allows


class RoleJail(PathJail):
    def __init__(self, base: PathJail, role: str):
        super().__init__(base.root, base.write_deny, base.shell_root if role == "rtl" else None)
        self.role, self.rules = role, ROLES[role]

    def _ok(self, rel: str, pats: tuple[str, ...]) -> bool:
        return any(fnmatch.fnmatch(rel, p) for p in pats)

    def resolve(self, rel: str, write: bool = False) -> Path:
        real = super().resolve(rel, write)
        if self.shell_root is not None and (real == self.shell_root or self.shell_root in real.parents):
            return real                                        # rtl role, read-only shell view
        inside = str(real.relative_to(self.root)) if real != self.root else "."
        if inside == "." and not write:
            return real
        if not self._ok(inside, self.rules["write" if write else "read"]):
            raise SecurityError("role", f"the {self.role} sub-agent may not {'write' if write else 'read'} {inside}")
        return real


def role_session(s: Session, role: str) -> Session:
    """A view of ``s`` for one sub-agent: same design, runner, audit and budget; a narrowed jail."""
    v = replace(s, jail=RoleJail(s.jail, role))
    v.audit, v.hw = s.audit, s.hw
    return v


def role_inputs(s: Session, role: str) -> dict[str, str]:
    """The files a sub-agent's first prompt carries, read through its own jail."""
    want = {"clarify": ["spec.md"], "model": ["spec.yaml"], "tests": ["spec.yaml", "model.py"],
            "rtl": ["spec.yaml", "ARCHITECTURE.md"]}[role]
    j = RoleJail(s.jail, role)
    out = {}
    for f in want:
        p = j.resolve(f)
        if p.is_file():
            out[f] = p.read_text()
    return out
