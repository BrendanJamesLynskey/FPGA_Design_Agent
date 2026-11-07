"""On-board self-check of c12_adsr_envelope: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x41445352          # "ADSR"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
