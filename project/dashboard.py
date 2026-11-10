"""The project dashboard: one self-contained static HTML page written from :func:`project.status.project_status`.

No server, no scripts, no external assets: it opens from the file system. It reuses the review pages' monochrome style
(``agent/graph/review.py`` ``CSS``, light and dark by ``prefers-color-scheme``). It shows the module graph as an SVG
(each box's outline says its state: solid when every stage so far passes, dashed when evidence is stale, filled when a
stage fails), a module-by-stage table, the evidence items with their keys, the open assumptions and the checker's
problems. Hand-written evidence is labelled on the page.

    python -m project status <dir> --html <out.html>
"""

from __future__ import annotations

import html
from typing import Any

from agent.graph.review import CSS

EXTRA_CSS = """
.banner{border:2px solid var(--fg);padding:8px 10px;margin:10px 0}
svg .box{fill:var(--bg);stroke:var(--fg);stroke-width:1.2}svg .box.pass{stroke-width:2.4}
svg .box.stale{stroke-dasharray:6 4;stroke-width:1.8}svg .box.fail{fill:var(--fg)}svg .box.none{stroke:var(--mut)}
svg text.inv{fill:var(--bg)}svg .edge{stroke:var(--fg);fill:none;stroke-width:1.4}svg .edge.x{stroke-dasharray:4 3}
svg .aux{stroke:var(--mut);fill:none;stroke-width:1;stroke-dasharray:2 3}svg text.m{fill:var(--mut)}
td.st{text-align:center;font:12px ui-monospace,Menlo,Consolas,monospace;white-space:nowrap}
td.st.stale{border-style:dashed}td.st.fail{background:var(--fg);color:var(--bg)}td.st.pass{font-weight:bold}
code{font:12px ui-monospace,Menlo,Consolas,monospace}
"""
LABEL = {"none": "-", "stale": "stale", "fail": "FAIL", "not-run": "not run", "pass": "pass"}


def _e(x: Any) -> str:
    return html.escape(str(x))


def _box_state(m: dict[str, Any]) -> str:
    states = [s["state"] for s in m["stages"]]
    if "fail" in states:
        return "fail"
    if "stale" in states:
        return "stale"
    return "pass" if m["reached"] >= 0 else "none"


def _columns(st: dict[str, Any]) -> list[list[str]]:
    """Modules in columns by their depth along the connections (sources left)."""
    names = [m["module"] for m in st["modules"]]
    depth = {n: 0 for n in names}
    for _ in range(len(names)):
        for x in st["connections"]:
            a, b = str(x.get("from", "")).split(".")[0], str(x.get("to", "")).split(".")[0]
            if a in depth and b in depth and depth[b] < depth[a] + 1 <= len(names):
                depth[b] = depth[a] + 1
    cols: list[list[str]] = [[] for _ in range(max(depth.values(), default=0) + 1)]
    for n in names:
        cols[depth[n]].append(n)
    return cols


def graph_svg(st: dict[str, Any]) -> str:
    mods = {m["module"]: m for m in st["modules"]}
    cols = _columns(st)
    bw, bh, gx, gy, x0, y0 = 250, 96, 150, 34, 10, 30
    pos: dict[str, tuple[int, int]] = {}
    for ci, col in enumerate(cols):
        for ri, n in enumerate(col):
            pos[n] = (x0 + ci * (bw + gx), y0 + ri * (bh + gy))
    rows = max((len(c) for c in cols), default=1)
    width = x0 * 2 + len(cols) * bw + (len(cols) - 1) * gx
    height = y0 + rows * (bh + gy) + 10
    out = [f'<svg viewBox="0 0 {width} {height}" style="max-width:{width}px" role="img" aria-label="module graph" xmlns="http://www.w3.org/2000/svg">',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--fg)"/></marker></defs>']
    for x in st["connections"]:
        a, b = str(x.get("from", "")).split(".")[0], str(x.get("to", "")).split(".")[0]
        if a not in pos or b not in pos:
            continue
        (ax, ay), (bx, by) = pos[a], pos[b]
        sx, sy, ex, ey = ax + bw, ay + bh // 2, bx, by + bh // 2
        cls = "edge x" if x.get("crossing") else "edge"
        out.append(f'<path class="{cls}" d="M{sx},{sy} C{sx + 40},{sy} {ex - 40},{ey} {ex},{ey}" marker-end="url(#arr)"/>')
        lab = str(x.get("from", "")).split(".")[1] + " → " + str(x.get("to", "")).split(".")[1]
        out.append(f'<text x="{(sx + ex) // 2}" y="{min(sy, ey) - 22}" text-anchor="middle">{_e(lab.split(" → ")[0])} →</text>')
        out.append(f'<text x="{(sx + ex) // 2}" y="{min(sy, ey) - 8}" text-anchor="middle">→ {_e(lab.split(" → ")[1])}</text>')
        if x.get("crossing"):
            out.append(f'<text class="m" x="{(sx + ex) // 2}" y="{min(sy, ey) + 16}" text-anchor="middle">'
                       f'{_e(x["crossing"].get("primitive"))}</text>')
    for n, (x, y) in pos.items():
        m = mods[n]
        state = _box_state(m)
        inv = ' class="inv"' if state == "fail" else ""
        dom = ", ".join(sorted(set((st["domains"].get(n) or {}).get("clocks", {}).values())))
        reached = f"reached {m['reached']}" if m["reached"] >= 0 else "no stage passed"
        stage = m["reached_stage"] or ""
        reent = "" if m["reentry"] is None else f"re-enter at {m['reentry']}"
        out.append(f'<rect class="box {state}" x="{x}" y="{y}" width="{bw}" height="{bh}" rx="3"/>')
        out.append(f'<text{inv} x="{x + 8}" y="{y + 18}" style="font-weight:bold">{_e(n)}</text>')
        out.append(f'<text{inv} x="{x + 8}" y="{y + 34}">{_e(m["kind"])} · {_e(dom)}</text>')
        out.append(f'<text{inv} x="{x + 8}" y="{y + 50}">{_e(reached)}</text>')
        out.append(f'<text{inv} x="{x + 8}" y="{y + 66}">{_e(stage)}</text>')
        out.append(f'<text{inv} x="{x + 8}" y="{y + 84}">{_e(reent)}</text>')
    out.append("</svg>")
    return "".join(out)


