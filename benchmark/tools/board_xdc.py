#!/usr/bin/env python3
"""Board pins for benchmark specs, and the reference XDC generated from a hidden spec.yaml.

    python3 benchmark/tools/board_xdc.py expand <spec.yaml>   # fill pins/iostandard into the ports list (in place)
    python3 benchmark/tools/board_xdc.py xdc <spec.yaml> <out.xdc>

Pins and I/O standards come only from Digilent's master XDC (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc).
Port names are the master XDC's; a vector port ``SW`` of width 16 maps to ``SW[0]``..``SW[15]``; a scalar such as
``JA1``, ``QSPI_DQ0`` or ``ACL_INT1`` maps to ``JA[1]``, ``QSPI_DQ[0]``, ``ACL_INT[1]``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "boards" / "nexys_a7_100t" / "Nexys-A7-100T-Master.xdc"
_LINE = re.compile(r"PACKAGE_PIN\s+(\S+)\s+IOSTANDARD\s+(\S+)\s*\}\s*\[get_ports\s*\{\s*(\S+)\s*\}\]")


def master() -> dict[str, tuple[str, str]]:
    out = {}
    for line in MASTER.read_text().splitlines():
        m = _LINE.search(line)
        if m:
            out[m.group(3)] = (m.group(1), m.group(2))
    return out


def bits(name: str, width: int) -> list[str]:
    """The master-XDC names of a port's bits, bit 0 first."""
    m = master()
    if width == 1:
        if name in m:
            return [name]
        g = re.fullmatch(r"(\w*?[A-Z_])(\d+)", name)
        if g and f"{g.group(1)}[{g.group(2)}]" in m:
            return [f"{g.group(1)}[{g.group(2)}]"]
        raise KeyError(f"no master-XDC pin for port {name}")
    out = [f"{name}[{i}]" for i in range(width)]
    missing = [b for b in out if b not in m]
    if missing:
        raise KeyError(f"no master-XDC pin for {missing}")
    return out


def pins_of(name: str, width: int) -> tuple[list[str], object]:
    m = master()
    bs = bits(name, width)
    pins = [m[b][0] for b in bs]
    stds = [m[b][1] for b in bs]
    if len(set(stds)) == 1:
        return pins, stds[0]
    default = max(set(stds), key=stds.count)
    iost: dict[str, str] = {"default": default}
    for i, s in enumerate(stds):
        if s != default:
            iost[f"{name}[{i}]"] = s
    return pins, iost


def expand(path: Path) -> None:
    """Add ``pins: [...]`` and ``iostandard`` to every one-line flow-mapping port that lacks them."""
    out = []
    in_ports = False
    for line in path.read_text().splitlines():
        if re.match(r"^ports:\s*$", line):
            in_ports = True
        elif re.match(r"^\S", line):
            in_ports = False
        m = re.match(r"^(\s*- \{)(.*)\}(\s*(#.*)?)$", line) if in_ports else None
        if m and "pins:" not in m.group(2):
            d = yaml.safe_load("{" + m.group(2) + "}")
            pins, iost = pins_of(d["name"], int(d.get("width", 1)))
            ist = iost if isinstance(iost, str) else "{" + ", ".join(
                f'{k if k == "default" else chr(34) + k + chr(34)}: {v}' for k, v in iost.items()) + "}"
            line = f"{m.group(1)}{m.group(2)}, pins: [{', '.join(pins)}], iostandard: {ist}}}{m.group(3)}"
        out.append(line)
    path.write_text("\n".join(out) + "\n")


def make_xdc(spec: dict) -> str:
    m = master()
    lines = [f"## design.xdc: {spec['name']} ({spec['top']}) on the Nexys A7-100T. Generated from the reference",
             "## spec by benchmark/tools/board_xdc.py; pins and IOSTANDARDs from Digilent's master XDC (MIT).", ""]
    asyn, outs = [], []
    for p in spec["ports"]:
        w = int(p.get("width", 1))
        for i, b in enumerate(bits(p["name"], w)):
            port = p["name"] if w == 1 else f"{p['name']}[{i}]"
            pin, std = m[b]
            extra = " PULLUP true" if p.get("pullup") else ""
            lines.append(f"set_property -dict {{ PACKAGE_PIN {pin:<5} IOSTANDARD {std}{extra} }} [get_ports {{ {port} }}];")
        if p["dir"] in ("in", "inout") and p.get("async", p["name"] != "CLK100MHZ"):
            asyn.append(p["name"] if w == 1 else f"{p['name']}[*]")
        if p["dir"] in ("out", "inout"):
            outs.append(p["name"] if w == 1 else f"{p['name']}[*]")
    clk = next(c for c in spec["clocks"] if c.get("port") == "CLK100MHZ")
    lines += ["", f"create_clock -add -name sys_clk_pin -period {1000 / clk['freq_mhz']:.2f} -waveform {{0 5}} "
              "[get_ports { CLK100MHZ }];", "",
              "set_property CFGBVS VCCO [current_design];", "set_property CONFIG_VOLTAGE 3.3 [current_design];",
              "set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];", "",
              "## Asynchronous inputs: synchronised in RTL (two ASYNC_REG flops or reset_sync); false-pathed.",
              f"set async_in [get_ports {{{' '.join(asyn)}}}]",
              "set_input_delay -clock sys_clk_pin 0.000 $async_in", "set_false_path -from $async_in", "",
              "## Registered outputs with no timing relationship to an external clock: false-pathed.",
              f"set slow_out [get_ports {{{' '.join(outs)}}}]",
              "set_output_delay -clock sys_clk_pin 0.000 $slow_out", "set_false_path -to $slow_out", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    cmd, spec = sys.argv[1], Path(sys.argv[2])
    if cmd == "expand":
        expand(spec)
    elif cmd == "xdc":
        Path(sys.argv[3]).write_text(make_xdc(yaml.safe_load(spec.read_text())))
    else:
        raise SystemExit(__doc__)
