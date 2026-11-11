#!/usr/bin/env python3
"""Check (and, where it is safe, repair) the .ltx probes file of an ILA that is an IP in the netlist (brief 48).

    python3 flow/ltx_fix.py <build dir>          reads <top>.ltx, probe_map.txt and probe_nets.txt; rewrites the .ltx

Measured on Vivado 2026.1: when a probe bit sits on a net that is one bit of a bus whose other bits are on other probe bits
(T1: the three low bits of ``win_addr``), ``write_debug_probes`` writes the net as ``{"name": "win_addr", "isBus": true}``
with no ``subnets``. The hardware manager then calls the whole file inconsistent (Labtools 27-1979: "unconnected port bits for
input port 0") and finds no probes at all, so a capture stops at "never armed". Each such entry is one bit; its real net name
is recorded at insertion time in probe_nets.txt (``<port> <bit> <net>``, written by flow/debug.tcl), so it is rewritten as
``{"name": "<net>", "isBus": false}``. Nothing else in the file changes.

Then the file is checked against probe_map.txt: every bit of every probe port must be covered by a pin whose nets give exactly
as many bits as its index range, and every named probe's bits must be inside a covered range. Any gap is an error (exit 1)
that stops the build, never a file that fails later on the board.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import ila


def _net_bits(net: dict) -> int | None:
    """Bits a net entry stands for: a plain net 1, a bus with subnets len(subnets), a bus without subnets unknown (None)."""
    if net.get("isBus"):
        sub = net.get("subnets")
        return len(sub) if sub else None
    return 1


def fix_and_check(build: Path) -> tuple[int, list[str]]:
    """Returns (entries repaired, problems). The .ltx is rewritten when anything was repaired."""
    ltxs = sorted(build.glob("*.ltx"))
    if len(ltxs) != 1:
        return 0, [f"{build}: expected one .ltx, found {len(ltxs)}"]
    ltx = ltxs[0]
    data = json.loads(ltx.read_text())
    slices = ila.read_probe_slices(build / "probe_map.txt")
    port_width: dict[int, int] = {}
    for _n, port, off, width in slices:
        port_width[port] = max(port_width.get(port, 0), off + width)
    names: dict[tuple[int, int], str] = {}
    pn = build / "probe_nets.txt"
    if pn.exists():
        for line in pn.read_text().splitlines():
            f = line.split()
            if len(f) == 3:
                names[(int(f[0]), int(f[1]))] = f[2]
    problems: list[str] = []
    fixed = 0
    covered: dict[int, set[int]] = {p: set() for p in port_width}
    cores = [c for root in data["ltx_root"]["ltx_data"] for c in root.get("debug_cores", []) if c.get("type", "").startswith("ILA")]
    if len(cores) != 1:
        return 0, [f"{ltx.name}: expected one ILA core, found {len(cores)}"]
    for pin in cores[0].get("pins", []):
        port, lo, hi = pin["portIndex"], pin["leftIndex"], pin["rightIndex"]
        nets = pin.get("nets", [])
        for k, net in enumerate(nets):
            if _net_bits(net) is None:
                # the nets of a segment are listed from its highest port bit down
                bit = hi - k
                if (port, bit) in names:
                    nets[k] = {"name": names[(port, bit)], "isBus": False}
                    fixed += 1
        sizes = [_net_bits(n) for n in nets]
        width = hi - lo + 1
        if None in sizes or sum(sizes) != width:
            problems.append(f"{ltx.name}: probe{port}[{lo}:{hi}] has nets for {sum(s or 0 for s in sizes)} of {width} bits"
                            + (" (a bus net without subnets)" if None in sizes else ""))
        covered.setdefault(port, set()).update(range(lo, hi + 1))
    for name, port, off, width in slices:
        miss = sorted(set(range(off, off + width)) - covered.get(port, set()))
        if miss:
            problems.append(f"{ltx.name}: probe {name} (probe{port}) bits {miss} are in no .ltx pin")
    for port, w in port_width.items():
        miss = sorted(set(range(w)) - covered.get(port, set()))
        if miss:
            problems.append(f"{ltx.name}: probe{port} bits {miss} are not covered ({len(miss)} fewer than probe_map.txt's {w})")
    if fixed and not problems:
        ltx.write_text(json.dumps(data, indent=4) + "\n")
    return fixed, problems


def main(argv: list[str] | None = None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if len(a) != 1:
        print(__doc__.split("\n", 1)[0], file=sys.stderr)
        return 2
    fixed, problems = fix_and_check(Path(a[0]))
    for p in problems:
        print("ltx_fix: " + p, file=sys.stderr)
    print(f"ltx_fix: {fixed} bus entries rewritten, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
