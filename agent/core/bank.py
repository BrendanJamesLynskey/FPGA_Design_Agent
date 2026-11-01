"""Frozen knowledge-bank access: ``tools/search_docs.py`` and ``tools/select_skills.py`` of
FPGA_Design_Agent_Knowledge, loaded from their folder. No network, no other source.

Chunk and skill text is **untrusted data**: tools return it inside a data envelope and the audit log
records what was loaded; nothing in it can change a tool's behaviour (the red-team tests inject
instructions into a chunk and check they are only text)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_BANK = Path(os.environ.get("FDA_KNOWLEDGE", Path(__file__).resolve().parents[3] / "FPGA_Design_Agent_Knowledge"))


def _load(path: Path, name: str):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"fda_bank_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)              # type: ignore[union-attr]
        return mod
    finally:
        sys.path.remove(str(path.parent))


class LocalBank:
    def __init__(self, root: Path = DEFAULT_BANK):
        self.root = Path(root)
        self._search = _load(self.root / "tools" / "search_docs.py", "search")
        self._select = _load(self.root / "tools" / "select_skills.py", "select")

    def search(self, query: str, k: int = 5, sections: list[str] | None = None) -> list[dict[str, Any]]:
        return self._search.search_docs(query, k=k, sections=sections, lib=self.root / "library")

    def skills(self, board: str | None, family: str | None, sections: list[str] | None,
               primary_only: bool = True, procedures: bool = False) -> list[dict[str, Any]]:
        """``[{path, axis, section, name, description, text}]`` for the board and family, filtered to the sections."""
        items = self._select.select(board=board, family=family, sections=sections, primary_only=primary_only,
                                    procedures=procedures, root=self.root)
        out = []
        for s in items:
            p = self.root / s.path
            out.append({"path": s.path, "axis": s.axis, "section": s.section, "name": s.name,
                        "description": s.description, "text": p.read_text(errors="replace")})
        return out
