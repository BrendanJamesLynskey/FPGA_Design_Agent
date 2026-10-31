"""On-board self-check of the configuration flash's JEDEC ID (run by flow/board_check.py).

Pass rule (pre-registered in brief 04c, written before any board run):
  - ID bytes 0-2 = 01 20 18 (manufacturer Cypress/Spansion, 128 Mb) and byte 5 = 80 (FL-S family),
    as both possible parts list them (S25FL128S data sheet 001-98283 Rev. *P Table 54; S25FL127S
    Rev. 11 Table 49; the Nexys A7 board may carry either, RM Table 3.2.1). Byte 3 (4D, the ID-CFI
    length), byte 4 (sector architecture) and bytes 6-7 (model number, ASCII) are recorded only;
  - the same 8 bytes on a second read in the same run.
The design can send no command but RDID (9Fh): see designs/b2_qspi_jedec/tests/test_qspi_rtl.py.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4232_5146          # "B2QF"
CTRL, STATUS, ID0, ID1, INFO = (p.WINDOW_BASE + i for i in range(5))
EXPECTED = {0: 0x01, 1: 0x20, 2: 0x18, 5: 0x80}


def read_id(sh: Any, timeout_s: float = 1.0) -> bytes:
    sh.write(CTRL, 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if not st & 1 and st & 2:
            break
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError(f"RDID did not finish (status 0x{st:X})")
    return (sh.read(ID0) | sh.read(ID1) << 32).to_bytes(8, "little")


def check(sh: Any) -> dict[str, Any]:
    a = read_id(sh)
    b = read_id(sh)
    ok = all(a[i] == v for i, v in EXPECTED.items()) and a == b
    model = a[6:8].decode("ascii", "replace")
    return {"id": a.hex(" "), "second_read": b.hex(" "),
            "expected": {str(i): f"{v:02x}" for i, v in EXPECTED.items()},
            "cfi_length": f"0x{a[3]:02X}", "sector_arch": f"0x{a[4]:02X}", "model_ascii": model,
            "sck_half_clocks": sh.read(INFO) & 0xFFFF, "pass": ok}
