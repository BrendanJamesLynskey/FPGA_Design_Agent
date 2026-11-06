"""On-board self-check of c16_ntt_engine: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x4e545445          # "NTTE"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
