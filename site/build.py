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
    ("index.html", "Home", "End-to-end FPGA Agent", "An open agent that turns a plain-English spec into a bitstream for AMD FPGA boards, measures its work on real hardware and uses what it measures to decide its next step.", ["loop"]),
    ("agent.html", "The agent", "The agent", "The agent itself: a LangGraph controller over Deep Agents or Claude Code role agents, drawn from its code, with a recorded run replayed through the diagrams.", ["agent_graph"]),
    ("how.html", "How it works", "How it works", "The stages, the verification gates V0 to V3, mutation testing, the knowledge bank and the tools, with a stage walk-through replayed from a real run record.", ["replay"]),
    ("flow-notes.html", "Beyond the flow", "Beyond the standard flow", "Where the agent's flow goes further than the standard Vivado flow: missing CDC constraints, crossings report_cdc cannot see, timing exceptions that hide failures, and more, each with its evidence and status.", ["flow_notes"]),
    ("expertise.html", "Expertise", "Areas of expertise", "What the agent knows, what its flow checks and what has been measured, area by area, in drawers; each area states how far its evidence goes.", []),
    ("examples.html", "Examples", "Examples", "Development tasks end to end: spec, clarify, gates, timing and area, and a hand-built design on the board.", ["board"]),
    ("problems.html", "Problems", "Problems", "Every benchmark task: development tasks in full with spec, hidden tests, reference RTL, mutants and the golden model running; held-out tasks by id and tier only.", ["catalogue_index"]),
    ("evaluation.html", "How it is evaluated", "How it is evaluated", "The held-out evaluation in plain words: split, hidden grader, three runs per task, task-level bootstrap.", []),
    ("results.html", "Results", "Results", "Development results; held-out results come with the baseline evaluation.", ["dev", "eval1"]),
]


NAV_SUB = [("agent.html", "agent.html#harness", "Harness")]     # brief 47: a section linked from the nav, after its page


def load_data(fixture: Path | None):
    d = {p.stem: json.loads(p.read_text()) for p in DATA.glob("*.json")}
    d["tasks"] = {p.stem: json.loads(p.read_text()) for p in sorted((DATA / "tasks").glob("*.json"))}
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
            ["Tools", f'Icarus Verilog {v["icarus"]}, cocotb {v["cocotb"]}, Verilator {v["verilator"]}, and the Vivado release the pre-registration pins (the next evaluation pins Vivado 2026.1)'],
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
        rows = [[r["run"], OUT_TEXT[r["outcome"]], f'{r["tests_passed"]} of {r["tests_total"]}', r["failure_class"] or "none"] for r in e["runs"]]
        return table(["Run", "Outcome", "Hidden tests", "What went wrong"], rows, num=(0,))
    if name == "t1_rtl":
        return f'<pre tabindex="0"><code>{html.escape(d["board"]["rtl"])}</code></pre>'
    if name == "problems_index":
        import catalogue_pages
        return catalogue_pages.index_body(d["catalogue"])
    if name == "dev_table":
        rows = [[r["task"], r["run"], OUT_TEXT[r["outcome"]], f'{r["tests_passed"]} of {r["tests_total"]}',
                 "" if r["wns_ns"] is None else f'{r["wns_ns"]:+.3f}', "" if r["lut"] is None else r["lut"]] for r in d["dev"]["runs_list"]]
        return table(["Task", "Run", "Outcome", "Hidden tests", "WNS (ns)", "LUT"], rows, num=(1, 4, 5))
    if name == "repo":
        return REPO
    if name == "xpm_figure":
        return xpm_figure(d["flow_notes"]["xpm"])
    if name == "xpm_table":
        x = d["flow_notes"]["xpm"]
        return table(["Measure", "Without the fix", "With xpm_cdc.tcl"], [
            ["report_cdc, xpm_cdc_single row", x["before"]["report_cdc_exception"]["single"], x["after"]["report_cdc_exception"]["single"]],
            ["report_cdc, xpm_cdc_gray row", x["before"]["report_cdc_exception"]["gray"], x["after"]["report_cdc_exception"]["gray"]],
            ["clk_a to clk_b setup WNS (ns)", f'{x["before"]["wns_ns"]:+.3f}', f'{x["after"]["wns_ns"]:+.3f}'],
            ["Failing endpoints on that path", x["before"]["failing_endpoints"], x["after"].get("failing_endpoints", "not recorded")],
        ], num=())
    if name == "mutant_table":
        def yn(v):
            return "not covered" if v is None else ("yes" if v else "no")
        rows = [[m["id"], m["what"], "not re-measured" if m["report_cdc"] is None else yn(m["report_cdc"]), yn(m["rig_sim"]), yn(m["gate_sim"]), yn(m["gate"])] for m in d["flow_notes"]["mutants"]]
        return table(["Mutant", "What is wrong", "report_cdc alone flags it", "Rig simulation with injection", "Gate's own injected simulation", "New gate flags it"], rows)
    if name == "tear_table":
        rows = [[("binary counter" if s["bus"] == "binary" else "Gray counter"), "on" if s["extra_cycle"] else "off", s["cycles"], s["torn_cycles"]]
                for s in d["flow_notes"]["tear"]["stats"]]
        return table(["Bus", "Extra cycle", "Cycles simulated", "Cycles with a torn value"], rows, num=(2, 3))
    if name in ("expertise_levels", "expertise_ladder", "expertise_drawers"):
        import expertise_page
        return getattr(expertise_page, name.split("_", 1)[1])(d["expertise"])
    if name.startswith("agent_") or name.startswith("harness_"):
        return agent_block(name, d)
    if name.startswith("loop_"):
        return loop_block(name, d)
    if name == "exception_figure":
        return exception_figure()
    raise KeyError(name)


