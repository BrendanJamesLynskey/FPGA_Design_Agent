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
BW, LH = 156, 15                 # block width, text line height
WG, WVG = 60, 30                 # wide layout: gap between columns, between blocks in a column
NG, NVG = 24, 46                 # narrow layout: gap between blocks in a row, between rows
NARROW_W = 360
STYLE = {"axi4lite": "bdl-bus", "axi4": "bdl-bus", "axis": "bdl-bus", "window": "bdl-win", "conduit": "bdl-sig"}


def e(s) -> str:
    return html.escape(str(s), quote=True)


def _fmt_hex(v: int, w: int = 8) -> str:
    return f"0x{v:0{w}X}"


# ------------------------------------------------------------------------------------------------- the level model
def _nodes(g: dict, key: str) -> tuple[list[dict], list[dict]]:
    """Nodes (blocks, plus a hierarchy's boundary ports) and edges of one level, with each node's text lines."""
    lv = g["levels"][key]
    pre = f"{key}/" if key else ""
    nodes, edges = [], []
    pins: dict = {}
    for L in lv["links"]:
        if L["kind"] != "conduit":
            continue
        for s in L["signals"]:
            if L["from"].startswith("port:") and not key:
                pins.setdefault(L["to"], []).append(f"{L['from'][5:]} in")
            if L["to"].startswith("port:") and not key:
                pins.setdefault(L["from"], []).append(f"{L['to'][5:]}" + (f"[{s['to_bits'][0]}:{s['to_bits'][1]}]" if s.get("to_bits") else "") + " out")
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
        if b["kind"] == "reset" and not key:
            dom = next((d for d in g["domains"] if d.get("reset_sync") == b["name"]), None)
            if dom:
                lines.append((f"{dom['reset_port']} in", "bdp"))
        for p in pins.get(b["id"], []):
            lines.append((p, "bdp"))
        if b.get("build"):
            bb = b["build"]
            lines.append((f"{bb.get('lut', 0)} LUT, {bb.get('ff', 0)} FF", "bdu"))
        nodes.append({"id": b["id"], "lines": lines, "kind": b["kind"], "block": True, "generated": b.get("generated")})
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
    for L in lv["links"]:
        if L["from"] in ids and L["to"] in ids:
            edges.append({"from": L["from"], "to": L["to"], "kind": L["kind"],
                          "label": str(L.get("width", "")) if L["kind"] == "conduit" else "",
                          "title": L["label"]})
    del pre
    return nodes, edges


def _ranks(nodes: list[dict], edges: list[dict]) -> dict:
    """Column per node: depth along the bus links (and boundary links); signal links only place the boundary outputs."""
    r = {n["id"]: 0 for n in nodes}
    bus = [x for x in edges if x["kind"] != "conduit"]
    for _ in range(len(nodes) + 1):
        ch = False
        for x in bus:
            if r[x["to"]] < r[x["from"]] + 1:
                r[x["to"]] = r[x["from"]] + 1
                ch = True
        if not ch:
            break
    outs = [n["id"] for n in nodes if n["id"].startswith("port:")]
    if outs:
        last = max([r[n["id"]] for n in nodes if not n["id"].startswith("port:")] + [0]) + 1
        for o in outs:
            r[o] = last
    return r


def _order(nodes, edges, ranks) -> dict:
    """Index within a column: by the mean position of the node's bus predecessors, then as listed."""
    pos: dict = {}
    for c in sorted(set(ranks.values())):
        col = [n["id"] for n in nodes if ranks[n["id"]] == c]
        def key(i):
            preds = [pos[x["from"]] for x in edges if x["to"] == i and x["from"] in pos]
            return (sum(preds) / len(preds) if preds else 1e9, col.index(i))
        for k, i in enumerate(sorted(col, key=key)):
            pos[i] = k
    return pos


def _box_h(n: dict) -> int:
    return 12 + LH * len(n["lines"]) + 4


