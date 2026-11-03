"""Read an ILA capture exported by flow/ila_capture.tcl (write_hw_ila_data -csv_file).

The CSV's columns are hardware probes, named after nets in the .ltx, and one ILA probe
port can be split over several of them (a bus whose bits sit on differently named nets
after synthesis). Two map files join them back up:
- ``probe_map.txt`` from the build (flow/debug.tcl): ``probe<i> <name> <width> <pins>``
- ``hw_probes.txt`` from the capture session: ``<port> <width> <map> <hw probe name>``,
  where ``<map>`` is the hw_probe's MAP property, e.g. ``probe8[6:3]`` (comma-joined
  if it has several ranges), most significant bit first. The CSV header is the hw probe
  name, with the net's own bus range appended for bus nets (``u_dut/count[15:14]``).
:func:`load_capture` returns ``{probes.yaml name: [port value per sample]}``.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path


def read_probe_map(path: Path) -> dict[int, tuple[str, int]]:
    """probe_map.txt -> {port: (name, width)}."""
    out = {}
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) >= 3 and f[0].startswith("probe"):
            out[int(f[0][5:])] = (f[1], int(f[2]))
    return out


def map_bits(m: str) -> list[int]:
    """'probe8[6:3]' or 'probe0[15:14],probe0[1]' -> port bits, MSB first."""
    bits: list[int] = []
    for tok in m.split(","):
        r = re.fullmatch(r"probe\d+\[(\d+)(?::(\d+))?\]", tok.strip())
        if not r:
            raise ValueError(f"cannot read hw_probe MAP {m!r}")
        hi = int(r.group(1))
        lo = int(r.group(2)) if r.group(2) is not None else hi
        bits += list(range(hi, lo - 1, -1))
    return bits


def read_hw_probes(path: Path) -> dict[str, tuple[int, list[int]]]:
    """hw_probes.txt -> {hw probe name: (port, port bits MSB first)} (the last of equal names: see read_hw_probe_list)."""
    return {n: pb for n, pb in read_hw_probe_list(path)}


def read_hw_probe_list(path: Path) -> list[tuple[str, tuple[int, list[int]]]]:
    """hw_probes.txt -> [(hw probe name, (port, port bits MSB first))] in file order. Names can repeat: one synthesised
    bus (counter_reg_n_0_) split over several non-adjacent slices gives several hw_probes of the same name."""
    out: list[tuple[str, tuple[int, list[int]]]] = []
    for line in path.read_text().splitlines():
        f = line.split(maxsplit=3)
        if len(f) == 4:
            port, width, m, name = int(f[0]), int(f[1]), f[2], f[3].strip()
            bits = map_bits(m)
            if len(bits) != width:
                raise ValueError(f"{path}: {name} is {width} bits wide but MAP {m} has {len(bits)}")
            out.append((name, (port, bits)))
    return out


def _range_text(bits: list[int]) -> str:
    return f"{bits[0]}:{bits[-1]}" if len(bits) > 1 else str(bits[0])


def _strip_range(h: str) -> str:
    """CSV headers add the net's own bus range to bus probes: 'u_dut/count[15:14]' -> 'u_dut/count'."""
    return re.sub(r"\[\d+(:\d+)?\]$", "", h)


def _value(text: str, radix: str) -> int:
    t = text.strip()
    r = radix.upper()
    if "BINARY" in r:
        return int(t, 2)
    if "SIGNED" in r:            # UNSIGNED or SIGNED: decimal
        return int(t, 10)
    return int(t, 16)


def load_capture(csv_path: Path, probe_map: Path, hw_probes: Path) -> dict[str, list[int]]:
    """{name: samples} for every probe port, plus 'TRIGGER' and 'sample' (sample in window)."""
    names = read_probe_map(probe_map)
    hwl = read_hw_probe_list(hw_probes)
    hwp = dict(hwl)
    dup = {n for n in hwp if sum(1 for m, _ in hwl if m == n) > 1}
    used: set[tuple[str, int]] = set()
    with open(csv_path, newline="") as f:
        rows = [r for r in csv.reader(f) if r]
    header, radix, data = [h.strip() for h in rows[0]], rows[1], rows[2:]
    if not radix[0].lower().startswith("radix"):
        raise ValueError(f"{csv_path}: second row is not the radix row: {radix[:3]}")
    n = len(data)
    ports: dict[int, list[int]] = {port: [0] * n for port in names}
    covered: dict[int, set[int]] = {port: set() for port in names}
    out: dict[str, list[int]] = {}
    for col, h in enumerate(header):
        vals = [_value(r[col], radix[col]) for r in data]
        if h == "Sample in Window":
            out["sample"] = vals
        elif h == "TRIGGER":
            out["TRIGGER"] = vals
        elif h in hwp or _strip_range(h) in hwp:
            base = h if h in hwp else _strip_range(h)
            if base in dup:
                # several hw_probes of one name: the CSV column carries the net's bus range ('name[15:12]'), which is
                # the slice's port-bit range for a pin-to-bit mapping; any other case is ambiguous, so say so
                rng = re.search(r"\[(\d+(?::\d+)?)\]$", h)
                cand = [(i, pb) for i, (m, pb) in enumerate(hwl) if m == base and (base, i) not in used
                        and rng is not None and _range_text(pb[1]) == re.sub(r"^(\d+):\1$", r"\1", rng.group(1))]
                if len(cand) != 1:
                    raise ValueError(f"{csv_path}: column {h!r} matches {len(cand)} of the hw_probes named {base!r} "
                                     "(equal names, bus range not equal to a port-bit range)")
                used.add((base, cand[0][0]))
                port, bits = cand[0][1]
            else:
                port, bits = hwp[base]
            w = len(bits)
            for k, v in enumerate(vals):
                acc = ports[port][k]
                for j, b in enumerate(bits):          # bits[0] is the column value's MSB
                    if (v >> (w - 1 - j)) & 1:
                        acc |= 1 << b
                ports[port][k] = acc
            covered[port] |= set(bits)
    for port, (name, width) in names.items():
        if covered[port] != set(range(width)):
            missing = sorted(set(range(width)) - covered[port])
            raise ValueError(f"{csv_path}: probe {name} (port {port}) bits {missing} are in no CSV column")
        out[name] = ports[port]
    return out