def agent_block(name, d):
    """agent.html (brief 43): figures from site/agent_page.py, tables from agent_graph.json."""
    import agent_page as ap
    A = dict(d["agent_graph"], vivado=d["board"]["vivado"])
    if name == "agent_arch":
        return ap.both(ap.architecture(A, "wide"), ap.architecture(A, "narrow"))
    if name == "agent_langgraph":
        return ap.both(ap.langgraph(A["graph"], "wide"), ap.langgraph(A["graph"], "narrow"))
    if name == "agent_pipeline":
        return ap.both(ap.pipeline(A, "wide"), ap.pipeline(A, "narrow"))
    if name == "agent_live":
        return ap.both(ap.live(A, "wide"), ap.live(A, "narrow"))
    if name == "agent_inner_da":
        return '<div class="agone">' + ap.inner(A, "deepagents") + "</div>"
    if name == "agent_inner_cc":
        return '<div class="agone">' + ap.inner(A, "claude_code") + "</div>"
    if name == "agent_roles":
        prof = A["defaults"]["profiles"]["cvdp"]
        st2 = {s["n"]: s for s in A["stages"]}[2]["tools"]
        rows = [[r["label"], r["what"], ", ".join(r["reads"]), ", ".join(r["writes"]),
                 f'Deep Agents: {A["defaults"]["model"]}; cvdp profile: {prof[r["id"]]["model"]}'] for r in A["roles"]]
        t = table(["Role", "Job", "May read", "May write", "Model (default; cvdp profile)"], rows)
        tl = table(["Role", "Tools in stage 2"], [[r["label"], ", ".join(st2.get(r["id"], []))] for r in A["roles"] if r["id"] in st2])
        return t + '<details class="more"><summary>Details: the tools each role gets in stage 2</summary>' + tl + "</details>"
    if name == "agent_runs":
        names = {"claude_code": "Claude Code", "deepagents": "Deep Agents", "mixed": "mixed"}
        return table(["Runs", "Harness", "Models", "Run records"], [[r["set"], names[r["harness"]], r["models"], r["records"]] for r in A["runs"]], num=(3,))
    if name == "agent_variants":
        out = ['<ul class="variants">']
        for a in A["arms"]:
            out.append(f'<li><div class="vh"><b>{html.escape(a["name"])}</b> <span class="tag run">{html.escape(a["status"])}</span></div>'
                       f'<p>Adds {html.escape(a["adds"])}.</p><div class="vfig">{ap.variant(a)}</div></li>')
        return "".join(out) + "</ul>"
    if name == "harness_layers":
        return ap.both(ap.harness_layers(A, "wide"), ap.harness_layers(A, "narrow"))
    if name == "harness_audit":
        h, s = A["harness"], A["harness"]["settings"]
        mw = "; ".join(m["name"].lstrip("_") for m in h["middleware"])
        return table(["Question", "What the code builds today"], [
            ["Libraries", f'deepagents {A["versions"]["deepagents"]}, LangGraph {A["versions"]["langgraph"]}, langchain-openai {A["versions"]["langchain-openai"]} (pinned)'],
            ["System prompt", "only ours: the role's prompt, with no Deep Agents base prompt" if h["system_prompt_only_ours"] else "ours plus the library's"],
            ["Tools offered", "the built-in file tools (" + ", ".join(A["inner"]["builtin_tools"]) + ") and the stage's own tools; "
             + ("a to-do tool" if h["todo_tool"] else "no to-do tool") + ", " + ("a sub-agent tool" if h["subagent_tool"] else "no sub-agent tool")],
            ["Middleware", mw],
            ["When old turns are summarised", f'at about {s["summarise_trigger_tokens"]:,} tokens, keeping the last {s["summarise_keep_messages"]} messages: the fixed default, as our model wrapper reports no context size'],
            ["File contents in older turns", f'once there are more than {s["truncate_args_after_messages"]} messages, anything over {s["truncate_args_over_chars"]:,} characters that the model wrote with write_file or edit_file is cut from all but the last {s["truncate_args_keep_messages"]} messages'],
            ["Large tool results", f'our tool layer clips every result at {s["registry_clip_chars"]:,} characters (the full text stays in the build folder), so the library\'s move to a file at {s["evict_tool_result_chars"]:,} characters never happens'],
            ["Prompt caching", "none in effect: the library's caching acts on Anthropic chat models only, and the role agents use OpenRouter models"],
            ["Limits", f'{s["recursion_limit"]["rtl"]} graph steps for the RTL writer, {s["recursion_limit"]["others"]} for the other roles; a simulation stops after four times its last passing run time plus two minutes, between {s["sim_timeout_s"]["min"]} s and {s["sim_timeout_s"]["max"]:,} s, and after {s["sim_timeout_s"]["default"]:,} s when there is no passing run yet'],
        ])
    if name == "harness_arms":
        rows = [[a["id"], a["name"], a["change"], a["evidence"], a["status"]] for a in A["harness"]["arms"]]
        return table(["Arm", "Change", "What it does", "Evidence that motivated it", "Result"], rows)
    if name == "harness_fixes":
        out = ['<ul class="fixes">']
        for f in A["harness"]["fixes"]:
            ev = " ".join(f'<a class="evsrc" href="{REPO}/blob/main/{html.escape(x)}">{html.escape(x.split("/")[-1])}</a>' for x in f["files"])
            out.append(f'<li><b>{html.escape(f["name"])}.</b> {html.escape(f["text"])} <span class="evl">Evidence: '
                       f'<a class="evsrc" href="{REPO}/pull/{f["pr"]}">pull request {f["pr"]}</a> {ev}</span></li>')
        return "".join(out) + "</ul>"
    raise KeyError(name)


