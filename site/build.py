#!/usr/bin/env python3
"""Build the static site: site/src/*.html (fragments with {{data.path}} tokens) -> site/public/*.html.

    python3 site/export.py        # results -> site/data/*.json
    python3 site/build.py         # write site/public/
    python3 site/build.py --check # exit 1 if public/ is stale, or if any number shown is not in site/data/*.json
    python3 site/build.py --fixture site/tests/fixtures/eval1_synthetic.json --out /tmp/x   # preview the eval-1 section

Number assertion: every numeric token in the visible text of the built pages must occur in the data files (or in
site/numbers_allow.txt, each entry with a reason). The synthetic eval-1 fixture is only ever used with --fixture and
is never copied into site/data/. eval-1 results appear when site/data/eval1.json exists (schema: tests/fixtures).
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
SRC = HERE / "src"
REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"

PAGES = [  # file, nav label, title, description, data keys inlined
    ("index.html", "Home", "End-to-end FPGA Agent", "An open agent that turns a plain-English spec into verified RTL and a bitstream for AMD FPGA boards, measured.", ["replay"]),
    ("how.html", "How it works", "How it works", "The stages, the verification gates V0 to V3, mutation testing, the knowledge bank and the tools, with a stage walk-through replayed from a real run record.", ["replay"]),
    ("examples.html", "Examples", "Examples", "Development tasks end to end: spec, clarify, gates, timing and area, and a hand-built design on the board.", ["board"]),
    ("evaluation.html", "How it is evaluated", "How it is evaluated", "The held-out evaluation in plain words: split, hidden grader, three runs per task, task-level bootstrap.", []),
    ("results.html", "Results", "Results", "Development results, and the held-out results once all 57 runs are scored.", ["dev", "eval1"]),
]


def load_data(fixture: Path | None):
    d = {p.stem: json.loads(p.read_text()) for p in DATA.glob("*.json")}
    if fixture:
        d["eval1"] = json.loads(fixture.read_text())
    return d


def lookup(d, path):
    cur = d
    for part in path.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, int) and abs(v) >= 1000:
        return f"{v:,}"
    return str(v)


def wh(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "not recorded"


def table(head, rows, num=()):
    h = "".join(f'<th class="num">{html.escape(x)}</th>' if i in num else f"<th>{html.escape(x)}</th>" for i, x in enumerate(head))
    b = ""
    for r in rows:
        b += "<tr>" + "".join(f'<td class="num">{html.escape(str(c))}</td>' if i in num else f"<td>{html.escape(str(c))}</td>" for i, c in enumerate(r)) + "</tr>"
    return f'<div class="tablewrap" tabindex="0"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


OUT_TEXT = {"pass": "passed", "caught_and_repaired": "gate failed, repaired, passed", "escape": "escape (own checks passed, hidden failed)",
            "internal_stop_hidden_pass": "internal stop, hidden tests pass", "fail": "failed"}


def block(name, d):
    """Server-side blocks: {{!name}}."""
    if name == "c14_table":
        ex = [e for e in d["examples"] if e["task"] == "c14_int8_dot_requant"][0]
        rows = []
        for r in ex["runs"]:
            rows.append([r["run"], OUT_TEXT[r["outcome"]], f'{r["tests_passed"]} of {r["tests_total"]}', r["failure_class"] or "none"])
        return table(["Run", "Outcome", "Hidden tests", "What went wrong (from the run record)"], rows, num=(0,))
    if name == "qor_table":
        rows = []
        for e in d["examples"]:
            for r in e["runs"]:
                if r["wns_ns"] is None:
                    continue
                rows.append([e["task"], r["run"], f'{r["tests_passed"]} of {r["tests_total"]}', f'{r["wns_ns"]:+.3f}', r["lut"], r["ff"], r["dsp"], fmt(r["bram36"]), wh(r["wall_h"])])
        return table(["Task", "Run", "Hidden tests", "WNS (ns)", "LUT", "FF", "DSP", "BRAM36", "Wall (h)"], rows, num=(1, 3, 4, 5, 6, 7, 8))
    if name == "eval_table":
        e = d["eval"]; v = e["tool_versions"]
        return table(["Fixed before the first scored run", "Value"], [
            ["Agent under test", f'tag {e["tag"]}, model {e["model"]}, Claude Code {v["claude_code"]}'],
            ["Tools", f'Vivado {v["vivado"]}, Icarus Verilog {v["icarus"]}, cocotb {v["cocotb"]}, Verilator {v["verilator"]}'],
            ["Tasks and runs", f'{e["tasks"]} tasks x {e["runs_per_task"]} runs = {e["runs"]} runs'],
            ["Interval", f'bootstrap over tasks, {e["resamples"]:,} resamples; planned half-width {e["planned_halfwidth"]} points'],
            ["Randomness", f'task order seed {e["seed"]}'],
        ])
    if name == "packs_table":
        us = d["packs"]["units"]
        rows = [[u["unit"], u["skills"], u["bytes"]] for u in us]
        return table(["Layer", "Skills", "Skill bytes"], rows, num=(1, 2))
    if name == "spec_c9":
        e = [x for x in d["examples"] if x["task"] == "c9_median3x3"][0]
        return f'<pre tabindex="0"><code>{html.escape(e["spec"])}</code></pre>'
    if name == "spec_c10":
        e = [x for x in d["examples"] if x["task"] == "c10_dds_sine"][0]
        return f'<pre tabindex="0"><code>{html.escape(e["spec"])}</code></pre>'
    if name == "spec_c14":
        e = [x for x in d["examples"] if x["task"] == "c14_int8_dot_requant"][0]
        return f'<pre tabindex="0"><code>{html.escape(e["spec"])}</code></pre>'
    if name == "c9_gates":
        e = [x for x in d["examples"] if x["task"] == "c9_median3x3"][0]["runs"][0]
        g = e["gates"]
        return table(["Check", "Result"], [[k, v] for k, v in g.items()])
    if name == "c10_runs":
        e = [x for x in d["examples"] if x["task"] == "c10_dds_sine"][0]
        rows = [[r["run"], OUT_TEXT[r["outcome"]], f'{r["tests_passed"]} of {r["tests_total"]}', r["failure_class"] or "none",
                 f'{r["wns_ns"]:+.3f}', r["lut"], r["ff"]] for r in e["runs"]]
        return table(["Run", "Outcome", "Hidden tests", "What went wrong", "WNS (ns)", "LUT", "FF"], rows, num=(0, 4, 5, 6))
    if name == "t1_rtl":
        return f'<pre tabindex="0"><code>{html.escape(d["board"]["rtl"])}</code></pre>'
    if name == "dev_table":
        rows = [[r["task"], r["run"], OUT_TEXT[r["outcome"]], f'{r["tests_passed"]} of {r["tests_total"]}',
                 "" if r["wns_ns"] is None else f'{r["wns_ns"]:+.3f}', "" if r["lut"] is None else r["lut"]] for r in d["dev"]["runs_list"]]
        return table(["Task", "Run", "Outcome", "Hidden tests", "WNS (ns)", "LUT"], rows, num=(1, 4, 5))
    raise KeyError(name)


def render_template(text, d):
    text = text.replace('<div class="tablewrap"><table>', '<div class="tablewrap" tabindex="0"><table>')
    text = re.sub(r"\{\{!(\w+)\}\}", lambda m: block(m.group(1), d), text)
    return re.sub(r"\{\{([\w.]+)\}\}", lambda m: html.escape(fmt(lookup(d, m.group(1)))), text)


def layout(fname, title, desc, body, keys, d, css, js):
    nav = "".join(f'<a href="{f}"{" aria-current=\"page\"" if f == fname else ""}>{html.escape(n)}</a>' for f, n, *_ in PAGES)
    scripts = "".join(f'<script type="application/json" data-key="{k}">{json.dumps(d[k], separators=(",", ":")).replace("</", "<\\/")}</script>'
                      for k in keys if k in d)
    idx = [p[0] for p in PAGES].index(fname)
    prev = PAGES[idx - 1] if idx else None
    nxt = PAGES[idx + 1] if idx + 1 < len(PAGES) else None
    pager = '<div class="pager">' + (f'<a href="{prev[0]}">&larr; {html.escape(prev[1])}</a>' if prev else "<span></span>") + \
            (f'<a href="{nxt[0]}">{html.escape(nxt[1])} &rarr;</a>' if nxt else "<span></span>") + "</div>"
    full = title if fname == "index.html" else f"{title} | End-to-end FPGA Agent"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(full)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<style>{css}</style>
</head>
<body>
<a class="visually-hidden" href="#main">Skip to content</a>
<header class="bar"><div class="wrap"><a class="brand" href="index.html">End-to-end FPGA Agent</a><nav aria-label="Pages">{nav}</nav><button id="theme" type="button" aria-label="Switch colour theme">Dark</button></div></header>
<main id="main" class="wrap">
{body}
{pager}
</main>
<footer><div class="wrap"><p>Code, results and the pre-registration: <a href="{REPO}">{REPO.split('//')[1]}</a>. Every number on these pages is read from a committed result file; the agent and the benchmark are from the repository at tag <a href="{REPO}/releases/tag/eval-1"><code>eval-1</code></a> or earlier. Development results are labelled as such and are not the held-out score.</p></div></footer>
{scripts}
<script>{js}</script>
</body>
</html>
"""


