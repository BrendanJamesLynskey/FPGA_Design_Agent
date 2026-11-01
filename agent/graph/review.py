"""Stage review pages (owner feature, brief 05b).

At each stage end the agent writes ``build/review/<nn>_<stage>.html``: one self-contained page (no external
assets), sober monochrome, light and dark by ``prefers-color-scheme``. It shows the stage's inputs and outputs,
the spec summary, the block diagram from ``ARCHITECTURE.md``, the testplan and coverage, a waveform snippet (from a
VCD, if the stage produced one), the gate results, and timing / utilisation / power, all read from the files the
flow wrote (never from the model's account). ``review_index.html`` links every stage and records who approved
what.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import yaml

CSS = """
:root{--bg:#fff;--fg:#111;--mut:#555;--line:#ccc;--pass:#111;--fail:#111;--chip:#eee}
@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#aaa;--line:#444;--chip:#222}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:16px}
main{max-width:980px;margin:auto}h1{font-size:1.4em;margin:.2em 0}h2{font-size:1.1em;border-bottom:1px solid var(--line);
padding-bottom:4px;margin-top:1.6em}table{border-collapse:collapse;width:100%;font-size:.92em}td,th{border:1px solid var(--line);
padding:4px 6px;text-align:left;vertical-align:top}pre{background:var(--chip);padding:8px;overflow-x:auto;font-size:.85em}
.mut{color:var(--mut)}.chip{display:inline-block;padding:0 6px;border:1px solid var(--fg);border-radius:3px;font-size:.85em}
.fail{background:var(--fg);color:var(--bg)}svg{max-width:100%;height:auto}svg text{fill:var(--fg);font:11px monospace}
svg .w{stroke:var(--fg);fill:none;stroke-width:1.2}a{color:var(--fg)}.wrap{overflow-x:auto}
"""


def _e(x: Any) -> str:
    return html.escape(str(x))


def _table(rows: list[list[Any]], head: list[str] | None = None) -> str:
    h = "<tr>" + "".join(f"<th>{_e(c)}</th>" for c in head) + "</tr>" if head else ""
    body = "".join("<tr>" + "".join(f"<td>{c if isinstance(c, Markup) else _e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="wrap"><table>{h}{body}</table></div>'


class Markup(str):
    pass


def chip(ok: bool | None) -> Markup:
    if ok is None:
        return Markup('<span class="chip">not run</span>')
    return Markup('<span class="chip">PASS</span>' if ok else '<span class="chip fail">FAIL</span>')


def _read(p: Path) -> str | None:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None


def _yaml(p: Path) -> dict:
    """Agent-written YAML may be invalid: the page shows that instead of failing."""
    try:
        v = yaml.safe_load(_read(p) or "")
        return v if isinstance(v, dict) else {}
    except yaml.YAMLError as e:
        return {"_invalid": str(e).splitlines()[0]}


def _json(p: Path) -> Any:
    t = _read(p)
    try:
        return json.loads(t) if t else None
    except ValueError:
        return None


def block_diagram(arch: str | None) -> str:
    """The architecture note's block diagram: the first fenced block under a heading containing 'diagram'."""
    if not arch:
        return '<p class="mut">No ARCHITECTURE.md yet.</p>'
    m = re.search(r"^#+[^\n]*diagram[^\n]*\n+```[^\n]*\n(.*?)```", arch, re.I | re.S | re.M)
    if not m:
        return '<p class="mut">ARCHITECTURE.md has no block diagram section.</p>'
    return f"<pre>{_e(m.group(1))}</pre>"


def vcd_svg(vcd: Path, signals: int = 6, max_t: int | None = None) -> str:
    """A small waveform from a VCD: the first ``signals`` 1-bit signals, as step lines."""
    text = _read(vcd)
    if not text:
        return '<p class="mut">No waveform for this stage.</p>'
    ids, order = {}, []
    for m in re.finditer(r"\$var\s+\w+\s+1\s+(\S+)\s+(\S+)", text):
        if m.group(1) not in ids:
            ids[m.group(1)] = m.group(2)
            order.append(m.group(1))
    t, ch = 0, {k: [] for k in order}
    for line in text.split("$enddefinitions", 1)[-1].splitlines():
        line = line.strip()
        if line.startswith("#"):
            t = int(line[1:] or 0)
        elif len(line) >= 2 and line[0] in "01xz" and line[1:] in ch:
            ch[line[1:]].append((t, line[0]))
    order = sorted(order, key=lambda k: -len(ch[k]))[:signals]           # the most active signals
    end = max_t or max([t] + [c[-1][0] for c in ch.values() if c]) or 1
    W, H, L = 860, 26, 150
    parts = []
    for i, k in enumerate(order):
        y0 = 10 + i * H
        pts, last = [], None
        for tt, v in ch[k]:
            if tt > end:
                break
            x = L + (W - L) * tt / end
            y = y0 + (2 if v == "1" else 18)
            if last is not None:
                pts.append(f"{x:.1f},{last:.1f}")
            pts.append(f"{x:.1f},{y:.1f}")
            last = y
        if last is not None:
            pts.append(f"{W},{last:.1f}")
        parts.append(f'<text x="4" y="{y0 + 14}">{_e(ids[k][:20])}</text>'
                     f'<polyline class="w" points="{" ".join(pts)}"/>')
    return (f'<svg viewBox="0 0 {W} {10 + len(order) * H}" role="img" aria-label="waveform">{"".join(parts)}</svg>'
            f'<p class="mut">{_e(vcd.name)}, 0 to {end} time units, the {len(order)} most active one-bit signals.</p>')


def write_page(design: Path, n: int, stage: str, info: dict[str, Any]) -> Path:
    """``info``: inputs (list), outputs (list), gates (list of [name, ok, detail]), approval (dict or None),
    visits, limits/used, vcd (path or None), notes (str)."""
    b = design / "build"
    spec = _yaml(design / "spec.yaml")
    gates = _json(b / "base" / "gates.json") or {}
    verif = info.get("verif") or _json(design.parent.parent / "build" / "verif" / "verif_gates.json")
    sec = [f"<h1>Stage {n}: {_e(stage)}</h1><p class=\"mut\">{_e(design.name)}; visit {info.get('visits', 1)}; "
           f"{_e(info.get('time', ''))}</p>"]
    sec.append("<h2>Exit gates</h2>" + _table([[g[0], chip(g[1]), g[2] if len(g) > 2 else ""]
                                               for g in info.get("gates", [])], ["gate", "result", "detail"]))
    sec.append("<h2>Inputs and outputs</h2>" + _table(
        [["inputs", ", ".join(info.get("inputs", [])) or "-"], ["outputs", ", ".join(info.get("outputs", [])) or "-"]]))
    ports = spec.get("ports") or []
    sec.append("<h2>Spec summary</h2>" + _table(
        [["title", spec.get("title", "-")], ["top", spec.get("top", "-")],
         ["clocks", "; ".join(f"{c.get('name')} {c.get('freq_mhz', c.get('frequency', ''))}" for c in
                              (spec.get("clocks") or []) if isinstance(c, dict)) or "-"],
         ["ports", len(ports)], ["open questions", len(spec.get("open_questions") or [])],
         ["resolved questions", len(spec.get("resolved_questions") or [])]]))
    sec.append("<h2>Block diagram</h2>" + block_diagram(_read(design / "ARCHITECTURE.md")))
    tp = _yaml(design / "verif" / "testplan.yaml")
    items = tp.get("items") or tp.get("requirements") or []
    vrows = [["testplan items", len(items) if items else "-"]]
    if tp.get("_invalid"):
        vrows.append(["testplan.yaml", "invalid YAML: " + tp["_invalid"]])
    if isinstance(verif, dict):
        vrows += [["verification reached", verif.get("reached", "-")], ["first failed", verif.get("first_failed", "-")]]
    sec.append("<h2>Testplan and coverage</h2>" + _table(vrows))
    vcd = info.get("vcd")
    sec.append("<h2>Waveform</h2>" + (vcd_svg(Path(vcd)) if vcd else '<p class="mut">No waveform for this stage.</p>'))
    t, u, p, env = (gates.get(k) or {} for k in ("timing", "utilization", "power", "power_environment"))
    if t or u or p:
        sec.append("<h2>Timing, utilisation, power</h2>" + _table([
            ["WNS / TNS (ns)", f"{t.get('wns_ns', '-')} / {t.get('tns_ns', '-')}"],
            ["WHS / THS (ns)", f"{t.get('whs_ns', '-')} / {t.get('ths_ns', '-')}"],
            ["LUT / FF", f"{u.get('lut', '-')} of {u.get('lut_available', '-')} / {u.get('ff', '-')} of {u.get('ff_available', '-')}"],
            ["BRAM / DSP", f"{u.get('bram_tile', '-')} / {u.get('dsp', '-')}"],
            ["power total (W)", f"{p.get('total_w', '-')} (confidence {p.get('confidence', '-')})"],
            ["junction (C)", f"{env.get('junction_c', '-')} at {env.get('ambient_c', '-')} C ambient"]]))
        sec.append('<p class="mut">From build/base/gates.json (flow/gates.py on the Vivado reports).</p>')
    used = info.get("used") or {}
    sec.append("<h2>Budget</h2>" + _table([[k, used.get(k, "-"), (info.get("limits") or {}).get(k, "-")]
                                           for k in ("turns", "seconds", "usd")], ["", "used", "limit"]))
    a = info.get("approval")
    sec.append("<h2>Review</h2>" + (_table([["decision", a.get("decision")], ["by", a.get("by")],
                                            ["note", a.get("note") or "-"]]) if a else '<p class="mut">Pending.</p>'))
    if info.get("notes"):
        sec.append(f"<h2>Notes</h2><pre>{_e(info['notes'])}</pre>")
    out = b / "review" / f"{n:02d}_{stage}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_page(f"{n:02d} {stage}", "".join(sec)))
    return out


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>'
            f"<body><main>{body}</main></body></html>\n")


def write_index(design: Path, history: list[dict[str, Any]]) -> Path:
    """``history``: one dict per stage visit: n, stage, page, passed, approval {decision, by, note}."""
    rows = [[h["n"], Markup(f'<a href="{_e(Path(h["page"]).name)}">{_e(h["stage"])}</a>'), chip(h.get("passed")),
             (h.get("approval") or {}).get("decision", "-"), (h.get("approval") or {}).get("by", "-"),
             (h.get("approval") or {}).get("note") or ""] for h in history]
    out = design / "build" / "review" / "review_index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_page("Review index", f"<h1>Review: {_e(design.name)}</h1>" +
                         _table(rows, ["#", "stage", "gates", "decision", "by", "note"])))
    return out
