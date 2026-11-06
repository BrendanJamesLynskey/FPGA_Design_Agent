"""On-board self-check of c14_int8_dot_requant: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x444f5451          # "DOTQ"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
