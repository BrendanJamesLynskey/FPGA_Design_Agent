"""site/traceability.html (brief 116): the body of the 'Traceability' page, drawn from site/data/traceability.json."""
from __future__ import annotations

import html

from story_page import REPO

E = html.escape
METHODS = [("sim_test", "Simulation test"), ("uvm_test", "UVM"), ("assertion", "SVA"), ("formal", "Formal"), ("formal_lean", "Lean (all widths)"), ("coverage_bin", "Coverage"),
           ("timing", "Timing"), ("sim_measurement", "Sim measure"), ("board_measurement", "Board"), ("review", "Review")]
STATE = {"verified": "verified", "fail": "fails", "not_run": "not run", "not_in_run": "not in the recorded run", "skipped": "skipped in the recorded run", "stale": "stale", "bounded": "bounded only",
         "no_measurement": "no measurement", "unapproved": "proved, statement not approved"}
MARK = {"pass": "pass", "fail": "FAIL", "not_run": "not run", "not_in_run": "not in the recorded run", "skipped": "skipped", "stale": "stale", "bounded": "bounded", "unapproved": "statement not approved"}
TIER = {"kernel_only": "kernel only", "compiled_decision_procedure": "kernel plus a compiled decision procedure", "unsound": "unsound"}
RTL_LINK = {"rtl_generated": "RTL-generated model", "transcription_tested": "transcription tested", "transcription_untested": "transcription untested", "model_only": "no RTL link"}
GAP = {"lean_frozen_statement_changed": "Lean: an approved statement changed", "lean_approval": "Lean: approval file problems", "lean_failing": "Lean proofs that fail",
       "lean_statement_unapproved": "Lean proofs whose statement is not approved by a human", "untraced_requirement": "Requirements with no verification item", "orphan_check": "Orphan checks (trace to no requirement)",
       "hardware_open": "Depend on an external element and not yet verified on hardware",
       "external_not_hardware_verified": "Depend on an external element and pass without hardware",
       "performance_sim_only": "Performance verified in simulation only", "no_passing_evidence": "No passing evidence",
       "stale_evidence": "Stale evidence", "bad_item": "Malformed entries"}
OPW = {"le": "at most", "ge": "at least", "lt": "below", "gt": "above", "eq": "equal to"}


def state_text(r: dict) -> str:
    if r["state"] == "verified" and r.get("external") and not r["hardware_verified"]:
        return "passes without hardware; hardware verification open"
    t = STATE[r["state"]]
    if r["state"] == "verified" and r["kind"] == "performance":
        t += " (" + {"board": "board-measured", "timing": "post-route timing"}.get(r["basis"], "simulation only") + ")"
    if r["state"] == "verified" and r.get("stale_items"):
        t += f"; {r['stale_items']} item(s) stale"
    if r["state"] == "verified" and r.get("lean_transcription_only"):
        t += "; the Lean proof is of a transcription of the RTL, not of the RTL itself"
    if r["state"] == "verified" and r.get("rests_on_delegated"):
        t += "; rests on a delegated acceptance of the Lean statement, not a human approval"
    return t


def lean_note(i: dict) -> str:
    L = i.get("lean")
    if i["method"] != "formal_lean" or not L:
        return ""
    bits = (["statement accepted on delegation, not a human approval" if L.get("approver_kind") == "agent_delegated" else "statement approved by a human"] if i["status"] == "pass" else []) + [TIER.get(L.get("tier") or "", "no build"), RTL_LINK.get(L.get("rtl_link") or "", "no RTL link"), (L.get("build_source") or "").replace(" (not re-run)", "")]
    return ' <span class="muted small">' + E("; ".join(b for b in bits if b)) + "</span>"


def link(path: str, text: str) -> str:
    return f'<a class="evsrc" href="{REPO}/blob/main/{E(path)}">{E(text)}</a>'


