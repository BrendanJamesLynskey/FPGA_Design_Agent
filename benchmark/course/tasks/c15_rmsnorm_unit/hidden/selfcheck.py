"""On-board self-check of c15_rmsnorm_unit: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x524d534e          # "RMSN"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
