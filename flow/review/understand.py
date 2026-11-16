"""The understanding part of a review, made by code from the sources (brief 84).

What the design is made of: modules and their ports and parameters, who instantiates whom, the clocks and resets as the
code uses them, the files grouped (RTL, tests, constraints, docs). The reviewer's reading adds what the design is for and
how it works; the facts here are what it is checked against. The hierarchy is read from the source text, not from an
elaborated netlist (a known gap: generate blocks that instantiate under conditions are all listed).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from flow.review.prepare import modules, strip_comments

_PORT = re.compile(r"\b(input|output|inout)\s+(?:(?:wire|reg|logic|var|signed|unsigned)\s+)*(\[[^\]]+\])?\s*(?:(?:wire|reg|logic)\s+)?(\w+)")
_PARAM = re.compile(r"\b(?:parameter|localparam)\s+(?:(?:int|integer|logic|bit|signed|unsigned)\s+)*(?:\[[^\]]+\]\s*)?(\w+)\s*=\s*([^,;)]+)")
_EDGE = re.compile(r"@\s*\(\s*((?:posedge|negedge)\s+\w+(?:\s*(?:or|,)\s*(?:posedge|negedge)\s+\w+)*)\s*\)")
_RST = re.compile(r"\b(\w*(?:rst|reset|nreset|resetn|aresetn|rstn)\w*)\b", re.I)


def header_ports(body: str) -> list[dict[str, str]]:
    head = body.split(");", 1)[0] if ");" in body else body[:2000]
    ports, last = [], ""
    for m in _PORT.finditer(head):
        ports.append({"dir": m.group(1), "width": (m.group(2) or "").strip(), "name": m.group(3)})
    return ports


def analyse(src: Path, rtl: list[str], top: str | None, tb: list[str], constraints: list[str], docs: list[str]) -> dict[str, Any]:
    files = [src / r for r in rtl]
    mods = modules(files)
    out_mods = []
    clocks: dict[str, set[str]] = {}
    for n, m in sorted(mods.items()):
        body = m["body"]
        ports = header_ports(body)
        edges = []
        for e in _EDGE.finditer(body):
            edges += re.findall(r"(posedge|negedge)\s+(\w+)", e.group(1))
        clk = sorted({s for k, s in edges if not _RST.fullmatch(s)})
        arst = sorted({f"{k} {s}" for k, s in edges if _RST.fullmatch(s)})
        clocks[n] = set(clk)
        out_mods.append({"name": n, "file": m["file"].relative_to(src).as_posix(), "line": m["line"],
                         "params": {k: v.strip() for k, v in _PARAM.findall(body.split(");", 1)[0] if ");" in body else body[:2000])},
                         "ports": ports, "clocks": clk, "async_reset_edges": arst,
                         "instances": [{"module": c, "name": i} for c, i in m["instances"]],
                         "loc": body.count("\n") + 1})
    order = [m["name"] for m in out_mods]
    topn = top if top in mods else (order[0] if order else None)
    return {"top": topn, "modules": out_mods, "rtl_files": rtl, "test_files": tb, "constraint_files": constraints, "doc_files": docs,
            "clock_domains": sorted({c for s in clocks.values() for c in s})}


def svg_block_diagram(u: dict[str, Any]) -> str:
    """The top module as a box, its inputs on the left and outputs on the right, and the sub-modules it instantiates
    listed inside (made from the source hierarchy)."""
    mods = {m["name"]: m for m in u["modules"]}
    t = mods.get(u["top"])
    if not t:
        return ""
    ins = [p for p in t["ports"] if p["dir"] != "output"]
    outs = [p for p in t["ports"] if p["dir"] == "output"]
    kids = t["instances"]
    rows = max(len(ins), len(outs), len(kids) + 1, 3)
    h = 40 + rows * 20
    w = 620
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="monospace" font-size="11">',
         f'<rect x="150" y="10" width="320" height="{h - 20}" fill="none" stroke="#222" stroke-width="1.5"/>',
         f'<text x="310" y="26" text-anchor="middle" font-weight="bold">{esc(t["name"])}</text>']
    for i, p in enumerate(ins):
        y = 46 + i * 20
        o.append(f'<line x1="110" y1="{y - 4}" x2="150" y2="{y - 4}" stroke="#222"/><text x="106" y="{y}" text-anchor="end">{esc(p["name"])}{esc(p["width"])}</text>')
    for i, p in enumerate(outs):
        y = 46 + i * 20
        o.append(f'<line x1="470" y1="{y - 4}" x2="510" y2="{y - 4}" stroke="#222"/><text x="514" y="{y}">{esc(p["name"])}{esc(p["width"])}</text>')
    for i, k in enumerate(kids):
        y = 46 + i * 20
        o.append(f'<rect x="200" y="{y - 13}" width="220" height="17" fill="none" stroke="#666"/><text x="310" y="{y}" text-anchor="middle">{esc(k["name"])} : {esc(k["module"])}</text>')
    o.append("</svg>")
    return "\n".join(o)


def hierarchy_text(u: dict[str, Any]) -> str:
    mods = {m["name"]: m for m in u["modules"]}
    lines: list[str] = []
    def walk(n: str, ind: int, inst: str, seen: tuple):
        m = mods.get(n)
        if not m:
            return
        lines.append("  " * ind + f"{inst + ' : ' if inst else ''}{n} ({m['file']}:{m['line']}, {m['loc']} lines; clocks {', '.join(m['clocks']) or 'none'})")
        for c in m["instances"]:
            if c["module"] not in seen:
                walk(c["module"], ind + 1, c["name"], seen + (n,))
    if u["top"]:
        walk(u["top"], 0, "", ())
    return "\n".join(lines)
