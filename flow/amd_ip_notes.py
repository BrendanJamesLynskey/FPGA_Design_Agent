#!/usr/bin/env python3
"""Which AMD AXI4-Lite IP a design instantiates, and what to watch for next to our generated register blocks (brief 69).

    python3 flow/amd_ip_notes.py designs/<d> [more paths]     # scan *.tcl, *.xdc, *.v, *.sv, *.vhd, *.yaml, *.md
    python3 flow/amd_ip_notes.py --all                         # every IP the measurements cover, with its notes

The notes are the differences from our house register conventions (docs/hwsw.md) that bite when an AMD block and a block
made by `hwsw/regmap.py` share a bus or a driver. They come from `amd_ip_probe/summary_spec.py`, whose every claim is
checked against the committed records in `results/69_amd_ip_conventions/` by `amd_ip_probe/tests/test_records.py`. They
were measured in behavioural simulation of one configuration of each IP (Vivado 2026.1): a different configuration can
differ, and the notes say so rather than hide it. Use the note as a prompt to check the product guide and the record,
not as a rule that holds for every family or generic.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "amd_ip_probe"))
import summary_spec as S  # noqa: E402

RECORDS = "results/69_amd_ip_conventions"
VLNV = re.compile(r"xilinx\.com:ip:(\w+):", re.I)
CREATE = re.compile(r"create_ip\b[^\n]*?-name\s+(\w+)\b[^\n]*?-vendor\s+xilinx\.com", re.I)
CREATE2 = re.compile(r"create_ip\b[^\n]*?-vendor\s+xilinx\.com[^\n]*?-name\s+(\w+)\b", re.I)
SUFFIX = {".tcl", ".xdc", ".v", ".sv", ".vhd", ".yaml", ".yml", ".md", ".json"}
# the generated block's own conventions (docs/hwsw.md), to set beside the AMD notes
HOUSE = [
    "our generated register blocks answer SLVERR to a read of a hole and OKAY to a write (`unmapped: split`); the AMD peripherals below answer OKAY, 0 to both",
    "ours honour byte strobes; the AMD peripherals ignore them: write whole words",
    "ours accept AW and W independently; the AMD peripherals wait for both",
    "ours have no read side effects; an AMD FIFO or status word may",
]
KNOWN = {S.IP_NAME[ip]: ip for ip in S.IPS}


def ips_in(text: str) -> set[str]:
    """The AMD IP catalogue names in a piece of text (a Tcl script, a block design, a YAML file) that the notes cover."""
    names = set(VLNV.findall(text)) | set(CREATE.findall(text)) | set(CREATE2.findall(text))
    return {n.lower() for n in names} & set(KNOWN)


def notes_for(names) -> dict[str, dict]:
    out = {}
    for n in sorted(names):
        ip = KNOWN[n]
        out[n] = {"ip": S.TITLES[ip], "record": f"{RECORDS}/{ip}.json", "guide": S.GUIDES[ip], "notes": list(S.NOTES[n])}
    return out


def scan(paths) -> dict:
    found: dict[str, list[str]] = {}
    for p in paths:
        p = Path(p)
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUFFIX
                                              and "build" not in f.parts and f.stat().st_size < 2_000_000)
        for f in files:
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for n in ips_in(text):
                found.setdefault(n, []).append(str(f))
    rep = notes_for(found)
    for n, fs in found.items():
        rep[n]["files"] = fs[:5]
    return {"ips": rep, "house": HOUSE if rep else [], "mixes_generated_blocks": _has_generated(paths)}


def _has_generated(paths) -> bool:
    for p in paths:
        p = Path(p)
        if p.is_dir() and any(p.rglob("*_regs.sv")):
            return True
    return False


def render(rep: dict) -> str:
    if not rep["ips"]:
        return "no AMD IP covered by brief 69 found"
    lines = []
    for n, d in rep["ips"].items():
        lines.append(f"{d['ip']} ({n}); record {d['record']}")
        lines += [f"  - {x}" for x in d["notes"]]
    if rep["mixes_generated_blocks"]:
        lines.append("this design also has generated register blocks (*_regs.sv); against ours:")
        lines += [f"  - {x}" for x in rep["house"]]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--all":
        rep = {"ips": notes_for(KNOWN), "house": HOUSE, "mixes_generated_blocks": True}
    elif argv:
        rep = scan(argv)
    else:
        print(__doc__)
        return 2
    print(json.dumps(rep, indent=1) if "--json" in argv else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if a != "--json"] + (["--json"] if "--json" in sys.argv else [])))
