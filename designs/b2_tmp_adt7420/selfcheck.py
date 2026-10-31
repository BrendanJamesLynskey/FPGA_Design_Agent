"""On-board self-check of the ADT7420 temperature sensor (run by flow/board_check.py).

Pass rule (pre-registered in brief 04c, written before any board run):
  - the ID register (0x0B) reads 0xCB (ADT7420 data sheet Rev. A, Table 6 / Table 19:
    manufacturer ID 11001b, revision 011b), with no NACK;
  - the temperature (registers 0x00-0x01, power-on 13-bit mode: code >> 3, 0.0625 C/LSB, two's
    complement; data sheet Table 8-9, RM section 12.3) is between 10 and 40 C.
Nothing is written to the sensor: the design only sets the register pointer and reads.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4232_5453          # "B2TS"
CTRL, STATUS, RDATA, INFO = (p.WINDOW_BASE + i for i in range(4))
ID_REG, ID_VALUE = 0x0B, 0xCB
TEMP_MIN_C, TEMP_MAX_C = 10.0, 40.0


def temperature_c(code16: int) -> float:
    """13-bit mode: the top 13 bits of the 16-bit register pair, two's complement, 1/16 C a step."""
    v = code16 >> 3
    if v & 0x1000:
        v -= 0x2000
    return v * 0.0625


def ptr_read(sh: Any, ptr: int, nbytes: int, timeout_s: float = 1.0) -> tuple[int, int]:
    sh.write(CTRL, (nbytes << 16) | (ptr << 8) | 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if not st & 1 and st & 2:
            return st, sh.read(RDATA)
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError(f"I2C read of 0x{ptr:02X} did not finish (status 0x{st:X})")


def check(sh: Any) -> dict[str, Any]:
    st_id, ident = ptr_read(sh, ID_REG, 1)
    st_t, code = ptr_read(sh, 0x00, 2)
    t = temperature_c(code)
    info = sh.read(INFO)
    res = {
        "id": f"0x{ident:02X}", "id_expected": f"0x{ID_VALUE:02X}", "id_nack": bool(st_id & 4),
        "temp_code": f"0x{code:04X}", "temperature_c": t, "temp_nack": bool(st_t & 4),
        "temp_range_c": [TEMP_MIN_C, TEMP_MAX_C],
        "i2c_address": f"0x{(info >> 16) & 0x7F:02X}", "scl_quarter_clocks": info & 0xFFFF,
    }
    res["pass"] = (ident == ID_VALUE and not st_id & 4 and not st_t & 4 and TEMP_MIN_C <= t <= TEMP_MAX_C)
    return res
