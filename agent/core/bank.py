"""Frozen knowledge-bank access: ``tools/search_docs.py`` and ``tools/select_skills.py`` of
FPGA_Design_Agent_Knowledge, loaded from their folder. No network, no other source.

Chunk and skill text is **untrusted data**: tools return it inside a data envelope and the audit log
records what was loaded; nothing in it can change a tool's behaviour (the red-team tests inject
instructions into a chunk and check they are only text)."""

from __future__ import annotations

import importlib.util
import inspect
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


#: sectioned vendor sets of the bank (``vendor/<name>/<section>/<skill>/SKILL.md``) that ``skills`` also reads. Until
#: f2-stage3-io only techniques, functions, family, board and procedures were read, so a section whose skills live in
#: the vendor axis (``constraints``: xdc-constraints-basics) always came back empty.
VENDOR_SETS = ("ross_distilled", "amd_constraints")   # brief 20: amd_constraints (13b) was never read, so the
#: exception, I/O-delay and clock skills did not reach the agent (run 1 of the d20 drill loaded only xdc-constraints-basics)


class LocalBank:
    def __init__(self, root: Path = DEFAULT_BANK):
        self.root = Path(root)
        self._search = _load(self.root / "tools" / "search_docs.py", "search")
        self._select = _load(self.root / "tools" / "select_skills.py", "select")

    def search(self, query: str, k: int = 5, sections: list[str] | None = None) -> list[dict[str, Any]]:
        return self._search.search_docs(query, k=k, sections=sections, lib=self.root / "library")

    def skills(self, board: str | None, family: str | None, sections: list[str] | None,
               primary_only: bool = True, procedures: bool = False, part: str | None = None) -> list[dict[str, Any]]:
        """``[{path, axis, section, name, description, text}]`` for the board and family, filtered to the sections.

        Brief 31: with ``part`` (build.yaml) and a bank whose ``select`` takes it, the family units come from the part, so
        a K26 design gets the Zynq UltraScale+ layer and never the Artix-7 one. A bank older than brief 31 falls back
        to ``family``."""
        if part and "part" in inspect.signature(self._select.select).parameters:
            items = self._select.select(board=board, part=part, sections=sections, primary_only=primary_only,
                                        procedures=procedures, root=self.root)
        else:
            items = self._select.select(board=board, family=family, sections=sections, primary_only=primary_only,
                                        procedures=procedures, root=self.root)
        if sections:
            known = {x.path for x in items}
            for v in VENDOR_SETS:
                try:
                    more = self._select.select(sections=sections, vendor=v, generic=False, primary_only=primary_only,
                                               procedures=False, root=self.root)
                except Exception:                      # a bank without that set: nothing to add
                    continue
                items = list(items) + [x for x in more if x.path not in known]
        out = []
        for s in items:
            p = self.root / s.path
            out.append({"path": s.path, "axis": s.axis, "section": s.section, "name": s.name,
                        "description": s.description, "text": p.read_text(errors="replace")})
        return out
