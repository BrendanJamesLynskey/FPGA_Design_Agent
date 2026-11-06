"""On-board self-check of c15_softmax_unit: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x534d4158          # "SMAX"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
