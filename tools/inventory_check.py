#!/usr/bin/env python3
"""Check a board's inventory.yaml against its master XDC (brief 04c).

    python3 tools/inventory_check.py [boards/nexys_a7_100t]

Fails (exit 1, one line per problem) unless:
  1. every peripheral has every required field, and every sourced field names at least one source
     whose document id is listed under ``documents``;
  2. ``usb_power_safe.verdict`` is one of yes / with conditions / no, with a reason;
  3. every pin in a peripheral's ``pins`` is in the master XDC under the same port name, with the
     same package pin and I/O standard; an empty ``pins`` needs a ``pins_note``; no package pin
     belongs to two ports;
  4. every ``core_io`` entry names a master-XDC section that exists and has ``pin_count`` ports;
  5. every port of the master XDC is covered, by a peripheral's pins or by a core_io section;
  6. every PACKAGE_PIN in designs/*/design.xdc uses the master XDC's I/O standard for that pin.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("id", "part", "function", "interface", "pins", "address_or_id", "reset_enable", "pullups",
            "clocking", "self_check", "current", "usb_power_safe", "sources")
SOURCED = ("part", "function", "interface", "pins", "address_or_id", "reset_enable", "pullups", "clocking",
           "self_check", "current", "usb_power_safe")
VERDICTS = ("yes", "with conditions", "no")
TOP_KEYS = ("schema", "board", "part", "master_xdc", "documents", "digilent_demos", "power", "core_io", "peripherals")
XDC_LINE = re.compile(r"^#?\s*set_property\s+-dict\s*\{\s*PACKAGE_PIN\s+(\w+)\s+IOSTANDARD\s+(\w+)\s*\}"
                      r"\s*\[get_ports\s*\{\s*([^\s}]+)\s*\}\]")


def parse_xdc(text: str) -> tuple[dict[str, tuple[str, str]], dict[str, list[str]]]:
    """Ports {name: (package pin, iostandard)} and sections {"## heading": [ports]} of an XDC."""
    ports: dict[str, tuple[str, str]] = {}
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("##") and not XDC_LINE.match(line.lstrip("#")):
            current = line.lstrip("#").strip()
            continue
        m = XDC_LINE.match(line.strip())
        if m:
            pin, std, port = m.groups()
            ports[port] = (pin, std)
            sections.setdefault(current, []).append(port)
    return ports, sections


def doc_id(source: str) -> str:
    return source.split()[0] if source.split() else ""


def check(board_dir: Path, designs_dir: Path | None = None) -> list[str]:
    problems: list[str] = []
    inv_file = board_dir / "inventory.yaml"
    inv = yaml.safe_load(inv_file.read_text())
    for k in TOP_KEYS:
        if k not in inv:
            problems.append(f"inventory: missing top-level key {k!r}")
    if problems:
        return problems
    ports, sections = parse_xdc((board_dir / inv["master_xdc"]).read_text())
    docs = set(inv["documents"])
    owner_of_pin: dict[str, str] = {}
    covered: set[str] = set()

    for p in inv["peripherals"]:
        pid = p.get("id", "?")
        for f in REQUIRED:
            if f not in p or p[f] in (None, ""):
                problems.append(f"{pid}: missing field {f!r}")
        src = p.get("sources") or {}
        for f in SOURCED:
            refs = src.get(f)
            if not refs:
                problems.append(f"{pid}: field {f!r} has no source")
                continue
            for r in refs:
                if doc_id(str(r)) not in docs:
                    problems.append(f"{pid}: source {r!r} of {f!r} names no document in documents")
        v = p.get("usb_power_safe") or {}
        if v.get("verdict") not in VERDICTS:
            problems.append(f"{pid}: usb_power_safe.verdict {v.get('verdict')!r} is not one of {VERDICTS}")
        if not v.get("reason"):
            problems.append(f"{pid}: usb_power_safe has no reason")
        pins = p.get("pins")
        if pins == {} and not p.get("pins_note"):
            problems.append(f"{pid}: no pins and no pins_note")
        for port, d in (pins or {}).items():
            if port not in ports:
                problems.append(f"{pid}: port {port} is not in {inv['master_xdc']}")
                continue
            covered.add(port)
            xpin, xstd = ports[port]
            if d.get("pin") != xpin:
                problems.append(f"{pid}: {port} pin {d.get('pin')} but the master XDC says {xpin}")
            if d.get("iostandard") != xstd:
                problems.append(f"{pid}: {port} iostandard {d.get('iostandard')} but the master XDC says {xstd}")
            if d.get("dir") not in ("in", "out", "inout"):
                problems.append(f"{pid}: {port} dir {d.get('dir')!r} is not in/out/inout")
            other = owner_of_pin.setdefault(str(d.get("pin")), (pid, port))
            if other != (pid, port):
                problems.append(f"{pid}: pin {d.get('pin')} ({port}) also belongs to {other[0]} ({other[1]})")

    for c in inv["core_io"]:
        sec = c.get("xdc_section")
        if sec not in sections:
            problems.append(f"core_io {c.get('id')}: no XDC section {sec!r}")
            continue
        if len(sections[sec]) != c.get("pin_count"):
            problems.append(f"core_io {c.get('id')}: section {sec!r} has {len(sections[sec])} ports, "
                            f"pin_count says {c.get('pin_count')}")
        covered.update(sections[sec])
        for r in c.get("sources") or []:
            if doc_id(str(r)) not in docs:
                problems.append(f"core_io {c.get('id')}: source {r!r} names no document in documents")
        if not c.get("sources"):
            problems.append(f"core_io {c.get('id')}: no sources")

    for port in sorted(set(ports) - covered):
        problems.append(f"master XDC port {port} ({ports[port][0]}) is in no peripheral and no core_io section")

    if designs_dir is not None:
        by_pin = {pin: (std, port) for port, (pin, std) in ports.items()}
        for xdc in sorted(designs_dir.glob("*/design.xdc")):
            for m in filter(None, (XDC_LINE.match(l.strip()) for l in xdc.read_text().splitlines())):
                pin, std, port = m.groups()
                if pin in by_pin and by_pin[pin][0] != std:
                    problems.append(f"{xdc.relative_to(designs_dir.parent)}: {port} on {pin} uses {std}, "
                                    f"the master XDC {by_pin[pin][0]} ({by_pin[pin][1]})")
                if pin not in by_pin:
                    problems.append(f"{xdc.relative_to(designs_dir.parent)}: {port} on {pin}, a pin the master XDC "
                                    "does not list")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("board_dir", nargs="?", type=Path, default=ROOT / "boards" / "nexys_a7_100t")
    ap.add_argument("--designs", type=Path, default=ROOT / "designs",
                    help="also check every designs/*/design.xdc against the master XDC ('' to skip)")
    a = ap.parse_args(argv)
    designs = a.designs if str(a.designs) not in ("", ".") else None
    problems = check(a.board_dir, designs)
    inv = yaml.safe_load((a.board_dir / "inventory.yaml").read_text())
    n_pins = sum(len(p.get("pins") or {}) for p in inv.get("peripherals", []))
    for line in problems:
        print(f"inventory_check: {line}")
    print(f"inventory_check: {a.board_dir.name}: {len(inv.get('peripherals', []))} peripherals, {n_pins} pins, "
          f"{len(inv.get('core_io', []))} core I/O groups, {len(inv.get('documents', {}))} documents: "
          f"{'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
