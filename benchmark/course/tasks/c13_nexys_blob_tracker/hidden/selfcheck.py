"""On-board self-check of c13_nexys_blob_tracker: blank until board use (brief 07a)."""

from __future__ import annotations

from typing import Any

DESIGN_ID = 0x424c4f42          # "BLOB"


def check(sh: Any) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
