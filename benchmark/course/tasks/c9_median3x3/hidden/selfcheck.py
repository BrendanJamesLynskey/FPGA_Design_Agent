"""On-board self-check of c9_median3x3: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x4d45444e          # "MEDN"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
