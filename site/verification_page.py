"""site/verification.html (brief 81): the body of the 'Verification' page, drawn from site/data/verification.json."""
from __future__ import annotations

import html

from story_page import REPO, link_chips

E = html.escape


def fm(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def mark(v, what: str) -> str:
    if v is None:
        return f'<td class="mk"><span class="sq na" aria-hidden="true">&ndash;</span><span class="vh">{E(what)}: cannot see this kind of fault</span></td>'
    cls = "y" if v else "n"
    txt = "flagged" if v else "not flagged"
    return f'<td class="mk"><span class="sq {cls}" aria-hidden="true"></span><span class="vh">{E(what)}: {txt}</span></td>'


def matrix(M: dict, first: str, caption: str, totals_label: str) -> str:
    head = "".join(f'<th class="mk" scope="col">{E(c)}</th>' for c in M["cols"])
    rows = "".join(f'<tr><th scope="row">{E(r.get("id", ""))}{" " if r.get("id") else ""}{E(r.get("what") or r["label"])}</th>' +
                   "".join(mark(f, M["cols"][i]) for i, f in enumerate(r["flags"])) + "</tr>" for r in M["rows"])
    tot = "".join(f'<td class="mk num">{t} of {len(M["rows"])}</td>' for t in M["totals"])
    return (f'<figure class="fig mxfig"><div class="tablewrap" tabindex="0"><table class="mx"><thead><tr><th scope="col">{E(first)}</th>{head}</tr></thead>'
            f'<tbody>{rows}</tbody><tfoot><tr><th scope="row">{E(totals_label)}</th>{tot}</tr></tfoot></table></div>'
            f'<figcaption>{E(caption)}</figcaption></figure>')


def stage_map(C: dict) -> str:
    T = {t["id"]: t for t in C["techniques"]}
    head = "".join(f'<th scope="col">{E(s["label"])}</th>' for s in C["stages"])
    rows = []
    for m in C["map"]:
        cells = []
        for s in C["stages"]:
            names = m["cells"].get(s["id"], [])
            cells.append(f'<td data-label="{E(s["label"])}">' + (" ".join(f"<code>{E(n)}</code>" for n in names) if names else '<span class="muted" aria-label="none">&middot;</span>') + "</td>")
        rows.append(f'<tr><th scope="row"><a href="#{m["technique"]}">{E(T[m["technique"]]["title"])}</a></th>{"".join(cells)}</tr>')
    return (f'<figure class="fig mapfig"><div class="tablewrap" tabindex="0"><table class="map"><thead><tr><th scope="col">Technique</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></figure>')


def closure_fig(P: dict) -> str:
    rows = P["rows"]
    W, X0, X1, RH, T = 400, 12, 388, 44, 4
    H = T + RH * len(rows) + 8
    sx = lambda v: X0 + (X1 - X0) * v / 100.0
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="clt cld"><title id="clt">Coverage and mutation score of T1 against the floors</title>'
           f'<desc id="cld">{"; ".join(E(r["label"]) + " " + fm(r["value"]) + " percent, floor " + fm(r["floor"]) for r in rows)}.</desc>']
    for i, r in enumerate(rows):
        y = T + RH * i
        out.append(f'<text class="flab" x="{X0}" y="{y + 13}">{E(r["label"])}</text>'
                   f'<text class="fval" x="{X1}" y="{y + 13}" text-anchor="end">{fm(r["value"])} %, floor {fm(r["floor"])} %</text>'
                   f'<rect class="sbox" x="{X0}" y="{y + 20}" width="{X1 - X0}" height="12"/>'
                   f'<rect class="{"sbar" if r["value"] >= r["floor"] else "sbad"}" x="{X0}" y="{y + 20}" width="{sx(r["value"]) - X0:.1f}" height="12"/>'
                   f'<line class="ftick" x1="{sx(r["floor"]):.1f}" y1="{y + 16}" x2="{sx(r["floor"]):.1f}" y2="{y + 37}"/>')
    out.append("</svg>")
    return f'<figure class="fig sfig">{"".join(out)}<figcaption>Bar: measured. Tick: the floor the flow will not let a plan lower.</figcaption></figure>'


def pin_fig(P: dict) -> str:
    out = []
    for i, s in enumerate(P["steps"]):
        cls = "ok" if s["ok"] else "bad"
        out.append(f'<li class="pstep {cls}"><span class="ptag">{"pass" if s["ok"] else "FAIL"}</span><b>{E(s["name"])}</b><span>{E(s["text"])}</span></li>')
    return f'<figure class="fig"><ol class="pin">{"".join(out)}</ol></figure>'


