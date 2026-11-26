"""Brief 219 fix 5: check the ``LOC`` site names of a design's XDC against the part's site list before synthesis.

The 209 pilot (p1_clkmeter run 3) lost a run at the constraints stage: the XDC put ``set_property LOC IBUFDS_GTE4_X1Y6`` on the
transceiver reference-clock buffer and Vivado answered ``'IBUFDS_GTE4_X1Y6' is not a valid site name``, once per visit, until the stage
budget ended. On a Zynq UltraScale+ part there is no site of type IBUFDS_GTE4: the buffer is a bel of the GTHE4_COMMON site of its quad
(``IBUFDS0_GTHE4`` for MGTREFCLK0, ``IBUFDS1_GTHE4`` for MGTREFCLK1; Vivado 2026.1 query, ``flow/gt_parts/xck26.json``). Constrain
the buffer through its package pins instead (the board file's ``gt.<port>.refclk`` pins), which is what a passing run did.

What is checked: a ``LOC`` whose name starts with a transceiver-column site type this part's data covers (GTHE4_CHANNEL, GTHE4_COMMON,
BUFG_GT, BUFG_GT_SYNC) must be a site of the part; an ``IBUFDS_GTE4_X<n>Y<n>`` name is never one on a part with data. A site type with
no data for the part is not checked (stated, never a pass): the check says nothing about it. A part with no data file is "not checked".

    python3 flow/xdc_sites.py <part> <file.xdc> [--board <board>]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
try:
    from flow import gt_data
except ImportError:                     # run as a script
    import gt_data                      # type: ignore[no-redef]

#: site types whose names are checked, longest first (BUFG_GT_SYNC before BUFG_GT)
CHECKED_TYPES = ("GTHE4_CHANNEL", "GTHE4_COMMON", "BUFG_GT_SYNC", "BUFG_GT")
_NAME = re.compile(r"^(?P<type>[A-Z][A-Z0-9_]*?)_X(?P<x>\d+)Y(?P<y>\d+)$")
_LOC = re.compile(r"\bLOC\s+(?P<site>[^\s\]}]+)")


def loc_names(xdc_text: str) -> list[tuple[int, str]]:
    """(line number, site name) of every ``LOC`` in a ``set_property`` line (plain or ``-dict``); a ``site/BEL`` gives the site."""
    out: list[tuple[int, str]] = []
    for n, raw in enumerate(xdc_text.splitlines(), 1):
        line = raw.split("#", 1)[0]
        if "set_property" not in line:
            continue
        for m in _LOC.finditer(line):
            out.append((n, m.group("site").strip("{}\"'").split("/", 1)[0]))
    return out


def board_refclk_hint(board: str | None, part_data: dict[str, Any], root: Path = ROOT) -> str:
    """Where the board's transceiver reference clock sits, from the board file's package pin and the part's pin table (empty if unknown)."""
    if not board:
        return ""
    f = root / "boards" / board / "board.yaml"
    try:
        gts = (yaml.safe_load(f.read_text()) or {}).get("gt") or {}
    except (OSError, yaml.YAMLError):
        return ""
    for port, gt in sorted(gts.items()):
        ref = (gt or {}).get("refclk") or {}
        pin = part_data.get("pins", {}).get(str(ref.get("p", "")))
        if not pin:
            continue
        m = re.match(r"MGTREFCLK([01])P", pin["func"])
        if m and pin["site"]:
            bel = (part_data.get("ref_buffer_bels", {}).get(pin["site"]) or [None, None])[int(m.group(1))]
            return (f" The board's gt.{port} reference clock is on package pins {ref['p']}/{ref['n']} ({pin['func']}), which belong to "
                    f"site {pin['site']}" + (f", bel {bel}" if bel else "") + ": put PACKAGE_PIN on the two ports and leave the buffer unplaced.")
    return ""


def check(xdc_text: str, part: str, board: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    """``{"checked": bool, "problems": [str], "why": str}``. ``checked`` False: no site data for the part (nothing said, not a pass)."""
    pd = gt_data.load_part(part)
    if pd is None:
        return {"checked": False, "problems": [], "why": f"no site data for part {part!r} (flow/gt_parts): LOC names not checked"}
    known = {s["site"] for s in pd.get("sites", [])}
    kinds = {s["type"] for s in pd.get("sites", [])}
    hint = board_refclk_hint(board, pd, root)
    problems: list[str] = []
    for n, site in loc_names(xdc_text):
        m = _NAME.match(site)
        if not m:
            continue
        t = m.group("type")
        if t == "IBUFDS_GTE4":
            problems.append(f"line {n}: LOC {site}: '{site}' is not a valid site name on {part}. There is no IBUFDS_GTE4 site; the "
                            f"reference-clock buffer is a bel (IBUFDS0_GTHE4 / IBUFDS1_GTHE4) of a GTHE4_COMMON site." + hint)
        elif t in CHECKED_TYPES and t in kinds and site not in known:
            near = sorted(s for s in known if s.startswith(t + "_X"))
            problems.append(f"line {n}: LOC {site}: '{site}' is not a valid {t} site on {part}; its sites are "
                            + ", ".join(near[:6]) + (f" ... ({len(near)} in all)" if len(near) > 6 else "") + ".")
    return {"checked": True, "problems": problems, "why": ""}


def message(problems: list[str]) -> str:
    return "constraints stage: LOC site names that the part does not have (checked before synthesis against flow/gt_parts): " + " | ".join(problems)


def main(argv: list[str] | None = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    board = a[a.index("--board") + 1] if "--board" in a else None
    if "--board" in a:
        del a[a.index("--board"):a.index("--board") + 2]
    if len(a) != 2:
        print(__doc__.splitlines()[0], file=sys.stderr)
        return 2
    r = check(Path(a[1]).read_text(errors="replace"), a[0], board)
    print(message(r["problems"]) if r["problems"] else (r["why"] or "LOC names ok"))
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
