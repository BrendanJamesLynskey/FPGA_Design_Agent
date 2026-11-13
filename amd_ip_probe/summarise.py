#!/usr/bin/env python3
"""Render the brief 69 summary table from summary_spec.py and check it against the committed records.

    python3 amd_ip_probe/summarise.py --check     # the cells' needles are in the records; the README table is current
    python3 amd_ip_probe/summarise.py --write     # rewrite the table in results/69_amd_ip_conventions/README.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import summary_spec as S  # noqa: E402

RES = ROOT / "results" / "69_amd_ip_conventions"
BEGIN, END = "<!-- summary:begin -->", "<!-- summary:end -->"
MARK = {"S": "=", "D": "≠", "N": "n/a", "P": "?"}


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def load(ip: str) -> dict:
    return json.loads((RES / f"{ip}.json").read_text())


def probe_text(rec: dict, name: str) -> str | None:
    for p in rec["probes"]:
        if p["probe"] == name:
            return norm(p["text"])
    return None


def problems() -> list[str]:
    out = []
    recs = {}
    for ip in S.IPS:
        f = RES / f"{ip}.json"
        if not f.exists():
            out.append(f"{ip}: record missing")
            continue
        recs[ip] = load(ip)
        r = recs[ip]
        if r.get("errors"):
            out.append(f"{ip}: errors in the record")
        names = [p["probe"] for p in r["probes"]]
        if "done" not in names or "timeout" in names:
            out.append(f"{ip}: the bench did not finish (no `done` line, or a timeout)")
        if r["meta"].get("vivado") != "2026.1":
            out.append(f"{ip}: made with Vivado {r['meta'].get('vivado')}")
    for pk, _t, _h in S.POINTS:
        for ip in S.IPS:
            c = S.C.get((pk, ip))
            if c is None:
                if pk in ("outside", "passerr", "order") and ip not in ("smartconnect", "axi_interconnect"):
                    continue
                if pk == "wide" and ip != "timer":
                    continue
                if ip not in ("smartconnect", "axi_interconnect"):
                    out.append(f"{pk}/{ip}: no cell")
                continue
            status, text, checks = c
            if status not in MARK:
                out.append(f"{pk}/{ip}: bad status {status}")
            if status in ("S", "D") and not checks:
                out.append(f"{pk}/{ip}: a measured cell needs a check")
            for chk in checks:
                probe, needle = chk[0], norm(chk[1])
                want = chk[2] if len(chk) > 2 else True
                t = probe_text(recs[ip], probe) if ip in recs else None
                if t is None:
                    out.append(f"{pk}/{ip}: probe {probe} not in the record")
                elif (needle in t) != want:
                    out.append(f"{pk}/{ip}: {'missing' if want else 'unexpected'} {needle!r} in {probe}")
    return out


def table() -> str:
    head = "| Point | House convention | " + " | ".join(S.TITLES[i] for i in S.IPS) + " |"
    sep = "|---|---|" + "---|" * len(S.IPS)
    rows = [head, sep]
    for pk, title, house in S.POINTS:
        cells = []
        for ip in S.IPS:
            c = S.C.get((pk, ip))
            if c is None:
                cells.append("n/a")
            else:
                st, text, _ = c
                cells.append(f"{MARK[st]} {text}" if st != "N" or pk in ("latency", "hole_read", "hole_write", "alias") else f"n/a {text}")
        rows.append(f"| {title} | {house} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def block() -> str:
    return f"{BEGIN}\n{table()}\n{END}"


def readme_ok() -> bool:
    t = (RES / "README.md").read_text()
    m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), t, re.S)
    return bool(m) and m.group(0) == block()


def main() -> int:
    if "--write" in sys.argv:
        f = RES / "README.md"
        t = f.read_text()
        t = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda m: block(), t, flags=re.S)
        f.write_text(t)
        return 0
    p = problems()
    if not readme_ok():
        p.append("README table is not current: run summarise.py --write")
    for x in p:
        print("PROBLEM", x)
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main())
