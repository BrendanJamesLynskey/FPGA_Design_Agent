"""On-board self-check of c9_nexys_vga_720p: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x56373230          # "V720"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
