#!/usr/bin/env python3
"""The clock-buffer cap on a published Fmax (brief 201, following brief 199).

An out-of-context run has no clock buffer, so its setup-derived Fmax (1000 / (period - WNS)) can exceed what a real
design can clock: every fabric clock goes through a BUFG/BUFGCE, and Vivado's `report_pulse_width` then adds a
"Min Period" check on the buffer's I pin. Measured with a BUFG in the clock path (results/199_dsp_fmax and
results/201_fmax_cap, Vivado 2026.1):

    xc7a100t / xc7a35t -1       BUFG/I   2.155 ns = 464.0 MHz   (DS181 Table 32, FMAX_BUFG, -1)
    xc7z020 -1                  BUFG/I   2.155 ns = 464.0 MHz   (DS187 Table 67, FMAX_BUFG, -1)
    xczu3eg -2 (0.85 V)         BUFGCE/I 1.290 ns = 775.2 MHz   (DS925 Table 84, BUFG FMAX, -2 at VCCINT 0.85 V = 775)
    xck26 -2LV                  BUFGCE/I 1.379 ns = 725.2 MHz   (DS925 Table 84, BUFG FMAX, -2 at VCCINT 0.72 V = 725)

`cap(part, fmax)` returns the capped figure and which limit binds; the raw number is the caller's to keep.

    python3 flow/fmax_cap.py <part> <fmax_mhz>        # print the capped figure and the binding limit
"""
from __future__ import annotations

import re
import sys

#: part family -> (BUFG minimum period in ns as Vivado reports it, source). Only parts the buffer was measured on, or whose
#: data-sheet figure the same Vivado check reproduces, are listed; others get no cap (cap() returns the input unchanged).
LIMITS = {
    "a7": (2.155, "Vivado report_pulse_width, BUFG/I, xc7a100tcsg324-1 (brief 199) and xc7a35tcpg236-1 (brief 201); DS181 Table 32 FMAX_BUFG -1 = 464 MHz"),
    "z7": (2.155, "Vivado report_pulse_width, BUFG/I, xc7z020clg484-1 (brief 201); DS187 Table 67 FMAX_BUFG -1 = 464 MHz"),
    "zu2": (1.290, "Vivado report_pulse_width, BUFGCE/I, xczu3eg-sfvc784-2-e (brief 201); DS925 Table 84 BUFG FMAX -2 at 0.85 V = 775 MHz"),
    "k26": (1.379, "Vivado report_pulse_width, BUFGCE/I, xck26-sfvc784-2LV-c (brief 199); DS925 Table 84 BUFG FMAX -2 at 0.72 V = 725 MHz"),
}
#: shorthand names used by the result scripts
ALIASES = {"a7": "a7", "k26": "k26", "z7": "z7", "zu2": "zu2"}


def family(part: str) -> str | None:
    """The LIMITS key for a part name or shorthand, or None when no buffer limit is recorded for it."""
    p = (part or "").lower()
    if p in ALIASES:
        return ALIASES[p]
    m = re.match(r"(xc7a\d+t?)[a-z]*\d*-(\d)(l|li|lq|i|q|c)?$", p)
    if m and m.group(2) == "1":
        return "a7"
    m = re.match(r"(xc7z0\d+)[a-z]*\d*-(\d)(l|li|lq|i|q|c)?$", p)
    if m and m.group(2) == "1":
        return "z7"
    if p.startswith("xck26-") and "-2lv" in p:
        return "k26"
    if re.match(r"xczu\d+(eg|ev|cg)-[a-z0-9]+-2(-[eic])?$", p):      # -2 at 0.85 V; -2L / -2LV are other voltages and not measured
        return "zu2"
    return None


def buffer_limit_mhz(part: str) -> float | None:
    fam = family(part)
    return round(1000.0 / LIMITS[fam][0], 1) if fam else None


def cap(part: str, fmax_mhz: float | None, bound: str = "setup slack at the target clock"):
    """(fmax_mhz, bound, buffer_mhz): the smaller of fmax_mhz and the clock-buffer limit of the part, and the name of the limit that binds.

    A limit within 0.5 MHz of an earlier one is the same limit (the earlier one is named), as in results/185_dsp_slices/run_dsp.py.
    With no buffer limit recorded for the part, or no fmax, the input comes back unchanged."""
    buf = buffer_limit_mhz(part)
    if fmax_mhz is None or buf is None:
        return fmax_mhz, bound, buf
    if buf < fmax_mhz - 0.5:
        return buf, "clock-buffer minimum period (BUFG)", buf
    return fmax_mhz, bound, buf


def restate(part: str, raw_mhz: float | None, bound: str = "setup slack at the target clock") -> dict:
    """The three fields a result row gets next to its raw figure: fmax_capped_mhz, fmax_bound, fmax_clock_buffer_mhz."""
    v, b, buf = cap(part, raw_mhz, bound)
    return {"fmax_capped_mhz": v, "fmax_bound": b, "fmax_clock_buffer_mhz": buf}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(cap(sys.argv[1], float(sys.argv[2])))
