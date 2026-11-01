"""A session: one design directory, one board, the security objects, and the stage the agent is in."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.core.runner import LocalRunner, Runner
from agent.core.security import AuditLog, HardwarePolicy, PathJail
from agent.core.trace import Trace

ROOT = Path(__file__).resolve().parents[2]
STAGES = ("clarify", "board-and-device-planning", "rtl-design-creation", "constraints", "synthesis",
          "implementation", "timing-closure", "power-closure", "drc-closure", "configuration-and-debug")


@dataclass
class Session:
    design: Path                                   # designs/<name>: the only place the agent may read or write
    root: Path = ROOT                              # the repo: flow/, shell/, boards/ (the agent never touches these)
    board: str = "nexys_a7_100t"
    family: str = "artix7"
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
        self.jail = self.jail or PathJail(self.design, shell_root=self.root / "shell")
        self.audit = self.audit or AuditLog(self.design / "build" / "audit.jsonl")
        self.hw = self.hw or HardwarePolicy(self.hw_budget)
