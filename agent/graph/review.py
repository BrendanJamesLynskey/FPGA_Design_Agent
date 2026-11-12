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

_ROOT = Path(__file__).resolve().parents[2]

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
svg .bus{stroke:var(--fg);fill:none;stroke-width:1.2}svg .bv{font:10px monospace;text-anchor:middle}
.diff{font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;white-space:pre;overflow-x:auto;background:var(--chip);padding:6px;margin:4px 0}
.diff span.add{background:var(--add)}.diff span.del{background:var(--del)}.diff .hunk{color:var(--mut)}
.k{font-weight:bold}.c{color:var(--mut);font-style:italic}.n{text-decoration:underline dotted}.s{text-decoration:underline}
.code{font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;white-space:pre;overflow-x:auto;background:var(--chip);padding:6px}
.who-owner{font-weight:bold}.who-auto{font-style:italic}
"""
CSS = CSS.replace(":root{--bg:#fff;--fg:#111;--mut:#555;--line:#ccc;--pass:#111;--fail:#111;--chip:#eee}",
                  ":root{--bg:#fff;--fg:#111;--mut:#555;--line:#ccc;--pass:#111;--fail:#111;--chip:#eee;--add:#d4d4d4;--del:#bbb}")
CSS = CSS.replace("@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#aaa;--line:#444;--chip:#222}}",
                  "@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#aaa;--line:#444;--chip:#222;--add:#3a3a3a;--del:#555}}")


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


_SV_KW = set("module endmodule input output inout logic wire reg always always_ff always_comb always_latch assign begin end if "
             "else case casez casex endcase default for generate endgenerate genvar parameter localparam posedge negedge "
             "or and function endfunction task endtask initial typedef enum int integer bit signed unsigned import "
             "package endpackage interface endinterface".split())
_SV_TOK = re.compile(r"(?P<c>//[^\n]*|/\*.*?\*/)|(?P<s>\"[^\"\n]*\")|(?P<n>\b\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+\b|\b\d[\d_]*\b)"
                     r"|(?P<w>\b[A-Za-z_]\w*\b)", re.S)


def sv_highlight(text: str) -> str:
    """HTML for SystemVerilog text: keywords, comments, strings and numbers in classes (no external JS)."""
    out, pos = [], 0
    for m in _SV_TOK.finditer(text):
        out.append(_e(text[pos:m.start()]))
        kind = m.lastgroup
        tok = _e(m.group())
        if kind == "w":
            out.append(f'<span class="k">{tok}</span>' if m.group() in _SV_KW else tok)
        else:
            out.append(f'<span class="{kind}">{tok}</span>')
        pos = m.end()
    out.append(_e(text[pos:]))
    return "".join(out)


def diff_html(files: list[dict[str, str]]) -> str:
    """A unified diff per file: added and removed lines marked by background, code highlighted."""
    if not files:
        return '<p class="mut">No change to the RTL, constraints or architecture since the previous stage.</p>'
    parts = []
    for f in files:
        lines = []
        for l in f["diff"].splitlines():
            if l.startswith(("diff ", "index ", "--- ", "+++ ", "new file", "deleted file")):
                continue
            if l.startswith("@@"):
                lines.append(f'<span class="hunk">{_e(l)}</span>')
            elif l.startswith("+"):
                lines.append(f'<span class="add">+{sv_highlight(l[1:])}</span>')
            elif l.startswith("-"):
                lines.append(f'<span class="del">-{sv_highlight(l[1:])}</span>')
            else:
                lines.append(f" {sv_highlight(l[1:])}" if l.startswith(" ") else _e(l))
        parts.append(f'<h3>{_e(f["path"])}</h3><div class="diff">' + "\n".join(lines) + "</div>")
    return "".join(parts)


def parse_vcd(text: str) -> tuple[dict[str, dict], int]:
    """{id: {name, width, changes: [(time, value)]}} and the last time. Scalars ('0'/'1'/'x'/'z') and vectors
    ('b1010 id' as a binary string, hex shown by the renderer)."""
    sig: dict[str, dict] = {}
    for m in re.finditer(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(\S+)(?:\s+\[[^\]]*\])?\s+\$end", text):
        w, i, name = int(m.group(1)), m.group(2), m.group(3)
        sig.setdefault(i, {"name": name, "width": w, "changes": []})
    t = 0
    for line in text.split("$enddefinitions", 1)[-1].splitlines():
        line = line.strip()
        if not line or line.startswith("$"):
            continue
        if line[0] == "#":
            t = int(line[1:] or 0)
        elif line[0] in "bB" and " " in line:
            v, i = line[1:].split(None, 1)
            if i in sig:
                sig[i]["changes"].append((t, v.lower()))
        elif line[0] in "01xXzZ" and line[1:] in sig:
            sig[line[1:]]["changes"].append((t, line[0].lower()))
    return sig, t


def _hex(v: str) -> str:
    return f"{int(v, 2):x}" if set(v) <= {"0", "1"} else ("x" if "x" in v else "z")


def vcd_svg(vcd: Path, signals: int = 8, max_t: int | None = None) -> str:
    """A waveform from a VCD (an FST is converted with fst2vcd if present): one-bit signals as step lines, **buses
    as boxes carrying their value in hex**, the most active signals first."""
    if vcd.suffix == ".fst":
        import shutil
        import subprocess
        import tempfile
        exe = shutil.which("fst2vcd")
        if not exe:
            return '<p class="mut">An FST waveform needs fst2vcd to be shown; it is not installed here.</p>'
        tmp = Path(tempfile.mkdtemp()) / "w.vcd"
        subprocess.run([exe, "-o", str(tmp), str(vcd)], capture_output=True)
        vcd = tmp
    text = _read(vcd)
    if not text:
        return '<p class="mut">No waveform for this stage.</p>'
    sig, last = parse_vcd(text)
    order = sorted((i for i in sig if sig[i]["changes"] and sig[i]["width"] <= 64), key=lambda k: -len(sig[k]["changes"]))[:signals]
    end = max_t or last or 1
    W, H, L = 860, 28, 150
    parts = []
    for row, k in enumerate(order):
        s = sig[k]
        y0 = 10 + row * H
        label = f'{s["name"][:18]}{"[" + str(s["width"] - 1) + ":0]" if s["width"] > 1 else ""}'
        parts.append(f'<text x="4" y="{y0 + 15}">{_e(label)}</text>')
        ch = [c for c in s["changes"] if c[0] <= end]
        if s["width"] == 1:
            pts, lasty = [], None
            for tt, v in ch:
                x = L + (W - L) * tt / end
                y = y0 + (2 if v == "1" else 20)
                if lasty is not None:
                    pts.append(f"{x:.1f},{lasty:.1f}")
                pts.append(f"{x:.1f},{y:.1f}")
                lasty = y
            if lasty is not None:
                pts.append(f"{W},{lasty:.1f}")
            parts.append(f'<polyline class="w" points="{" ".join(pts)}"/>')
        else:
            for j, (tt, v) in enumerate(ch):
                x0 = L + (W - L) * tt / end
                x1 = L + (W - L) * (ch[j + 1][0] if j + 1 < len(ch) else end) / end
                if x1 - x0 < 0.5:
                    continue
                parts.append(f'<polygon class="bus" points="{x0 + 2:.1f},{y0 + 11} {x0 + 5:.1f},{y0 + 2} {max(x1 - 3, x0 + 5):.1f},{y0 + 2} '
                             f'{max(x1 - 0.5, x0 + 6):.1f},{y0 + 11} {max(x1 - 3, x0 + 5):.1f},{y0 + 20} {x0 + 5:.1f},{y0 + 20}"/>')
                if x1 - x0 > 7 * (len(_hex(v)) + 1):
                    parts.append(f'<text class="bv" x="{(x0 + x1) / 2:.1f}" y="{y0 + 15}">{_e(_hex(v))}</text>')
    nb = sum(1 for k in order if sig[k]["width"] > 1)
    return (f'<svg viewBox="0 0 {W} {10 + len(order) * H}" role="img" aria-label="waveform">{"".join(parts)}</svg>'
            f'<p class="mut">{_e(vcd.name)}, 0 to {end} time units: the {len(order)} most active signals, '
            f'{nb} of them buses shown as hex values.</p>')


def constraints_html(design: Path, board_dir: Path) -> str:
    """design.xdc in full, and each pin traced to the board inventory (boards/<board>/inventory.yaml)."""
    xdc = _read(design / "design.xdc")
    if not xdc:
        return '<p class="mut">No design.xdc yet.</p>'
    inv = _yaml(board_dir / "inventory.yaml")
    master, by_section = {}, {}
    try:
        import sys as _sys
        _sys.path.insert(0, str(_ROOT))
        from tools.inventory_check import parse_xdc            # the checker CI runs on the inventory
        ports, sections = parse_xdc((board_dir / str(inv.get("master_xdc", "master.xdc"))).read_text())
        master = {pin.upper(): (port, std) for port, (pin, std) in ports.items()}
        for sec, plist in sections.items():
            for pt in plist:
                by_section[pt] = sec
    except Exception:                                          # noqa: BLE001  (no inventory: the table says so)
        pass
    entries = {e.get("xdc_section"): e for k in ("core_io", "peripherals") for e in (inv.get(k) or []) if isinstance(e, dict)}
    rows = []
    for m in re.finditer(r"set_property\s+(?:-dict\s*\{[^}]*?PACKAGE_PIN\s+(\w+)[^}]*\}|PACKAGE_PIN\s+(\w+))\s*\[get_ports\s*\{?\s*([^\]\}\s]+\]?)", xdc):
        pin, port = m.group(1) or m.group(2), m.group(3)
        mp = master.get(pin.upper())
        ent = entries.get(by_section.get(mp[0])) if mp else None
        rows.append([port, pin, f"master XDC port {mp[0]} ({mp[1]})" if mp else "not in the master XDC",
                     f"{ent['id']}: {str(ent.get('what', ''))[:80]}" if ent else "-"])
    tbl = _table(rows, ["port", "pin", "master XDC", "board inventory entry"]) if rows else '<p class="mut">No PACKAGE_PIN lines.</p>'
    return f'<div class="code">{_e(xdc)}</div>' + "<h3>Pins traced to the board inventory</h3>" + tbl


def corner_cases_html(verif: dict | None) -> str:
    """Which requirement each test discharges and which coverage bins it hit (from verif_gates' coverage_detail)."""
    cd = (verif or {}).get("coverage_detail")
    if not cd:
        return '<p class="mut">No coverage detail yet (V2 evidence has not run).</p>'
    rows = []
    for r in cd.get("requirements", []):
        bins = "; ".join(f"{n} {v['hit']}/{v['total']}" for n, v in (r.get("bins") or {}).items()) or "-"
        rows.append([r["id"], ", ".join(r.get("tests") or []) or "-", bins])
    unhit = (verif.get("stages", {}).get("V3", {}).get("checks", {}).get("functional_bins_unhit", {}) or {}).get("value") or []
    return _table(rows, ["requirement", "tests that discharge it", "bins hit / total"]) + (
        f'<p class="mut">Unhit bins: {_e(", ".join(map(str, unhit)))}</p>' if unhit else "")


def traceability_html(verif: dict | None) -> str:
    rows = (verif or {}).get("traceability")
    if not rows:
        return '<p class="mut">No traceability table yet.</p>'
    return _table([[r["requirement"], r["method"], r["artefact"], chip(True if r["result"] == "pass" else
                    (None if r["result"] == "pending" else False)), r["detail"]] for r in rows],
                  ["requirement", "method", "artefact", "result", "detail"])


def standards_html(res: dict | None) -> str:
    if not res or "rules" not in res:
        return '<p class="mut">The standards checker has not run yet.</p>'
    rows = []
    for r in res["rules"]:
        st = r["status"]
        c = chip(True if st == "pass" else False if st in ("fail", "not_run") else None) if st != "review_only" \
            else Markup('<span class="chip">review only</span>')
        if st == "skipped":
            continue
        detail = "; ".join(f"{f['file']}:{f['line']} {f['message']}" for f in r["findings"][:4]) or r.get("why_not_run", "")
        rows.append([r["id"], r["title"], c, detail])
    return _table(rows, ["rule", "text", "result", "findings"])


def who_html(rows: list[dict] | None) -> str:
    if not rows:
        return '<p class="mut">Nothing recorded yet.</p>'
    return _table([[r["seq"] + 1, Markup(f'<span class="who-{r["who"]}">{_e(r["who"])}</span>'), r["stage"], r["what"],
                    r.get("detail", "")] for r in rows], ["#", "who", "stage", "what", "detail"])


def _latest_wave(design: Path) -> Path | None:
    waves = sorted([*design.rglob("*.vcd"), *design.rglob("*.fst")], key=lambda p: p.stat().st_mtime)
    return waves[-1] if waves else None


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
    warns = gates.get("warnings") or []
    if warns:       # recorded, not gated (brief 05g): the post-synthesis QoR score
        sec.append("<h2>Warnings (recorded, not gates)</h2>" + _table(
            [[w.get("stage", ""), w.get("name", ""), f"score {w.get('score')} (min {w.get('min')}): {w.get('meaning', '')}",
              w.get("note", "")] for w in warns], ["stage", "warning", "value", "note"]))
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
    sec.append("<h2>RTL diff against the previous stage</h2>" + diff_html(info.get("diff") or []))
    sec.append("<h2>Corner cases hit</h2>" + corner_cases_html(verif if isinstance(verif, dict) else None))
    sec.append("<h2>Traceability: requirement, proof method, artefact, result</h2>"
               + traceability_html(verif if isinstance(verif, dict) else None))
    sec.append("<h2>Design standards (v1.0)</h2>" + standards_html(info.get("standards")))
    sec.append("<h2>Constraints for approval</h2>" + constraints_html(design, _ROOT / "boards" / info.get("board", "nexys_a7_100t")))
    vcd = info.get("vcd") or _latest_wave(design)
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
    sec.append("<h2>Models by role</h2>" + roles_html(info.get("role_models"), info.get("role_usage")))
    a = info.get("approval")
    sec.append("<h2>Review</h2>" + (_table([["decision", a.get("decision")], ["by", a.get("by")],
                                            ["note", a.get("note") or "-"]]) if a else '<p class="mut">Pending.</p>'))
    sec.append("<h2>Who did what</h2>" + who_html(info.get("owner_rows")))
    if info.get("notes"):
        sec.append(f"<h2>Notes</h2><pre>{_e(info['notes'])}</pre>")
    out = b / "review" / f"{n:02d}_{stage}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_page(f"{n:02d} {stage}", "".join(sec)))
    return out


def roles_html(roles: dict | None, usage: list[dict] | None = None) -> str:
    """Which harness and model ran each sub-agent role (05f), with this stage's use of each. The stage machine itself is
    plain code, and the interview oracle always runs on the run's own model (luna by default): neither is a role."""
    if not roles:
        return '<p class="mut">Not recorded.</p>'
    use: dict[str, dict[str, Any]] = {}
    for u in usage or []:
        d = use.setdefault(u["role"], {"turns": 0, "tokens": 0, "wall_s": 0.0, "usd": 0.0, "plan": 0.0})
        d["turns"] += u.get("turns") or 0
        d["tokens"] += u.get("tokens") or 0
        d["wall_s"] += u.get("wall_s") or 0
        d["usd"] += u.get("cost_usd") or 0
        d["plan"] += u.get("plan_cost_estimate_usd") or 0
    rows = [[r, s["harness"], s["model"], s.get("effort") or "CLI default",
             (f"{use[r]['turns']} turns, {use[r]['tokens']} tokens, {use[r]['wall_s']:.0f} s, "
              f"${use[r]['usd']:.4f} reported, ${use[r]['plan']:.4f} plan estimate") if r in use else "-"]
            for r, s in roles.items()]
    return _table(rows, ["role", "harness", "model", "effort", "use this stage"])


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{CSS}</style></head>'
            f"<body><main>{body}</main></body></html>\n")


