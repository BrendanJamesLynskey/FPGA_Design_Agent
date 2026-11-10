#!/usr/bin/env python3
"""Cross-probe summary and device-map SVG from build/<variant>/xprobe.json (brief 18, section 3).

    python3 flow/xprobe.py designs/<name>/build/base/xprobe.json --svg xprobe.svg [--summary]

``xprobe.json`` is written by flow/xprobe.tcl (set FDA_XPROBE=1 for flow/run_vivado.sh, or run flow/xprobe_run.tcl on a
post_route.dcp). Project mode shows this by clicking from the timing report into the RTL and the device view; here it is data:

* :func:`summary`: the worst setup and hold path per clock group with the RTL module, file and line and the clock region of
  its start and end, and the high-fanout nets with their driver. flow/gates.py adds it to gates.json as ``xprobe`` (evidence
  for the QoR gate and for the repair prompt; no gate reads it).
* :func:`render_svg`: the device map: clock regions, every placed slice cell coloured by RTL module, the worst paths drawn.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

PALETTE = ["#4d6a8a", "#a3622b", "#5b8a5b", "#8a4f7a", "#9a8a2b", "#3f8a8a", "#8a5252", "#6b6b6b", "#2b6b9a", "#7a8a3f"]


def _where(c: dict | None) -> str:
    if not c:
        return "unknown"
    f = c.get("file")
    src = f"{Path(f).name}:{c['line']}" if f and c.get("line") is not None else "no RTL location"
    return f"{c.get('module') or '?'} {src} ({c.get('clock_region') or 'no region'}, {c.get('loc') or 'unplaced'})"


def summary(x: dict, per_group: int = 1) -> dict:
    """Worst path per (kind, clock group) with RTL and placement locations, plus the high-fanout nets."""
    out: list[dict] = []
    seen: dict[tuple[str, str], int] = {}
    for p in x["paths"]:
        k = (p["kind"], p["group"])
        if seen.get(k, 0) >= per_group:
            continue
        seen[k] = seen.get(k, 0) + 1
        s, e = p["start"], p["end"]
        regions = [c.get("clock_region") for c in p["cells"] if c.get("clock_region")]
        crosses = list(dict.fromkeys(regions))
        out.append({
            "kind": p["kind"], "group": p["group"], "slack_ns": p["slack"], "logic_levels": p.get("logic_levels"),
            "net_delay_ns": p.get("net_delay"), "logic_delay_ns": p.get("logic_delay"),
            "from": {"module": s["module"], "file": s.get("file"), "line": s.get("line"), "clock_region": s.get("clock_region"), "loc": s.get("loc")},
            "to": {"module": e["module"], "file": e.get("file"), "line": e.get("line"), "clock_region": e.get("clock_region"), "loc": e.get("loc")},
            "regions_crossed": crosses,
            "text": f"{p['kind']} slack {p['slack']} ns ({p['group']}): {_where(s)} -> {_where(e)}"
                    + (f"; path regions {' -> '.join(crosses)}" if len(crosses) > 1 else ""),
        })
    hf = [{"net": n["net"], "fanout": n["fanout"], "driver_module": (n.get("driver") or {}).get("module"),
           "driver_file": (n.get("driver") or {}).get("file"), "driver_line": (n.get("driver") or {}).get("line"),
           "load_regions": n.get("load_regions", {})} for n in x["high_fanout_nets"][:5]]
    return {"part": x["part"], "wns_ns": x["wns"], "whs_ns": x["whs"], "paths": out, "high_fanout_nets": hf}


def render_svg(x: dict, px: int = 7) -> str:
    regs = x["clock_regions"]
    xmax = max(r["x1"] for r in regs) + 1
    ymax = max(r["y1"] for r in regs) + 1
    sx, sy = px, px / 2
    w, h = xmax * sx + 220, ymax * sy + 40
    ox, oy = 10, 20
    X = lambda v: ox + v * sx
    Y = lambda v: oy + (ymax - v) * sy
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" font-family="sans-serif" font-size="9">',
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<text x="{ox}" y="12" font-size="10" fill="#222">{escape(x["part"])}: slice map by RTL module (WNS {x["wns"]} ns, WHS {x["whs"]} ns)</text>']
    for r in regs:
        o.append(f'<rect x="{X(r["x0"]):.1f}" y="{Y(r["y1"] + 1):.1f}" width="{(r["x1"] - r["x0"] + 1) * sx:.1f}" height="{(r["y1"] - r["y0"] + 1) * sy:.1f}" fill="none" stroke="#999" stroke-width="0.8"/>')
        o.append(f'<text x="{X(r["x0"]) + 3:.1f}" y="{Y(r["y1"] + 1) + 10:.1f}" fill="#888">{r["name"]}</text>')
    for m, cx, cy in x["slice_cells"]:
        o.append(f'<rect x="{X(cx):.1f}" y="{Y(cy + 1):.1f}" width="{sx - 1:.1f}" height="{max(sy - 0.5, 1):.1f}" fill="{PALETTE[m % len(PALETTE)]}" fill-opacity="0.75"/>')
    seen: set[tuple] = set()
    for p in x["paths"][: len(x["paths"])]:
        pts = []
        for c in p["cells"]:
            m = re.match(r"SLICE_X(\d+)Y(\d+)", c.get("loc") or "")
            if m:
                pts.append((int(m[1]), int(m[2])))
        key = tuple(pts)
        if len(pts) < 2 or key in seen:
            continue
        seen.add(key)
        if len(seen) > 4:
            break
        d = " ".join(f"{X(a) + sx / 2:.1f},{Y(b) - sy / 2 + sy:.1f}" for a, b in pts)
        dash = ' stroke-dasharray="3 2"' if p["kind"] == "hold" else ""
        col = "#b00020" if p["kind"] == "setup" else "#1a5fb4"
        o.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="1.6"{dash}><title>{escape(p["kind"])} {p["slack"]} ns</title></polyline>')
        a, b = pts[0], pts[-1]
        o.append(f'<circle cx="{X(a[0]) + sx / 2:.1f}" cy="{Y(a[1]) - sy / 2 + sy:.1f}" r="3" fill="{col}"/>')
        o.append(f'<circle cx="{X(b[0]) + sx / 2:.1f}" cy="{Y(b[1]) - sy / 2 + sy:.1f}" r="3" fill="none" stroke="{col}" stroke-width="1.4"/>')
    lx = xmax * sx + 25
    o.append(f'<text x="{lx}" y="{oy + 8}" font-weight="bold" fill="#222">RTL module (top level)</text>')
    for i, m in enumerate(x["modules"]):
        yy = oy + 20 + i * 14
        o.append(f'<rect x="{lx}" y="{yy - 8}" width="10" height="10" fill="{PALETTE[i % len(PALETTE)]}" fill-opacity="0.75"/><text x="{lx + 15}" y="{yy}" fill="#222">{escape(m)}</text>')
    yy = oy + 40 + len(x["modules"]) * 14
    o.append(f'<line x1="{lx}" y1="{yy}" x2="{lx + 22}" y2="{yy}" stroke="#b00020" stroke-width="1.6"/><text x="{lx + 28}" y="{yy + 3}" fill="#222">worst setup paths</text>')
    o.append(f'<line x1="{lx}" y1="{yy + 14}" x2="{lx + 22}" y2="{yy + 14}" stroke="#1a5fb4" stroke-width="1.6" stroke-dasharray="3 2"/><text x="{lx + 28}" y="{yy + 17}" fill="#222">worst hold paths</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("json")
    ap.add_argument("--svg")
    ap.add_argument("--summary", action="store_true", help="print the summary as text")
    a = ap.parse_args(argv)
    x = json.loads(Path(a.json).read_text())
    if a.svg:
        Path(a.svg).write_text(render_svg(x))
    if a.summary or not a.svg:
        s = summary(x)
        print(f"{s['part']}: WNS {s['wns_ns']} ns, WHS {s['whs_ns']} ns")
        for p in s["paths"]:
            print(" ", p["text"])
        for n in s["high_fanout_nets"]:
            print(f"  fanout {n['fanout']}: {n['net']} driven in {n['driver_module']} {Path(n['driver_file'] or '').name}:{n['driver_line']}; loads {n['load_regions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
