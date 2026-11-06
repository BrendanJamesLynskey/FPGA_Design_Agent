"""On-board self-check of c16_nexys_aes_uart: blank until board use (brief 07a). The subject is the USB-UART itself, so the test shell is not embedded (NO_SHELL)."""

from __future__ import annotations

from typing import Any

NO_SHELL = True


def check(sh: Any = None) -> dict[str, Any]:
    return {"pass": None, "note": "not written yet"}