def trace_matrix_html(t: dict | None) -> str:
    """Brief 53: the traceability matrix (build/trace/trace.json, flow/traceability.py): requirement -> design elements ->
    method -> verifications -> result, then the gates with the ids each is missing."""
    if not t or "requirements" not in t:
        return '<p class="mut">No traceability matrix yet (flow/traceability.py writes build/trace/trace.json at stage 2).</p>'
    res = lambda r: chip(True if r == "pass" else None if r in ("pending",) else False)
    rows = []
    for r in t["requirements"]:
        for i, m in enumerate(r["methods"] or [{"method": "-", "status": "missing", "verifications": []}]):
            ver = "; ".join(f"{v['artefact']} ({v['via']}): {v['result']}" for v in m["verifications"]) or "none"
            rows.append([r["id"] if i == 0 else "", r.get("text", "") if i == 0 else "",
                         ", ".join(r.get("design_elements") or []) or "-" if i == 0 else "", m["method"], ver, res(m["status"])])
    s = t.get("artefact_summary") or {}
    gates = [[n, chip(c["pass"]), c.get("why") or "none missing"] for n, c in (t.get("gates") or {}).items()]
    cov = (t.get("coverage") or {}).get("summary") or {}
    covtxt = "; ".join(f"{k} {v.get('hit')}/{v.get('points')}" for k, v in cov.items() if isinstance(v, dict) and v.get("points"))
    holes = (t.get("coverage") or {}).get("holes") or []
    return (_table(rows, ["requirement", "text", "design elements", "method", "verifications (how linked)", "result"])
            + f'<p class="mut">{_e(t.get("note", ""))} Artefacts: {s.get("total", "-")} ({s.get("citing", "-")} cite a '
              f'requirement, {s.get("robustness", 0)} robustness, {s.get("structural", 0)} structural, {s.get("untagged", 0)} '
              f'untagged). Coverage: {_e(covtxt or "not measured")}; {len(holes)} hole(s), '
              f'{sum(1 for h in holes if not h.get("justified_by"))} without a justification. Deferred: '
              f'{_e(", ".join(t.get("defer") or []) or "none")}.</p>'
            + "<h3>Traceability gates</h3>" + _table(gates, ["gate", "result", "detail"]))


def write_index(design: Path, history: list[dict[str, Any]], role_models: dict | None = None) -> Path:
    """``history``: one dict per stage visit: n, stage, page, passed, approval {decision, by, note}."""
    rows = [[h["n"], Markup(f'<a href="{_e(Path(h["page"]).name)}">{_e(h["stage"])}</a>'), chip(h.get("passed")),
             (h.get("approval") or {}).get("decision", "-"), (h.get("approval") or {}).get("by", "-"),
             (h.get("approval") or {}).get("note") or ""] for h in history]
    out = design / "build" / "review" / "review_index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_page("Review index", f"<h1>Review: {_e(design.name)}</h1>" +
                         _table(rows, ["#", "stage", "gates", "decision", "by", "note"])
                         + "<h2>Traceability matrix</h2>" + trace_matrix_html(_json(design / "build" / "trace" / "trace.json"))
                         + ("<h2>Models by role</h2>" + roles_html(role_models) if role_models else "")))
    return out