def loop_block(name, d):
    """index.html (brief 47): the feedback loop on the bench, the legs and where each label comes from."""
    import loop_page as lp
    L = d["loop"]
    if name == "loop_hero":
        import agent_page as ap
        return ap.both(lp.hero(L, "wide"), lp.hero(L, "narrow"))
    if name == "loop_legs":
        return lp.legs_table(L, REPO)
    if name == "loop_sources":
        return table(["Station", "Label", "Read from"], lp.sources_table(L))
    raise KeyError(name)


def xpm_figure(x):
    """Two-clock probe and the setup slack on the crossing, before and after; all numbers from the data."""
    b, a = x["before"]["wns_ns"], x["after"]["wns_ns"]
    zero, k = 120, 17.0
    xb, xa = zero + b * k, zero + a * k
    return f"""<div class="fig"><svg viewBox="0 0 400 190" role="img" aria-labelledby="xp1t xp1d">
<title id="xp1t">The probe design: two clock domains joined by two XPM crossings</title>
<desc id="xp1d">A clk_a domain with a {x["clk_a_period_ns"]} ns period feeds clk_b, with a {x["clk_b_period_ns"]} ns period, through one xpm_cdc_single and one xpm_cdc_gray.</desc>
<rect class="box" x="6" y="6" width="120" height="178"/><text x="14" y="24">clk_a, {x["clk_a_period_ns"]} ns</text>
<rect class="box" x="274" y="6" width="120" height="178"/><text x="282" y="24">clk_b, {x["clk_b_period_ns"]} ns</text>
<rect class="boxink" x="18" y="52" width="86" height="30"/><text x="26" y="71">source flop</text>
<rect class="boxink" x="18" y="122" width="86" height="30"/><text x="28" y="141">source bus</text>
<rect class="boxink" x="296" y="52" width="76" height="30"/><text x="304" y="71">stage 1, 2</text>
<rect class="boxink" x="296" y="122" width="76" height="30"/><text x="304" y="141">Gray stage</text>
<line class="ink" x1="104" y1="67" x2="296" y2="67"/><path class="ink" d="M290 62 L296 67 L290 72"/>
<line class="ink" x1="104" y1="137" x2="296" y2="137"/><path class="ink" d="M290 132 L296 137 L290 142"/>
<text x="134" y="58">xpm_cdc_single</text><text x="140" y="128">xpm_cdc_gray</text>
</svg></div>
<div class="fig"><svg viewBox="0 0 400 130" role="img" aria-labelledby="xp2t xp2d">
<title id="xp2t">Setup slack on the clk_a to clk_b path, before and after</title>
<desc id="xp2d">Before the fix the worst setup slack is {b:+.3f} ns. After it is {a:+.3f} ns.</desc>
<defs><pattern id="hatchwarn" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="var(--warn)" stroke-width="2"/></pattern></defs>
<line class="rule" x1="{zero}" y1="22" x2="{zero}" y2="118"/>
<text x="6" y="14">worst setup slack, clk_a to clk_b (ns)</text>
<rect class="barneg" x="{xb:.1f}" y="32" width="{zero - xb:.1f}" height="26"/>
<text x="6" y="75">before: {b:+.3f}</text>
<rect class="barpos" x="{zero}" y="82" width="{xa - zero:.1f}" height="26"/>
<text x="{zero + 8}" y="99" class="inv">after: {a:+.3f}</text>
</svg></div>"""


