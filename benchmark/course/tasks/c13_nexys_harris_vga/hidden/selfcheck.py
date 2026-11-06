"""On-board self-check of c13_nexys_harris_vga: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x48415252          # "HARR"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
