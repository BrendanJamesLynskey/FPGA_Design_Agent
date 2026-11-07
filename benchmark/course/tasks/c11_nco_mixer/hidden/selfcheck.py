"""On-board self-check of c11_nco_mixer: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x4e434f4d          # "NCOM"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