def exception_figure():
    """A timing path with and without an over-broad false path (schematic, no measured values)."""
    def panel(covered, ident):
        path = '<rect class="boxink" x="14" y="36" width="64" height="30"/><text x="22" y="55">launch</text>' \
               '<rect class="box" x="132" y="36" width="116" height="30"/><text x="146" y="55">logic, too slow</text>' \
               '<rect class="boxink" x="302" y="36" width="64" height="30"/><text x="308" y="55">capture</text>' \
               '<line class="ink" x1="78" y1="51" x2="132" y2="51"/><line class="ink" x1="248" y1="51" x2="302" y2="51"/>'
        if covered:
            cover = '<rect class="dash" x="6" y="26" width="368" height="50"/><text x="10" y="92">set_false_path covers this path</text>' \
                    '<text x="10" y="112">timing report: path not timed, no violation listed</text>'
        else:
            cover = '<text x="10" y="92">no exception on this path</text>' \
                    '<text x="10" y="112">timing report: negative slack, violation listed</text>'
        label = "With a blanket false path" if covered else "Without an exception"
        return f'<div class="fig"><svg viewBox="0 0 400 124" role="img" aria-label="{label}: a path that fails setup" ><text x="6" y="16" class="big">{label}</text>{path}{cover}</svg></div>'
    return '<div class="cols">' + panel(False, "a") + panel(True, "b") + "</div>"


def render_template(text, d):
    text = text.replace('<div class="tablewrap"><table>', '<div class="tablewrap" tabindex="0"><table>')
    text = re.sub(r"\{\{!(\w+)\}\}", lambda m: block(m.group(1), d), text)
    return re.sub(r"\{\{([\w.]+)\}\}", lambda m: html.escape(fmt(lookup(d, m.group(1)))), text)


def layout(fname, title, desc, body, keys, d, css, js, prefix="", current=None, pager=None):
    cur = current or fname
    nav = "".join(f'<a href="{prefix}{f}"{" aria-current=\"page\"" if f == cur else ""}>{html.escape(n)}</a>' +
                  "".join(f'<a class="sub" href="{prefix}{h}">{html.escape(w)}</a>' for a, h, w in NAV_SUB if a == f) for f, n, *_ in PAGES)
    scripts = "".join(f'<script type="application/json" data-key="{k}">{json.dumps(d[k], separators=(",", ":")).replace("</", "<\\/")}</script>'
                      for k in keys if k in d)
    if pager is None:
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
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<style>{css}</style>
</head>
<body>
<a class="visually-hidden" href="#main">Skip to content</a>
<header class="bar"><div class="wrap"><a class="brand" href="{prefix}index.html">End-to-end FPGA Agent</a><nav aria-label="Pages">{nav}</nav><button id="theme" type="button" aria-label="Switch to dark theme">Dark</button></div></header>
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


