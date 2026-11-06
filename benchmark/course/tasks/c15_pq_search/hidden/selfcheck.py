"""On-board self-check of c15_pq_search: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x50515352          # "PQSR"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