def depth_fig(V: dict) -> str:
    n, k = V["fa_depth"], V["fk_depth"]
    W, H, X0, X1 = 400, 150, 12, 388
    mid = X0 + (X1 - X0) * 0.45
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="dpt dpd"><title id="dpt">Bounded proof against k-induction</title>'
           f'<desc id="dpd">A bounded proof covers clock cycles zero to {n} and nothing after. A k-induction proof with k of {k} covers every cycle.</desc>',
           f'<text class="flab" x="{X0}" y="16">Bounded proof, depth {n}</text>',
           f'<rect class="sbar" x="{X0}" y="24" width="{mid - X0:.1f}" height="16"/>',
           f'<rect class="sunk" x="{mid:.1f}" y="24" width="{X1 - mid:.1f}" height="16"/>',
           f'<text class="slab" x="{X0}" y="54">cycle 0</text><text class="slab" x="{mid:.1f}" y="54" text-anchor="middle">{n}</text>'
           f'<text class="slab" x="{X1}" y="54" text-anchor="end">not checked</text>',
           f'<text class="flab" x="{X0}" y="88">k-induction, k = {k}</text>',
           f'<rect class="sbar" x="{X0}" y="96" width="{(X1 - X0) * 0.3:.1f}" height="16"/>',
           f'<rect class="sbar2" x="{X0 + (X1 - X0) * 0.3:.1f}" y="96" width="{(X1 - X0) * 0.7:.1f}" height="16"/>',
           f'<text class="slab" x="{X0}" y="126">base case: cycles 0 to {k}</text>'
           f'<text class="slab" x="{X1}" y="126" text-anchor="end">step: every later cycle</text>',
           "</svg>"]
    return (f'<figure class="fig sfig">{"".join(out)}<figcaption>Solid: shown to hold. Dashed outline: not checked. The step case is only provable when the block\'s '
            f'internal state is constrained enough, which is why some state machines here stay bounded.</figcaption></figure>')


def formal_tbl(F: dict) -> str:
    rows = "".join(f'<tr><td>{E(r["block"])}</td><td>{E(r["what"])}</td><td>{E(r["method"])}</td><td>{E(r["status"])}</td>'
                   f'<td class="num">{"" if r["seconds"] is None else fm(r["seconds"])}</td></tr>' for r in F["rows"])
    return ('<div class="tablewrap" tabindex="0"><table><thead><tr><th>Block</th><th>Property</th><th>Method</th><th>Result</th><th class="num">Seconds</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def unb_tables(U: dict) -> str:
    a = "".join(f'<tr><td>{E(r["block"])}</td><td>{E(r["method"])}</td><td>{E(r["status"])}</td><td class="num">{fm(r["seconds"])}</td></tr>' for r in U["attempts"])
    e = "".join(f'<tr><td>{E(r["case"])}</td><td>{E(r["expected"])}</td><td>{E(r["result"])}</td><td class="num">{fm(r["seconds"])}</td></tr>' for r in U["equivalence"])
    return ('<div class="tablewrap" tabindex="0"><table><thead><tr><th>Block</th><th>Method</th><th>Result</th><th class="num">Seconds</th></tr></thead>'
            f'<tbody>{a}</tbody></table></div>', '<div class="tablewrap" tabindex="0"><table><thead><tr><th>Pair compared</th><th>Meant to be</th><th>eqy says</th><th class="num">Seconds</th></tr></thead>'
            f'<tbody>{e}</tbody></table></div>')


def cex_fig(X: dict) -> str:
    n = X["cycles"]
    rows = [("aresetn", "reset released"), ("awvalid", "address valid"), ("wvalid", "write data valid"), ("bvalid", "write response valid")]
    W, LX, RH, T = 400, 120, 30, 6
    cw = (W - LX - 8) / n
    H = T + RH * (len(rows) + 1) + 18
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="cxt cxd" class="cex"><title id="cxt">Counterexample found by the solver</title>'
           f'<desc id="cxd">Signals of the AXI4-Lite checker over {n} clock cycles. The address is accepted, a write response is valid, no write data is ever valid, and the mutated checker flags the early response only in one cycle.</desc>']
    series = [(label, X["signals"][k]) for k, label in rows] + [("checker flags it", X["flags"])]
    for i, (label, vals) in enumerate(series):
        y = T + RH * i
        out.append(f'<text class="flab" x="4" y="{y + 18}">{E(label)}</text>')
        for c, v in enumerate(vals):
            x = LX + c * cw
            out.append(f'<rect class="{"cxh" if v else "cxl"}" x="{x + 1:.1f}" y="{y + (4 if v else 18)}" width="{cw - 2:.1f}" height="{14 if v else 2}"/>')
    out.append(f'<rect class="future cxfut" x="{LX + n * cw:.1f}" y="0" width="0" height="{H - 18}"/>'
               f'<text class="slab" x="{LX}" y="{H - 4}">step 0</text><text class="slab cxstep" x="{W - 8}" y="{H - 4}" text-anchor="end">step {n - 1}</text></svg>')
    return (f'<figure class="fig sfig cexfig" data-cycles="{n}" data-lx="{LX}" data-cw="{cw:.3f}" data-w="{W}">{"".join(out)}'
            f'<div class="ctl"><label for="cexr">Replay to step</label><input id="cexr" type="range" min="0" max="{n - 1}" value="{n - 1}" aria-label="Replay the counterexample to a step">'
            f'<span class="pos cexpos">{n - 1}</span></div></figure>')


