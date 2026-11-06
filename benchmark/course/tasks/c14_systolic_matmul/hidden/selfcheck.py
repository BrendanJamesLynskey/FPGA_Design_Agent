"""On-board self-check of c14_systolic_matmul: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x4d4d3458          # "MM4X"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
