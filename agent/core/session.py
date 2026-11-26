"""A session: one design directory, one board, the security objects, and the stage the agent is in."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.core.runner import LocalRunner, Runner
from agent.core.security import AuditLog, HardwarePolicy, PathJail
from agent.core.trace import Trace

ROOT = Path(__file__).resolve().parents[2]
STAGES = ("clarify", "board-and-device-planning", "rtl-design-creation", "constraints", "synthesis",
          "implementation", "timing-closure", "power-closure", "drc-closure", "configuration-and-debug")


#: target part -> the knowledge-bank family the agent's default family is set to (brief 31). The bank itself picks every
#: family unit from the part (select_skills.families_for_part); this only keeps ``Session.family`` consistent with it.
PART_FAMILY = ((r"^xc7[as]", "artix7"), (r"^xc7z", "zynq7000"), (r"^(xck2[46]|xczu)", "zynq_ultrascale_plus"))


def family_for_part(part: str | None) -> str | None:
    for pat, fam in PART_FAMILY:
        if part and re.match(pat, part.strip().lower()):
            return fam
    return None


def part_of(design: Path) -> str | None:
    """The ``part`` of designs/<name>/build.yaml, or None when there is no build.yaml or no part in it."""
    f = Path(design) / "build.yaml"
    if not f.exists():
        return None
    try:
        import yaml
        return (yaml.safe_load(f.read_text()) or {}).get("part")
    except Exception:                                  # a broken build.yaml is reported by the flow, not here
        return None


@dataclass
class Session:
    design: Path                                   # designs/<name>: the only place the agent may read or write
    root: Path = ROOT                              # the repo: flow/, shell/, boards/ (the agent never touches these)
    board: str = "nexys_a7_100t"
    family: str = "artix7"
    part: str | None = None                        # build.yaml `part`; when set, the bank's family units follow it
    runner: Runner = field(default_factory=LocalRunner)
    bank: Any = None                               # knowledge bank (agent.core.bank), frozen
    stage: str = "clarify"
    hw_budget: int = 6
    trace: Trace | None = None
    audit: AuditLog = None                         # type: ignore[assignment]
    jail: PathJail = None                          # type: ignore[assignment]
    hw: HardwarePolicy = None                      # type: ignore[assignment]
    #: brief 36: ``"router"`` ranks ``load_skill(sections)`` by relevance inside its cap; ``"off"`` (default) keeps the
    #: eval-1 order. Set from Config.skill_routing (Deep Agents) or FDA_SKILL_ROUTING (the Claude Code arm's MCP server).
    skill_routing: str = "off"
    #: brief 42: harness arms on for this session, e.g. ``("H1", "H2")``; empty (default) is the unchanged baseline.
    harness_arms: tuple[str, ...] = ()
    #: brief 196: the run directory whose ``policy.json`` pins the run's settings (outside the design directory, so no role reaches it); the
    #: ``build`` tool passes the pinned security request to the flow in ``FDA_SECURITY``. None: no pin (a hand-run session).
    policy_run_dir: Path | None = None
    #: brief 222: the run directory whose ``permissions.json`` is the run's permission policy; every tool call is checked against it
    #: (``agent.core.permissions.tool_gate``). None: a hand-run session, which still passes the never-rules.
    permissions_run_dir: Path | None = None

    def __post_init__(self) -> None:
        self.design = Path(self.design).resolve()
        self.root = Path(self.root).resolve()
        from agent.access import require_or_exit      # brief 94: a session is the agent's tool surface
        require_or_exit("Session")
        self.part = self.part or part_of(self.design)
        self.family = family_for_part(self.part) or self.family
        self.jail = self.jail or PathJail(self.design, shell_root=self.root / "shell")
        self.audit = self.audit or AuditLog(self.design / "build" / "audit.jsonl")
        self.hw = self.hw or HardwarePolicy(self.hw_budget)
        if self.jail.policy is None:                   # brief 102: a design with a project.yaml is a managed project
            from agent.core.managed import policy_for
            self.jail.policy = policy_for(self.design)
        if self.jail.policy is not None and hasattr(self.runner, "ro_paths"):     # brief 102F: a container runner mounts the protected files read-only
            self.runner.ro_paths = self.jail.policy.protected_files
        from agent import access                       # brief 94: attribute the run to the entry that admitted it (name only)
        if access.CURRENT:
            self.audit.log({"event": "access", "entry": access.CURRENT})
