"""The Showcase section (brief 61): the index page and one page per showcase project, from site/showcase/*.yaml.

The data contract is documented in docs/showcase_pages.md. In short:
- one YAML file per project in site/showcase/ (a file whose name starts with "_" is ignored);
- `status` is `in_progress`, `planned` or `published`; only a `published` project gets a page, and only a published
  project may carry numbers;
- every number in a published page's text is a `{name}` placeholder filled from a committed result file by a value
  expression (the same forms as the expertise page, `python3 -c "import expertise; print(expertise.EXPR)"`);
- the hero is one of the shared graphics kit's kinds (`wave`, `hist`, `shmoo`), read from a committed JSON file in
  the normalised form the kit draws (validated here, so a page cannot ship a hero the kit cannot draw).

`build()` returns what site/data/showcase.json holds; `page_body()` renders a project page; `index_body()` the index.
"""
from __future__ import annotations

import glob
import html
import json
import re
from pathlib import Path

import yaml

import expertise

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIR = HERE / "showcase"
REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
E = html.escape

STATUS = {"published": "Measured", "in_progress": "In progress", "planned": "Planned"}
KINDS = ("wave", "hist", "shmoo")
#: words a showcase's text may hold that look like numbers but are names (parts, boards, standards, releases)
PROSE_OK = re.compile(expertise.PROSE_OK.pattern + r"|AXI4-Lite|AXI4-Stream|xc7a100tcsg324-1|A7-100T|Nexys A7|KR260|KV260|"
                      r"64b/66b|8b/10b|1G|10G|25G|RGMII|SFP\+|VCCINT|VCCAUX|VCCBRAM|DDR\d|JTAG|UART|XADC|SYSMON")
REQUIRED = {"published": ["id", "title", "one_line", "board", "part", "headline", "hero", "story", "evidence", "limits"],
            "in_progress": ["id", "title", "one_line", "board", "what_it_will_show"],
            "planned": ["id", "title", "one_line"]}
STORY = ["problem", "how", "results", "agent"]
#: the evidence drawer's groups, in order; a published page must have at least one item of each
EVIDENCE = {"record": "Run records and raw captures", "conditions": "Operating conditions (die temperature and rails)",
            "versions": "Tool versions and build ID", "requirements": "Requirements traced"}


class ContractError(ValueError):
    pass


def _numbers(s: str) -> list[str]:
    return expertise.NUM.findall(PROSE_OK.sub(" ", str(s)))


def _no_typed_numbers(where: str, s: str):
    bad = _numbers(re.sub(r"\{\w+\}", " ", str(s)))
    if bad:
        raise ContractError(f"{where}: typed number(s) {bad}; use a {{name}} placeholder with a value expression")


def _fill(where: str, text: str, values: dict) -> str:
    _no_typed_numbers(where, text)
    def one(m):
        k = m.group(1)
        if k not in values:
            raise ContractError(f"{where}: no value named {k}")
        return expertise.fmt(values[k])
    return re.sub(r"\{(\w+)\}", one, str(text))


def _values(spec: dict, where: str) -> dict:
    out = {}
    for k, v in (spec or {}).items():
        if not glob.glob(str(ROOT / v["source"])):
            raise ContractError(f"{where}: value {k}: no file {v['source']}")
        out[k] = expertise.evaluate(v["expr"], {"source": v["source"]})
    return out


def _get(doc, path):
    return expertise._path(doc, path) if path else doc


def hero_data(h: dict, where: str) -> dict:
    """Read and check the hero's normalised data (see docs/showcase_pages.md, "Hero kinds")."""
    if h.get("kind") not in KINDS:
        raise ContractError(f"{where}: hero.kind must be one of {KINDS}")
    p = ROOT / h["source"]
    if not p.exists():
        raise ContractError(f"{where}: hero source {h['source']} does not exist")
    d = _get(json.loads(p.read_text()), h.get("path"))
    k = h["kind"]
    need = {"wave": ["unit", "x", "signals"], "hist": ["unit", "samples", "bins"], "shmoo": ["x", "y", "points"]}[k]
    miss = [n for n in need if n not in d]
    if miss:
        raise ContractError(f"{where}: hero ({k}) data lacks {miss}")
    if k == "wave":
        n = len(d["x"])
        for s in d["signals"]:
            if len(s["v"]) != n or s.get("kind", "bit") not in ("bit", "bus", "wave", "text"):
                raise ContractError(f"{where}: wave signal {s.get('name')} has {len(s['v'])} values for {n} samples or a bad kind")
    if k == "hist":
        if not d["samples"] or not (isinstance(d["bins"], int) and d["bins"] > 1):
            raise ContractError(f"{where}: hist needs samples and an integer bins > 1")
    if k == "shmoo":
        xs, ys = d["x"]["values"], d["y"]["values"]
        for pt in d["points"]:
            if pt["x"] not in xs or pt["y"] not in ys:
                raise ContractError(f"{where}: shmoo point {pt} is off the grid")
    return {"kind": k, "data": d, "source": h["source"]}


