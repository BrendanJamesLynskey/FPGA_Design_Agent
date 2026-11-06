"""On-board self-check of c16_montgomery_mult: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x4d4f4e54          # "MONT"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