def card(t: dict) -> str:
    det = "".join(f"<p>{E(x)}</p>" for x in t["detail"])
    ev = link_chips(t["links"])
    return (f'<article class="xcard vcard" id="{t["id"]}"><h3>{E(t["title"])}</h3>'
            f'<dl class="xd"><dt>What it is</dt><dd>{E(t["what"])}</dd>'
            f'<dt>Catches</dt><dd>{E(t["catches"])}</dd>'
            f'<dt>Cannot find</dt><dd>{E(t["cannot"])}</dd>'
            f'<dt>Where it runs</dt><dd>{E(t["how"])}</dd>'
            f'<dt>Evidence</dt><dd>{E(t["evidence"])}</dd></dl>'
            f'<details class="more"><summary>Engineering detail and records</summary>{det}<p class="evl">Records: {ev}</p></details></article>')


def body(S: dict) -> str:
    C = S["content"]
    T, V = C["text"], C["values"]
    out = ['<p class="eyebrow">Verification</p><h1>How the designs are verified</h1>',
           f'<p class="lede">{E(T["lede"])}</p><p>{E(T["best"])}</p><p>{E(T["nulls"])}</p>'
           f'<details class="more"><summary>How to read this page</summary><p>{E(T["how_to_read"])}</p></details>']
    out.append(f'<div class="facts"><div class="fact"><div class="n">{V["c_gate"]} of {V["c_mut"]}</div><p>faulty clock-crossing designs flagged by the gate; the tool&#39;s own report flagged {V["c_tool"]}.</p></div>'
               f'<div class="fact"><div class="n">{V["d_esc"]} of {V["d_runs"]}</div><p>development runs where the agent&#39;s own checks passed and the hidden tests failed.</p></div>'
               f'<div class="fact"><div class="n">{fm(V["m_first"])} %</div><p>first-run mutation score on the reference design; {V["m_surv"]} survivors were reset-state faults the tests had never looked at.</p></div></div>')
    out.append('<nav class="jump" aria-label="On this page"><a href="#map">Where it runs</a><a href="#catches">What each catches</a><a href="#techniques">Techniques</a>'
               '<a href="#formal">Formal</a><a href="#limits">Limits</a></nav>')
    out.append(f'<h2 id="map">Which technique runs where</h2><p>{E(T["map_intro"])}</p>')
    out.append(stage_map(C))
    out.append(f'<h2 id="catches">What each technique catches</h2><p>{E(T["catch_intro"])}</p>')
    out.append('<h3>Clock-domain crossings</h3>')
    out.append(matrix(C["cdc"], "Faulty design", E(T["cdc_note"]) and T["cdc_note"], "Flagged"))
    out.append('<h3>Bus protocol and data bugs, on the board</h3>')
    out.append(matrix(C["axi"], "Seeded bug", T["axi_note"], "Flagged"))
    out.append(f'<h3>A fault only the board shows</h3><p>{E(T["pin_intro"])}</p>')
    out.append(pin_fig(C["pin"]))
    out.append(f'<p>{E(T["pin_note"])}</p>')
    out.append(f'<h3>How close the reference design is to the floors</h3><p>{E(T["closure_intro"])}</p>')
    out.append(closure_fig(C["closure"]))
    out.append(f'<p>{E(T["closure_note"])}</p>')
    out.append('<h2 id="techniques">The techniques, one by one</h2><div class="xcards">' + "".join(card(t) for t in C["techniques"]) + "</div>")
    out.append(f'<h2 id="formal">Formal proofs: what bounded means</h2><p>{E(T["depth_intro"])}</p>')
    out.append(depth_fig(V))
    out.append(f'<p>{E(T["formal_note"])}</p>')
    ut, et = unb_tables(C["unb"])
    out.append(f'<h3>Proofs for every cycle</h3><p>{E(T["unb_intro"])}</p>{ut}')
    out.append(f'<h3>A real counterexample</h3><p>{E(T["cex_intro"])}</p>{cex_fig(C["unb"]["cex"])}<p>{E(T["cex_note"])}</p>')
    out.append(f'<h3>Equivalence checking</h3><p>{E(T["eq_intro"])}</p>{et}<p>{E(T["eq_note"])}</p>')
    out.append(f'<details class="more"><summary>Every formal job in the records, with its method</summary>{formal_tbl(C["formal"])}</details>')
    out.append(f'<h2 id="limits">Limits</h2><p>{E(T["limits"])}</p>')
    out.append(f'<p>How each check was found and corrected is on the <a href="story.html#loop">how-it-was-built page</a>; the documents are '
               f'<a href="{REPO}/blob/main/docs/verification.md">docs/verification.md</a> and <a href="{REPO}/blob/main/docs/traceability.md">docs/traceability.md</a>.</p>')
    return "".join(out)
