"""Problem catalogue pages (brief 09b S2): problems.html and problems/<id>.html, from site/data/catalogue.json and
site/data/tasks/<id>.json. Called by build.py. Code is highlighted here, at build time (no script, no dependency)."""
from __future__ import annotations

import html
import json
import re

REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
BLOB = REPO + "/blob/main/"
E = html.escape

SET_LABEL = {"v1": "Benchmark v1", "course": "Course tier", "v2": "Benchmark v2"}
OUTCOME = {"pass": "passed", "caught_and_repaired": "gate failed, repaired, passed",
           "escape": "escape: own checks passed, hidden tests failed", "internal_stop_hidden_pass": "stopped on an internal gate; hidden tests pass",
           "fail": "failed"}
PROOF = {"simulation": "simulation", "formal": "formal", "hardware": "on the board", "analysis": "report analysis"}


def tier_label(t):
    return f"course part {t[1:]}" if re.fullmatch(r"C\d+", t) else t


# ------------------------------------------------------------------ highlighting (monochrome: weight and style only)
SV_KW = set("""module endmodule input output inout logic wire reg always always_ff always_comb always_latch assign begin end if
else case casez casex endcase default for while generate endgenerate genvar localparam parameter typedef enum struct packed
signed unsigned function endfunction return int integer posedge negedge or and not initial package endpackage import
automatic unique priority bit byte shortint longint task endtask interface endinterface modport break continue""".split())
PY_KW = set("""def class return if elif else for while in not and or is None True False import from as with try except finally
raise assert lambda yield async await pass break continue global nonlocal del""".split())
TOK = {
    "systemverilog": re.compile(r"(?P<c>//[^\n]*|/\*.*?\*/)|(?P<s>\"(?:\\.|[^\"\\])*\")|(?P<w>`?[A-Za-z_$][\w$]*)", re.S),
    "python": re.compile(r"(?P<c>#[^\n]*)|(?P<s>\"\"\".*?\"\"\"|'''.*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')|(?P<w>[A-Za-z_]\w*)", re.S),
}
TOK["verilog"] = TOK["systemverilog"]


def highlight(text, lang):
    rx = TOK.get(lang)
    if not rx:
        return E(text)
    kw = PY_KW if lang == "python" else SV_KW
    out, pos = [], 0
    for m in rx.finditer(text):
        out.append(E(text[pos:m.start()]))
        t = m.group(0)
        if m.group("c"):
            out.append(f'<span class="hc">{E(t)}</span>')
        elif m.group("s"):
            out.append(f'<span class="hs">{E(t)}</span>')
        elif t in kw or t.startswith("`"):
            out.append(f'<span class="hk">{E(t)}</span>')
        else:
            out.append(E(t))
        pos = m.end()
    out.append(E(text[pos:]))
    return "".join(out)


