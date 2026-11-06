"""On-board self-check of c13_hough_lines: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x484f5547          # "HOUG"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
