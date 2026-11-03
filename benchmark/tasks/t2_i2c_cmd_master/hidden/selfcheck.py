"""On-board self-check of t2_i2c_cmd_master against the board's ADT7420 (I2C address 0x4B).

Pass rule (written before any board run):
  - INFO reads QUARTER = 250 (100 kHz);
  - START, WRITE 0x96 (ACK), WRITE 0x0B (ACK), repeated START, WRITE 0x97 (ACK), READ with NACK, STOP gives
    RXDATA = 0xCB (ADT7420 ID register, data sheet Table 19) with no NACK at any step;
  - the same sequence with pointer 0x00 and two READs (ACK, then NACK) gives a temperature between 10 and 40 C in
    the sensor's power-on 13-bit format (code >> 3, 1/16 C a step);
  - an address probe of 0x48 (no device there) NACKs.
Nothing is written to the sensor's registers: only the pointer.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4932_434D          # "I2CM"
CMD, STATUS, RXDATA, INFO = (p.WINDOW_BASE + i for i in range(4))
START, WRITE, READ, STOP = 1, 2, 3, 4
BUSY, NACK = 1, 2


def cmd(sh: Any, op: int, data: int = 0, nack: int = 0) -> int:
    sh.write(CMD, op | data << 8 | nack << 16)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if not st & BUSY:
            return st
        if time.monotonic() - t0 > 0.5:
            raise TimeoutError(f"command {op} stuck busy (status 0x{st:X})")


def reg_read(sh: Any, ptr: int, n: int) -> tuple[list[int], bool]:
    nacks = []
    cmd(sh, START)
    nacks.append(cmd(sh, WRITE, 0x4B << 1) & NACK)
    nacks.append(cmd(sh, WRITE, ptr) & NACK)
    cmd(sh, START)
    nacks.append(cmd(sh, WRITE, 0x4B << 1 | 1) & NACK)
    out = []
    for i in range(n):
        cmd(sh, READ, nack=int(i == n - 1))
        out.append(sh.read(RXDATA))
    cmd(sh, STOP)
    return out, any(nacks)


def check(sh: Any) -> dict[str, Any]:
    q = sh.read(INFO)
    ident, nack_id = reg_read(sh, 0x0B, 1)
    raw, nack_t = reg_read(sh, 0x00, 2)
    code = (raw[0] << 8 | raw[1]) >> 3
    t = (code - 0x2000 if code & 0x1000 else code) / 16
    cmd(sh, START)
    probe_nack = bool(cmd(sh, WRITE, 0x48 << 1) & NACK)
    cmd(sh, STOP)
    res = {"quarter": q, "id": f"0x{ident[0]:02X}", "temp_raw": [f"0x{b:02X}" for b in raw], "temperature_c": t,
           "nack_seen": nack_id or nack_t, "probe_0x48_nack": probe_nack}
    res["pass"] = (q == 250 and ident[0] == 0xCB and not (nack_id or nack_t) and 10.0 <= t <= 40.0 and probe_nack)
    return res
