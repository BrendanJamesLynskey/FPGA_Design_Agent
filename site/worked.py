"""The site's story pages (brief 117): the home page's flow figure and mini evidence matrix, and the KR260 worked example.

build() reads site/worked/worked.yaml and the committed records it names and returns the data written to data/kr260.json:
every number the three pages show. A `path` fact is read from a JSON record; a `quote` fact is accepted only if the quoted
text occurs in the record (so a record that changes under the page fails the export). Figures are drawn here, in the manner
of agent_page.py: two layouts (wide 940, narrow 360), the site's tokens, one accent, no glow.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import yaml

from agent_page import E, box, defs, lines, text, wrap

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
TRACE_HREF = "traceability.html"      # brief 116's page; its route is not known yet. The one place to fix at merge (also used by build.py).
INSPECT_PLACEHOLDER = "brief 118 (one-command Vivado project and checkpoint view, not merged)"


def blob(path):
    return f"{REPO}/blob/main/{path}"


def _dig(d, path):
    for p in path.split("."):
        d = d[int(p)] if isinstance(d, list) else d[p]
    return d


def _fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def build():
    Y = yaml.safe_load((Path(__file__).parent / "worked" / "worked.yaml").read_text())
    facts, src = {}, {}
    cache = {}
    for f in Y["facts"]:
        p = ROOT / f["file"]
        assert p.exists(), f"missing record {f['file']}"
        if "quote" in f:
            assert f["quote"] in p.read_text(), f"{f['id']}: quote not found in {f['file']}"
            v = f["value"]
        else:
            j = cache.setdefault(f["file"], json.loads(p.read_text()))
            if "count_true" in f:
                v = sum(1 for x in _dig(j, f["count_true"]).values() if x is True)
            elif "count_all" in f:
                v = len(_dig(j, f["count_all"]))
            else:
                v = _dig(j, f["path"])
                if "round" in f:
                    v = round(v, f["round"])
        facts[f["id"]] = v
        src[f["id"]] = f["file"]
    per = Y["period_ns"]
    fib = facts["fibre_ns"]

    def ttt(e, l):                      # (L - E) x period - fibre: the board's tick-to-trade (docs/latency_definitions.md)
        return round((l - e) * per - fib, 1)
    builds = []
    for k, label, e, l, note in [
        ("ctl", "control (97C)", "ctl_E", "ctl_L", "the default build"),
        ("both", "agent_both (97C)", "both_E", "both_L", "two latency changes (brief 97)"),
        ("all3", "all3 (97C)", "all3_E", "all3_L", "three latency changes (brief 97)"),
        ("buf", "with the AMD-macro elastic buffer (96C)", "buf_E", "buf_L", "needed for a real network card"),
        ("gp", "with our own elastic buffer (96E)", "gp_E", "gp_L", "the same job, less delay")]:
        E_, L_ = facts[e], facts[l]
        facts[f"{k}_ttt"] = ttt(E_, L_)
        facts[f"{k}_LE"] = L_ - E_
        builds.append({"id": k, "label": label, "note": note, "E": E_, "L": L_, "LE": L_ - E_, "ttt": ttt(E_, L_)})
    facts["period"] = per
    kinds = Y["kinds"]
    reqs = []
    for r in Y["requirements"]:
        cells = {}
        for kid, c in r["cells"].items():
            cells[kid] = {"state": c["state"], "text": c["text"].format(**{k: _fmt(v) for k, v in facts.items()}), "file": c["file"]}
            assert (ROOT / c["file"]).exists(), c["file"]
        reqs.append({"id": r["id"], "text": r["text"], "cells": cells})
    return {"facts": facts, "sources": src, "builds": builds, "kinds": kinds, "requirements": reqs}


# ------------------------------------------------------------------ the flow figure (home page)

# stage names are the controller's own (site/data/agent_graph.json: stages); the layers are this project's
AGENT_STAGES = ["Interview", "Plan", "RTL and tests", "Constraints", "Build", "Closure"]
TOOL_EVID = ["Simulation", "Formal", "Timing", "Clock crossings"]
HW_EVID = ["Eye scan", "JTAG and SYSMON reads", "Debug captures", "Latency loop", "Optical module readings"]


def _node(x, y, w, h, rows, cls="nd", tcls="s"):
    return box(x, y, w, h, cls) + lines(x + w / 2, y + 18, rows, tcls, 15, "middle")


def flow(lay):
    p = f"fl{lay[0]}"
    o = []
    if lay == "wide":
        W, H = 940, 440
        o.append(_node(0, 150, 120, 70, ["Specification", "ports, rules,", "limits, intent"], "nd youbox", "t" if False else "s"))
        o.append(text(60, 140, "YOU", "tg", "middle"))
        o.append(f'<path class="ed" d="M120 185 H150" marker-end="url(#{p}-ah)"/>')
        # agent band
        o.append(box(150, 10, 300, 380, "band"))
        o.append(text(165, 32, "AGENT: implements", "tg"))
        for i, s in enumerate(AGENT_STAGES):
            o.append(box(170, 46 + i * 55, 260, 42, "chip2"))
            o.append(text(300, 72 + i * 55, s, "", "middle"))
        # evidence layers
        o.append(f'<path class="ed" d="M450 185 H480" marker-end="url(#{p}-ah)"/>')
        o.append(box(480, 10, 250, 180, "band"))
        o.append(text(495, 32, "EVIDENCE 1: tools only", "tg"))
        for i, s in enumerate(TOOL_EVID):
            o.append(box(495, 44 + i * 34, 220, 28, "chip"))
            o.append(text(605, 63 + i * 34, s, "s", "middle"))
        o.append(box(480, 200, 250, 190, "band hwband"))
        o.append(text(495, 222, "EVIDENCE 2: hardware", "tg"))
        for i, s in enumerate(HW_EVID):
            o.append(box(495, 234 + i * 30, 220, 25, "chip hw"))
            o.append(text(605, 251 + i * 30, s, "s", "middle"))
        o.append(f'<path class="ed" d="M730 185 H760" marker-end="url(#{p}-ah)"/>')
        o.append(_node(760, 130, 180, 110, ["Evidence against", "every requirement:", "the traceability", "matrix"], "nd", "s"))
        o.append(text(850, 120, "YOU judge it", "tg", "middle"))
        o.append(f'<path class="ed dashb2" d="M850 240 V415 H60 V225" marker-end="url(#{p}-ah)"/>')
        o.append(text(455, 434, "Not thorough enough, or the spec was wrong: back to the specification or to the agent", "s", "middle"))
        return f'<svg class="ag flow" viewBox="0 0 {W} {H+10}" role="img" aria-labelledby="{p}-t"><title id="{p}-t">{E(TITLE)}</title>{defs(p)}{"".join(o)}</svg>'
    W = 360
    y = 0
    o.append(text(10, 14, "YOU", "tg"))
    o.append(_node(10, 22, 340, 44, ["Specification: ports, rules, limits, intent"], "nd", "s"))
    o.append(f'<path class="ed" d="M180 66 V84" marker-end="url(#{p}-ah)"/>')
    h = 40 + len(AGENT_STAGES) * 4 + 0
    o.append(box(10, 86, 340, 70, "band"))
    o.append(text(20, 106, "AGENT: implements", "tg"))
    o.append(lines(20, 126, ["Interview, plan, RTL and tests,", "constraints, build, closure"], "s", 15))
    o.append(f'<path class="ed" d="M180 156 V174" marker-end="url(#{p}-ah)"/>')
    o.append(box(10, 176, 340, 74, "band"))
    o.append(text(20, 196, "EVIDENCE 1: tools only", "tg"))
    o.append(lines(20, 216, ["Simulation, formal, timing,", "clock crossings"], "s", 15))
    o.append(f'<path class="ed" d="M180 250 V268" marker-end="url(#{p}-ah)"/>')
    o.append(box(10, 270, 340, 110, "band hwband"))
    o.append(text(20, 290, "EVIDENCE 2: hardware", "tg"))
    o.append(lines(20, 310, ["Eye scan, JTAG and SYSMON reads,", "debug captures, latency loop,", "optical module readings"], "s", 15))
    o.append(f'<path class="ed" d="M180 380 V398" marker-end="url(#{p}-ah)"/>')
    o.append(_node(10, 400, 340, 44, ["Traceability matrix: every requirement"], "nd", "s"))
    o.append(f'<path class="ed" d="M180 444 V462" marker-end="url(#{p}-ah)"/>')
    o.append(text(10, 476, "YOU", "tg"))
    o.append(_node(10, 484, 340, 62, ["Judge: is it thorough enough?", "If not, back to the spec or the agent"], "nd youbox", "s"))
    return f'<svg class="ag flow" viewBox="0 0 {W} 556" role="img" aria-labelledby="{p}-t"><title id="{p}-t">{E(TITLE)}</title>{defs(p)}{"".join(o)}</svg>'


TITLE = ("The flow: you write the specification; the agent implements it in stages; two layers of evidence come back, tool checks "
         "and hardware verification on the board with instruments; you judge the traceability matrix and send work back if it is not thorough enough.")


def flow_both():
    return f'<div class="agfig"><div class="lay-w">{flow("wide")}</div><div class="lay-n">{flow("narrow")}</div></div>'


# ------------------------------------------------------------------ the mini matrix (home page) and the builds table

def matrix(d):
    K = d["kinds"]
    head = "".join(f'<th scope="col">{E(k["label"])}</th>' for k in K)
    rows = []
    for ri, r in enumerate(d["requirements"]):
        cells = []
        for ki, k in enumerate(K):
            c = r["cells"].get(k["id"])
            if not c:
                cells.append('<td class="ev none" data-order="%d"><span class="mk" aria-hidden="true">-</span><span class="vh">no evidence of this kind recorded</span></td>' % ki)
                continue
            label = {"pass": "passed", "measured": "measured"}[c["state"]]
            cells.append(f'<td class="ev {c["state"]}" data-order="{ki}"><details><summary><span class="mk" aria-hidden="true">{"+" if c["state"]=="pass" else "~"}</span><span class="vh">{label}: </span>'
                         f'<span class="sw">{label}</span></summary><p>{E(c["text"])} <a href="{blob(c["file"])}">record</a></p></details></td>')
        rows.append(f'<tr><th scope="row"><span class="rid">{r["id"]}</span> {E(r["text"])}</th>{"".join(cells)}</tr>')
    return (f'<div class="tablewrap" tabindex="0"><table class="evm" id="evm"><caption class="vh">Requirements of the KR260 10G design against kinds of evidence</caption>'
            f'<thead><tr><th scope="col">Requirement</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def builds_table(d):
    rows = "".join(f'<tr><td>{E(b["label"])}<br><span class="muted small">{E(b["note"])}</span></td><td class="num">{_fmt(b["E"])}</td><td class="num">{_fmt(b["L"])}</td>'
                   f'<td class="num">{_fmt(b["LE"])}</td><td class="num">{_fmt(b["ttt"])}</td></tr>' for b in d["builds"])
    return ('<div class="tablewrap" tabindex="0"><table><thead><tr><th>Build</th><th class="num">Echo E (clocks)</th><th class="num">Loop L (clocks)</th>'
            '<th class="num">L &minus; E (clocks)</th><th class="num">Tick-to-trade (ns)</th></tr></thead><tbody>' + rows + '</tbody></table></div>')