def load(directory: Path = DIR) -> list[dict]:
    out = []
    for p in sorted(directory.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        y = yaml.safe_load(p.read_text())
        st = y.get("status")
        if st not in STATUS:
            raise ContractError(f"{p.name}: status must be one of {list(STATUS)}")
        miss = [k for k in REQUIRED[st] if k not in y]
        if miss:
            raise ContractError(f"{p.name}: missing {miss}")
        if not re.fullmatch(r"[a-z0-9_]+", y["id"]):
            raise ContractError(f"{p.name}: id must be lower-case letters, digits and _")
        out.append((p.name, y))
    return out


def resolve(name: str, y: dict) -> dict:
    """One project, with every placeholder filled and the hero read; text fields of unpublished projects may hold no number."""
    st = y["status"]
    r = {"id": y["id"], "title": y["title"], "status": st, "status_label": STATUS[st], "order": y.get("order", 99)}
    if st != "published":
        for k in ("title", "one_line", "what_it_will_show", "board"):
            if k in y:
                _no_typed_numbers(f"{name}: {k}", y[k])
                r[k] = y[k]
        if "part" in y:
            r["part"] = y["part"]
        return r
    vals = _values(y.get("values"), name)
    f = lambda k, t: _fill(f"{name}: {k}", t, vals)
    r.update({"one_line": f("one_line", y["one_line"]), "board": y["board"], "part": y["part"], "headline": f("headline", y["headline"]),
              "vivado": y.get("vivado", "2026.1"), "values": vals})
    r["hero"] = hero_data(y["hero"], name)
    r["hero"]["caption"] = f("hero.caption", y["hero"].get("caption", ""))
    st_ = y["story"]
    miss = [k for k in STORY if k not in st_]
    if miss:
        raise ContractError(f"{name}: story lacks {miss}")
    r["story"] = {"problem": f("story.problem", st_["problem"]), "how": f("story.how", st_["how"]),
                  "results": [f("story.results", t) for t in st_["results"]],
                  "agent": {k: ([f("story.agent", t) for t in v] if isinstance(v, list) else f("story.agent", v)) for k, v in st_["agent"].items()}}
    if "architecture" in st_:
        a = st_["architecture"]
        ids = {b[0] for b in a["blocks"]}
        for l in a.get("links", []):
            if l[0] not in ids or l[1] not in ids:
                raise ContractError(f"{name}: architecture link {l} names an unknown block")
        r["story"]["architecture"] = a
    for e in y["evidence"]:
        if e.get("kind") not in EVIDENCE:
            raise ContractError(f"{name}: evidence kind must be one of {list(EVIDENCE)}")
        if e.get("path") and not glob.glob(str(ROOT / e["path"])):
            raise ContractError(f"{name}: evidence path {e['path']} does not exist")
    miss = [k for k in EVIDENCE if k not in {e["kind"] for e in y["evidence"]}]
    if miss:
        raise ContractError(f"{name}: evidence lacks {miss} (say 'not recorded' in an item's text rather than leave a kind out)")
    r["evidence"] = [{"kind": e["kind"], "label": e["label"], "path": e.get("path"), "text": f("evidence", e.get("text", ""))}
                     for e in y["evidence"]]
    lim = y["limits"]
    r["limits"] = {k: [f(f"limits.{k}", t) for t in lim.get(k, [])] for k in ("not_measured", "nulls", "next")}
    if "try_it" in y:
        r["try_it"] = {"command": y["try_it"]["command"], "note": f("try_it", y["try_it"].get("note", ""))}
    r["description"] = f("description", y.get("description", y["one_line"]))
    return r


def build(directory: Path = DIR) -> dict:
    projects = [resolve(n, y) for n, y in load(directory)]
    projects.sort(key=lambda p: (list(STATUS).index(p["status"]), p["order"], p["title"]))
    return {"projects": projects, "counts": {s: sum(1 for p in projects if p["status"] == s) for s in STATUS}}


# ------------------------------------------------------------------------------------------------------- rendering

def _link(path: str, label: str | None = None) -> str:
    return f'<a href="{REPO}/tree/main/{E(path)}">{E(label or path)}</a>'


def card(p: dict, prefix: str = "") -> str:
    tag = f'<span class="tag{" run" if p["status"] != "published" else ""}">{E(p["status_label"])}</span>'
    title = f'<a href="{prefix}showcase/{p["id"]}.html">{E(p["title"])}</a>' if p["status"] == "published" else E(p["title"])
    board = f'<p class="small muted">{E(p["board"])}{(" (" + E(p["part"]) + ")") if p.get("part") else ""}</p>' if p.get("board") else ""
    body = f'<p>{E(p["one_line"])}</p>'
    if p["status"] == "published":
        body += f'<p class="sc-head"><b>{E(p["headline"])}</b></p>'
    elif p.get("what_it_will_show"):
        body += f'<p class="small"><span class="muted">What it will show:</span> {E(p["what_it_will_show"])}</p>'
    return f'<li class="sc-card sc-{p["status"]}" id="sc-{p["id"]}"><div class="vh"><h3>{title}</h3> {tag}</div>{board}{body}</li>'


def index_body(S: dict) -> str:
    pub = [p for p in S["projects"] if p["status"] == "published"]
    prog = [p for p in S["projects"] if p["status"] == "in_progress"]
    plan = [p for p in S["projects"] if p["status"] == "planned"]
    out = []
    if not pub:
        out.append("<p>None has a committed board result yet, so this page lists the work in progress and shows no numbers; "
                   "each project gets its page here when its first board result is committed.</p>")
    if pub:
        out.append('<h2 id="measured">Measured on the board</h2><ul class="sc-grid">' + "".join(card(p) for p in pub) + "</ul>")
    if prog:
        out.append('<h2 id="in-progress">Being built now</h2><p>Each page will lead with the measured result in one line and a replay '
                   'of the recorded data, then the problem, how it works, the results, what the agent did, the evidence and the limits.</p>'
                   '<ul class="sc-grid">' + "".join(card(p) for p in prog) + "</ul>")
    if plan:
        out.append('<details class="more"><summary>Planned next</summary><ul class="sc-plan">' +
                   "".join(f'<li><b>{E(p["title"])}.</b> {E(p["one_line"])}</li>' for p in plan) + "</ul></details>")
    return "\n".join(out)


def arch_svg(a: dict, pid: str) -> str:
    """The architecture diagram: blocks left to right (wide) or top to bottom (narrow), links labelled, from the data."""
    import agent_page as ap
    blocks = a["blocks"]
    idx = {b[0]: i for i, b in enumerate(blocks)}
    def lay(wide):
        n = len(blocks)
        if wide:
            W, bw, bh, gap = 940, min(170, (940 - 40 - 50 * (n - 1)) / n), 64, 50
            pos = {b[0]: (20 + i * (bw + gap), 40) for i, b in enumerate(blocks)}
            H = 150
        else:
            W, bw, bh, gap = 360, 220, 52, 56
            pos = {b[0]: (70, 16 + i * (bh + gap)) for i, b in enumerate(blocks)}
            H = 16 + n * (bh + gap)
        body = []
        for b in blocks:
            x, y = pos[b[0]]
            body.append(ap.box(x, y, bw, bh))
            rows = ap.wrap(b[1], bw - 16, 13)[:3]
            y0 = y + bh / 2 - (len(rows) - 1) * 8 + 4
            body.append(ap.lines(x + bw / 2, y0, rows, "", 16, "middle"))
        for l in a.get("links", []):
            (x1, y1), (x2, y2) = pos[l[0]], pos[l[1]]
            lab = l[2] if len(l) > 2 else ""
            if wide:
                fwd = idx[l[1]] > idx[l[0]]
                if fwd and idx[l[1]] == idx[l[0]] + 1:
                    d = f"M{x1 + bw:g} {y1 + bh / 2:g} L{x2:g} {y2 + bh / 2:g}"
                    tx, ty = (x1 + bw + x2) / 2, y1 + bh / 2 - 8
                else:      # a return or a skip: under the blocks
                    yb = y1 + bh + 24
                    d = f"M{x1 + bw / 2:g} {y1 + bh:g} L{x1 + bw / 2:g} {yb:g} L{x2 + bw / 2:g} {yb:g} L{x2 + bw / 2:g} {y2 + bh + 2:g}"
                    tx, ty = (x1 + x2 + bw) / 2, yb + 14
                body.append(ap.edge(d, f"sc{pid}{'w' if wide else 'n'}"))
                if lab:
                    body.append(ap.text(tx, ty, lab, "s", "middle"))
            else:
                if idx[l[1]] == idx[l[0]] + 1:
                    d = f"M{x1 + bw / 2:g} {y1 + bh:g} L{x2 + bw / 2:g} {y2:g}"
                    tx, ty = x1 + bw / 2 + 8, (y1 + bh + y2) / 2 + 4
                    body.append(ap.edge(d, f"sc{pid}n"))
                    if lab:
                        body.append(ap.text(tx, ty, lab, "s"))
                else:
                    xr = x1 + bw + 20 if idx[l[1]] < idx[l[0]] else x1 - 20
                    d = f"M{x1 + (bw if xr > x1 else 0):g} {y1 + bh / 2:g} L{xr:g} {y1 + bh / 2:g} L{xr:g} {y2 + bh / 2:g} L{x2 + (bw if xr > x1 else 0):g} {y2 + bh / 2:g}"
                    body.append(ap.edge(d, f"sc{pid}n"))
                    if lab:
                        for k, row in enumerate(ap.wrap(lab, 60, 11)):
                            body.append(ap.text(xr + (4 if xr > x1 else -4), (y1 + y2 + bh) / 2 + k * 13, row, "s", "start" if xr > x1 else "end"))
        label = "Architecture: " + ", then ".join(b[1] for b in blocks)
        return ap.svg(f"sc{pid}{'w' if wide else 'n'}", W, H, "".join(body), label, "scarch")
    return ap.both(lay(True), lay(False))


def page_body(p: dict) -> str:
    S = p["story"]
    h = p["hero"]
    hero = (f'<figure><div class="player kit" id="hero-{p["id"]}" data-kit="{h["kind"]}" data-key="showcase_hero" '
            f'aria-label="{E(p["title"])}: replay of the recorded data"><div class="phost"><div class="kitart"></div>'
            f'<p class="cap" aria-live="polite">{E(h["caption"])}</p></div></div>'
            f'<figcaption>{E(h["caption"])} Data: {_link(h["source"])}.</figcaption></figure>')
    ag = S["agent"]
    agent_rows = "".join(f'<dt>{E(k.replace("_", " ").capitalize())}</dt><dd>' +
                         ("<ul>" + "".join(f"<li>{E(x)}</li>" for x in v) + "</ul>" if isinstance(v, list) else E(v)) + "</dd>"
                         for k, v in ag.items())
    ev = ""
    for k, t in EVIDENCE.items():
        ev += f"<h3>{E(t)}</h3><ul>" + "".join(
            f'<li>{_link(e["path"], e["label"]) if e["path"] else E(e["label"])}{(": " + E(e["text"])) if e["text"] else ""}</li>'
            for e in p["evidence"] if e["kind"] == k) + "</ul>"
    lim = p["limits"]
    limits = "".join(f'<h3>{t}</h3><ul>' + "".join(f"<li>{E(x)}</li>" for x in lim[k]) + "</ul>"
                     for k, t in (("not_measured", "Not measured"), ("nulls", "No effect found"), ("next", "Next")) if lim[k])
    tri = ""
    if p.get("try_it"):
        tri = (f'<h2 id="try">Try it</h2><pre><code>{E(p["try_it"]["command"])}</code></pre>' +
               (f'<p>{E(p["try_it"]["note"])}</p>' if p["try_it"]["note"] else ""))
    arch = f'<figure>{arch_svg(S["architecture"], p["id"])}</figure>' if S.get("architecture") else ""
    return f"""<p class="eyebrow"><a href="../showcase.html">Showcase</a> &middot; {E(p["board"])} ({E(p["part"])}) &middot; Vivado {E(p["vivado"])}</p>
<h1>{E(p["title"])}</h1>
<p class="lede sc-headline">{E(p["headline"])}</p>
{hero}
<h2 id="problem">The problem</h2>
<p>{E(S["problem"])}</p>
<h2 id="how">How it works</h2>
<p>{E(S["how"])}</p>
{arch}
<h2 id="results">Results</h2>
<ul class="sc-results">{"".join(f"<li>{E(t)}</li>" for t in S["results"])}</ul>
<h2 id="agent">What the agent did</h2>
<dl class="sc-agent">{agent_rows}</dl>
<details class="more" id="evidence"><summary>Evidence: run records, captures, operating conditions, versions and requirements</summary>{ev}</details>
<h2 id="limits">Limits</h2>
{limits}
{tri}"""