def task_order(d):
    C = d["catalogue"]
    doms = list(C["domains"])
    return sorted(C["tasks"], key=lambda r: (doms.index(r["domain"]), r["set"] != "v1", r["id"]))


def build(outdir: Path, d, check_numbers=True):
    """Pages {relative path: html}. Number check per page: the shared data (without the per-task files) plus, on a task
    page, that task's own data file only; so a number on one task page must come from that task's committed files."""
    import catalogue_pages
    css = (SRC / "site.css").read_text()
    js = (SRC / "app.js").read_text()
    shared = {k: v for k, v in d.items() if k != "tasks"}
    if "catalogue" in d:
        shared["catalogue_index"] = {"domains": d["catalogue"]["domains"]}
    pages, page_data = {}, {}
    for fname, label, title, desc, keys in PAGES:
        body = render_template((SRC / fname).read_text(), d)
        pages[fname] = layout(fname, title, desc, body, keys, shared, css, js)
        page_data[fname] = shared
    if "catalogue" in d:
        order = task_order(d)
        for i, r in enumerate(order):
            T = d["tasks"][r["id"]]
            prev = order[i - 1] if i else None
            nxt = order[i + 1] if i + 1 < len(order) else None
            body = catalogue_pages.task_body(T, d["catalogue"], prev, nxt)
            pd = dict(shared); pd["trace"] = T["trace"]
            desc = f'{T["heading"]}: the spec, hidden tests, reference RTL, mutants and golden model of benchmark task {T["id"]}.'
            fn = f'problems/{T["id"]}.html'
            pages[fn] = layout("problems.html", T["heading"], desc, body, ["trace"], pd, css, js, prefix="../", current="problems.html",
                               pager='<div class="pager"><a href="../problems.html">&larr; All problems</a><span></span></div>')
            page_data[fn] = {"shared": {k: v for k, v in shared.items() if k != "catalogue_index"}, "task": T}
    bad = []
    if check_numbers:
        allow = allow_tokens()
        cache = {}
        for fname, page in pages.items():
            key = fname if fname.startswith("problems/") else "_shared"
            if key not in cache:
                cache[key] = data_tokens(page_data[fname]) | allow
            ok = cache[key]
            for tok in visible_numbers(page):
                t = tok.lstrip("+-") if tok[0] in "+-" else tok
                if tok not in ok and t not in ok and tok.rstrip(",") not in ok:
                    bad.append((fname, tok))
    return pages, bad


def static_files(d):
    """Binary and download files written beside the pages: the code of each development task, for its Download links."""
    out = {"favicon.svg": (SRC / "favicon.svg").read_bytes(), "t1_on_nexys_a7.jpg": (ROOT / "docs/img/t1_on_nexys_a7.jpg").read_bytes(),
           "vercel.json": b'{"cleanUrls": true, "trailingSlash": false}\n'}
    for tid, T in d.get("tasks", {}).items():
        for grp in T["files"].values():
            for f in grp:
                out[f"problems/{tid}/{f['name']}"] = (ROOT / f["path"]).read_bytes()
    return out


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
    static = static_files(d)
    if "--check" in args:
        stale = [f for f, p in pages.items() if not (out / f).exists() or (out / f).read_text() != p]
        stale += [f for f, b in static.items() if not (out / f).exists() or (out / f).read_bytes() != b]
        known = set(pages) | set(static)
        extra = [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.relative_to(out).as_posix() not in known]
        if stale or extra:
            print("stale:", stale, "unexpected:", extra)
            sys.exit(1)
        print("ok:", len(pages), "pages, numbers all in data")
        return
    out.mkdir(parents=True, exist_ok=True)
    for f, p in pages.items():
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        (out / f).write_text(p)
    for f, b in static.items():
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        (out / f).write_bytes(b)
    print("wrote", len(pages), "pages to", out)


if __name__ == "__main__":
    main()