def visible_numbers(page: str):
    t = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", page)
    t = re.sub(r"(?s)<head>.*?</head>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.findall(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?", t)


def data_tokens(d):
    toks = set()
    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            toks.update({fmt(v), str(v), f"{v:,}" if isinstance(v, int) else str(v), f"{v:+.3f}", f"{v:.2f}", f"{v:.1f}", f"{abs(v):g}"})
        elif isinstance(v, str):
            toks.update(re.findall(r"\d[\d,]*(?:\.\d+)?", v))
        elif isinstance(v, list):
            for x in v: walk(x)
        elif isinstance(v, dict):
            for x in v.values(): walk(x)
    walk(d)
    return toks


def allow_tokens():
    out = set()
    for line in (HERE / "numbers_allow.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.update(line.split())
    return out


def build(outdir: Path, d, check_numbers=True):
    css = (SRC / "site.css").read_text()
    js = (SRC / "app.js").read_text()
    pages = {}
    for fname, label, title, desc, keys in PAGES:
        body = render_template((SRC / fname).read_text(), d)
        pages[fname] = layout(fname, title, desc, body, keys, d, css, js)
    bad = []
    if check_numbers:
        ok = data_tokens(d) | allow_tokens()
        for fname, page in pages.items():
            for tok in visible_numbers(page):
                t = tok.lstrip("+-") if tok[0] in "+-" else tok
                if tok not in ok and t not in ok and tok.rstrip(",") not in ok:
                    bad.append((fname, tok))
    return pages, bad


def main():
    args = sys.argv[1:]
    fixture = Path(args[args.index("--fixture") + 1]) if "--fixture" in args else None
    out = Path(args[args.index("--out") + 1]) if "--out" in args else HERE / "public"
    d = load_data(fixture)
    pages, bad = build(out, d)
    if bad:
        print("numbers not found in site/data (add to the data, or to numbers_allow.txt with a reason):")
        for b in sorted(set(bad)):
            print("  ", b)
        sys.exit(1)
    static = {"favicon.svg": (SRC / "favicon.svg").read_bytes(), "t1_on_nexys_a7.jpg": (ROOT / "docs/img/t1_on_nexys_a7.jpg").read_bytes(),
              "vercel.json": b'{"cleanUrls": true, "trailingSlash": false}\n'}
    if "--check" in args:
        stale = [f for f, p in pages.items() if not (out / f).exists() or (out / f).read_text() != p]
        stale += [f for f, b in static.items() if not (out / f).exists() or (out / f).read_bytes() != b]
        if stale:
            print("stale:", stale)
            sys.exit(1)
        print("ok:", len(pages), "pages, numbers all in data")
        return
    out.mkdir(parents=True, exist_ok=True)
    for f, p in pages.items():
        (out / f).write_text(p)
    for f, b in static.items():
        (out / f).write_bytes(b)
    print("wrote", len(pages), "pages to", out)


if __name__ == "__main__":
    main()
