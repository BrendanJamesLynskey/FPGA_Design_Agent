"""GTH data the GT gates (flow/gt_gates.py) and the link planner (flow/gt_plan.py) check against (brief 56A).

Numbers are our own tabulation of AMD DS925 v1.30 (2026-07-09) tables 99 (line-rate windows by PLL and output divider) and 104
(user-clock maxima), and UG576 v1.7.1 (divider sets, VCO bands). Speed grades are the columns of those tables:
"3" = -3 at 0.90 V, "2" and "1" = -2 and -1 at 0.85 V, "2LV" and "1LV" = -2 and -1 at 0.72 V (the K26 is "2LV").
Package pins and sites come from Vivado 2026.1 queries (`flow/gt_parts/<family>.json`, written by
designs/b56a_gth_serdes/probe/gt_sites.tcl). Unknown parts or speed grades make a check "not applicable", never a pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PARTS_DIR = Path(__file__).with_name("gt_parts")
GRADES = ("3", "2", "1", "2LV", "1LV")
#: transceiver maximum line rate, Gb/s (DS925 v1.30 table 99, FGTHMAX; the minimum is 0.5 at every grade)
FGTHMAX = {"3": 16.375, "2": 16.375, "1": 12.5, "2LV": 12.5, "1LV": 10.3125}
FGTHMIN = 0.5
#: output divider D -> (min, max) line rate in Gb/s, by speed grade (table 99). The CPLL has no D = 16.
_CPLL = {"3": {1: (4, 12.5), 2: (2, 6.25), 4: (1, 3.125), 8: (0.5, 1.5625)},
         "2": {1: (4, 12.5), 2: (2, 6.25), 4: (1, 3.125), 8: (0.5, 1.5625)},
         "1": {1: (4, 8.5), 2: (2, 4.25), 4: (1, 2.125), 8: (0.5, 1.0625)},
         "2LV": {1: (4, 8.5), 2: (2, 4.25), 4: (1, 2.125), 8: (0.5, 1.0625)},
         "1LV": {1: (4, 8.5), 2: (2, 4.25), 4: (1, 2.125), 8: (0.5, 1.0625)}}
_Q0_HI = {"3": 16.375, "2": 16.375, "1": 12.5, "2LV": 12.5, "1LV": 10.3125}
_Q0_D2 = {"3": 8.1875, "2": 8.1875, "1": 8.15, "2LV": 8.1875, "1LV": 8.15}
_Q0_D4 = {"3": 4.0938, "2": 4.0938, "1": 4.075, "2LV": 4.0938, "1LV": 4.075}
_Q0_D8 = {"3": 2.0469, "2": 2.0469, "1": 2.0375, "2LV": 2.0469, "1LV": 2.0375}
_Q0_D16 = {"3": 1.0234, "2": 1.0234, "1": 1.0188, "2LV": 1.0234, "1LV": 1.0188}
_Q1_D1 = {"3": 13.0, "2": 13.0, "1": 12.5, "2LV": 12.5, "1LV": 10.3125}


def windows(pll: str, grade: str) -> dict[int, tuple[float, float]]:
    """{divider: (min, max) Gb/s} for CPLL, QPLL0 or QPLL1 at a speed grade (KeyError for an unknown grade)."""
    if pll == "CPLL":
        return dict(_CPLL[grade])
    if pll == "QPLL0":
        return {1: (9.8, _Q0_HI[grade]), 2: (4.9, _Q0_D2[grade]), 4: (2.45, _Q0_D4[grade]), 8: (1.225, _Q0_D8[grade]),
                16: (0.6125, _Q0_D16[grade])}
    if pll == "QPLL1":
        return {1: (8.0, _Q1_D1[grade]), 2: (4.0, 6.5), 4: (2.0, 3.25), 8: (1.0, 1.625), 16: (0.5, 0.8125)}
    raise KeyError(pll)


#: (internal width, user width) -> TXUSRCLK2/RXUSRCLK2 maximum, MHz, by grade (table 104)
_USR2 = {(16, 16): (511.719, 511.719, 390.625, 390.625, 322.266), (16, 32): (255.859, 255.859, 195.313, 195.313, 161.133),
         (32, 32): (511.719, 511.719, 390.625, 390.625, 322.266), (32, 64): (255.859, 255.859, 195.313, 195.313, 161.133),
         (20, 20): (409.375, 409.375, 312.5, 312.5, 257.813), (20, 40): (204.688, 204.688, 156.25, 156.25, 128.906),
         (40, 40): (409.375, 409.375, 312.5, 312.5, 257.813), (40, 80): (204.688, 204.688, 156.25, 156.25, 128.906)}
#: internal width -> TXUSRCLK/RXUSRCLK maximum, MHz, by grade (table 104)
_USR = {16: (511.719, 511.719, 390.625, 390.625, 322.266), 32: (511.719, 511.719, 390.625, 390.625, 322.266),
        20: (409.375, 409.375, 312.5, 312.5, 257.813), 40: (409.375, 409.375, 312.5, 312.5, 257.813)}
_COL = {"3": 0, "2": 1, "1": 2, "2LV": 3, "1LV": 4}


def usrclk2_max(int_w: int, ext_w: int, grade: str) -> float | None:
    row = _USR2.get((int_w, ext_w))
    return row[_COL[grade]] if row else None


def usrclk_max(int_w: int, grade: str) -> float | None:
    row = _USR.get(int_w)
    return row[_COL[grade]] if row else None


#: reference clock input range, MHz (table 101) and the DRP clock maximum (table 100)
REFCLK_RANGE_MHZ = (60.0, 820.0)
DRP_MAX_MHZ = 250.0


def speed_grade(part: str) -> str | None:
    """'2LV' for xck26-sfvc784-2LV-c, '2' for xczu5ev-sfvc784-2-i; None where the grade is ambiguous or not a GTH column."""
    m = re.search(r"-(\d)(LV|L)?-[a-z]$", part)
    if not m or m.group(2) == "L":
        return None
    g = m.group(1) + (m.group(2) or "")
    return g if g in GRADES else None


def load_part(part: str) -> dict | None:
    """The package-pin table of a part (gt_parts/<device>.json), or None. The file name is the device name (xck26)."""
    dev = part.split("-")[0]
    f = PARTS_DIR / f"{dev}.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    return d if d.get("part", "").split("-")[0] == dev else None


def quad_of_channel(site: str) -> str | None:
    """'GTHE4_COMMON_X0Y1' for the channel 'X0Y6' (four channels to a quad)."""
    m = re.fullmatch(r"(?:GTHE4_CHANNEL_)?X(\d+)Y(\d+)", site.strip())
    return f"GTHE4_COMMON_X{m.group(1)}Y{int(m.group(2)) // 4}" if m else None