def page(st: dict[str, Any]) -> str:
    title = f"Project {st['project']}"
    parts = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
             f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
             f"<style>{CSS}{EXTRA_CSS}</style></head><body><main>",
             f"<h1>{_e(title)}</h1>",
             f'<p class="mut">board {_e(st["board"])} · checker: {"valid" if st["valid"] else "INVALID"} · '
             f'{len(st["modules"])} modules · {len(st["assumptions_open"])} open assumptions</p>']
    if st["hand_written"]:
        parts.append('<div class="banner"><b>Hand-written evidence.</b> The evidence of '
                     f'{_e(", ".join(st["hand_written"]))} was written by hand to exercise this page (brief 27 P0). '
                     "Nothing on it was measured, and nobody has approved these modules yet.</div>")
    if st["errors"]:
        parts.append("<h2>Problems</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in st["errors"]) + "</ul>")
    if st["warnings"]:
        parts.append("<h2>Warnings</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in st["warnings"]) + "</ul>")
    parts.append("<h2>Module graph</h2>" + f'<div class="wrap">{graph_svg(st)}</div>'
                 + '<p class="mut">Box outline: solid when every stage so far passes, dashed when evidence is stale, '
                 "filled when a stage fails. A dashed link is a clock-domain crossing.</p>")
    head = "".join(f'<th title="{_e(n)}">{i}</th>' for i, n in enumerate(st["stages"]))
    rows = []
    for m in st["modules"]:
        cells = "".join(f'<td class="st {s["state"]}">{_e(LABEL[s["state"]])}</td>' for s in m["stages"])
        rows.append(f"<tr><td><b>{_e(m['module'])}</b></td>{cells}</tr>")
    parts.append('<h2>Stages</h2><div class="wrap"><table><tr><th>module</th>' + head + "</tr>" + "".join(rows)
                 + "</table></div><p class=\"mut\">" + " · ".join(f"{i} {_e(n)}" for i, n in enumerate(st["stages"]))
                 + "</p>")
    ev_rows = []
    for m in st["modules"]:
        for s in m["stages"]:
            for it in s["items"]:
                extra = ", ".join(f"{k} {v}" for k, v in it.items()
                                  if k not in ("stage", "kind", "result", "key", "current", "note"))
                ev_rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in (
                    f"<b>{_e(m['module'])}</b>", f"{s['n']} {_e(s['stage'])}", _e(it.get("kind")), _e(it.get("result")),
                    "current" if it["current"] else "<b>stale</b>", f"<code>{_e(str(it.get('key'))[:12])}</code>",
                    _e(extra), _e(it.get("note", "")))) + "</tr>")
    if ev_rows:
        parts.append('<h2>Evidence</h2><div class="wrap"><table><tr><th>module</th><th>stage</th><th>kind</th>'
                     "<th>result</th><th>key</th><th>recorded key</th><th>values</th><th>note</th></tr>"
                     + "".join(ev_rows) + "</table></div><p class=\"mut\">An item is current only when its recorded "
                     "key equals the key of today's inputs (python -m project hash).</p>")
    re_rows = [[m["module"], "-" if m["reentry"] is None else f"{m['reentry']} {st['stages'][m['reentry']]}",
                m["reentry_why"] or ""] for m in st["modules"]]
    parts.append('<h2>Re-entry</h2><div class="wrap"><table><tr><th>module</th><th>re-enter at</th><th>why</th></tr>'
                 + "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in re_rows)
                 + "</table></div>")
    if st["assumptions_open"]:
        parts.append('<h2>Open assumptions</h2><div class="wrap"><table><tr><th>id</th><th>assumption</th>'
                     "<th>default</th><th>reason</th><th>affects</th></tr>" + "".join(
                         "<tr>" + "".join(f"<td>{_e(a.get(k, ''))}</td>" for k in ("id", "text", "default", "reason"))
                         + f"<td>{_e(', '.join(map(str, a.get('affects') or [])))}</td></tr>"
                         for a in st["assumptions_open"]) + "</table></div>")
    parts.append("</main></body></html>\n")
    return "".join(parts)