def matrix(g: dict) -> str:
    items = {i["id"]: i for i in g["items"]}
    head = "".join(f'<th class="mk" scope="col">{E(n)}</th>' for _, n in METHODS)
    rows = []
    for r in g["requirements"]:
        cells = []
        for m, _ in METHODS:
            its = [items[x] for x in r["items"] if items[x]["method"] == m]
            cells.append('<td class="mk">' + "<br>".join(
                f'<span class="tr-{i["status"]}">{MARK[i["status"]]}</span>' + (f' <span class="muted small">{E(i["instrument"])}</span>' if i.get("instrument") else "") + lean_note(i)
                for i in its) + "</td>")
        ext = f'<br><span class="muted small">Depends on {E(r["external"])}; hardware verification {r["hardware_closure"]}.</span>' if r.get("external") else ""
        st = "" if r["state"] == "verified" else " muted"
        rows.append(f'<tr id="{E(g["design"])}-{E(r["id"])}"><th scope="row"><b>{E(r["id"])}</b> {E(r["title"])}{ext}</th><td>{E(r["kind"])}</td>'
                    f'<td class="{st.strip()}">{E(state_text(r))}</td>{"".join(cells)}</tr>')
    return ('<div class="tablewrap" tabindex="0"><table class="mx trm"><thead><tr><th scope="col">Requirement</th><th scope="col">Kind</th><th scope="col">State</th>'
            f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def gaps(g: dict) -> str:
    if not g["gaps"]:
        return "<p>None.</p>"
    out = []
    for t in GAP:
        xs = [x for x in g["gaps"] if x["type"] == t]
        if xs:
            out.append(f"<h4>{E(GAP[t])}</h4><ul>" + "".join(f'<li><code>{E(str(x["id"]))}</code> {E(x["text"])}</li>' for x in xs) + "</ul>")
    return "".join(out)


def requirement(g: dict, r: dict) -> str:
    items = {i["id"]: i for i in g["items"]}
    pf = r.get("performance")
    li = []
    for x in r["items"]:
        i = items[x]
        ev = i.get("evidence")
        a = " " + link(ev["file"], "evidence") if ev and ev.get("exists") else ""
        extra = f' ({E(i["stale_because"])})' if i.get("stale_because") else ""
        li.append(f'<li>{E(i["method"].replace("_", " "))}{" / " + E(i["instrument"].replace("_", " ")) if i.get("instrument") else ""}: '
                  f'<b>{MARK[i["status"]]}</b>, {E(i["title"] or i["id"])}: {E(str(i["detail"]))}{extra}{a}</li>')
    b = (f'<p>Bound: {E(pf["quantity"])} {OPW.get(pf["op"], E(pf["op"]))} {E(str(pf["bound"]))} {E(pf["unit"])}. Condition: {E(pf["condition"])}.</p>' if pf else "")
    ext = f'<p>External element: {E(r["external"])}. Hardware verification: {E(r["hardware_closure"])}.</p>' if r.get("external") else ""
    return (f'<details class="more"><summary><b>{E(r["id"])}</b> {E(r["title"])}: {E(state_text(r))}</summary><p>{E(r.get("text", ""))}</p>{b}{ext}'
            f'<p class="muted small">Specification status: {E(r.get("spec_status", "unspecified"))}. Source: {E(r.get("source", ""))}</p><ul>{"".join(li)}</ul></details>')


def body(S: dict) -> str:
    C = S["content"]
    out = ['<p class="eyebrow">Specification and evidence</p><h1>What is specified, and what checks it</h1>',
           f'<p class="lede">{E(C["framing"])}</p>',
           '<p>Each row is a requirement. Each column is a way of checking it. Every status is computed by code from an evidence file; none is typed. '
           'A performance requirement counts as verified only when a measured value lies inside its bound, and the page says whether that was measured on the board, '
           'by post-route timing, or in simulation only. A requirement that depends on something outside the design, such as a network card or a second clock, '
           'is shown plainly as open until hardware verification has been done. Evidence that is older than the design files it is about is marked stale. '
           'Requirements here were drafted from the designs&#39; own documents and none has been agreed by a human yet.</p>']
    for g in C["designs"]:
        s = g["summary"]
        out.append(f'<h2 id="{E(g["design"])}">{E(g["design"])}</h2><p>{E(s["line"])}</p>')
        out.append(f'<div class="facts"><div class="fact"><div class="n">{s["requirements"]}</div><p>requirements</p></div>'
                   f'<div class="fact"><div class="n">{s["by_state"].get("verified", 0)}</div><p>verified</p></div>'
                   f'<div class="fact"><div class="n">{s["external_hardware_done"]} of {s["external"]}</div><p>requirements that depend on an external element closed by hardware verification</p></div></div>')
        big = len(g["requirements"]) > 30 or g["source_schema"].endswith("v0") or not any(i["method"] == "board_measurement" for i in g["items"])
        m = matrix(g)
        out.append(f'<details class="more"><summary>Matrix of {E(g["design"])}</summary>{m}</details>' if big else m)
        out.append("<h3>Gaps</h3>" + gaps(g))
        if not big:
            out.append("<h3>Each requirement, with its evidence</h3>" + "".join(requirement(g, r) for r in g["requirements"]))
        out.append(f'<p class="muted small">Files: {link(g["path"] + "/verif/matrix.md", "matrix.md")} {link(g["path"] + "/verif/testplan.yaml", "testplan.yaml")}</p>')
    out.append(f'<p>Schema, status rules and the gate are in {link("flow/trace_v1.py", "flow/trace_v1.py")}; the earlier requirement tags are in '
               f'<a href="{REPO}/blob/main/docs/traceability.md">docs/traceability.md</a>.</p>')
    return "".join(out)
