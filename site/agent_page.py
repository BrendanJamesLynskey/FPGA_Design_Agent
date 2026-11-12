"""SVG figures for agent.html (brief 43), drawn from site/data/agent_graph.json.

Every figure has two hand-tuned layouts: a wide one (viewBox 940 wide, shown from 820 px) and a narrow one (360 wide,
for phones), on fixed grids. The nodes and edges come from the data; only their positions are chosen here, per node
id, so a node the code adds and this file does not place fails the build (KeyError) and the site test.

Type: the site's sans at three sizes (classes t = 15 px, default 13 px, s = 11 px). Strokes 1.5 px. Monochrome
tokens, one accent (--accent) for "active", --warn for a failed gate.
"""
from __future__ import annotations

import html
import math

E = html.escape
CW13, CW11 = 6.7, 5.8          # average glyph advance of the site's sans at 13 and 11 px (measured in Chrome, rounded up)


def tw(text, size=13):
    return len(text) * (CW13 if size == 13 else CW11 if size == 11 else 7.9)


def wrap(text, width, size=11):
    per = max(8, int(width / (CW11 if size == 11 else CW13)))
    out, line = [], ""
    for w in text.split():
        if line and len(line) + 1 + len(w) > per:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


def defs(p):
    return (f'<defs><marker id="{p}-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path class="ah" d="M0 0 L10 5 L0 10 z"/></marker>'
            f'<marker id="{p}-aha" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path class="aha" d="M0 0 L10 5 L0 10 z"/></marker></defs>')


def svg(p, w, h, body, label, cls):
    return (f'<svg class="ag {cls}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{p}-t"><title id="{p}-t">{E(label)}</title>'
            f'{defs(p)}{body}</svg>')


def text(x, y, s, cls="", anchor="start"):
    c = f' class="{cls}"' if cls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{x:g}" y="{y:g}"{c}{a}>{E(s)}</text>'


def lines(x, y, rows, cls="s", lh=15, anchor="start"):
    return "".join(text(x, y + i * lh, r, cls, anchor) for i, r in enumerate(rows))


def box(x, y, w, h, cls="nd", rx=6, extra=""):
    return f'<rect class="{cls}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx}"{extra}/>'


def edge(d, p, cls="ed", extra=""):
    return f'<path class="{cls}" d="{d}" marker-end="url(#{p}-ah)"{extra}/>'


def both(wide, narrow):
    return f'<div class="agfig"><div class="lay-w">{wide}</div><div class="lay-n">{narrow}</div></div>'


# ---------------------------------------------------------------- 1. the LangGraph controller, from get_graph()

GPOS = {  # hand-tuned centres per node id: wide (row) and narrow (column)
    "wide": {"__start__": (34, 96), "work": (176, 96), "gate": (360, 96), "review": (544, 96), "advance": (728, 96), "__end__": (904, 96)},
    "narrow": {"__start__": (130, 22), "work": (130, 92), "gate": (130, 186), "review": (130, 280), "advance": (130, 374), "__end__": (130, 466)},
}
NW, NH = 124, 46


def _gedge(e, pos, lay, p):
    s, t = e["source"], e["target"]
    (x1, y1), (x2, y2) = pos[s], pos[t]
    term = {"__start__", "__end__"}
    if lay == "wide":
        if s == "advance" and t == "work":            # the conditional loop, under the row
            d = f"M{x1} {y1 + NH / 2} C{x1} {y1 + 92}, {x2} {y2 + 92}, {x2} {y2 + NH / 2 + 2}"
            lab = (x1 + x2) / 2, y1 + 86, "middle"
        else:
            sx = x1 + (10 if s in term else NW / 2)
            ex = x2 - (12 if t in term else NW / 2 + 1)
            d = f"M{sx} {y1} L{ex} {y2}"
            lab = (sx + ex) / 2, y1 - 12, "middle"
    else:
        if s == "advance" and t == "work":            # loop on the right of the column
            d = f"M{x1 + NW / 2} {y1} C{x1 + 215} {y1}, {x2 + 215} {y2}, {x2 + NW / 2 + 2} {y2}"
            lab = x1 + 74, (y1 + y2) / 2 + 4, "start"
        else:
            sy = y1 + (10 if s in term else NH / 2)
            ey = y2 - (12 if t in term else NH / 2 + 1)
            d = f"M{x1} {sy} L{x2} {ey}"
            lab = x1 - 10, (sy + ey) / 2 + 4, "end"
    return d, lab


