"""On-board self-check of t2_adt7420_alarm with the board's ADT7420 (0x4B).

Pass rule (written before any board run):
  - after a configure with THIGH = 0x7F80 (255 C, never reached) and TLOW = 0xC000 (-128 C), STATUS shows
    CONFIGURED, no NACK and, within 1 s, VALID; ALARM is 0;
  - TEMP (16-bit, 1/128 C, two's complement) is between 10 and 40 C, MIN <= TEMP <= MAX, MAX - MIN < 2 C over
    3 s of readings, and SAMPLES grows by 12 +/- 2 in 3 s (PERIOD 0.25 s);
  - over those 3 s at least one reading has a non-zero value in its three low bits (16-bit mode really set; in
    13-bit mode they are flag bits, all 0 for these limits);
  - with THIGH = TEMP - 2 C and a configure, ALARM becomes 1 within 1 s (comparator mode, INT active low);
    with THIGH back to 0x7F80 and a configure, ALARM returns to 0 within 1 s.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5441_4C4D          # "TALM"
CTRL, STATUS, THIGH, TLOW, TEMP, MAX, MIN, SAMPLES = (p.WINDOW_BASE + i for i in range(8))
CONFIGURED, VALID, NACK, ALARM = 2, 4, 8, 16


def s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def configure(sh: Any, thigh: int, tlow: int) -> int:
    sh.write(THIGH, thigh)
    sh.write(TLOW, tlow)
    sh.write(CTRL, 1)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.0:
        st = sh.read(STATUS)
        if st & VALID:
            return st
    return sh.read(STATUS)


def wait_alarm(sh: Any, want: bool) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.0:
        if bool(sh.read(STATUS) & ALARM) == want:
            return True
    return False


def check(sh: Any) -> dict[str, Any]:
    st = configure(sh, 0x7F80, 0xC000)
    s0 = sh.read(SAMPLES)
    temps = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3.0:
        temps.append(sh.read(TEMP))
        time.sleep(0.1)
    s1 = sh.read(SAMPLES)
    tmax, tmin, temp = s16(sh.read(MAX)), s16(sh.read(MIN)), s16(sh.read(TEMP))
    odd = any(v & 7 for v in temps)
    c = temp / 128
    configure(sh, (temp - 256) & 0xFFFF, 0xC000)
    alarm_on = wait_alarm(sh, True)
    configure(sh, 0x7F80, 0xC000)
    alarm_off = wait_alarm(sh, False)
    res = {"status": f"0x{st:02X}", "temperature_c": c, "max_c": tmax / 128, "min_c": tmin / 128,
           "samples_in_3s": s1 - s0, "odd_low_bits_seen": odd, "alarm_on": alarm_on, "alarm_off": alarm_off}
    res["pass"] = bool(st & CONFIGURED and st & VALID and not st & NACK and not st & ALARM and 10 <= c <= 40
                       and tmin <= temp <= tmax and tmax - tmin < 256 and 10 <= s1 - s0 <= 14 and odd
                       and alarm_on and alarm_off)
    return res
