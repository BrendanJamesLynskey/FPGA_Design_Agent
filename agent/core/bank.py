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


#: vendor units that are not sectioned (as AMD ships them); the bank's own ``sections.UNSECTIONED`` names the same one
UNSECTIONED_VENDOR = ("ross_shipped",)

#: read first, in this order, so a skill the agent already got stays ahead of the newly read units. ``load_skill`` keeps
#: only the first six skills; units are otherwise read in name order, and ``amba_axi`` / ``amd_ip_cores`` would push
#: ``ross_distilled`` (xdc-constraints-basics, timing-methodology) out of a six-skill answer. An order hint only: it names
#: no unit that must exist, and every other sectioned unit is still read.
VENDOR_FIRST = ("ross_distilled", "amd_constraints")


def vendor_units(root: Path, unsectioned=UNSECTIONED_VENDOR) -> list[str]:
    """The sectioned vendor units of the bank at ``root``, found from its layout: every ``vendor/<unit>/`` that holds
    ``<section>/<skill>/SKILL.md`` (``ross_distilled``, ``amd_constraints``, ``amd_ip_cores``, ``amba_axi``,
    ``vivado_synthesis``, ``free_simulators`` at the pin), without the unsectioned ones. Nothing is listed by hand, so a
    unit added to the bank reaches the agent when the bank is re-pinned (brief 20 found the old hard-coded pair left four
    units unread)."""
    v = Path(root) / "vendor"
    if not v.is_dir():
        return []
    found = [u.name for u in sorted(v.iterdir())
             if u.is_dir() and u.name not in unsectioned and any(u.glob("*/*/SKILL.md"))]
    return sorted(found, key=lambda n: (VENDOR_FIRST.index(n) if n in VENDOR_FIRST else len(VENDOR_FIRST), n))


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
            for v in vendor_units(self.root):
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
