"""On-board self-check of c12_nexys_pwm_audio: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x50574d41          # "PWMA"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
