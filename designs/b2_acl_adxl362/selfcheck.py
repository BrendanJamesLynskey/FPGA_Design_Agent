"""On-board self-check of the ADXL362 accelerometer (run by flow/board_check.py).

Pass rule (pre-registered in brief 04c, written before any board run):
  - registers 0x00-0x02 read AD 1D F2 (DEVID_AD, DEVID_MST, PARTID; ADXL362 data sheet Rev. G,
    register map); REVID (0x03) is recorded, not judged (the data sheet gives its reset value as
    0x01, but a later silicon revision would differ);
  - after POWER_CTL (0x2D) = 0x02 (measurement mode, default +/-2 g, 100 Hz) and a wait of
    100 ms (> 4/ODR = 40 ms, "measurement mode instruction to valid data"), one X/Y/Z sample at
    rest has magnitude within [0.57, 1.43] g. Tolerance from the data sheet's Table 1: scale
    factor 1000 LSB/g with sensitivity calibration error +/-10 % (0.9-1.1 g for 1 g), plus the
    worst-case 0 g offsets (X, Y +/-150 mg, Z +/-250 mg: vector length 0.33 g) on whichever
    axes carry gravity, so 0.9 - 0.33 = 0.57 and 1.1 + 0.33 = 1.43 whatever the board's tilt.
  - POWER_CTL is written back to 0x00 (standby) afterwards and read back.
The accelerometer has no non-volatile memory; POWER_CTL is the only register written.
"""

from __future__ import annotations

import math
import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4232_4143          # "B2AC"
CTRL, STATUS, TX0, TX1, RX0, RX1, INFO = (p.WINDOW_BASE + i for i in range(7))
IDS = bytes([0xAD, 0x1D, 0xF2])
G_MIN, G_MAX = 0.57, 1.43
LSB_PER_G = 1000.0


def transfer(sh: Any, tx: bytes, timeout_s: float = 1.0) -> bytes:
    pad = tx.ljust(8, b"\0")
    sh.write(TX0, int.from_bytes(pad[:4], "little"))
    sh.write(TX1, int.from_bytes(pad[4:], "little"))
    sh.write(CTRL, (len(tx) << 8) | 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if not st & 1 and st & 2:
            break
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError(f"SPI transfer did not finish (status 0x{st:X})")
    rx = sh.read(RX0) | sh.read(RX1) << 32
    return rx.to_bytes(8, "little")[:len(tx)]


def check(sh: Any) -> dict[str, Any]:
    ids = transfer(sh, bytes([0x0B, 0x00, 0, 0, 0, 0]))[2:]
    transfer(sh, bytes([0x0A, 0x2D, 0x02]))                     # measurement mode
    time.sleep(0.1)
    raw = transfer(sh, bytes([0x0B, 0x0E] + [0] * 6))[2:]
    xyz = [int.from_bytes(raw[2 * i:2 * i + 2], "little", signed=True) for i in range(3)]
    g = [v / LSB_PER_G for v in xyz]
    mag = math.sqrt(sum(a * a for a in g))
    transfer(sh, bytes([0x0A, 0x2D, 0x00]))                     # back to standby
    power_ctl = transfer(sh, bytes([0x0B, 0x2D, 0]))[2]
    res = {"ids": ids[:3].hex(" "), "ids_expected": IDS.hex(" "), "revid": f"0x{ids[3]:02X}",
           "xyz_lsb": xyz, "xyz_g": [round(a, 3) for a in g], "magnitude_g": round(mag, 4),
           "magnitude_range_g": [G_MIN, G_MAX], "power_ctl_after": f"0x{power_ctl:02X}",
           "sclk_half_clocks": sh.read(INFO) & 0xFFFF}
    res["pass"] = ids[:3] == IDS and G_MIN <= mag <= G_MAX and power_ctl == 0
    return res
