"""The block-design viewer: a static, data-driven page drawn from ``gen/graph.json``.

The diagrams are SVG drawn here, in Python, from the graph (one per design level, in two layouts: left to right for
wide screens, top to bottom for phones), so they need no script to be read. The script (``mountBlockDesign`` in
site/src/app.js) adds the level tabs and the drawer that opens when a block is clicked. The same body is used by the
stand-alone ``gen/viewer.html`` (with the site's own stylesheet and script inlined) and by the site's block-design
pages, so the two cannot differ.

Layout: blocks are placed in columns by their depth along the bus links (masters before slaves); a block with no bus
link goes in the first column. Signal links between blocks in one column run down the column; links that jump
columns, or go back, run in a channel under the blocks. Board pins are listed inside the block they connect to.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from flow.blockdesign import model as M

REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
STYLE = {"axi4lite": "bdl-bus", "axi4": "bdl-bus", "axis": "bdl-bus", "window": "bdl-win", "conduit": "bdl-sig"}


def e(s) -> str:
    return html.escape(str(s), quote=True)


def _fmt_hex(v: int, w: int = 8) -> str:
    return f"0x{v:0{w}X}"


# ------------------------------------------------------------------------------------------------- the level model
def _size_txt(n: int) -> str:
    return f"{n // 1024} KB" if n % 1024 == 0 and n >= 1024 else f"{n} B"


def _range_of(g: dict, slave: str) -> dict | None:
    return next((r for r in g["address_map"]["ranges"] if r["slave"] == slave), None)


def _bits_txt(n: int) -> str:
    return f"{n}b"


def _nodes(g: dict, key: str) -> tuple[list[dict], list[dict]]:
    """Nodes (blocks, a hierarchy's boundary ports, and at the top the board pins) and edges of one level, with text lines."""
    lv = g["levels"][key]
    nodes, edges = [], []
    top = not key
    pinw = {p["name"]: p for p in lv["ports"]}
    clk_ports = {d["clock_port"] for d in g["domains"]}
    for b in lv["blocks"]:
        lines = [(b["name"] + (" (hierarchy)" if b["kind"] == "hierarchy" else ""), "bdn")]
        comp = b["component"] if b["kind"] != "hierarchy" else f"{b['component']}.yaml"
        if b["kind"] == "interconnect":
            comp = f"axil_xbar {len(b['masters'])} x {len(b['slaves'])}"
        if b.get("variant"):
            comp += f" / {b['variant']}"
        lines.append((comp, "bdc"))
        if b.get("domain") and b["kind"] != "hierarchy":
            f = b.get("freq_mhz")
            lines.append((f"{b['domain']}" + (f", {f:g} MHz" if f else ""), "bdd"))
        anchors = {}
        if b["kind"] == "interconnect":                      # one row per slave port: its name, base address and size
            for k, s in enumerate(b["slaves"]):
                r = _range_of(g, s)
                if r:
                    anchors[f"m{k}"] = len(lines)
                    lines.append((f"{s.split('.')[-1]} {_fmt_hex(r['base'])} {_size_txt(r['size'])}", "bda"))
            for h in g["address_map"]["holes"]:
                if h.get("xbar") == b["name"]:
                    lines.append((f"hole {_fmt_hex(h['base'])}-{_fmt_hex(h['base'] + h['size'] - 1)}", "bdp"))
        if b.get("build"):
            bb = b["build"]
            lines.append((f"{bb.get('lut', 0)} LUT, {bb.get('ff', 0)} FF", "bdu"))
        nodes.append({"id": b["id"], "lines": lines, "kind": b["kind"], "block": True, "generated": b.get("generated"),
                      "anchors": anchors, "domain": b.get("domain")})
    if key:
        for x in lv["exports"]:
            nodes.append({"id": f"in:{x['name']}", "lines": [(x["name"], "bdn"), ("AXI4-Lite in", "bdc")],
                          "kind": "port", "block": False})
            edges.append({"from": f"in:{x['name']}", "to": x["inst"], "kind": "axi4lite", "label": "", "title": f"{x['name']} -> {x['inst']}.{x['iface']}"})
        for p in lv["ports"]:
            if p["dir"] == "out":
                nodes.append({"id": f"port:{p['name']}", "lines": [(p["name"], "bdn"), (f"boundary out, {p['width']} bit" + ("s" if p["width"] > 1 else ""), "bdc")],
                              "kind": "port", "block": False})
    ids = {n["id"] for n in nodes}
    used_pins: dict = {}

    def end(s: str) -> str:
        if top and s.startswith("port:"):
            used_pins[s[5:]] = True
            return "pin:" + s[5:]
        return s
    for L in lv["links"]:
        a, b = end(L["from"]), end(L["to"])
        if top:
            ids |= {x for x in (a, b) if x.startswith("pin:")}
        if a in ids and b in ids:
            if L["kind"] in ("axi4lite", "axi4"):
                lab = _bits_txt(L["data_w"])
            elif L["kind"] == "conduit":
                lab = _bits_txt(L["width"])
            else:
                lab = ""
            edges.append({"from": a, "to": b, "kind": L["kind"], "label": lab, "title": L["label"],
                          "from_if": L.get("from_if"), "to_if": L.get("to_if")})
    if top:
        for d in g["domains"]:                                # the reset pin feeds its synchroniser; the clock pin feeds the rail
            rs = next((n for n in nodes if n["id"] == d.get("reset_sync")), None)
            if rs and d["reset_port"] in pinw:
                used_pins[d["reset_port"]] = True
                edges.append({"from": f"pin:{d['reset_port']}", "to": rs["id"], "kind": "conduit", "label": "1b",
                              "title": f"{d['reset_port']} -> {rs['id']}"})
        for p in lv["ports"]:
            if p["kind"] == "clock" or p["name"] in clk_ports:
                used_pins[p["name"]] = True
        for name in used_pins:
            p = pinw.get(name)
            if not p:
                continue
            w = p["width"]
            nodes.append({"id": f"pin:{name}", "lines": [(name, "bdn"), (f"{p['dir']} pin" + (f", {w} bits" if w > 1 else ""), "bdc")],
                          "kind": "pin", "block": False, "dir": p["dir"], "clock": p["kind"] == "clock", "reset": p["kind"] == "reset"})
        edges = [x for x in edges if x["from"] in {n["id"] for n in nodes} and x["to"] in {n["id"] for n in nodes}]
    return nodes, edges


CW = 7.7                         # width of one character of the 12.5 px monospace used in the boxes


def _w(n: dict) -> float:
    base = max(len(t) * CW for t, _ in n["lines"]) + 18
    return max(base, 108 if n["kind"] == "pin" else 136)


def _ranks(nodes: list[dict], edges: list[dict]) -> dict:
    """Column per node: depth along the bus links (and boundary links); signal links only place the boundary outputs.
    Board pins sit outside the columns: -1 is the left edge, and the number of columns the right edge."""
    r = {n["id"]: 0 for n in nodes if n["kind"] != "pin"}
    bus = [x for x in edges if x["kind"] != "conduit" and x["from"] in r and x["to"] in r]
    for _ in range(len(nodes) + 1):
        ch = False
        for x in bus:
            if r[x["to"]] < r[x["from"]] + 1:
                r[x["to"]] = r[x["from"]] + 1
                ch = True
        if not ch:
            break
    outs = [i for i in r if i.startswith("port:")]
    if outs:
        last = max([v for i, v in r.items() if not i.startswith("port:")] + [0]) + 1
        for o in outs:
            r[o] = last
    ncol = max(r.values()) + 1
    for n in nodes:
        if n["kind"] != "pin":
            continue
        nb = [x["to"] if x["from"] == n["id"] else x["from"] for x in edges if n["id"] in (x["from"], x["to"])]
        col = r.get(nb[0], 0) if nb else 0
        r[n["id"]] = -1 if (n["dir"] == "in" and col == 0) or (not nb) or col == 0 else ncol
    return r


def _order(nodes, edges, ranks) -> dict:
    """Index within a column: by the mean position of the node's bus predecessors, then as listed; a reset synchroniser last."""
    pos: dict = {}
    for c in sorted(set(ranks.values())):
        col = [n["id"] for n in nodes if ranks[n["id"]] == c]
        kind = {n["id"]: n["kind"] for n in nodes}
        def key(i):
            preds = [pos[x["from"]] for x in edges if x["to"] == i and x["from"] in pos]
            return (kind[i] == "reset", sum(preds) / len(preds) if preds else 1e9, col.index(i))
        for k, i in enumerate(sorted(col, key=key)):
            pos[i] = k
    return pos


LH = 16


def _box_h(n: dict) -> int:
    return 12 + LH * len(n["lines"]) + 4


# ---------------------------------------------------------------------------------------------------------- drawing
def _box_svg(n: dict, x: float, y: float, title: str) -> str:
    h, w = _box_h(n), n["w"]
    cls = {"hierarchy": "bdb bdh", "interconnect": "bdb bdx", "port": "bdb bdport", "reset": "bdb bdr", "pin": "bdb bdpin"}.get(n["kind"], "bdb")
    if n.get("generated"):
        cls += " bdgen"
    out = []
    if n["block"]:
        out.append(f'<g class="bdblk" tabindex="0" role="button" data-id="{e(n["id"])}" aria-label="{e(title)}">')
        out.append(f'<rect class="bdfocus" x="{x - 4:.0f}" y="{y - 4:.0f}" width="{w + 8:.0f}" height="{h + 8}"/>')
    else:
        out.append('<g class="bdpt">')
    out.append(f'<rect class="{cls}" x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h}"/>')
    if n["kind"] == "hierarchy":
        out.append(f'<rect class="bdh2" x="{x + 3:.0f}" y="{y + 3:.0f}" width="{w - 6:.0f}" height="{h - 6}"/>')
    for i, (t, c) in enumerate(n["lines"]):
        out.append(f'<text class="{c}" x="{x + 9:.0f}" y="{y + 17 + i * LH:.0f}">{e(t)}</text>')
    out.append("</g>")
    return "".join(out)


def _arrow(x: float, y: float, d: str, cls: str) -> str:
    """An arrowhead with its tip at (x, y) pointing right, left or down."""
    pts = {"r": f"{x - 8:.1f},{y - 4:.1f} {x:.1f},{y:.1f} {x - 8:.1f},{y + 4:.1f}",
           "l": f"{x + 8:.1f},{y - 4:.1f} {x:.1f},{y:.1f} {x + 8:.1f},{y + 4:.1f}",
           "d": f"{x - 4:.1f},{y - 8:.1f} {x:.1f},{y:.1f} {x + 4:.1f},{y - 8:.1f}"}[d]
    return f'<polygon class="bda-{cls}" points="{pts}"/>'


def _edge_svg(x: dict, d: str, tip: tuple, lab: tuple | None) -> str:
    cls = STYLE.get(x["kind"], "bdl-sig")
    s = f'<g class="bde"><path class="{cls}" d="{d}"/>' + _arrow(tip[0], tip[1], tip[2], "sig" if cls == "bdl-sig" else "bus")
    s += f'<title>{e(x["title"])}</title></g>'
    if x["label"] and lab is not None:
        s += f'<text class="bdw" x="{lab[0]:.0f}" y="{lab[1]:.0f}" text-anchor="{lab[2]}">{e(x["label"])}</text>'
    return s


def _spread(i: int, n: int, y0: float, h: float) -> float:
    return y0 + h * (i + 1) / (n + 1)


def svg_level(g: dict, key: str, lay: str) -> str:
    nodes, edges = _nodes(g, key)
    if not nodes:
        return ""
    for n in nodes:
        n["w"] = _w(n)
    ranks = _ranks(nodes, edges)
    order = _order(nodes, edges, ranks)
    byid = {n["id"]: n for n in nodes}
    place: dict = {}
    cols = sorted(set(ranks.values()))
    ncol = max(v for v in ranks.values() if v >= 0) + 1
    domains = [d for d in g["domains"]] if not key else []
    narrow = lay != "wide"
    if narrow:                                    # a pin goes in the rank of the block it connects to: inputs before it, outputs after it
        for n in nodes:
            if n["kind"] == "pin":
                nb = [x["to"] if x["from"] == n["id"] else x["from"] for x in edges if n["id"] in (x["from"], x["to"])]
                nb = [m for m in nb if m in ranks and not m.startswith("pin:")]
                ranks[n["id"]] = ranks[nb[0]] if nb else min(v for v in ranks.values())
        cols = sorted(set(ranks.values()))
        order = _order(nodes, edges, ranks)
        for n in nodes:
            if n["kind"] == "pin":
                order[n["id"]] = (-1 if n["dir"] == "in" else 99) + order[n["id"]] / 100
            elif n["kind"] == "reset":
                order[n["id"]] = 50
    if not narrow:
        WG = 64
        cx, x = {}, 8
        for c in cols:
            cx[c] = x
            x += max(byid[i]["w"] for i in ranks if ranks[i] == c) + WG
        width = x - WG + 8
        for c in cols:
            y = 8
            for i in sorted([i for i in ranks if ranks[i] == c], key=lambda i: order[i]):
                place[i] = (cx[c], y)
                y += _box_h(byid[i]) + 28
        for c in (-1, ncol):                                  # pins: next to what they connect to, clock last
            pcol = sorted([i for i in ranks if ranks[i] == c], key=lambda i: order[i])
            if not pcol:
                continue
            def tgt_y(i):
                nb = [x["to"] if x["from"] == i else x["from"] for x in edges if i in (x["from"], x["to"])]
                nb = [m for m in nb if m in place]
                return place[nb[0]][1] if nb else 1e9
            y = 8
            for i in sorted(pcol, key=lambda i: (byid[i].get("clock", False), byid[i].get("reset", False), tgt_y(i))):
                yy = max(y, tgt_y(i)) if tgt_y(i) < 1e9 else y
                if byid[i].get("clock"):
                    yy = max(y, 0)
                place[i] = (cx[c], yy)
                y = yy + _box_h(byid[i]) + 14
        bottom = max(place[i][1] + _box_h(byid[i]) for i in place)
    else:
        NG, NVG = 24, 44
        width = 360
        rows_of: dict = {}
        y = 8
        for c in cols:
            col = sorted([i for i in ranks if ranks[i] == c], key=lambda i: order[i])
            k = 0
            while k < len(col):
                row, tot = [col[k]], byid[col[k]]["w"]
                k += 1
                while k < len(col) and tot + NG + byid[col[k]]["w"] <= width - 16:
                    row.append(col[k])
                    tot += NG + byid[col[k]]["w"]
                    k += 1
                x0 = (width - tot) / 2
                for i in row:
                    place[i] = (x0, y)
                    rows_of[i] = y
                    x0 += byid[i]["w"] + NG
                y += max(_box_h(byid[i]) for i in row) + NVG
        bottom = max(place[i][1] + _box_h(byid[i]) for i in place)

    # edges ---------------------------------------------------------------------------------------------------------
    outs: dict = {}
    ins: dict = {}
    for k, x in enumerate(edges):
        outs.setdefault(x["from"], []).append(k)
        ins.setdefault(x["to"], []).append(k)
    parts, chan, nchan, gapn, margn = [], bottom + 14, 0, {}, 0
    for k, x in enumerate(edges):
        A, B = byid[x["from"]], byid[x["to"]]
        a, b = place[A["id"]], place[B["id"]]
        ha, hb = _box_h(A), _box_h(B)
        ia, ib = outs[A["id"]].index(k), ins[B["id"]].index(k)
        na, nb = len(outs[A["id"]]), len(ins[B["id"]])
        ra, rb = ranks[A["id"]], ranks[B["id"]]
        anchor = A.get("anchors", {}).get(x.get("from_if"))
        if not narrow:
            sy = a[1] + 12 + LH * anchor + 2 if anchor is not None else _spread(ia, na, a[1], ha)
            ty = _spread(ib, nb, b[1], hb)
            if rb > ra and (rb == ra + 1 or (rb == ncol and ra == ncol - 1)) or (ra == -1 and rb == 0):
                sx, tx = a[0] + A["w"], b[0]
                gk = (ra, rb)
                gapn[gk] = gapn.get(gk, 0) + 1
                xm = sx + 10 + (gapn[gk] - 1) * 7
                parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{xm:.0f} V{ty:.0f} H{tx:.0f}", (tx, ty, "r"), (tx - 12, ty - 5, "end")))
            elif rb < ra and ra - rb == 1:                          # back to a pin on the left edge
                sx, tx = a[0], b[0] + B["w"]
                gk = (rb, ra, "back")
                gapn[gk] = gapn.get(gk, 0) + 1
                xm = sx - 10 - (gapn[gk] - 1) * 7
                parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{xm:.0f} V{ty:.0f} H{tx:.0f}", (tx, ty, "l"), (tx + 12, ty - 5, "start")))
            elif ra == rb and b[1] > a[1]:
                lx = a[0] + A["w"] - 24 - 14 * ia
                parts.append(_edge_svg(x, f"M{lx:.0f} {a[1] + ha:.0f} V{b[1]:.0f}", (lx, b[1], "d"), (lx + 8, b[1] - 8, "start")))
            else:
                yc = chan + nchan * 8
                nchan += 1
                sx, tx = a[0] + A["w"], b[0]
                ty = _spread(ib, nb, b[1], hb)
                if tx < sx:                                        # target left of the source: leave and enter on the left
                    sx, tx = a[0], b[0] + B["w"]
                    parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{sx - 12:.0f} V{yc:.0f} H{tx + 12:.0f} V{ty:.0f} H{tx:.0f}", (tx, ty, "l"), (tx + 12, ty - 5, "start")))
                else:
                    parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{sx + 12:.0f} V{yc:.0f} H{tx - 12:.0f} V{ty:.0f} H{tx:.0f}", (tx, ty, "r"), (tx - 12, ty - 5, "end")))
        else:
            sx, tx = a[0] + A["w"] * (ia + 1) / (na + 1), b[0] + B["w"] * (ib + 1) / (nb + 1)
            if abs(a[1] - b[1]) < 1:                               # side by side in one row
                l, r = (a, b) if a[0] < b[0] else (b, a)
                lw = A["w"] if l is a else B["w"]
                yy = a[1] + min(ha, hb) / 2
                if a[0] < b[0]:
                    parts.append(_edge_svg(x, f"M{l[0] + lw:.0f} {yy:.0f} H{r[0]:.0f}", (r[0], yy, "r"), (r[0] - 3, yy - 5, "end")))
                else:
                    parts.append(_edge_svg(x, f"M{r[0]:.0f} {yy:.0f} H{l[0] + lw:.0f}", (l[0] + lw, yy, "l"), (l[0] + lw + 3, yy - 5, "start")))
            elif b[1] > a[1] + ha and b[1] - (a[1] + ha) < NVG + 1:
                gk = round(a[1])
                gapn[gk] = gapn.get(gk, 0) + 1
                ym = a[1] + ha + 12 + (gapn[gk] - 1) * 6
                parts.append(_edge_svg(x, f"M{sx:.0f} {a[1] + ha:.0f} V{ym:.0f} H{tx:.0f} V{b[1]:.0f}", (tx, b[1], "d"), (tx + 6, b[1] - 10, "start")))
            else:                                                  # not the next row: down the left margin
                margn += 1
                m = 4 + 5 * margn
                ay, by = a[1] + 22 + 4 * ia, b[1] + 22 + 4 * ib
                parts.append(_edge_svg(x, f"M{a[0]:.0f} {ay:.0f} H{m:.0f} V{by:.0f} H{b[0]:.0f}", (b[0], by, "r"), (b[0] - 10, by - 5, "end")))
    height = (chan + nchan * 8 + 6) if nchan else bottom + 10
    # the clock and reset rail: the domain's clock, and the reset the synchroniser makes from the reset pin ---------------
    rail_svg = ""
    if domains:
        d = domains[0]
        yc, yr = height + 10, height + 22
        rail_svg += f'<path class="bdl-clk" d="M5 {yc:.0f} H{width - 5:.0f}"/><path class="bdl-rst" d="M5 {yr:.0f} H{width - 5:.0f}"/>'
        f = f"{d['freq_mhz']:g} MHz" if d.get("freq_mhz") else ""
        rail_svg += (f'<text class="bdp" x="8" y="{yr + 17:.0f}">clock {e(d["clock_port"])}{", " + f if f else ""}, all blocks in {e(d["name"])}</text>')
        rs = byid.get(d.get("reset_sync"))
        if rs:
            rail_svg += (f'<text class="bdp" x="8" y="{yr + 17 + LH:.0f}">reset from {e(d["reset_port"])} via {e(rs["id"])}</text>')
        ck = next((n for n in nodes if n["kind"] == "pin" and n.get("clock")), None)
        if ck:                                                     # the clock pin down the left margin to the clock line
            px, py = place[ck["id"]]
            mx = 3
            rail_svg += f'<path class="bdl-clk" d="M{px:.0f} {py + _box_h(ck) / 2:.0f} H{mx} V{yc:.0f}"/><circle class="bddot" cx="{mx}" cy="{yc:.0f}" r="2.5"/>'
        if rs:
            px, py = place[rs["id"]]
            if narrow:
                mx = 4 + 5 * (margn + 1)
                rail_svg += (f'<path class="bdl-rst" d="M{px:.0f} {py + _box_h(rs) - 12:.0f} H{mx} V{yr:.0f}"/><circle class="bddot" cx="{mx}" cy="{yr:.0f}" r="2.5"/>')
            else:
                sx = px + rs["w"] / 2
                rail_svg += (f'<path class="bdl-rst" d="M{sx:.0f} {py + _box_h(rs):.0f} V{yr:.0f}"/><circle class="bddot" cx="{sx:.0f}" cy="{yr:.0f}" r="2.5"/>')
        height = yr + 17 + LH + 8 if rs else yr + 20
    boxes = []
    for n in nodes:
        t = " ".join(t for t, _ in n["lines"][:2])
        boxes.append(_box_svg(n, place[n["id"]][0], place[n["id"]][1], f"{t}: show details"))
    lvname = g["levels"][key]["name"]
    title = f"Top level of {g['design']}" if not key else f"Hierarchy {key} ({lvname})"
    nbl = sum(1 for n in nodes if n["block"])
    npin = sum(1 for n in nodes if n["kind"] == "pin")
    desc = f"{nbl} block{'s' if nbl != 1 else ''}" + (f", {npin} board pins" if npin else "") + f" and {len(edges)} links"
    return (f'<svg class="bdsvg" viewBox="0 0 {width:.0f} {height:.0f}" role="group" '
            f'aria-label="{e(title)}: {e(desc)}"><title>{e(title)}</title>' + "".join(parts) + rail_svg + "".join(boxes) + "</svg>")


def addr_svg(g: dict) -> str:
    """The address window the map uses, to scale: each range a filled bar, each hole hatched."""
    am = g["address_map"]
    rs = am["ranges"]
    if not rs:
        return ""
    lo = min(r["base"] for r in rs)
    hi = max(r["base"] + r["size"] for r in rs)
    W, x0 = 340, 10
    sc = W / (hi - lo)
    rows = []
    rows.append(f'<rect class="bdhole" x="{x0}" y="22" width="{W}" height="26"/>')
    for r in rs:
        x = x0 + (r["base"] - lo) * sc
        rows.append(f'<rect class="bdrange" x="{x:.1f}" y="22" width="{max(2, r["size"] * sc):.1f}" height="26"><title>{e(r["slave"])}: '
                    f'{_fmt_hex(r["base"])} to {_fmt_hex(r["base"] + r["size"] - 1)}</title></rect>')
    rows.append(f'<text x="{x0}" y="14">{_fmt_hex(lo)}</text>')
    rows.append(f'<text x="{x0 + W}" y="14" text-anchor="end">{_fmt_hex(hi - 1)}</text>')
    y = 70
    for k, r in enumerate(rs):                     # a key under the bar: one row per range, then the holes
        rows.append(f'<rect class="bdrange" x="{x0}" y="{y - 9}" width="10" height="10"/>')
        rows.append(f'<text x="{x0 + 16}" y="{y}">{e(r["slave"])}: {_fmt_hex(r["base"])}, {r["size"] // 1024} KB</text>')
        y += 18
    for h in am["holes"]:
        rows.append(f'<rect class="bdhole" x="{x0}" y="{y - 9}" width="10" height="10"/>')
        rows.append(f'<text x="{x0 + 16}" y="{y}">hole: {_fmt_hex(h["base"])} to {_fmt_hex(h["base"] + h["size"] - 1)}, DECERR</text>')
        y += 18
    return (f'<svg class="bdaddr" viewBox="0 0 360 {y}" role="img" aria-label="Address map from {_fmt_hex(lo)} to {_fmt_hex(hi - 1)}">'
            f'<title>Address map</title>' + "".join(rows) + "</svg>")


# ----------------------------------------------------------------------------------------------------------- the page
def _table(head, rows, num=()) -> str:
    h = "".join(f'<th{" class=num" if i in num else ""}>{e(x)}</th>' for i, x in enumerate(head))
    b = "".join("<tr>" + "".join(f'<td{" class=num" if i in num else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tablewrap" tabindex="0"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def count_blocks(g: dict) -> tuple[int, int, dict]:
    """(all blocks, blocks at the top, blocks inside each hierarchy): every box in the diagram, a hierarchy counting as one."""
    top = len(g["levels"][""]["blocks"])
    inside = {k: len(lv["blocks"]) for k, lv in g["levels"].items() if k}
    return top + sum(inside.values()), top, inside


def count_text(g: dict) -> str:
    total, top, inside = count_blocks(g)
    parts = [f"{top} at the top"] + [f"{n} inside {k}" for k, n in inside.items()]
    return f"blocks ({', '.join(parts)})"


def check_text(chk: dict) -> str:
    """What the hierarchy check proved, in the words of what it looked for (build.json's ``check``)."""
    t = (f"RTL instances found in the synthesised netlist with the module the diagram names (the {chk['expected']} include the generated wrappers)")
    if not chk.get("pass"):
        t = "MISMATCH: " + t
    if chk.get("edges_expected"):
        t += (f"; {chk.get('edges_matched', 0)} of {chk['edges_expected']} links between blocks found as nets, in the "
              "direction drawn, and no net between two blocks left undrawn")
        nv = chk.get("edges_not_visible") or []
        nv = len(nv) if isinstance(nv, list) else int(nv)
        if nv:
            t += f" ({nv} not compared: {'it goes' if nv == 1 else 'they go'} through logic or synthesis removed the pins)"
    if chk.get("ranges_checked"):
        t += f"; the crossbar's {chk['ranges_checked']} address ranges equal the built RTL's"
    return t


def scope_line(g: dict) -> str:
    """The design's limits in one line, from the data: the buses used, the clock domains, the tool that built it."""
    kinds = {L["kind"] for lv in g["levels"].values() for L in lv["links"]} - {"conduit", "window", "interrupt"}
    bus = " and ".join(KIND_LABEL_BUS[k] for k in sorted(kinds)) + " only" if kinds else ""
    doms = g["domains"]
    num = {1: "one"}.get(len(doms), str(len(doms)))
    freqs = sorted({f"{d['freq_mhz']:g} MHz" for d in doms if d.get("freq_mhz")})
    dom = f"{num} {' / '.join(freqs)} clock domain" + ("s" if len(doms) != 1 else "")
    built = (f"built with Vivado {g['build']['tool']} but not yet run on the board" if g.get("build") else "not yet built")
    return f'<p class="scope"><b>Scope:</b> {e(", ".join(x for x in (bus, dom, built) if x))}.</p>'


KIND_LABEL_BUS = {"axi4lite": "AXI4-Lite", "axi4": "AXI4", "axis": "AXI4-Stream"}


def terms() -> str:
    return ('<dl class="bdterms"><div><dt><code>ip_lib</code></dt><dd>the project\'s own library of verified hardware blocks; each has a '
            'description, tests and measured cost.</dd></div>'
            '<div><dt>UART test shell</dt><dd>the fixed wrapper that lets a PC read and write the design\'s registers over the board\'s '
            'USB-UART.</dd></div></dl>')


def _endpoint(s: str, port: str | None) -> str:
    s = s.replace("port:", "")
    return f"{s}.{port}" if port else s


def body(g: dict, key: str = "bd_graph", repo_links: bool = True) -> str:
    """The viewer's HTML (without the page frame). ``key`` names the JSON data block the script reads."""
    levels = list(g["levels"])
    tabs = "".join(f'<button type="button" class="bdtab" data-level="{e(k)}" aria-pressed="{"true" if i == 0 else "false"}">'
                   f'{e("Top level" if not k else k + " (hierarchy)")}</button>' for i, k in enumerate(levels))
    figs = []
    for i, k in enumerate(levels):
        figs.append(f'<div class="bdlevel" data-level="{e(k)}"{"" if i == 0 else " hidden"}>'
                    f'<div class="agfig"><div class="lay-w">{svg_level(g, k, "wide")}</div><div class="lay-n">{svg_level(g, k, "narrow")}</div></div></div>')
    chk = g.get("check")
    build = g.get("build")
    head = []
    s = f'<p class="lede">{e(g["summary"])}</p>' if g.get("summary") else ""
    s += scope_line(g)
    facts = [f'<div class="fact"><div class="n">{count_blocks(g)[0]}</div><p>{e(count_text(g))}, generated from '
             f'<code>{e(g["levels"][""]["file"])}</code></p></div>']
    if build:
        facts.append(f'<div class="fact"><div class="n">{build["wns_ns"]:+.3f} ns</div><p>worst setup slack after routing on the '
                     f'{e(g["part"])}, Vivado {e(build["tool"])}; timing, DRC and methodology gates {"passed" if build["gates_pass"] else "FAILED"}</p></div>')
    if chk:
        short = "RTL instances found in the synthesised netlist with the module the diagram names" + (
            f"; {chk.get('edges_matched', 0)} of {chk['edges_expected']} links found as nets" if chk.get("edges_expected") else "")
        nv = chk.get("edges_not_visible") or []
        nv = len(nv) if isinstance(nv, list) else int(nv)
        short += f" ({nv} not compared)" if nv and chk.get("edges_expected") else ""
        facts.append(f'<div class="fact"><div class="n">{chk["matched"]} of {chk["expected"]}</div><p>{e(short)} '
                     '(<a href="#build">what was checked</a>)</p></div>')
    head.append(s + '<div class="facts">' + "".join(facts) + "</div>" + terms())
    kk = lambda c, d: f'<svg viewBox="0 0 30 10" class="bdkey"><path class="{c}" d="{d}"/></svg>'
    legend = ('<div class="legend bdlegend">'
              f'<span>{kk("bdl-bus", "M0 5 H30")} AXI4-Lite bus, arrow from master to slave, labelled with its data width</span>'
              f'<span>{kk("bdl-win", "M0 5 H30")} register window</span>'
              f'<span>{kk("bdl-sig", "M0 5 H30")} signals, labelled with their width in bits</span>'
              f'<span>{kk("bdl-clk", "M0 5 H30")} clock rail</span><span>{kk("bdl-rst", "M0 5 H30")} reset rail</span>'
              '<span><svg viewBox="0 0 30 12" class="bdkey"><rect class="bdb bdgen" x="1" y="1" width="28" height="10"/></svg> added by automation</span>'
              '<span><svg viewBox="0 0 30 12" class="bdkey"><rect class="bdb bdh" x="1" y="1" width="28" height="10"/></svg> hierarchy</span>'
              '<span><svg viewBox="0 0 30 12" class="bdkey"><rect class="bdb bdpin" x="1" y="1" width="28" height="10"/></svg> board pin</span></div>')
    out = ['<div class="bdpage">', "".join(head),
           '<section class="bd" data-key="' + e(key) + '">',
           '<h2 id="diagram">The diagram</h2>',
           '<p>Click or tab to a block to see its variant, parameters (and where each value came from), measured cost and, '
           'from the build, its share of the logic and its worst slack. Arrow keys move between blocks and Esc goes back to the crossbar. '
           'A hierarchy opens as its own level.</p>',
           '<div class="bdmain"><div class="bdfig">',
           f'<div class="bdtabs" role="group" aria-label="Design level">{tabs}</div>',
           "".join(figs), legend, "</div>",
           '<aside class="bddrawer panel" id="bd-drawer" role="region" aria-label="Block details" aria-live="polite" tabindex="-1">'
           '<p class="muted">Select a block in the diagram to see its details here.</p></aside></div>',
           "</section>"]
    # connections
    rows = []
    for k, lv in g["levels"].items():
        for L in lv["links"]:
            rows.append([e(k or "top"), f'<code>{e(_endpoint(L["from"], L.get("from_if")))}</code>', f'<code>{e(_endpoint(L["to"], L.get("to_if")))}</code>', e(L["label"])])
    out.append('<h2 id="links">Links</h2>' + _table(["Level", "From", "To", "What"], rows))
    # domains and crossings
    drows = [[e(d["name"]), f'<code>{e(d["clock_port"])}</code>', e(f'{d["freq_mhz"]:g}' if d.get("freq_mhz") else ""),
              f'<code>{e(d["reset_port"] or "")}</code>', e(d.get("reset_sync") or "")] for d in g["domains"]]
    xrows = [[f'<code>{e(x["from"])}</code>', f'<code>{e(x["to"])}</code>', e(f'{x["from_domain"]} to {x["to_domain"]}'),
              e(x["synchroniser"] or "none"), "yes" if x["safe"] else "<b>no</b>"] for x in g["crossings"]]
    out.append('<h2 id="domains">Clock domains and crossings</h2>'
               + _table(["Domain", "Clock", "MHz", "Reset in", "Reset synchroniser"], drows, num=(2,))
               + "<p>Every place a signal enters a domain other than its own, and what makes it safe. The validator refuses a "
                 "crossing with no synchroniser (BD-CDC-01, BD-CDC-02) and a bus link between domains (BD-CDC-03).</p>"
               + _table(["From", "To", "Domains", "Synchroniser", "Safe"], xrows))
    # address map
    arows = []
    for r in g["address_map"]["ranges"]:
        regs = ", ".join(f'{x["name"]} +{x["offset"]:#x}' for x in r["registers"] if x["name"] != "WINDOW") or (
            "the block's own register window" if r["registers"] else "")
        arows.append([f'<code>{e(r["slave"])}</code>', f'<code>{_fmt_hex(r["base"])}</code>', f'<code>{_fmt_hex(r["base"] + r["size"] - 1)}</code>',
                      e(f'{r["size_kb"]:g} KB'), e("fixed in the design" if r["fixed"] else "by the address editor"), e(regs)])
    out.append('<h2 id="address-map">Address map</h2><div class="fig">' + addr_svg(g) + "</div>"
               + _table(["Slave", "Base", "Last", "Size", "Placed", "Registers"], arows)
               + (f'<p>Exported as a C header and a page: <a href="{REPO}/blob/main/{e(g["files"]["header"])}"><code>{e(g["files"]["header"].split("/")[-1])}</code></a>, '
                  f'<a href="{REPO}/blob/main/{e(g["files"]["map_doc"])}"><code>{e(g["files"]["map_doc"].split("/")[-1])}</code></a>.</p>' if repo_links and g.get("files") else ""))
    # build
    if build:
        brows = []
        for lv in g["levels"].values():
            for b in lv["blocks"]:
                bb = b.get("build")
                if not bb:
                    continue
                brows.append([f'<code>{e(b["id"])}</code>', e(b["component"]), bb.get("lut", ""), bb.get("ff", ""), e(f'{bb.get("bram", 0):g}'),
                              bb.get("dsp", ""), e("" if bb.get("wns_ns") is None else f'{bb["wns_ns"]:+.3f}')])
        out.append('<h2 id="build">From the build</h2>'
                   f'<p>Built with Vivado {e(build["tool"])} for the {e(g["part"])} ({e(g["board"])}), build ID <code>{e(build["build_id"])}</code>. '
                   'Per block: its share of the routed design (cells inside its instance, from the hierarchical utilisation '
                   'report) and the worst setup slack of the paths that end inside it.</p>'
                   + (f'<p><strong>Diagram against the build{"" if chk.get("pass") else " (MISMATCH)"}:</strong> '
                      f'{chk["matched"]} of {chk["expected"]} {e(check_text(chk)).replace("MISMATCH: ", "")}.</p>' if chk else '')
                   + _table(["Block", "Component", "LUT", "FF", "Block RAM tiles", "DSP", "Worst setup slack (ns)"], brows, num=(2, 3, 4, 5, 6)))
    # validation
    drows = [[e(d["severity"]), f'<code>{e(d["code"])}</code>', e(d["where"]), e(d["msg"])] for d in g["diagnostics"]]
    out.append('<h2 id="checks">What the validator said</h2>'
               "<p>The design passes when there are no errors. Warnings and notes are kept in the manifest.</p>"
               + (_table(["Severity", "Code", "Where", "Message"], drows) if drows else "<p>Nothing to report.</p>"))
    out.append("</div>")
    return "\n".join(out)


def standalone(g: dict) -> str:
    """gen/viewer.html: the body in a plain page with the site's stylesheet and script inlined (no network)."""
    css = (M.ROOT / "site" / "src" / "site.css").read_text()
    js = (M.ROOT / "site" / "src" / "app.js").read_text()
    data = json.dumps(g, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(g["design"])}: block design</title>
<meta name="color-scheme" content="light dark">
<style>{css}</style>
</head>
<body>
<main id="main" class="wrap">
<h1>{e(g["design"])}</h1>
{body(g, "bd_graph", repo_links=False)}
</main>
<script type="application/json" data-key="bd_graph">{data}</script>
<script>{js}</script>
</body>
</html>
"""


def enrich(g: dict, ddir: Path | None = None) -> dict:
    """Fields the page shows that are derived from the graph (kept as data, so the site's number check sees them)."""
    g = json.loads(json.dumps(g))
    for r in g["address_map"]["ranges"]:
        r["size_kb"] = r["size"] / 1024
    if ddir is not None:
        rel = Path(ddir).resolve().relative_to(M.ROOT)
        g["files"] = {"design": f"{rel}/blockdesign.yaml", "header": f"{rel}/gen/addrmap.h", "map_doc": f"{rel}/gen/address_map.md",
                      "manifest": f"{rel}/gen/manifest.json", "rtl": f"{rel}/gen/rtl"}
    return g


def load_graph(ddir: Path) -> dict:
    """The graph with the build's annotation merged in, when there is one for this graph (results/blockdesign/<name>/build.json)."""
    from flow.blockdesign import annotate
    g = json.loads((Path(ddir) / "gen" / "graph.json").read_text())
    ann = annotate.results_file(g["design"])
    if ann.is_file():
        a = json.loads(ann.read_text())
        if a.get("graph_sha256") == annotate.graph_sha(g):     # a build of this very graph
            g = annotate.merge(g, a)
    return enrich(g, ddir)


def write(ddir: Path, out: Path | None = None) -> Path:
    g = load_graph(ddir)
    p = out or Path(ddir) / "gen" / "viewer.html"
    p.write_text(standalone(g))
    return p