def langgraph(G, lay):
    p = f"lg{lay[0]}"
    pos = GPOS[lay]
    W, H = (940, 200) if lay == "wide" else (360, 492)
    out = []
    for e in G["edges"]:
        d, (lx, ly, an) = _gedge(e, pos, lay, p)
        dash = ' stroke-dasharray="5 4"' if e["conditional"] else ""
        out.append(f'<path class="ed" d="{d}"{dash} marker-end="url(#{p}-ah)" data-e="{E(e["source"])}~{E(e["target"])}"/>')
        rows = [e["label"]]
        if lay == "narrow" and e["source"] == "advance" and e["target"] == "work":
            rows = e["label"].replace(", or ", ",|or ").split("|")
        elif lay == "wide" and not e["conditional"] and len(e["label"]) > 9:
            w = e["label"].split(" ")
            k = max(1, len(w) // 2)
            rows, ly = [" ".join(w[:k]), " ".join(w[k:])], ly - 14
        out.append(lines(lx, ly, rows, "s el", 14, an))
    for n in G["nodes"]:
        x, y = pos[n["id"]]
        if n["id"] in ("__start__", "__end__"):
            out.append(f'<g data-n="{E(n["id"])}"><circle class="{"term" if n["id"] == "__start__" else "termo"}" cx="{x}" cy="{y}" r="10"/>'
                       + (text(x, y + 28, n["label"], "s", "middle") if lay == "wide" else text(x + 18, y + 4, n["label"], "s")) + "</g>")
        else:
            out.append(f'<g data-n="{E(n["id"])}">{box(x - NW / 2, y - NH / 2, NW, NH)}{text(x, y + 5, n["label"], "t", "middle")}</g>')
    return svg(p, W, H, "".join(out), "The agent's LangGraph: start, work, gate, review, advance, then work again or end; read from the compiled graph", "lg")


# ---------------------------------------------------------------- 2. architecture

def _chips(items, x0, y0, width, h=30, gap=8, arrows=False, size=13, p="ar"):
    """Place chips left to right, wrapping; returns (svg, height used)."""
    out, x, y = [], x0, y0
    prev = None
    for it in items:
        label, cls = (it, "chip") if isinstance(it, str) else it
        w = tw(label, size) + 22
        step = gap + (16 if arrows else 0)
        if x > x0 and x + w > x0 + width:
            x, y, prev = x0, y + h + 10, None
        if arrows and prev is not None:
            out.append(edge(f"M{prev + 3} {y + h / 2} L{x - 3} {y + h / 2}", p))
        out.append(box(x, y, w, h, cls, 4) + text(x + w / 2, y + h / 2 + 4.5, label, "" if size == 13 else "s", "middle"))
        prev = x + w
        x += w + step
    return "".join(out), y + h - y0


def architecture(A, lay):
    wide = lay == "wide"
    W = 940 if wide else 360
    bx = 34 if wide else 22                # band left: the return rail runs in the margin on its left
    bw = 556 if wide else W - bx
    st = A["stages"]
    v = A["versions"]
    layers = [
        ("spec", "Spec and interview", [("spec.md, plain English", "chip"), ("interview", "chip"), ("spec.yaml, signed off", "chip")], True, None),
        ("ctl", "LangGraph controller", [("work", "chip"), ("gate", "chip"), ("review", "chip"), ("advance", "chip")], True,
         f"LangGraph {v['langgraph']}: the stage machine, its limits and its repair routing, in code"),
        ("roles", "Role agents", [(r["label"], "chip") for r in A["roles"]], False,
         "same roles, prompts, tools and gates on either harness"),
        ("tools", "Tool layer", [(g, "chip") for g in ("Files", "Knowledge", "Verification", "Vivado")], False,
         f"one registry: in process for Deep Agents, over MCP {v['mcp']} for Claude Code; path jail, argument check, audit log"),
        ("flow", "Flow", [(f"Vivado {A['vivado']}", "chip"), ("Icarus and cocotb", "chip"), ("Verilator", "chip"), ("SymbiYosys", "chip")], False,
         "fixed commands built by the tools; the model never writes Tcl or shell"),
        ("gates", "Gates", [("V0 to V3", "chip"), ("stage gates", "chip"), ("design standards", "chip"), ("CDC and timing exceptions", "chip")], False,
         "parsed from the reports by code; the agent's own tests never decide"),
        ("board", "Board shell", [("program SRAM, after approval", "chip"), ("UART test shell", "chip")], False,
         "the model is never offered the board"),
    ]
    between = {"spec": "spec.yaml", "ctl": "stage prompt, files, repair notes", "roles": "tool calls, schema-checked",
               "tools": "fixed commands", "flow": "reports and logs", "gates": "bitstream, once approved"}
    out, y, mids = [], 6, {}
    for lid, title, chips, arrows, note in layers:
        inner = [text(bx + 14, y + 24, title, "t")]
        cs, ch = _chips(chips, bx + 14, y + 36, bw - 28, arrows=arrows)
        inner.append(cs)
        h = 36 + ch + 12
        if lid == "roles":                     # the harness switch, under the four roles
            sy = y + h
            sw = (bw - 28 - 36) / 2 if wide else bw - 28
            a = ("Deep Agents", f"deepagents {v['deepagents']}; OpenRouter models")
            b = ("Claude Code", "headless; Anthropic models")
            if wide:
                inner.append(f'<g class="sw" data-h="deepagents">{box(bx + 14, sy, sw, 46, "chip2", 4)}{text(bx + 26, sy + 19, a[0])}{text(bx + 26, sy + 36, a[1], "s")}</g>')
                inner.append(text(bx + 14 + sw + 18, sy + 28, "or", "s", "middle"))
                inner.append(f'<g class="sw" data-h="claude_code">{box(bx + 14 + sw + 36, sy, sw, 46, "chip2", 4)}{text(bx + 26 + sw + 36, sy + 19, b[0])}{text(bx + 26 + sw + 36, sy + 36, b[1], "s")}</g>')
                h += 46 + 12
            else:
                for k, (t1, t2) in enumerate((a, b)):
                    yy = sy + k * 64
                    hh = 18 + 15 * len(wrap(t2, sw - 24))
                    inner.append(f'<g class="sw" data-h="{"deepagents" if k == 0 else "claude_code"}">{box(bx + 14, yy, sw, hh + 10, "chip2", 4)}'
                                 f'{text(bx + 26, yy + 19, t1)}{lines(bx + 26, yy + 36, wrap(t2, sw - 24))}</g>')
                    if k == 0:
                        inner.append(text(bx + 14 + sw / 2, yy + hh + 26, "or", "s", "middle"))
                h += 64 + 18 + 15 * len(wrap(b[1], sw - 24)) + 22
        if note:
            nl = wrap(note, bw - 28)
            inner.append(lines(bx + 14, y + h + 2, nl))
            h += 15 * len(nl) + 6
        out.append(f'<g data-l="{lid}">{box(bx, y, bw, h, "band", 8)}{"".join(inner)}</g>')
        mids[lid] = (y, h)
        y += h
        if lid in between:
            ax = bx + 40
            out.append(edge(f"M{ax} {y + 2} L{ax} {y + 34}", "ar") + text(ax + 12, y + 22, between[lid], "s"))
            y += 38
    # the return rail: gates -> controller, on the left margin
    gy, gh = mids["gates"]
    cy, chh = mids["ctl"]
    rx = 14 if wide else 9
    out.append(f'<path class="ed" d="M{bx} {gy + 24} L{rx} {gy + 24} L{rx} {cy + 24} L{bx - 2} {cy + 24}" marker-end="url(#ar-ah)"/>')
    if wide:
        out.append(f'<g transform="translate({rx - 5} {(gy + cy) / 2 + 40}) rotate(-90)">{text(0, 0, "gate results, failures", "s", "middle")}</g>')
    else:
        out.append(f'<g transform="translate({rx - 4} {(gy + cy) / 2 + 40}) rotate(-90)">{text(0, 0, "gate results, failures", "s", "middle")}</g>')
    # beside: the knowledge bank and the project layer
    B = A["bank"]
    bank_rows = [f"private; pinned at commit {B['pin']}", f"{B['skills']} skills in {B['units']} units"] + \
        [f"{x['layer']}: {x['skills']}" for x in B["layers"]]
    proj_rows = ["a module graph (design.yaml)", "a contract for each module", "contract tests, generated without a model",
                 "beside the agent today: its own commands, not yet called by the graph"]
    if wide:
        sx, sw = 640, 300
        ty, th = mids["tools"]
        ry, rh = mids["roles"]
        by0 = ry
        rows = bank_rows + ["", "reached from the tool layer through", "load_skill and search_docs"]
        bh = 40 + 15 * len(rows) + 8
        out.append(f'<g data-l="bank">{box(sx, by0, sw, bh, "band", 8)}{text(sx + 14, by0 + 24, "Knowledge bank", "t")}{lines(sx + 14, by0 + 46, rows)}</g>')
        out.append(f'<path class="ed" d="M{bx + bw} {ty + 52} L{sx - 30} {ty + 52} L{sx - 30} {by0 + bh / 2} L{sx - 2} {by0 + bh / 2}" marker-end="url(#ar-ah)"/>')
        py0 = mids["spec"][0]
        prow = [x for r in proj_rows for x in wrap(r, sw - 28)]
        ph = 40 + 15 * len(prow) + 8
        out.append(f'<g data-l="project">{box(sx, py0, sw, ph, "band dashb", 8)}{text(sx + 14, py0 + 24, "Project layer", "t")}{lines(sx + 14, py0 + 46, prow)}</g>')
        H = max(y, py0 + ph, by0 + bh) + 6
    else:
        for lid, title, rows in (("bank", "Knowledge bank", bank_rows + ["reached through load_skill and search_docs"]),
                                 ("project", "Project layer", proj_rows)):
            y += 18
            rr = [x for r in rows for x in wrap(r, bw - 28)]
            h = 40 + 15 * len(rr) + 8
            out.append(f'<g data-l="{lid}">{box(bx, y, bw, h, "band" + (" dashb" if lid == "project" else ""), 8)}{text(bx + 14, y + 24, title, "t")}{lines(bx + 14, y + 46, rr)}</g>')
            y += h
        H = y + 6
    body = "".join(out).replace("url(#ar-ah)", f"url(#ar{lay[0]}-ah)")
    return svg(f"ar{lay[0]}", W, H, body, "Architecture: spec and interview, the LangGraph controller, role agents on either harness, "
               "the tool layer, the flow, the gates and the board shell, with the knowledge bank and project layer beside them", "arch")


# ---------------------------------------------------------------- 3. inside one role agent

def inner(A, kind):
    """kind 'deepagents' (from the compiled role agent) or 'claude_code' (the headless arm)."""
    W = 380
    p = f"in{kind[0]}"
    out = []
    if kind == "deepagents":
        I, words = A["inner"], A["inner_words"]
        out.append(text(0, 18, "Deep Agents role agent", "t"))
        out.append(text(0, 36, f"create_deep_agent, deepagents {A['versions']['deepagents']}", "s"))
        # the model <-> tools loop drawn from the compiled inner graph
        mx, tx, yy = 70, 300, 96
        assert {"model", "tools"} <= set(I["nodes"])
        out.append(box(mx - 60, yy - 22, 120, 44) + text(mx, yy + 5, words["model"], "", "middle"))
        out.append(box(tx - 60, yy - 22, 120, 44) + text(tx, yy + 5, words["tools"], "", "middle"))
        e = {(a, b) for a, b, _ in I["edges"]}
        if ("model", "tools") in e:
            out.append(edge(f"M{mx + 60} {yy - 8} L{tx - 62} {yy - 8}", p))
        if ("tools", "model") in e:
            out.append(edge(f"M{tx - 60} {yy + 8} L{mx + 62} {yy + 8}", p))
        out.append(text((mx + tx) / 2, yy - 30, "until no more calls", "s", "middle"))
        bt = I["builtin_tools"]
        out.append(text(0, 148, "Built-in tools, on a jailed file backend:", ""))
        cs, ch = _chips([(t, "chip") for t in bt], 0, 158, W, h=26, gap=6, size=11)
        out.append(cs)
        y = 158 + ch + 22
        out.append(text(0, y, "Plus the stage's own tools from the tool layer.", "s"))
        out.append(text(0, y + 18, ("A to-do tool: " + ("yes" if I["todo_tool"] else "none") + ". Sub-agents: " +
                                    ("yes" if I["subagent_tool"] else "none (switched off)") + "."), "s"))
        H = y + 30
        label = "Inside a Deep Agents role agent: a model and tool loop over a jailed file backend"
    else:
        out.append(text(0, 18, "Claude Code role agent", "t"))
        out.append(text(0, 36, "one headless claude -p call per role turn", "s"))
        mx, tx, yy = 70, 300, 96
        out.append(box(mx - 60, yy - 22, 120, 44) + text(mx, yy + 5, "model call", "", "middle"))
        out.append(box(tx - 60, yy - 22, 120, 44) + text(tx, yy + 5, "MCP tools", "", "middle"))
        out.append(edge(f"M{mx + 60} {yy - 8} L{tx - 62} {yy - 8}", p))
        out.append(edge(f"M{tx - 60} {yy + 8} L{mx + 62} {yy + 8}", p))
        out.append(text((mx + tx) / 2, yy - 30, "until no more calls", "s", "middle"))
        rows = ["Every built-in tool off; only the agent's MCP server.", "No user settings, skills or project files loaded.",
                "The same role jail and audit log as the Deep Agents tools."]
        out.append(text(0, 148, "Configured to match:", ""))
        out.append(lines(0, 168, rows))
        H = 168 + 15 * len(rows) + 4
        label = "Inside a Claude Code role agent: one headless call per turn, only the agent's MCP tools"
    return svg(p, W, H, "".join(out), label, "inner")


# ---------------------------------------------------------------- 4. the stage pipeline

def pipeline(A, lay):
    wide = lay == "wide"
    p = f"pl{lay[0]}"
    W = 940 if wide else 360
    S = A["stages"]
    out, rows = [], []
    L = 44                                   # arcs run in x < L
    y = 8
    for s in S:
        gate_words = [g["words"] for g in s["gates"]]
        if wide:
            gl = wrap("; ".join(gate_words), 330)
            h = max(52, 16 + 15 * len(gl) + 10)
        else:
            gl = wrap("; ".join(gate_words), W - L - 28)
            h = 34 + 15 * len(gl) + 22
        rows.append((s, y, h, gl))
        y += h + 14
    H = y
    uf = [r for r in rows if r[0]["ultrafast"]]
    if uf:
        y0 = uf[0][1] - 6
        y1 = uf[-1][1] + uf[-1][2] + 6
        out.append(box(L - 6, y0, W - L + 6, y1 - y0, "ufband", 8))
        out.append(text(W, y1 + 18, "UltraFast stages (AMD UG949), inside the dotted line", "s", "end"))
        H = max(H, y1 + 26)
    for s, y, h, gl in rows:
        lim = s["limits"]
        bud = f"{lim['turns']} turns a visit, {s['visits']} visits"
        back = ", ".join(str(t) for t in s["loops_to"]) or "none"
        if wide:
            out.append(f'<g data-s="{s["n"]}" tabindex="0" class="stg">{box(L, y, 250, h)}'
                       f'{text(L + 14, y + 22, str(s["n"]), "t")}{text(L + 40, y + 22, s["label"], "t")}'
                       f'{text(L + 40, y + 40, ", ".join(_role_label(A, r) for r in s["roles"]), "s")}</g>')
            out.append(lines(L + 270, y + 18, gl))
            out.append(text(L + 620, y + 18, bud, "s"))
            out.append(text(L + 620, y + 34, "on failure, back to: " + back, "s"))
            if s["n"] == 2:
                cs, _ = _chips([(f"V{k}", "chip") for k in range(4)], L + 270, y + 18 + 15 * len(gl) - 6, 300, h=22, gap=6, arrows=True, size=11, p=p)
                out.append(cs)
        else:
            out.append(f'<g data-s="{s["n"]}" tabindex="0" class="stg">{box(L, y, W - L, h)}'
                       f'{text(L + 12, y + 22, str(s["n"]), "t")}{text(L + 36, y + 22, s["label"], "t")}</g>')
            out.append(lines(L + 12, y + 42, gl))
            out.append(text(L + 12, y + 42 + 15 * len(gl) + 2, bud + "; back to: " + back, "s"))
        if s["n"] < len(S) - 1:
            cx = L + 125 if wide else L + 160
            out.append(edge(f"M{cx} {y + h + 1} L{cx} {y + h + 12}", p))
    # repair arcs (shown for a focused stage and by the replay): left margin
    ys = {s["n"]: (y + h / 2) for s, y, h, gl in rows}
    for s, y, h, gl in rows:
        for t in s["loops_to"]:
            a, b = ys[s["n"]], ys[t]
            bulge = L - 8 - min(30, 5 + 4 * abs(s["n"] - t))
            out.append(f'<path class="arc" data-arc="{s["n"]}~{t}" d="M{L} {a} C{bulge} {a}, {bulge} {b}, {L - 1} {b}" marker-end="url(#{p}-aha)"/>')
    return svg(p, W, H, "".join(out), "The stages from interview to the board, the gates of each, their budgets, and where a failure goes back to", "pipe")


def _role_label(A, r):
    return {x["id"]: x["label"] for x in A["roles"]}[r]


# ---------------------------------------------------------------- 5. the live replay figure (animated by app.js)

def live(A, lay):
    wide = lay == "wide"
    p = f"lv{lay[0]}"
    W = 940 if wide else 360
    S = A["stages"]
    out = []
    # stage strip
    n = len(S)
    cw = (W - 2 * (n - 1)) / n
    for s in S:
        x = s["n"] * (cw + 2)
        out.append(f'<g data-st="{s["n"]}">{box(x, 26, cw, 40, "cell", 3)}{text(x + cw / 2, 44 if wide else 51, str(s["n"]), "s", "middle")}'
                   + (text(x + cw / 2, 59, s["label"].split(" ")[0], "s", "middle") if wide else "") + "</g>")
    out.append(text(0, 14, "Stages", "s"))
    out.append('<path class="rarc" d="" data-rarc="1" marker-end="url(#' + p + '-aha)"/>')
    # controller loop
    if wide:
        P = {"work": (110, 132), "gate": (330, 132), "review": (550, 132), "advance": (770, 132), "__end__": (904, 132)}
        E2 = {"work~gate": f"M172 132 L267 132", "gate~review": "M392 132 L487 132", "review~advance": "M612 132 L707 132",
              "advance~work": "M770 155 C770 200, 110 200, 110 156", "advance~__end__": "M832 132 L891 132",
              "__start__~work": "M110 84 L110 108"}
    else:
        P = {"work": (90, 120), "gate": (270, 120), "review": (270, 206), "advance": (90, 206), "__end__": (90, 276)}
        E2 = {"work~gate": "M152 120 L207 120", "gate~review": "M270 143 L270 182", "review~advance": "M208 206 L153 206",
              "advance~work": "M90 183 L90 144", "advance~__end__": "M90 229 L90 263", "__start__~work": "M20 120 L27 120"}
    for k, d in E2.items():
        dash = ' stroke-dasharray="5 4"' if k.startswith("advance~") else ""
        out.append(f'<path class="ed" id="{p}-e-{k.replace("~", "-")}" data-e="{k}" d="{d}"{dash} marker-end="url(#{p}-ah)"/>')
    for k, (x, y) in P.items():
        if k == "__end__":
            out.append(f'<g data-n="__end__"><circle class="termo" cx="{x}" cy="{y}" r="10"/>{text(x + (0 if wide else 18), y + (28 if wide else 4), "end", "s", "middle" if wide else "start")}</g>')
        else:
            out.append(f'<g data-n="{k}">{box(x - 62, y - 23, 124, 46)}{text(x, y + 5, k, "t", "middle")}</g>')
    out.append(f'<circle class="tok" r="6" cx="{P["work"][0]}" cy="{P["work"][1] - 23}" data-tok="1"/>')
    # roles, gate result, decision
    roles = A["roles"]
    if wide:
        ry, gx, gw, dx = 222, 262, 384, 676
        out.append(text(0, ry - 8, "Role agents", "s"))
        for k, r in enumerate(roles):
            x = (k % 2) * 116
            yy = ry + (k // 2) * 40
            out.append(f'<g data-r="{r["id"]}">{box(x, yy, 108, 32, "chip", 4)}{text(x + 54, yy + 21, r["label"], "", "middle")}</g>')
        out.append(text(gx, ry - 8, "Gate result", "s"))
        out.append(f'<g data-gate="1">{box(gx, ry, gw, 72, "gbox", 4)}<text class="gt" x="{gx + 14}" y="{ry + 22}"></text>'
                   f'<text class="gt s" x="{gx + 14}" y="{ry + 40}"></text><text class="gt s" x="{gx + 14}" y="{ry + 56}"></text></g>')
        out.append(text(dx, ry - 8, "Next", "s"))
        out.append(f'<g data-next="1">{box(dx, ry, W - dx, 72, "gbox", 4)}<text class="nt" x="{dx + 14}" y="{ry + 22}"></text>'
                   f'<text class="nt s" x="{dx + 14}" y="{ry + 40}"></text><text class="nt s" x="{dx + 14}" y="{ry + 56}"></text></g>')
        ty = ry + 110
        per, chw = 8, (W - 7 * 8) / 8
    else:
        ry = 312
        out.append(text(0, ry - 8, "Role agents", "s"))
        for k, r in enumerate(roles):
            x = (k % 2) * 182
            yy = ry + (k // 2) * 40
            out.append(f'<g data-r="{r["id"]}">{box(x, yy, 178, 32, "chip", 4)}{text(x + 89, yy + 21, r["label"], "", "middle")}</g>')
        gy = ry + 96
        out.append(text(0, gy - 8, "Gate result", "s"))
        out.append(f'<g data-gate="1">{box(0, gy, W, 88, "gbox", 4)}<text class="gt" x="14" y="{gy + 22}"></text>'
                   + "".join(f'<text class="gt s" x="14" y="{gy + 40 + 15 * i}"></text>' for i in range(3)) + "</g>")
        ny = gy + 112
        out.append(text(0, ny - 8, "Next", "s"))
        out.append(f'<g data-next="1">{box(0, ny, W, 72, "gbox", 4)}<text class="nt" x="14" y="{ny + 22}"></text>'
                   f'<text class="nt s" x="14" y="{ny + 40}"></text><text class="nt s" x="14" y="{ny + 56}"></text></g>')
        ty = ny + 106
        per, chw = 3, (W - 2 * 8) / 3
    out.append(text(0, ty - 8, "Tool layer: called this visit (count), offered, not offered", "s"))
    tools = [t for t in A["tools"]]
    for k, t in enumerate(tools):
        x = (k % per) * (chw + 8)
        yy = ty + (k // per) * 38
        out.append(f'<g data-t="{t["name"]}">{box(x, yy, chw, 30, "tchip", 4)}{text(x + 10, yy + 19.5, t["name"], "s")}'
                   f'<text class="tc s" x="{x + chw - 10:g}" y="{yy + 19.5}" text-anchor="end"></text></g>')
    H = ty + math.ceil(len(tools) / per) * 38 + 4
    return svg(p, W, H, "".join(out), "Replay of a recorded run through the controller, the role agents, the gates and the tool layer", "live")


# ---------------------------------------------------------------- 6. workflow variants (brief 42)

VARIANT_BASE = ["interview", "plan", "work", "gate", "advance"]
VARIANT_AT = {"before work": (2, "skill shortlist"), "after the interview": (1, "spec reviewer"), "the RTL writer": (3, None),
              "the plan": (2, "modules in parallel"), "the constraints stage": (4, "constraints critic")}


def variant(arm):
    """A small strip: the baseline chain with the arm's step added (dashed, accent)."""
    p = f"va{arm['id']}"
    at, extra = VARIANT_AT[arm["at"]]
    label = extra or {"A3": "N candidates", "A5": "retrieve, adapt"}[arm["id"]]
    chain = list(VARIANT_BASE)
    chain.insert(at, ("+" + label))
    out, x = [], 0
    for k, c in enumerate(chain):
        add = c.startswith("+")
        t = c[1:] if add else c
        w = tw(t, 11) + 16
        out.append(box(x, 6, w, 26, "vadd" if add else "chip", 4) + text(x + w / 2, 23, t, "s", "middle"))
        if k < len(chain) - 1:
            out.append(edge(f"M{x + w + 2} 19 L{x + w + 13} 19", p))
        x += w + 16
    return svg(p, x, 38, "".join(out), f"{arm['name']}: {arm['adds']}", "var").replace("<svg ", f'<svg style="max-width:{x:g}px" ', 1)


# ---------------------------------------------------------------- 7. the harness, layer by layer (brief 47)

MW_SHORT = {"FilesystemMiddleware": "file tools", "_ParentNotifierMiddleware": "parent notifier",
            "SummarizationMiddleware": "summarisation", "PatchToolCallsMiddleware": "patch tool calls",
            "AnthropicPromptCachingMiddleware": "Anthropic prompt caching", "UnsupportedContentMiddleware": "unsupported content"}


def harness_layers(A, lay):
    """Model, middleware, tools, jailed filesystem, our tool layer and gates: what a Deep Agents role agent runs inside."""
    wide = lay == "wide"
    p = f"hl{lay[0]}"
    W = 940 if wide else 360
    h, s = A["harness"], A["harness"]["settings"]
    roles = {r["id"]: r for r in A["roles"]}
    groups = []
    for g in ("Files", "Knowledge", "Verification", "Vivado"):
        groups.append(g + ": " + ", ".join(t["name"] for t in A["tools"] if t["group"] == g and t["model_may_call"]))
    layers = [
        ("model", "Model", [(f'{A["defaults"]["model"]}, through OpenRouter', "chip")],
         "one call per turn; the system prompt is the role's prompt alone" if h["system_prompt_only_ours"] else "one call per turn"),
        ("mw", "Middleware, in stack order", [(MW_SHORT[m["name"]], "chip" if m["acts"] else "tchip0") for m in h["middleware"]],
         f'summarises older turns at about {s["summarise_trigger_tokens"]:,} tokens; dotted: present, but does nothing for these models; '
         + ("no to-do list" if not h["todo_tool"] else "a to-do list") + ", " + ("no sub-agents" if not h["subagent_tool"] else "sub-agents")),
        ("tools", "Tools the model is offered", [("built-in: " + ", ".join(A["inner"]["builtin_tools"]), "chip")] + [(g, "chip") for g in groups],
         "the stage decides which of ours a role gets"),
        ("fs", "Jailed filesystem", [("RTL writer: the design folder", "chip"), ("other roles: an in-memory copy of their inputs", "chip")],
         "every path checked against the role's read and write lists; a write outside them is refused and logged"),
        ("ours", "Our tool layer and gates", [("argument check", "chip"), (f'output clipped at {s["registry_clip_chars"]:,} characters', "chip"),
                                               ("audit log", "chip"), ("gates in code", "chip")],
         f'fixed Vivado and simulator commands; a simulation stops after at most {s["sim_timeout_s"]["max"]:,} s'),
    ]
    out, y = [], 4
    for k, (lid, title, chips, note) in enumerate(layers):
        inner_ = [text(14, y + 24, title, "t")]
        items = []
        for lab, cls in chips:
            rows = wrap(lab, W - 60, 13) if tw(lab) + 22 > W - 28 else [lab]
            items.append((rows, cls))
        cx, cy, used = 14, y + 36, 0
        for rows, cls in items:
            w = max(tw(r) for r in rows) + 22
            hh = 14 + 16 * len(rows)
            if cx > 14 and cx + w > W - 14:
                cx, cy = 14, cy + used + 8
                used = 0
            inner_.append(box(cx, cy, w, hh, cls, 4) + lines(cx + 11, cy + 19, rows, "", 16))
            cx += w + 8
            used = max(used, hh)
        hgt = cy + used - y + 10
        nl = wrap(note, W - 28)
        inner_.append(lines(14, y + hgt + 4, nl))
        hgt += 15 * len(nl) + 6
        out.append(f'<g data-hl="{lid}">{box(0, y, W, hgt, "band", 8)}{"".join(inner_)}</g>')
        y += hgt
        if k < len(layers) - 1:
            out.append(edge(f"M40 {y + 2} L40 {y + 22}", p) + text(52, y + 16, ["each call and its reply pass through", "the tool calls it asks for", "built-in tools: reads and writes", "our tools: through the registry"][k], "s"))
            y += 26
    return svg(p, W, y + 4, "".join(out), "The harness of a Deep Agents role agent, layer by layer: model, middleware, tools, jailed filesystem, our tool layer and gates", "harn")


# ---------------------------------------------------------------- 8. harness experiment results (brief 61, from brief 42 round 1)

def harness_results(A, lay):
    """Paired change against the baseline for each measured arm and metric: the median (dot) and its 95 % bootstrap
    interval (bar), as a percentage of the baseline's median; 0 and the pre-registered 30 % bar drawn as rules."""
    arms = [a for a in A["harness"]["arms"] if a.get("result")]
    mets = [("cost_usd", "cost"), ("tokens", "tokens"), ("wall_s", "wall time")]
    lo, hi = -80, 40
    wide = lay == "wide"
    W = 940 if wide else 360
    L = 250 if wide else 92
    R = 20
    X = lambda v: L + (W - L - R) * (max(lo, min(hi, v)) - lo) / (hi - lo)
    rh, gap, top = 22, 18, 40
    out = []
    y = top
    rows = []
    for a in arms:
        rows.append(("arm", a, None, y))
        y += rh
        for k, w in mets:
            rows.append(("row", a, (k, w), y))
            y += rh
        y += gap
    H = y + 30
    ytop, ybot = top - 6, y - gap + 4
    for v in range(lo, hi + 1, 20):
        out.append(f'<line class="hgrid" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{ytop}" y2="{ybot}"/>')
        out.append(text(X(v), ybot + 16, f"{v:+d} %" if v else "0", "s", "middle"))
    out.append(f'<line class="hzero" x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{ytop - 8}" y2="{ybot}"/>')
    out.append(f'<line class="hbar30" x1="{X(-30):.1f}" x2="{X(-30):.1f}" y1="{ytop - 8}" y2="{ybot}"/>')
    out.append(text(X(-30) - 4, ytop - 12, "adopt bar: 30 % less", "s", "end"))
    out.append(text(X(0) + 4, ytop - 12, "no change", "s"))
    out.append(text(W - R, ybot + 32, "change against the baseline, % of its median (95 % interval)", "s", "end"))
    for kind, a, m, yy in rows:
        if kind == "arm":
            r = a["result"]
            out.append(text(0, yy + 14, f'{a["id"]} {a["name"]}', "t" if wide else ""))
            continue
        k, w = m
        p = a["result"]["paired"][k]
        out.append(text(L - 10 if wide else L - 6, yy + 14, w, "s", "end"))
        ok = p["excludes_0"]
        out.append(f'<line class="{"hci" if ok else "hci0"}" x1="{X(p["lo_pct"]):.1f}" x2="{X(p["hi_pct"]):.1f}" y1="{yy + 10}" y2="{yy + 10}"/>')
        out.append(f'<circle class="{"hpt" if ok else "hpt0"}" cx="{X(p["rel_pct"]):.1f}" cy="{yy + 10}" r="5"/>')
        if wide:
            out.append(text(X(hi) + 0, yy + 14, "", "s"))
    label = "; ".join(f'{a["id"]}: ' + ", ".join(f'{w} {a["result"]["paired"][k]["rel_pct"]:+g} % (interval {a["result"]["paired"][k]["lo_pct"]:+g} to {a["result"]["paired"][k]["hi_pct"]:+g} %)'
                                               for k, w in mets) for a in arms)
    return svg(f"hr{lay[0]}", W, H, "".join(out), "Harness experiments, paired change against the baseline: " + label, "hres")