# ---------------------------------------------------------------------------------------------------------- drawing
def _box_svg(n: dict, x: float, y: float, title: str) -> str:
    h = _box_h(n)
    cls = {"hierarchy": "bdb bdh", "interconnect": "bdb bdx", "port": "bdb bdport", "reset": "bdb bdr"}.get(n["kind"], "bdb")
    if n.get("generated"):
        cls += " bdgen"
    out = []
    if n["block"]:
        out.append(f'<g class="bdblk" tabindex="0" role="button" data-id="{e(n["id"])}" aria-label="{e(title)}">')
    else:
        out.append('<g class="bdpt">')
    out.append(f'<rect class="{cls}" x="{x:.0f}" y="{y:.0f}" width="{BW}" height="{h}"/>')
    if n["kind"] == "hierarchy":
        out.append(f'<rect class="bdh2" x="{x + 3:.0f}" y="{y + 3:.0f}" width="{BW - 6}" height="{h - 6}"/>')
    for i, (t, c) in enumerate(n["lines"]):
        out.append(f'<text class="{c}" x="{x + 8:.0f}" y="{y + 16 + i * LH:.0f}">{e(t)}</text>')
    out.append("</g>")
    return "".join(out)


def _edge_svg(x: dict, d: str, lx=None, ly=None) -> str:
    cls = STYLE.get(x["kind"], "bdl-sig")
    s = f'<path class="{cls}" d="{d}"><title>{e(x["title"])}</title></path>'
    if x["label"] and lx is not None:
        s += f'<text class="bdw" x="{lx:.0f}" y="{ly:.0f}">{e(x["label"])}</text>'
    return s


