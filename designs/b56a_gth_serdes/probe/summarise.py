#!/usr/bin/env python3
"""summarise.py <probe dir> : the RESULT lines of the probe logs (build/probe/<name>.log) as a markdown table and a JSON file.

    python3 designs/b56a_gth_serdes/probe/summarise.py designs/b56a_gth_serdes/build/probe results/56a_serdes/probe

Writes <out>/probe_results.json (stage, status, seconds, the exact error text up to 600 characters, peak RSS) and prints the table.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STAGES = ("create", "generate", "synth_ip", "top", "impl", "bit")


def parse(d: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for log in sorted(d.glob("*.log")):
        name = log.stem
        rec = {"stages": {}, "tier": None, "version": None, "peak_rss_mib": None}
        for line in log.read_text(errors="replace").splitlines():
            m = re.match(r"PROBE (\S+) VERSION (\S+) TIER (\S+)", line)
            if m:
                rec["version"], rec["tier"] = m.group(2), m.group(3)
            m = re.match(r"RESULT (\S+) (\S+) (OK|FAIL|STOPPED)\s*(.*)$", line)
            if m:
                rec["stages"][m.group(2)] = {"status": m.group(3), "detail": m.group(4).strip()}
        t = log.with_suffix(".time")
        if t.exists():
            mm = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t.read_text(errors="replace"))
            if mm:
                rec["peak_rss_mib"] = round(int(mm.group(1)) / 1024)
        out[name] = rec
    return out


def table(res: dict[str, dict]) -> str:
    rows = ["| IP | " + " | ".join(STAGES) + " | peak RSS MiB |", "|---|" + "---|" * (len(STAGES) + 1)]
    for n, r in res.items():
        cells = []
        for s in STAGES:
            st = r["stages"].get(s)
            cells.append("-" if st is None else ("OK" if st["status"] == "OK" else st["status"]))
        rows.append(f"| `{n}` | " + " | ".join(cells) + f" | {r['peak_rss_mib']} |")
    return "\n".join(rows)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    res = parse(src)
    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
        out.mkdir(parents=True, exist_ok=True)
        (out / "probe_results.json").write_text(json.dumps(res, indent=1) + "\n")
    print(table(res))
    for n, r in res.items():
        for s, st in r["stages"].items():
            if st["status"] != "OK":
                print(f"\n{n} {s} {st['status']}: {st['detail']}")
