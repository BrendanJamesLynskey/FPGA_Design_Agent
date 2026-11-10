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

    def __post_init__(self) -> None:
        self.design = Path(self.design).resolve()
        self.root = Path(self.root).resolve()
        self.part = self.part or part_of(self.design)
        self.family = family_for_part(self.part) or self.family
        self.jail = self.jail or PathJail(self.design, shell_root=self.root / "shell")
        self.audit = self.audit or AuditLog(self.design / "build" / "audit.jsonl")
        self.hw = self.hw or HardwarePolicy(self.hw_budget)
