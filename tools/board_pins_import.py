#!/usr/bin/env python3
"""Write a board's own master XDC from a vendor's documented pin list (brief 95).

    python3 tools/board_pins_import.py boards/<board>/pins_import.yaml [--source-dir DIR] [--check]

A pin assignment is a fact about a board, so a board whose vendor file has no licence we can copy (or whose pins come
from a board file or a reference design) gets our own XDC, written in one format the agent's tools parse
(``set_property -dict { PACKAGE_PIN <pin> IOSTANDARD <std> } [get_ports { <port> }];``). The spec names every source file by
URL (pinned to a commit) and SHA-256, the renames that turn the vendor's names into ``led[0]``, ``sw[3]`` and so on, and
the I/O standard rules. The source files themselves are not committed; ``--source-dir`` reads local copies (files named by the source id) instead of
fetching, and ``--check`` fails if the committed XDC differs from what the spec produces.

Spec fields::

    board: <id>
    out: <path of the XDC, relative to the repo root>
    title: <one line for the header>
    sources: [{id, url, sha256, format: xdc | board-store-xml, licence: <one line>, use: <what it supplies>}]
    include: [<regex on the source name>, ...]   # optional; default every pin
    exclude: [<regex>, ...]                      # optional
    rename: [[<regex>, <replacement>], ...]      # first match wins; applied to the source name
    iostandard: {default: <std>, by_name: [[<regex>, <std>]], by_bank: {<bank>: <std>}, bank_file: <json pin->bank>,
                 std_from_pin: true (a pin named by two sources takes the standard from the one that has it),
                 only: [<std>] (leave out pins whose standard is another), only_reason: <text>}
    section_by: [[<regex on the new name>, <section heading>]]    # optional ordering and headings
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

_DICT = re.compile(r"^#*\s*set_property\s+-dict\s*\{\s*PACKAGE_PIN\s+(\w+)\s+IOSTANDARD\s+(\w+)[^}]*\}\s*"
                   r"\[get_ports\s*\{?\s*((?:[^\s{}\[\]]|\[\d+\])+)\s*\}?\s*\]")
_PIN = re.compile(r"^#*\s*set_property\s+PACKAGE_PIN\s+(\w+)\s+\[get_ports\s*\{?\s*((?:[^\s{}\[\]]|\[\d+\])+)\s*\}?\s*\]")
_STD = re.compile(r"^#*\s*set_property\s+IOSTANDARD\s+(\w+)\s+\[get_ports\s*\{?\s*((?:[^\s{}\[\]]|\[\d+\])+)\s*\}?\s*\]")
_XML = re.compile(r'<pin\s+index\s*="\d+"\s+name\s*="([^"]+)"([^>]*?)loc\s*="([^"]+)"')
_XML_STD = re.compile(r'iostandard\s*="([^"]+)"')


def parse_xdc(text: str) -> list[tuple[str, str, str | None]]:
    """(port, pin, iostandard or None) in file order; commented-out pin lines count (vendor masters comment them)."""
    pins: dict[str, str] = {}
    stds: dict[str, str] = {}
    order: list[str] = []
    for line in text.splitlines():
        m = _DICT.match(line.strip())
        if m:
            pins[m.group(3)], stds[m.group(3)] = m.group(1), m.group(2)
            order.append(m.group(3))
            continue
        m = _PIN.match(line.strip())
        if m:
            pins[m.group(2)] = m.group(1)
            order.append(m.group(2))
            continue
        m = _STD.match(line.strip())
        if m:
            stds[m.group(2)] = m.group(1)
    seen: list[str] = []
    for p in order:
        if p not in seen:
            seen.append(p)
    return [(p, pins[p], stds.get(p)) for p in seen]


def parse_board_store_xml(text: str) -> list[tuple[str, str, str | None]]:
    out = []
    for name, middle, loc in _XML.findall(text):
        s = _XML_STD.search(middle)
        out.append((name.strip(), loc, s.group(1) if s else None))
    return out


def fetch(src: dict[str, Any], source_dir: Path | None) -> str:
    if source_dir and (source_dir / src["id"]).is_file():          # a local copy named by the source id
        data = (source_dir / src["id"]).read_bytes()
    else:
        data = urllib.request.urlopen(src["url"], timeout=60).read()
    got = hashlib.sha256(data).hexdigest()
    if got != src["sha256"]:
        raise SystemExit(f"{src['id']}: sha256 {got} differs from the spec's {src['sha256']}")
    return data.decode("utf8", "replace")


def build(spec: dict[str, Any], source_dir: Path | None = None) -> str:
    entries: list[tuple[str, str, str | None, str]] = []
    for src in spec["sources"]:
        text = fetch(src, source_dir)
        rows = parse_xdc(text) if src["format"] == "xdc" else parse_board_store_xml(text)
        entries += [(n, p, s, src["id"]) for n, p, s in rows]
    inc = [re.compile(x) for x in spec.get("include", [])]
    exc = [re.compile(x) for x in spec.get("exclude", [])]
    ren = [(re.compile(a), b) for a, b in spec.get("rename", [])]
    rules = spec.get("iostandard", {})
    if rules.get("std_from_pin"):          # a pin listed by two sources: the one with a standard gives it to the other; the first name stays
        std_of = {pin: std for _n, pin, std, _s in entries if std}
        merged: dict[str, tuple[str, str, str | None, str]] = {}
        for n, pin, std, sid in entries:
            if pin not in merged:
                merged[pin] = (n, pin, std or std_of.get(pin), sid)
        entries = list(merged.values())
    only = set(rules.get("only", []))
    banks = json.loads((ROOT / rules["bank_file"]).read_text()) if rules.get("bank_file") else {}
    by_name = [(re.compile(a), b) for a, b in rules.get("by_name", [])]
    sections = [(re.compile(a), b) for a, b in spec.get("section_by", [])]
    out: dict[str, tuple[str, str, str, str]] = {}
    skipped: list[str] = []
    for name, pin, std, sid in entries:
        if inc and not any(r.search(name) for r in inc):
            continue
        if any(r.search(name) for r in exc):
            continue
        new = next((r.sub(b, name) for r, b in ren if r.search(name)), name)
        iost = next((b for r, b in by_name if r.search(new)), None) or std
        if iost is None and str(banks.get(pin)) in {str(k) for k in rules.get("by_bank", {})}:
            iost = {str(k): v for k, v in rules["by_bank"].items()}[str(banks[pin])]
        iost = iost or rules.get("default")
        if iost is not None and only and iost not in only:     # a standard the spec does not trust for this board: leave the pin out
            skipped.append(f"{new} on {pin} ({sid}; the source says {iost}, which this board's spec does not accept: {rules.get('only_reason', 'see the spec')})")
            continue
        if iost is None:                                       # never invent a standard: list the pin, leave it out
            skipped.append(f"{new} on {pin} ({sid})")
            continue
        if new in out and out[new][0] != pin:
            raise SystemExit(f"{new}: two pins ({out[new][0]}, {pin})")
        out[new] = (pin, iost, sid, name)
    head = [f"## {spec['title']}",
            f"## Written by tools/board_pins_import.py from boards/{spec['board']}/pins_import.yaml. Pin locations are facts about the board;",
            "## this file is our own listing of them in one format, not a copy of a vendor file. Sources:"]
    for src in spec["sources"]:
        head.append(f"##   {src['id']}: {src['url']} (sha256 {src['sha256'][:12]}...; {src['licence']}); supplies {src['use']}")
    head += ["## Every port is commented out in the vendor style: the agent's board_constraints tool writes the lines a design uses."]
    if skipped:
        head += ["## Left out because no source gives its I/O standard (a standard is never invented): " + "; ".join(skipped)]
    head += [""]
    body: list[str] = []
    last = None
    ordered = list(out.items())
    if sections:
        def key(item):
            for i, (r, _h) in enumerate(sections):
                if r.search(item[0]):
                    return i
            return len(sections)
        ordered.sort(key=key)
    for port, (pin, iost, sid, orig) in ordered:
        if sections:
            h = next((hh for r, hh in sections if r.search(port)), "Other")
            if h != last:
                body += ["", f"## {h}"]
                last = h
        body.append(f"#set_property -dict {{ PACKAGE_PIN {pin:<5} IOSTANDARD {iost:<10} }} [get_ports {{ {port} }}]; # {sid}: {orig}")
    return "\n".join(head + body) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--source-dir", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    spec = yaml.safe_load(a.spec.read_text())
    text = build(spec, a.source_dir)
    out = ROOT / spec["out"]
    if a.check:
        if not out.is_file() or out.read_text() != text:
            print(f"{spec['out']} differs from what {a.spec} produces", file=sys.stderr)
            return 1
        return 0
    out.write_text(text)
    print(f"wrote {spec['out']}: {text.count('#set_property')} ports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