# ------------------------------------------------------------------ minimal markdown for spec.md (headings, lists, paragraphs, code)
def inline(s):
    s = E(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def markdown(md):
    out, para, items = [], [], []
    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>"); para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"); items.clear()
    for line in md.splitlines():
        if not line.strip():
            flush(); continue
        if line.startswith("#"):
            flush()
            lvl = min(4, len(line) - len(line.lstrip("#")) + 2)
            out.append(f"<h{lvl}>{inline(line.lstrip('#').strip())}</h{lvl}>")
        elif re.match(r"\s*[-*] ", line):
            if para:
                out.append("<p>" + inline(" ".join(para)) + "</p>"); para.clear()
            items.append(re.sub(r"^\s*[-*] ", "", line))
        elif items and line.startswith(" "):
            items[-1] += " " + line.strip()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def table(head, rows, num=()):
    h = "".join(f'<th class="num">{E(x)}</th>' if i in num else f"<th>{E(x)}</th>" for i, x in enumerate(head))
    b = "".join("<tr>" + "".join(f'<td class="num">{c}</td>' if i in num else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tablewrap" tabindex="0"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def jscript(key, obj):
    return f'<script type="application/json" data-key="{key}">' + json.dumps(obj, separators=(",", ":")).replace("</", "<\\/") + "</script>"


# ------------------------------------------------------------------ index page
def index_body(C):
    doms = C["domains"]
    rows = C["tasks"]
    by_dom = {}
    for r in rows:
        by_dom.setdefault(r["domain"], []).append(r)
    n = C["counts"]
    # hero: tasks per domain, every domain shown (empty ones too: the coverage gap is the point of v2)
    mx = max(len(v) for v in by_dom.values())
    bars = []
    for d, name in doms.items():
        k = len(by_dom.get(d, []))
        w = 100 * k / mx if k else 0
        lab = f'<b>{d}</b> {E(name)}'
        # an empty domain has no section to jump to: plain text, not a dead #dom-X link
        head = f'<a class="dl" href="#dom-{d}" data-dom="{d}">{lab}</a>' if k else f'<span class="dl dl-empty">{lab}</span>'
        bars.append(f'<li>{head}'
                    f'<span class="db" aria-hidden="true"><span style="width:{w:.1f}%"></span></span><span class="mono">{k}</span></li>')
    hero = ('<figure class="domfig"><ul class="dombars" aria-label="Development tasks per domain">' + "".join(bars) + "</ul>"
            '<figcaption>Development tasks with a page, per domain of the coverage survey. Empty rows are domains with no task yet; '
            "benchmark v2 adds tasks to every domain. Select a domain to filter the list.</figcaption></figure>")
    tiers = sorted({r["tier"] for r in rows}, key=lambda t: (t[0] != "T", int(t[1:])))
    boards = sorted({r["board"] for r in rows})
    sel = lambda nm, lab, opts: (f'<label>{lab} <select id="f-{nm}" data-f="{nm}"><option value="">all</option>' +
                                 "".join(f'<option value="{E(v)}">{E(t)}</option>' for v, t in opts) + "</select></label>")
    filt = ('<div class="filters" role="group" aria-label="Filter the problems">' +
            sel("domain", "Domain", [(d, f"{d} {doms[d]}") for d in doms if d in by_dom]) +
            sel("tier", "Tier", [(t, tier_label(t)) for t in tiers]) +
            sel("board", "Board", [(b, C["boards"].get(b, b)) for b in boards]) +
            '<span class="mono small" id="f-count" aria-live="polite"></span></div>')
    lists = []
    for d, name in doms.items():
        if d not in by_dom:
            continue
        cards = []
        for r in sorted(by_dom[d], key=lambda r: (r["set"] != "v1", r["id"])):
            res = (f'{r["hidden_passes"]} of {r["runs"]} agent runs passed' if r["runs"] else "no agent run yet")
            cards.append(f'<li class="pcard" data-domain="{d}" data-tier="{E(r["tier"])}" data-board="{E(r["board"])}">'
                         f'<a href="problems/{E(r["id"])}.html"><span class="pt">{E(r["heading"])}</span></a>'
                         f'<span class="pm mono">{E(r["id"])}</span>'
                         f'<span class="pm">{E(SET_LABEL[r["set"]])}, {E(tier_label(r["tier"]))}, {E(C["boards"].get(r["board"], r["board"]))}. '
                         f'{r["mutants"]} mutants; {res}.' + (' <span class="tag">Animated</span>' if r["showcase"] else "") + "</span></li>")
        lists.append(f'<section class="dom" id="dom-{d}" data-domain="{d}"><h3>{d}. {E(name)}</h3><ul class="plist">{"".join(cards)}</ul></section>')
    # held-out
    ho = {}
    for h in C["held_out"]:
        ho.setdefault((h["set"], h["tier"]), []).append(h["id"])
    ho_rows = [[E(SET_LABEL[s]), E(tier_label(t)), str(len(ids)), ", ".join(f"<code>{E(i)}</code>" for i in sorted(ids))]
               for (s, t), ids in sorted(ho.items(), key=lambda kv: (kv[0][0] != "v1", kv[0][1][0], int(kv[0][1][1:])))]
    moved = ""
    if C["moved"]:
        moved = ("<p>Moved from held-out to development after eval-1 (their pass counts were seen), listed by id and tier; "
                 "their files are still in the private repository, so they have no page yet: " +
                 ", ".join(f'<code>{E(m["id"])}</code> ({E(tier_label(m["tier"]))})' for m in C["moved"]) + ".</p>")
    if C["v2_cells"]:
        v2 = table(["Domain", "Tier", "Development", "Held out"],
                   [[f'{c["domain"]} {E(doms[c["domain"]])}', E(c["tier"]), str(c["dev"]), str(c["held_out"])] for c in C["v2_cells"]], num=(2, 3))
    else:
        v2 = ('<p>No benchmark v2 block has been drawn yet, so there is no v2 held-out task to count. When one is, this table gives '
              "the number of held-out tasks per domain and tier, and nothing else about them.</p>")
    return f"""<h1>Problems</h1>
<p class="lede">Every task in the benchmark. Each development task has its own page with the request the agent is given, the hidden spec and tests, a hand-written solution, the planted bugs the tests must catch, its golden model running, and the agent's runs. Held-out tasks are kept private and listed here by id and tier only.</p>
<div class="facts">
<div class="fact"><div class="n">{n["dev_pages"]}</div><p>development tasks with a page: {n["v1_dev"]} from benchmark v1, {n["course_dev"]} from the course tier.</p></div>
<div class="fact"><div class="n">{n["held_listed"]}</div><p>held-out tasks, listed by id and tier only (those ids are already public in the split files).</p></div>
<div class="fact"><div class="n">{n["mutants"]}</div><p>deliberate bugs (mutants) across the development tasks, each one failing the hidden tests.</p></div>
</div>
{hero}
<h2>Development tasks</h2>
{filt}
{"".join(lists)}
<h2 id="held-out">Held-out tasks</h2>
<p>These are kept for scoring. Their specs, tests, models and reference designs are in a private repository and never appear on this site.</p>
{table(["Set", "Tier", "Tasks", "Ids"], ho_rows, num=(2,))}
{moved}
<h3>Benchmark v2</h3>
{v2}
<h2 id="made">How the problems are made</h2>
<ol class="made">
<li><strong>The request.</strong> A short request in plain English, written as a user would ask. It leaves things out on purpose, so the agent has to ask. Every answer is settled in a hidden full spec (ports, clocks, reset, register map, behaviour, requirements), and a stand-in user answers only from that. <span class="small muted"><code>spec.md</code>, <code>hidden/spec.yaml</code></span></li>
<li><strong>The hidden tests.</strong> A cocotb bench drives the design through the board's pins, or through the test shell over the serial link, and compares it with the model. The agent never sees it. <span class="small muted"><code>hidden/acceptance.py</code></span></li>
<li><strong>The independent model.</strong> A golden model written from the hidden spec alone, never from RTL. The animation on each page runs it. <span class="small muted"><code>hidden/model.py</code></span></li>
<li><strong>The reference design.</strong> Hand-written RTL that passes every test and every flow gate. It proves the task can be done on the board; it is not agent output. <span class="small muted"><code>ref/rtl/</code></span></li>
<li><strong>The mutants.</strong> Deliberate bugs, each a small edit to the reference. Every one must fail the hidden tests, which shows the tests can tell a right design from a nearly right one. <span class="small muted"><code>hidden/mutants.yaml</code></span></li>
<li><strong>The held-out draw.</strong> A seeded draw holds out about a third of each tier. Benchmark v2 holds out one task in every block of three per domain and tier, drawn from the frozen files, so nobody chooses which. <a href="{BLOB}benchmark/v2/README.md">More on benchmark v2</a>.</li>
</ol>
<p class="small muted">Course-tier tasks are adapted from the owner's FPGA design course (Parts 9 to 16; the course itself is private). Code on these pages is from the repository under its MIT licence.</p>
"""


# ------------------------------------------------------------------ task page
def code_block(tid, f, kind_label):
    return (f'<details class="code"><summary><span class="mono">{E(f["name"])}</span> <span class="muted small">{kind_label}, '
            f'{f["lines"]} lines</span></summary><div class="codebar small"><a href="{E(tid)}/{E(f["name"])}" download>Download</a>'
            f'<a href="{BLOB}{E(f["path"])}">On GitHub</a><span class="muted">MIT licence</span></div>'
            f'<pre tabindex="0"><code>{highlight(f["text"], f["lang"])}</code></pre></details>')


def task_body(T, C, prev, nxt):
    doms = C["domains"]
    I = T["interface"]
    tags = (f'<span class="tag">{E(SET_LABEL[T["set"]])}</span> <span class="tag">{E(tier_label(T["tier"]))}</span> '
            f'<span class="tag">{E(T["domain"])} {E(doms[T["domain"]])}</span> <span class="tag">{E(C["boards"].get(T["board"], T["board"]))}</span>')
    tr = T["trace"]
    if T["showcase"]:
        anim = (f'<figure><div class="player trace" id="trace" data-hero="{E(T["id"])}" aria-label="Golden model replay">'
                '<div class="hero-art"></div><div class="wave"></div><p class="cap" aria-live="polite"></p></div>')
    else:
        anim = ('<figure><div class="player trace" id="trace" aria-label="Golden model replay">'
                '<div class="wave"></div><p class="cap" aria-live="polite"></p></div>')
    anim += (f'<figcaption>The task\'s own golden model (<code>hidden/model.py</code>) run on a fixed input when the site is built, so this is '
             f'what the hidden tests check. {E(tr["stimulus"])} Space plays and pauses, arrow keys step.</figcaption></figure>')
    # interface
    ports = table(["Port", "Direction", "Width", "Note"], [[f"<code>{E(p['name'])}</code>", E(p["dir"]), str(p["width"]), E(p["note"])] for p in I["ports"]], num=(2,))
    regs = ""
    if I["registers"]:
        regs = ("<h3>Registers behind the test shell</h3>" +
                table(["Offset", "Name", "Access", "Bits"], [[f"<code>{E(r['offset'])}</code>", f"<code>{E(r['name'])}</code>", E(r["access"]), E(r["bits"])] for r in I["registers"]]) +
                (f'<p class="small muted">{E(I["unmapped"])}</p>' if I["unmapped"] else ""))
    params = ", ".join(f"<code>{E(k)}</code> = {E(str(v))}" for k, v in I["parameters"].items())
    bparams = ", ".join(f"<code>{E(k)}</code> = {E(str(v))}" for k, v in T["bench_parameters"].items())
    reqs = "".join(f'<li><span class="mono">{E(r["id"])}</span> {E(r["text"])} <span class="muted">(shown by {E(", ".join(PROOF.get(p, p) for p in r["proof"]))})</span></li>'
                   for r in T["requirements"])
    beh = "".join(f"<h4>{E(h)}</h4><ul>" + "".join(f"<li>{E(x)}</li>" for x in lines) + "</ul>" for h, lines in T["behaviour"])
    assum = ""
    if T["assumptions"]:
        assum = "<h3>Settled assumptions</h3><ul>" + "".join(f'<li>{E(a["assumption"])} <span class="muted">{E(a["reason"])}</span></li>' for a in T["assumptions"]) + "</ul>"
    ck = T.get("check")
    if ck:
        mk = ck["mutants"]
        muts = table(["Mutant", "File", "The bug", "Hidden tests that fail"],
                     [[f"<code>{E(m['name'])}</code>", f"<code>{E(m['file'])}</code>", E(m["why"]),
                       (", ".join(f"<code>{E(t)}</code>" for t in mk[m["name"]]["failed_tests"]) if mk.get(m["name"], {}).get("killed") else "not recorded as killed")]
                      for m in T["mutants"]])
        nk = sum(1 for m in T["mutants"] if mk.get(m["name"], {}).get("killed"))
        mut_note = (f'<p>Each is a small edit to the reference RTL. In the committed check ({E(ck["sim"])}, {E(ck["date"])}, '
                    f'<a href="{BLOB}{E(ck["path"])}"><code>{E(ck["path"].split("/")[-1])}</code></a>) the reference passed '
                    f'{"all" if ck["ref_pass"] else "not all"} {ck["ref_tests"]} hidden tests and {nk} of {len(T["mutants"])} mutants failed them.</p>')
    else:
        muts = table(["Mutant", "File", "The bug"], [[f"<code>{E(m['name'])}</code>", f"<code>{E(m['file'])}</code>", E(m["why"])] for m in T["mutants"]])
        mut_note = "<p>Each is a small edit to the reference RTL. No committed check result for this task is on this branch.</p>"
    code = "".join(code_block(T["id"], f, "reference RTL") for f in T["files"]["rtl"])
    code += "".join(code_block(T["id"], f, "hidden cocotb acceptance tests") for f in T["files"]["tests"])
    code += "".join(code_block(T["id"], f, "golden model") for f in T["files"]["model"])
    # agent runs
    if T["runs"]:
        rows = []
        for r in T["runs"]:
            rec = f'{BLOB}results/course/{E(T["id"])}/run_{r["run"]}.json'
            q = "" if r["wns_ns"] is None else f'{r["wns_ns"]:+.3f}'
            rows.append([f'<a href="{rec}">run {r["run"]}</a>', E(r["date"]), E(OUTCOME.get(r["outcome"], r["outcome"])),
                         f'{r["tests_passed"]} of {r["tests_total"]}', q, "" if r["lut"] is None else str(r["lut"]),
                         "" if r["ff"] is None else str(r["ff"]), "" if r["dsp"] is None else str(r["dsp"]),
                         E(r["failure_class"] or "none")])
        k = sum(1 for r in T["runs"] if r["hidden_pass"])
        runs = (f'<p><span class="tag">Development, not the held-out score</span> {k} of {len(T["runs"])} committed development runs passed every hidden test '
                f'({E(T["runs"][0]["model"])}). Partial credit is the hidden tests passed; slack is post-route at 100 MHz and the counts include the test shell.</p>' +
                table(["Record", "Date", "Outcome", "Hidden tests", "WNS (ns)", "LUT", "FF", "DSP", "What went wrong"], rows, num=(3, 4, 5, 6, 7)) +
                '<p class="small muted">Agent-written RTL is not committed per run, so only the reference RTL is shown above.</p>')
    else:
        runs = "<p>No development run of the agent on this task is committed yet.</p>"
    data = ""
    if T["data_files"]:
        data = ("<p>Handed over with the spec (the agent may read them): " + ", ".join(f'<a href="{BLOB}{E(T["path"])}/data/{E(x)}"><code>{E(x)}</code></a>' for x in T["data_files"]) + ".</p>")
    scope = f'<p class="small muted">Scope: {E(json.dumps(T["scope"]) if not isinstance(T["scope"], str) else T["scope"])}</p>' if T["scope"] else ""
    course = ('<p class="small muted">Adapted from a project in the owner\'s FPGA design course (the course itself is private).</p>' if T["set"] == "course" else "")
    pn = ('<div class="pager">' + (f'<a href="{E(prev["id"])}.html">&larr; {E(prev["heading"])}</a>' if prev else "<span></span>") +
          (f'<a href="{E(nxt["id"])}.html">{E(nxt["heading"])} &rarr;</a>' if nxt else "<span></span>") + "</div>")
    res = f' Resources expected: {E(T["resources_expected"])}.' if T["resources_expected"] else ""
    return f"""<p class="crumbs small"><a href="../problems.html">Problems</a> / <a href="../problems.html#dom-{E(T["domain"])}">{E(T["domain"])}. {E(doms[T["domain"]])}</a></p>
<h1>{E(T["heading"])}</h1>
<p class="tags"><code>{E(T["id"])}</code> {tags}</p>
{anim}
<h2>The problem</h2>
<p>{E(T["what"])}</p>
<p><strong>Where it is used.</strong> {E(T["where"])}</p>
{course}
<h2>The spec the agent is given</h2>
<div class="spec">{markdown(T["spec_md"])}</div>
<p class="small muted">Exactly <a href="{BLOB}{E(T["path"])}/spec.md"><code>spec.md</code></a>. Anything it leaves open, the agent has to ask about.</p>
{data}
<h2>Interface</h2>
<p>Top module <code>{E(I["top"])}</code> on the {E(C["boards"].get(T["board"], T["board"]))} (<code>{E(T["part"])}</code>). Clock: {E("; ".join(I["clocks"]))}. Reset: {E(I["reset"])}.{res}</p>
<p>Top-level parameters (board values): {params}.{(" The hidden bench shrinks them to " + bparams + ".") if bparams else ""}{" The bench builds it without the test shell, since its subject is the USB-UART itself." if T["no_shell"] else ""}</p>
{ports}
{regs}
<h2>What the hidden tests check</h2>
<p>The requirements in the hidden spec, and how each is shown to hold:</p>
<ul class="reqs">{reqs}</ul>
<details class="rules"><summary>The full behaviour rules from <code>hidden/spec.yaml</code></summary>{beh}</details>
{assum}
{scope}
<h2>What the tests catch: the mutants</h2>
{mut_note}
{muts}
<h2>Sample solution</h2>
<p class="note">Hand-written reference for the benchmark, not agent output; it passes every test, and the listed mutants fail them. With it, the hidden cocotb tests and the golden model. Repository licence: MIT.</p>
{code}
<h2>The agent on this task</h2>
{runs}
{pn}
"""