def svg_level(g: dict, key: str, lay: str) -> str:
    nodes, edges = _nodes(g, key)
    if not nodes:
        return ""
    ranks = _ranks(nodes, edges)
    order = _order(nodes, edges, ranks)
    byid = {n["id"]: n for n in nodes}
    place: dict = {}
    ncol = max(ranks.values()) + 1
    if lay == "wide":
        y_of_col = {}
        for c in range(ncol):
            y = 8
            for i in sorted([n for n in ranks if ranks[n] == c], key=lambda i: order[i]):
                place[i] = (8 + c * (BW + WG), y)
                y += _box_h(byid[i]) + WVG
            y_of_col[c] = y
        width = 16 + ncol * BW + (ncol - 1) * WG
    else:
        y = 8
        for c in range(ncol):
            col = sorted([n for n in ranks if ranks[n] == c], key=lambda i: order[i])
            per = max(1, (NARROW_W - 16 + NG) // (BW + NG))
            for k in range(0, len(col), per):
                row = col[k:k + per]
                tot = len(row) * BW + (len(row) - 1) * NG
                x0 = (NARROW_W - tot) / 2
                hmax = 0
                for j, i in enumerate(row):
                    place[i] = (x0 + j * (BW + NG), y)
                    hmax = max(hmax, _box_h(byid[i]))
                y += hmax + NVG
        width = NARROW_W
    bottom = max(place[i][1] + _box_h(byid[i]) for i in place)
    parts = []
    chan = bottom + 14
    nchan = 0
    srcs_in_gap: dict = {}
    for x in edges:
        a, b = place[x["from"]], place[x["to"]]
        ha, hb = _box_h(byid[x["from"]]), _box_h(byid[x["to"]])
        if lay == "wide":
            ra, rb = ranks[x["from"]], ranks[x["to"]]
            if rb == ra + 1:
                k = srcs_in_gap.setdefault((ra, x["from"]), len([s for s in srcs_in_gap if s[0] == ra]))
                sx, sy = a[0] + BW, a[1] + ha / 2
                tx, ty = b[0], b[1] + hb / 2
                xm = sx + WG / 2 + (k - 0) * 6 - 6
                parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{xm:.0f} V{ty:.0f} H{tx:.0f}", tx - 16, ty - 5))
            elif ra == rb and b[1] > a[1]:
                lx = a[0] + BW - 24
                parts.append(_edge_svg(x, f"M{lx:.0f} {a[1] + ha:.0f} V{b[1]:.0f}", lx + 5, (a[1] + ha + b[1]) / 2 + 4))
            else:
                yc = chan + nchan * 8
                nchan += 1
                sx, sy = a[0] + BW, a[1] + ha / 2
                tx, ty = b[0], b[1] + hb / 2
                parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} H{sx + 12:.0f} V{yc:.0f} H{tx - 12:.0f} V{ty:.0f} H{tx:.0f}", tx - 16, ty - 5))
        else:
            sx, sy = a[0] + BW / 2, a[1] + ha
            tx, ty = b[0] + BW / 2, b[1]
            if abs(a[1] - b[1]) < 1:                         # side by side in one row
                l, r = (a, b) if a[0] < b[0] else (b, a)
                yy = a[1] + min(ha, hb) / 2
                parts.append(_edge_svg(x, f"M{l[0] + BW:.0f} {yy:.0f} H{r[0]:.0f}", l[0] + BW + 4, yy - 5))
            elif b[1] > a[1] + ha:
                ym = a[1] + ha + NVG / 2 - 4
                parts.append(_edge_svg(x, f"M{sx:.0f} {sy:.0f} V{ym:.0f} H{tx:.0f} V{ty:.0f}", tx + 5, ty - 6))
            else:
                yc = chan + nchan * 8
                nchan += 1
                parts.append(_edge_svg(x, f"M{a[0]:.0f} {a[1] + ha / 2:.0f} H6 V{b[1] + hb / 2:.0f} H{b[0]:.0f}", None, None))
    height = (chan + nchan * 8 + 6) if nchan else bottom + 10
    boxes = []
    for n in nodes:
        t = " ".join(t for t, _ in n["lines"][:2])
        boxes.append(_box_svg(n, place[n["id"]][0], place[n["id"]][1], f"{t}: show details"))
    lvname = g["levels"][key]["name"]
    title = f"{'Top level' if not key else 'Hierarchy ' + key} of {g['design']}" if not key else f"Hierarchy {key} ({lvname})"
    desc = f"{sum(1 for n in nodes if n['block'])} blocks and {len(edges)} links"
    return (f'<svg class="bdsvg" viewBox="0 0 {width:.0f} {height:.0f}" style="max-width:{width:.0f}px" role="group" '
            f'aria-label="{e(title)}: {e(desc)}"><title>{e(title)}</title>' + "".join(parts) + "".join(boxes) + "</svg>")


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
    nb = sum(1 for lv in g["levels"].values() for b in lv["blocks"] if b["kind"] != "hierarchy")
    s = f'<p class="lede">{e(g["summary"])}</p>' if g.get("summary") else ""
    facts = [f'<div class="fact"><div class="n">{nb}</div><p>blocks in {len(levels)} level{"s" if len(levels) > 1 else ""}, '
             f'generated from <code>{e(g["levels"][""]["file"])}</code></p></div>']
    if build:
        facts.append(f'<div class="fact"><div class="n">{build["wns_ns"]:+.3f} ns</div><p>worst setup slack after routing on the '
                     f'{e(g["part"])}, Vivado {e(build["tool"])}; timing, DRC and methodology gates {"passed" if build["gates_pass"] else "FAILED"}</p></div>')
    if chk:
        facts.append(f'<div class="fact"><div class="n">{chk["matched"]} of {chk["expected"]}</div><p>blocks found in the synthesised '
                     f'hierarchy, each with the module the diagram names: {"the diagram matches the netlist" if chk["pass"] else "MISMATCH"}</p></div>')
    head.append(s + '<div class="facts">' + "".join(facts) + "</div>")
    legend = ('<div class="legend bdlegend"><span><svg viewBox="0 0 30 10" class="bdkey"><path class="bdl-bus" d="M0 5 H30"/></svg> AXI4-Lite bus</span>'
              '<span><svg viewBox="0 0 30 10" class="bdkey"><path class="bdl-win" d="M0 5 H30"/></svg> register window</span>'
              '<span><svg viewBox="0 0 30 10" class="bdkey"><path class="bdl-sig" d="M0 5 H30"/></svg> signals (the number is the bits)</span>'
              '<span><svg viewBox="0 0 30 12" class="bdkey"><rect class="bdb bdgen" x="1" y="1" width="28" height="10"/></svg> added by automation</span>'
              '<span><svg viewBox="0 0 30 12" class="bdkey"><rect class="bdb bdh" x="1" y="1" width="28" height="10"/></svg> hierarchy</span></div>')
    out = ['<div class="bdpage">', "".join(head),
           '<section class="bd" data-key="' + e(key) + '">',
           '<h2 id="diagram">The diagram</h2>',
           '<p>Click or tab to a block to see its variant, parameters (and where each value came from), measured cost and, '
           'from the build, its share of the logic and its worst slack. A hierarchy opens as its own level.</p>',
           f'<div class="bdtabs" role="group" aria-label="Design level">{tabs}</div>',
           "".join(figs), legend,
           '<div class="bddrawer panel" id="bd-drawer" aria-live="polite" tabindex="-1"><p class="muted">No block selected.</p></div>',
           "</section>"]
    # connections
    rows = []
    for k, lv in g["levels"].items():
        for L in lv["links"]:
            rows.append([e(k or "top"), f'<code>{e(L["from"].replace("port:", ""))}</code>', f'<code>{e(L["to"].replace("port:", ""))}</code>', e(L["label"])])
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
