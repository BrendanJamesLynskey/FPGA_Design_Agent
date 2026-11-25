"""Browser views of a finished build, for people without Vivado (brief 118; used by flow/inspect_build.py).

Static files next to the build (``build/<variant>/inspect/``): ``index.html``, ``src/*.html`` (RTL with line anchors) and
``schematics/*.svg``. Everything is read from the build's own reports (``utilization_hier.rpt``, ``timing_worst_setup.rpt``,
``timing_worst_hold.rpt``, ``timing_summary.rpt``, ``xprobe.json`` when it exists) and from the sources; nothing is estimated and nothing
here talks to a network (no external script, font or image). Read-only.

Schematics: Yosys (OSS CAD Suite, found as in flow/checks/elab.py) elaborates one module with the slang front end, one level deep (its
instances stay boxes); ``netlistsvg`` draws it when it is installed (``FDA_NETLISTSVG``, ``PATH``, or ``~/.local/opt/netlistsvg``), otherwise a
plain built-in layered drawing is used. A schematic is of the module as written in today's tree with default parameters, not of the netlist Vivado made: for that, open a checkpoint in Vivado.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

SOURCE_EXT = (".sv", ".v", ".svh", ".vh", ".vhd", ".vhdl")
MAX_SCHEMATIC_CELLS = 400

CSS = """
:root{--bg:#fafafa;--fg:#1a1a1a;--mut:#666;--line:#d4d4d4;--card:#fff;--bad:#a4262c;--ok:#1b6e3c;--warn:#8a5a00;--bar:#7a8a99}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111;--fg:#e8e8e8;--mut:#9a9a9a;--line:#333;--card:#181818;--bad:#ff7b72;--ok:#56d364;--warn:#e3b341;--bar:#6a7a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:1.4rem;margin:.2em 0}h2{font-size:1.1rem;margin:1.6em 0 .4em;border-bottom:1px solid var(--line)}
code,pre,td.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}table{border-collapse:collapse;width:100%;background:var(--card)}
th,td{border:1px solid var(--line);padding:3px 7px;text-align:left;vertical-align:top}th{font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
.warn{border:1px solid var(--warn);color:var(--warn);padding:6px 10px;margin:6px 0;background:var(--card)}.ok{color:var(--ok)}.bad{color:var(--bad)}.mut{color:var(--mut)}
details{margin-left:14px}summary{cursor:pointer}.row{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.nm{font-family:ui-monospace,monospace;font-size:13px}
.bar{display:inline-block;height:8px;background:var(--bar);vertical-align:middle}.scroll{overflow-x:auto}a{color:inherit}body{overflow-wrap:anywhere}td.nw,th.nw{white-space:nowrap;overflow-wrap:normal}
pre.src{background:var(--card);border:1px solid var(--line);padding:0;overflow-x:auto}pre.src span.l{display:block;padding:0 8px}pre.src span.l:target{background:rgba(255,200,0,.25)}
pre.src span.l i{display:inline-block;width:4em;color:var(--mut);font-style:normal;user-select:none}
input[type=search]{padding:4px 8px;border:1px solid var(--line);background:var(--card);color:var(--fg);width:min(100%,360px)}
@media (max-width:640px){main{padding:12px 16px}}
"""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body><main>{body}</main></body></html>
"""


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


# --- utilisation by hierarchy ---------------------------------------------------------------------------------------------------------
def parse_util_hier(text: str) -> tuple[list[str], list[dict]]:
    """(column names, rows) of the ``Utilization by Hierarchy`` table; a row has name, module, level, vals (name -> int or float)."""
    rows, cols, header = [], [], None
    for ln in text.splitlines():
        if not ln.startswith("|"):
            continue
        cells = [c.strip("\n") for c in ln.strip().strip("|").split("|")]
        if header is None:
            if cells and cells[0].strip() == "Instance":
                header = [c.strip() for c in cells]
                cols = header[2:]
            continue
        if len(cells) != len(header):
            continue
        raw = cells[0]
        name = raw.strip()
        lvl = (len(raw) - len(raw.lstrip())) // 2
        vals = {}
        for k, v in zip(cols, cells[2:]):
            try:
                vals[k] = float(v.strip()) if "." in v else int(v.strip())
            except ValueError:
                vals[k] = 0
        rows.append({"name": name, "module": cells[1].strip(), "level": lvl, "vals": vals})
    return cols, rows


def build_tree(rows: list[dict]) -> dict | None:
    """Nest the rows by indentation; the ``(name)`` rows (a module's own logic) become ``own`` on their parent."""
    root, stack = None, []
    for r in rows:
        if r["name"].startswith("(") and r["name"].endswith(")"):
            if stack:
                stack[-1]["own"] = r["vals"]
            continue
        node = {**r, "children": [], "own": None, "path": ""}
        while stack and stack[-1]["level"] >= r["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
            node["path"] = (stack[-1]["path"] + "/" if stack[-1]["path"] else "") + r["name"]
        else:
            root = node
            node["path"] = ""
        stack.append(node)
    return root


# --- RTL index and source pages -------------------------------------------------------------------------------------------------------
def module_index(root: Path, files: list[str]) -> dict[str, tuple[str, int]]:
    idx: dict[str, tuple[str, int]] = {}
    for rel in files:
        if not rel.endswith(SOURCE_EXT):
            continue
        p = root / rel
        if not p.is_file():
            continue
        for i, ln in enumerate(p.read_text(errors="replace").splitlines(), 1):
            m = re.match(r"\s*(?:module|entity)\s+(\w+)", ln)
            if m and m.group(1) not in idx:
                idx[m.group(1)] = (rel, i)
    return idx


def src_name(rel: str) -> str:
    return rel.replace("/", "__") + ".html"


def write_sources(root: Path, files: list[str], out: Path, changed: set[str]) -> list[str]:
    d = out / "src"
    d.mkdir(parents=True, exist_ok=True)
    done = []
    for rel in files:
        p = root / rel
        if not p.is_file() or p.suffix not in SOURCE_EXT + (".xdc",):
            continue
        lines = p.read_text(errors="replace").splitlines()
        banner = ('<div class="warn">This file differs from the one the build used: the checkpoints hold the build\'s version, not this text.</div>'
                  if rel in changed else '<p class="mut">The file as it is in the tree now; it matches the build\'s manifest.</p>')
        body = "".join(f'<span class="l" id="L{i}"><i>{i}</i>{esc(t) or "&nbsp;"}</span>' for i, t in enumerate(lines, 1))
        (d / src_name(rel)).write_text(PAGE.format(title=esc(Path(rel).name), css=CSS, body=f'<p><a href="../index.html">back</a></p><h1>{esc(rel)}</h1>{banner}<pre class="src">{body}</pre>'))
        done.append(rel)
    return done


# --- timing ---------------------------------------------------------------------------------------------------------------------------
def parse_paths(text: str) -> list[dict]:
    """The paths of a Vivado ``report_timing`` text: slack, endpoints, clocks, requirement, delays and each cell on the path."""
    paths = []
    blocks = re.split(r"(?m)^(?=Slack \()", text)
    for blk in blocks:
        m = re.match(r"Slack \((\w+)\)\s*:\s*(-?[\d.]+)ns", blk)
        if not m:
            continue

        def g(rx: str, flags: int = 0) -> str:
            mm = re.search(rx, blk, flags)
            return mm.group(1).strip() if mm else ""
        p = {"met": m.group(1), "slack": float(m.group(2)), "source": g(r"^\s+Source:\s+(\S+)", re.M), "dest": g(r"^\s+Destination:\s+(\S+)", re.M),
             "src_clk": g(r"Source:.*\n\s+\(.*?clocked by (\S+)"), "dst_clk": g(r"Destination:.*\n\s+\(.*?clocked by (\S+)"),
             "group": g(r"Path Group:\s+(\S+)"), "type": g(r"Path Type:\s+(.*)"), "requirement": g(r"Requirement:\s+(\S+)"),
             "data_delay": g(r"Data Path Delay:\s+(.*)"), "levels": g(r"Logic Levels:\s+(.*)"), "skew": g(r"Clock Path Skew:\s+(\S+)"), "cells": []}
        pend = None
        for ln in blk.splitlines():
            cm = re.match(r"^\s+(\S+)\s+(\w+)(?:\s+\(\S+\))?\s*$", ln)
            if cm and re.match(r"(SLICE|GTH|GTY|BUFG|DSP|RAMB|URAM|IOB|IDELAY|ODELAY|BITSLICE|MMCM|PLL|CMAC|PCIE|HPIOB|HRIO|HDIO|LAGUNA|[A-Z]+_X\d+Y\d+)", cm.group(1)):
                pend = (cm.group(1), cm.group(2))
            cm2 = re.match(r"^\s+(?:(\S+)\s+(\w+)\s+(?:\(\S+\)\s+)?)?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+[rf]\s+(\S+)\s*$", ln)
            if cm2:
                site, typ = (cm2.group(1), cm2.group(2)) if cm2.group(1) else (pend or ("", ""))
                p["cells"].append({"site": site, "type": typ, "incr": float(cm2.group(3)), "arrival": float(cm2.group(4)), "pin": cm2.group(5)})
                pend = None
        paths.append(p)
    return paths


def resolve_module(pin: str, hier: list[tuple[str, str]]) -> str:
    """The module of the deepest hierarchy instance that prefixes the pin's name (hier: (path, module))."""
    best = ""
    for path, mod in hier:
        if path and (pin == path or pin.startswith(path + "/")) and len(path) > len(best[0] if best else ""):
            best = (path, mod)
    return best[1] if best else ""


def flat_hier(tree: dict | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def walk(n: dict) -> None:
        out.append((n["path"], n["module"]))
        for c in n["children"]:
            walk(c)
    if tree:
        walk(tree)
    return out


def strip_param(mod: str) -> str:
    return re.sub(r"__parameterized\d*(__\d+)?$|__\d+$", "", mod)


# --- schematics -----------------------------------------------------------------------------------------------------------------------
def netlistsvg_path() -> str | None:
    for c in (os.environ.get("FDA_NETLISTSVG"), shutil.which("netlistsvg"), str(Path.home() / ".local/opt/netlistsvg/node_modules/.bin/netlistsvg")):
        if c and Path(c).is_file():
            return c
    return None


def yosys_modules(files: list[Path], module: str, ip_names: set[str]) -> tuple[dict | None, str]:
    """Elaborate ``module`` with the repository's own elaboration helper (flow/checks/elab.py: yosys-slang, with a blackbox declared from
    the instantiation site of every XPM macro, AMD primitive or IP the sources use). (module JSON, note)."""
    from flow.checks import elab
    if not elab.find_tool():
        return None, "yosys (OSS CAD Suite 20261112) not found: set FDA_OSS_CAD or install it under ~/.local/opt/oss-cad-suite"
    sv, _vh, hdr, _o = elab.classify(files)
    el = elab.run_sv(sv, hdr, module, [], elab.workdir(), ip_names=ip_names)
    if not el.ok or module not in el.modules:
        return None, f"yosys/slang could not elaborate {module}: " + "; ".join(el.errors)[:300]
    return el.modules, "default parameters; AMD macros, primitives and IP are boxes" + (f" ({len(el.stubbed)} declared from their instantiations)" if el.stubbed else "")


def one_module(j: dict, module: str) -> dict:
    mods = j["modules"]
    m = mods[module]
    m.setdefault("attributes", {})["top"] = "00000000000000000000000000000001"
    return {"creator": j.get("creator", ""), "modules": {module: m}}


def builtin_svg(j: dict, module: str) -> str:
    """A plain layered drawing: ports on the left and right, one box per cell, a line per driver-to-sink connection."""
    m = j["modules"][module]
    drv: dict[int, str] = {}
    sinks: dict[int, list[str]] = {}
    nodes: dict[str, dict] = {}
    alias: dict[int, int] = {}                # $buf cells only rename a net: their output bit is their input bit
    for c in m["cells"].values():
        if c["type"] == "$buf":
            for a, y in zip(c["connections"].get("A", []), c["connections"].get("Y", [])):
                if isinstance(a, int) and isinstance(y, int):
                    alias[y] = a

    def rb(b: Any) -> Any:
        while isinstance(b, int) and b in alias:
            b = alias[b]
        return b
    for pn, p in m["ports"].items():
        nid = f"P:{pn}"
        nodes[nid] = {"label": f"{pn}[{len(p['bits'])}]" if len(p["bits"]) > 1 else pn, "kind": "in" if p["direction"] == "input" else "out"}
        for b in map(rb, p["bits"]):
            if isinstance(b, int):
                (drv.__setitem__(b, nid) if p["direction"] == "input" else sinks.setdefault(b, []).append(nid))
    for cn, c in m["cells"].items():
        if c["type"] == "$buf":
            continue
        nid = f"C:{cn}"
        nodes[nid] = {"label": c["type"].lstrip("$").split("$")[0], "sub": cn.lstrip("$")[:28], "kind": "cell"}
        for pn, bits in c["connections"].items():
            dirn = c.get("port_directions", {}).get(pn, "input")
            for b in map(rb, bits):
                if isinstance(b, int):
                    (drv.__setitem__(b, nid) if dirn == "output" else sinks.setdefault(b, []).append(nid))
    edges = {(drv[b], s) for b, ss in sinks.items() if b in drv for s in ss if drv[b] != s}
    depth = {n: 0 for n in nodes}
    for _ in range(40):
        ch = False
        for a, b in edges:
            if nodes[b]["kind"] != "in" and depth[b] < depth[a] + 1 and depth[a] < 39:
                depth[b] = depth[a] + 1
                ch = True
        if not ch:
            break
    outs = [n for n in nodes if nodes[n]["kind"] == "out"]
    mx = max([depth[n] for n in nodes if nodes[n]["kind"] != "out"] + [0]) + 1
    for n in outs:
        depth[n] = mx
    cols: dict[int, list[str]] = {}
    for n in nodes:
        cols.setdefault(depth[n], []).append(n)
    W, H, GX, GY = 150, 30, 70, 14
    pos = {}
    for d, ns in cols.items():
        for i, n in enumerate(sorted(ns, key=lambda x: nodes[x]["label"])):
            pos[n] = (20 + d * (W + GX), 20 + i * (H + GY))
    wd = 40 + (mx + 1) * (W + GX)
    ht = 40 + max(len(v) for v in cols.values()) * (H + GY)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {wd} {ht}" width="{wd}" height="{ht}" font-family="sans-serif" font-size="11">',
         '<rect width="100%" height="100%" fill="#fff"/>']
    for a, b in sorted(edges):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        o.append(f'<path d="M{x1 + W},{y1 + H / 2} C{x1 + W + 40},{y1 + H / 2} {x2 - 40},{y2 + H / 2} {x2},{y2 + H / 2}" fill="none" stroke="#8a97a6" stroke-width="0.8"/>')
    for n, (x, y) in pos.items():
        nd = nodes[n]
        fill = "#eef3f8" if nd["kind"] == "cell" else "#f3efe6"
        o.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="3" fill="{fill}" stroke="#333"/>'
                 f'<text x="{x + 5}" y="{y + 13}" fill="#111">{esc(nd["label"])[:24]}</text>'
                 + (f'<text x="{x + 5}" y="{y + 25}" fill="#666" font-size="9">{esc(nd["sub"])}</text>' if nd.get("sub") else ""))
    o.append("</svg>")
    return "\n".join(o)


def schematic_sources(srcs: list[Path]) -> tuple[list[Path], str | None]:
    """``(files the schematic drawer reads, the fail-closed text for the files it does not)``: Yosys with the slang front end reads
    SystemVerilog and Verilog; a VHDL file is named in the text (brief 153), never dropped silently."""
    from flow import sources
    return [p for p in srcs if p.suffix in (".sv", ".v")], sources.no_reader(srcs, {"sv"}, "the schematic drawer (Yosys with the slang front end)")


def make_schematic(files: list[Path], module: str, out: Path, ip_names: set[str], use_ns: bool = True) -> dict:
    d = out / "schematics"
    d.mkdir(parents=True, exist_ok=True)
    jf = d / f"{module}.json"
    mods, note = yosys_modules(files, module, ip_names)
    if mods is None:
        return {"module": module, "ok": False, "note": note}
    j = {"modules": mods}
    ncell = sum(1 for c in mods[module]["cells"].values() if c["type"] != "$buf")
    if ncell > MAX_SCHEMATIC_CELLS:
        return {"module": module, "ok": False, "note": f"{ncell} cells at one level: too many to draw; pick a smaller module with --schematic"}
    one = one_module(j, module)
    jf.write_text(json.dumps(one))
    svg = d / f"{module}.svg"
    ns = netlistsvg_path() if use_ns else None
    tool = "built-in drawing"
    if ns:
        r = subprocess.run([ns, str(jf), "-o", str(svg)], capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and svg.is_file():
            tool = "netlistsvg"
        else:
            ns = None
            errl = [x for x in r.stderr.splitlines() if "Error" in x] or r.stderr.strip().splitlines() or ["failed"]
            why = errl[0].strip()[:100]
            tool = f"built-in drawing (netlistsvg failed: {why})"
    if not ns:
        svg.write_text(builtin_svg(one, module))
    jf.unlink()
    return {"module": module, "ok": True, "cells": ncell, "tool": tool, "note": note, "svg": f"schematics/{module}.svg"}


# --- the index page -------------------------------------------------------------------------------------------------------------------
def _num(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else f"{v}"


def render_tree(n: dict, cols: list[str], total_lut: int, idx: dict, depth: int = 0) -> str:
    v = n["vals"]
    lut = v.get("Total LUTs", 0)
    w = max(1, int(120 * lut / total_lut)) if total_lut and lut else 0
    mod = strip_param(n["module"])
    link = ""
    if mod in idx:
        f, ln = idx[mod]
        link = f' <a href="src/{src_name(f)}#L{ln}">{esc(mod)} ({esc(Path(f).name)}:{ln})</a>'
    else:
        link = f' <span class="mut">{esc(n["module"])}</span>'
    nums = " ".join(f"{k.replace('Total ', '')} {_num(v.get(k, 0))}" for k in ("Total LUTs", "FFs", "RAMB36", "RAMB18", "URAM", "DSP Blocks") if v.get(k))
    head = f'<span class="nm">{esc(n["name"])}</span>{link} <span class="mut">{esc(nums)}</span> <span class="bar" style="width:{w}px"></span>'
    if not n["children"]:
        return f'<div class="row" style="margin-left:14px" data-s="{esc((n["path"] + " " + n["module"]).lower())}">{head}</div>'
    kids = "".join(render_tree(c, cols, total_lut, idx, depth + 1) for c in sorted(n["children"], key=lambda c: -c["vals"].get("Total LUTs", 0)))
    return f'<details{" open" if depth < 2 else ""} data-s="{esc((n["path"] + " " + n["module"]).lower())}"><summary>{head}</summary>{kids}</details>'


def write_views(b: Any, out: Path, cps: dict, st: dict, schematic_modules: list[str]) -> dict:
    reports: list[str] = []
    files = list(b.prep.get("files", []))
    srcs = [p for p in b.listed("sources") if p.is_file()]
    idx = module_index(b.root, [str(p.relative_to(b.root)) if str(p).startswith(str(b.root)) else str(p) for p in srcs])
    changed = set(st["changed_files"])
    src_done = write_sources(b.root, [str(p.relative_to(b.root)) for p in srcs if str(p).startswith(str(b.root))] + [f for f in files if f.endswith(".xdc")], out, changed)
    body = [f"<h1>{esc(b.design_rel)} <span class='mut'>({esc(b.variant)})</span></h1>",
            f"<p class='mut'>Read-only view of build {esc(st['build_stamp'])} (ID {esc(st['build_id'])}), Vivado {esc(st['vivado'])}, part {esc(b.prep['part'])}, top <code>{esc(b.prep['top'])}</code>. "
            "Made from the build's own reports; open the checkpoints in Vivado for the full netlist, device and timing views (INSPECT.md).</p>"]
    if st["warnings"]:
        body += [f'<div class="warn"><b>Check before you trust this:</b> {esc(w)}</div>' for w in st["warnings"]]
    else:
        body += ['<p class="ok">The tree matches this build: every input file equals the build manifest and the commit is unchanged.</p>']
    body += [f"<p class='mut'>Git commit of the build: <code>{esc(st['recorded_commit'])}</code>{' (with uncommitted changes)' if st['recorded_dirty'] else ''}. A checkpoint is a snapshot of that commit, not of today's RTL.</p>"]
    body += ["<h2>Checkpoints</h2><div class='scroll'><table><tr><th class='nw'>Stage</th><th class='nw'>File</th><th>Holds</th><th class='nw'>Size</th></tr>"
             + "".join(f"<tr><td class='nw'>{esc(s)}</td><td class='mono nw'>{esc(c['file'].name)}</td><td>{esc(c['what'])}</td><td class='n nw'>" + (f"{c['bytes'] / 1e6:.1f} MB" if c["exists"] else "not in this build") + "</td></tr>" for s, c in cps.items())
             + "</table></div>"]
    # hierarchy
    tree = None
    up = b.dir / "utilization_hier.rpt"
    if up.is_file():
        reports.append(up.name)
        cols, rows = parse_util_hier(up.read_text(errors="replace"))
        tree = build_tree(rows)
    if tree:
        tot = tree["vals"].get("Total LUTs", 0)
        body += ["<h2>Hierarchy and utilisation</h2>",
                 "<p class='mut'>Instances, largest first, from <code>utilization_hier.rpt</code> (routed). Numbers include the instance's children. "
                 "Module names link to the RTL line where the module starts. <input type='search' id='q' placeholder='filter by instance or module'></p>",
                 '<div id="tree">' + render_tree(tree, cols, tot, idx) + "</div>",
                 "<script>document.getElementById('q').addEventListener('input',function(e){var v=e.target.value.toLowerCase();"
                 "document.querySelectorAll('#tree [data-s]').forEach(function(n){n.style.display=(!v||n.dataset.s.indexOf(v)>=0)?'':'none';"
                 "if(v&&n.tagName==='DETAILS'&&n.dataset.s.indexOf(v)>=0)n.open=true;});});</script>"]
    else:
        body += ["<h2>Hierarchy and utilisation</h2><p class='mut'>This build has no utilization_hier.rpt (it did not reach the post-route reports).</p>"]
    hier = flat_hier(tree)
    # timing
    tp = []
    for fn, label in (("timing_worst_setup.rpt", "setup"), ("timing_worst_hold.rpt", "hold")):
        f = b.dir / fn
        if f.is_file():
            reports.append(fn)
            tp += [(label, p) for p in parse_paths(f.read_text(errors="replace"))]
    ts = b.dir / "timing_summary.rpt"
    more = []
    if ts.is_file():
        reports.append(ts.name)
        txt = ts.read_text(errors="replace")
        m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*\n.*\n\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)", txt)
        if m:
            body += [f"<h2>Timing</h2><p>Routed: worst setup slack <b>{m.group(1)} ns</b> (TNS {m.group(2)}, {m.group(3)} failing of {m.group(4)} endpoints), worst hold slack <b>{m.group(5)} ns</b> (THS {m.group(6)}, {m.group(7)} failing of {m.group(8)} endpoints). From <code>timing_summary.rpt</code>.</p>"]
        more = [("setup", p) for p in parse_paths(txt) if p["type"].lower().startswith("setup")][:10]
    if not tp and not more:
        body += ["<h2>Timing</h2><p class='mut'>No timing reports in this build.</p>"]
    elif tp or more:
        if "<h2>Timing</h2>" not in "".join(body):
            body += ["<h2>Timing</h2>"]
        body += ["<h3>The worst path of each kind, cell by cell</h3>"]
        for label, p in tp:
            body += [path_html(p, label, hier, idx)]
        if more:
            body += ["<h3>Worst setup paths of the timing summary (up to 10)</h3><div class='scroll'><table><tr><th>Slack</th><th>Group</th><th>From</th><th>To</th><th>Levels</th><th>RTL (from module to module)</th></tr>"
                     + "".join(f"<tr><td class='n'>{p['slack']:+.3f}</td><td>{esc(p['group'])}</td><td class='mono'>{esc(p['source'])}</td><td class='mono'>{esc(p['dest'])}</td><td>{esc(p['levels'])}</td><td>{mod_link(p['source'], hier, idx)} to {mod_link(p['dest'], hier, idx)}</td></tr>" for _, p in more)
                     + "</table></div>"]
    xp = b.dir / "xprobe.json"
    if xp.is_file():
        from flow import xprobe
        reports.append(xp.name)
        x = json.loads(xp.read_text())
        s = xprobe.summary(x, per_group=2)
        body += ["<h3>Cross-probe (xprobe.json): RTL file and line, clock region, per clock group</h3><ul>" + "".join(f"<li>{esc(p['text'])}</li>" for p in s["paths"]) + "</ul>"]
        body += ["<div class='scroll'>" + xprobe.render_svg(x) + "</div>"]
    # schematics
    sch, notes = [], []
    mods = schematic_modules or [b.prep["top"]]
    src_files, _unread = schematic_sources(srcs)
    if _unread:                                         # brief 153: a VHDL design gets a said-so note, not an empty schematic list
        notes.append(_unread)
    ip_names = {p.stem for p in (b.dir / "ip").rglob("*.xci")} if (b.dir / "ip").is_dir() else set()
    for mname in mods:
        r = make_schematic(src_files, mname, out, ip_names)
        sch.append(r)
        if not r["ok"]:
            notes.append(f"{mname}: {r['note']}")
    body += ["<h2>Schematics</h2><p class='mut'>One module, one level deep (its instances are boxes), elaborated from the RTL in today's tree, not the netlist Vivado made. "
             "Add modules with <code>--schematic MODULE</code>.</p>"
             + (f"<p class='bad'>{esc(_unread)}</p>" if _unread else "") + "<ul>"]
    for r in sch:
        if r["ok"]:
            body.append(f"<li><a href='{r['svg']}'>{esc(r['module'])}</a> <span class='mut'>({r['cells']} cells, {r['tool']}, {esc(r['note'])})</span></li>")
        else:
            body.append(f"<li>{esc(r['module'])}: <span class='mut'>{esc(r['note'])}</span></li>")
    body += ["</ul>"]
    body += ["<h2>Sources</h2><ul>" + "".join(f"<li><a href='src/{src_name(r)}'>{esc(r)}</a>" + (" <span class='bad'>differs from the build</span>" if r in changed else "") + "</li>" for r in src_done) + "</ul>"]
    (out / "index.html").write_text(PAGE.format(title=f"Inspect {esc(b.name)}", css=CSS, body="\n".join(body)))
    return {"reports": reports, "schematics": [r["module"] for r in sch if r["ok"]], "notes": notes, "sources": len(src_done)}


def mod_link(pin: str, hier: list[tuple[str, str]], idx: dict) -> str:
    mod = strip_param(resolve_module(pin, hier))
    if mod in idx:
        f, ln = idx[mod]
        return f'<a href="src/{src_name(f)}#L{ln}">{esc(mod)} ({esc(Path(f).name)}:{ln})</a>'
    return esc(mod or "-")


def path_html(p: dict, label: str, hier: list, idx: dict) -> str:
    rows = "".join(f"<tr><td class='mono nw'>{esc(c['site'])}</td><td class='nw'>{esc(c['type'])}</td><td class='n nw'>{c['incr']:.3f}</td><td class='n nw'>{c['arrival']:.3f}</td><td class='mono'>{esc(c['pin'])}</td></tr>" for c in p["cells"])
    cls = "bad" if p["slack"] < 0 else "ok"
    return (f"<details open><summary><b>{esc(label)}</b> slack <span class='{cls}'>{p['slack']:+.3f} ns</span> ({esc(p['met'])}), group {esc(p['group'])}, "
            f"{esc(p['src_clk'])} to {esc(p['dst_clk'])}, requirement {esc(p['requirement'])}, {esc(p['levels'])}</summary>"
            f"<p class='mono'>from {esc(p['source'])} ({mod_link(p['source'], hier, idx)})<br>to {esc(p['dest'])} ({mod_link(p['dest'], hier, idx)})<br>"
            f"data path {esc(p['data_delay'])}; clock skew {esc(p['skew'])} ns</p>"
            f"<div class='scroll'><table><tr><th class='nw'>Site</th><th class='nw'>Cell</th><th class='nw'>Incr (ns)</th><th class='nw'>Arrival (ns)</th><th>Pin</th></tr>{rows}</table></div></details>")
