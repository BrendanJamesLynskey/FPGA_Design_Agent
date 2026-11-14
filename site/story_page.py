"""site/story.html (brief 76): the body of the 'How it was built' page, drawn from site/data/story.json."""
from __future__ import annotations

import html
from datetime import date

E = html.escape
REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
OUTCOME = {"escape": "escape: own checks passed, hidden tests failed",
           "internal_stop_hidden_pass": "stopped by the agent's own gates; hidden tests pass",
           "caught_and_repaired": "a gate failed, was repaired, passed", "pass": "passed", "fail": "failed"}


def nd(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{d.day} {d.strftime('%b')}"


def fm(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def pr_chips(prs) -> str:
    return " ".join(f'<a class="evsrc" href="{REPO}/pull/{p["n"]}" title="{E(p["title"])}">#{p["n"]}</a>' for p in prs)


def link_chips(links) -> str:
    return " ".join(f'<a class="evsrc" href="{E(l["url"])}">{E(l["path"].split("/")[-1] or l["path"])}</a>' for l in links)


def pr_bars(by_day) -> str:
    """Merged pull requests per day: the shape of the work, from the dated snapshot."""
    days = [date.fromisoformat(d) for d, _ in by_day]
    d0, d1 = days[0], days[-1]
    n = (d1 - d0).days + 1
    cnt = {d: c for d, c in by_day}
    mx = max(cnt.values())
    W, H, L, B = 400, 150, 8, 28
    bw = (W - 2 * L) / n
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="prt prd"><title id="prt">Merged pull requests per day</title>'
           f'<desc id="prd">A bar for each day from {nd(d0.isoformat())} to {nd(d1.isoformat())}; the tallest holds {mx} pull requests.</desc>']
    for i in range(n):
        d = date.fromordinal(d0.toordinal() + i)
        c = cnt.get(d.isoformat(), 0)
        x = L + i * bw
        h = (H - B - 18) * c / mx
        if c:
            out.append(f'<rect class="sbar" x="{x + 2:.1f}" y="{H - B - h:.1f}" width="{bw - 4:.1f}" height="{h:.1f}"/>'
                       f'<text class="sval" x="{x + bw / 2:.1f}" y="{H - B - h - 4:.1f}" text-anchor="middle">{c}</text>')
        out.append(f'<text class="slab" x="{x + bw / 2:.1f}" y="{H - B + 13}" text-anchor="middle">{d.day}</text>')
        if i == 0 or d.day == 1:
            out.append(f'<text class="slab" x="{x + bw / 2:.1f}" y="{H - B + 25}" text-anchor="middle">{d.strftime("%b")}</text>')
    out.append(f'<line class="rule" x1="{L}" y1="{H - B}" x2="{W - L}" y2="{H - B}"/></svg>')
    return '<figure class="fig sfig">' + "".join(out) + '<figcaption>Merged pull requests per day. The count over the dates the project ran is the pace of the work; the next section says what each stretch changed.</figcaption></figure>'


def forest(P: dict, fid: str) -> str:
    rows = P["rows"]
    lo = min(min(r["lo"] for r in rows), 0)
    hi = max(max(r["hi"] for r in rows), 0)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    W, X0, X1, RH, T = 400, 14, 386, 46, 4
    H = T + RH * len(rows) + 20
    sx = lambda v: X0 + (v - lo) / (hi - lo) * (X1 - X0)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="{fid}t {fid}d"><title id="{fid}t">{E(P["title"])}</title>'
           f'<desc id="{fid}d">{"; ".join(E(r["label"]) + " " + fm(r["est"]) + ", interval " + fm(r["lo"]) + " to " + fm(r["hi"]) for r in rows)}.</desc>']
    z = sx(0)
    out.append(f'<text class="slab" x="{z:.1f}" y="{H - 5}" text-anchor="middle">0</text>')
    for i, r in enumerate(rows):
        y = T + RH * i
        null = r["lo"] <= 0 <= r["hi"]
        cls = "fnull" if null else "fsig"
        out.append(f'<line class="rule" x1="{z:.1f}" y1="{y + 20}" x2="{z:.1f}" y2="{y + 40}"/>'
                   f'<text class="flab" x="{X0}" y="{y + 14}">{E(r["label"])}</text>'
                   f'<text class="fval" x="{X1}" y="{y + 14}" text-anchor="end">{fm(r["est"])} [{fm(r["lo"])}, {fm(r["hi"])}]</text>'
                   f'<line class="{cls}" x1="{sx(r["lo"]):.1f}" y1="{y + 30}" x2="{sx(r["hi"]):.1f}" y2="{y + 30}"/>'
                   f'<line class="{cls}" x1="{sx(r["lo"]):.1f}" y1="{y + 24}" x2="{sx(r["lo"]):.1f}" y2="{y + 36}"/>'
                   f'<line class="{cls}" x1="{sx(r["hi"]):.1f}" y1="{y + 24}" x2="{sx(r["hi"]):.1f}" y2="{y + 36}"/>'
                   f'<rect class="m{cls}" x="{sx(r["est"]) - 4:.1f}" y="{y + 26}" width="8" height="8"/>')
    out.append("</svg>")
    note = f' {E(P["note"])}' if P.get("note") else ""
    return (f'<figure class="fig sfig">{"".join(out)}<figcaption>{E(P["unit"][:1].upper() + P["unit"][1:])}. Filled square, dark line: the interval excludes zero. '
            f'Hollow square, grey line: it includes zero, so no difference is shown.{note}</figcaption></figure>')


def runs_fig(P: dict) -> str:
    rows = P["rows"]
    body = "".join(
        f'<tr><td class="num">{r["run"]}</td><td class="num">{r["got"]} of {r["of"]}</td><td>{E(OUTCOME.get(r["outcome"], r["outcome"]))}</td>'
        f'<td>{(E(r["fix"]) + " " + f"<a class=evsrc href={REPO}/pull/{r["fix_pr"]}>#{r["fix_pr"]}</a>") if r["fix_pr"] else "none: the last run"}</td></tr>' for r in rows)
    W, H = 400, 110
    bw = (W - 40) / len(rows)
    bars = []
    for i, r in enumerate(rows):
        h = 64 * r["got"] / r["of"]
        x = 20 + i * bw
        bars.append(f'<rect class="sbar" x="{x + 8:.1f}" y="{80 - h:.1f}" width="{bw - 16:.1f}" height="{max(h, 1):.1f}"/>'
                    f'<rect class="sbox" x="{x + 8:.1f}" y="16" width="{bw - 16:.1f}" height="64"/>'
                    f'<text class="sval" x="{x + bw / 2:.1f}" y="10" text-anchor="middle">{r["got"]} of {r["of"]}</text>'
                    f'<text class="slab" x="{x + bw / 2:.1f}" y="96" text-anchor="middle">run {r["run"]}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="c14t"><title id="c14t">{E(P["title"])}: hidden tests passed in each run</title>'
           + "".join(bars) + "</svg>")
    return (f'<figure class="fig sfig">{svg}<figcaption>{E(P["title"])}. Hidden tests passed in each run of one task; the table gives the fix that followed each run.</figcaption></figure>'
            f'<div class="tablewrap" tabindex="0"><table><thead><tr><th>Run</th><th class="num">Hidden tests</th><th>How it ended</th><th>Fix that followed</th></tr></thead><tbody>{body}</tbody></table></div>')


def ledger(C: dict) -> str:
    F = C["findings"]
    ds = sorted({f["date"] for f in F})
    d0, d1 = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    n = (d1 - d0).days + 1
    causes = C["causes"]
    W, LX, RH, T = 400, 172, 24, 4
    cw = (W - LX - 28) / n
    H = T + RH * len(causes) + 24
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="ldt ldd"><title id="ldt">Findings by cause class over time</title>'
           f'<desc id="ldd">One square per finding with a recorded fix, by the day of the fix and the cause class; the count per class is at the right.</desc>']
    for i, c in enumerate(causes):
        y = T + RH * i
        out.append(f'<text class="flab" x="4" y="{y + 16}">{E(c)}</text><line class="rule" x1="{LX}" y1="{y + RH - 1}" x2="{W - 24}" y2="{y + RH - 1}"/>'
                   f'<text class="fval" x="{W - 4}" y="{y + 16}" text-anchor="end">{C["cause_n"][c]}</text>')
        stack = {}
        for f in F:
            if f["cause"] != c:
                continue
            k = (date.fromisoformat(f["date"]) - d0).days
            s = stack.get(k, 0)
            stack[k] = s + 1
            x = LX + k * cw + 1 + s * 3
            out.append(f'<rect class="{"fsigm" if f.get("kind") == "instrument" else "fnullm"}" x="{x:.1f}" y="{y + 5 + s * 2}" width="{max(cw - 3, 6):.1f}" height="10"><title>{E(nd(f["date"]))}, #{f["pr"]}: {E(f["finding"])}</title></rect>')
    for k in range(n):
        d = date.fromordinal(d0.toordinal() + k)
        out.append(f'<text class="slab" x="{LX + k * cw + cw / 2:.1f}" y="{H - 8}" text-anchor="middle">{d.day}</text>')
    out.append("</svg>")
    rows = "".join(f'<tr><td>{nd(f["date"])}</td><td>{E(f["cause"])}</td><td>{E(f["finding"])}</td><td>{E(f["fix"])}</td>'
                   f'<td><a class="evsrc" href="{REPO}/pull/{f["pr"]}">#{f["pr"]}</a></td></tr>' for f in F)
    return (f'<figure class="fig sfig">{"".join(out)}<figcaption>Each square is one finding with a recorded fix, placed by cause class and by the day of its fix in November. Outlined squares are faults in the measuring instrument itself. The table below lists every finding. '
            f'The count of findings per class is at the right.</figcaption></figure>'
            f'<details class="more"><summary>All {C["values"]["findings_n"]} findings, with the cause class and the fix</summary>'
            f'<div class="tablewrap" tabindex="0"><table><thead><tr><th>Date</th><th>Cause</th><th>Finding</th><th>Fix</th><th>PR</th></tr></thead><tbody>{rows}</tbody></table></div></details>')


def card(e: dict, C: dict) -> str:
    V = C["verdicts"]
    plot = ""
    if e["plot"] == "c14_runs":
        plot = runs_fig(C["plots"]["c14_runs"])
    elif e["plot"]:
        plot = forest(C["plots"][e["plot"]], "f_" + e["plot"])
    det = "".join(f"<p>{E(x)}</p>" for x in e["detail"])
    ev = " ".join(x for x in (pr_chips(e["prs"]), link_chips(e["links"])) if x)
    return (f'<article class="xcard v-{e["verdict"]}" id="{e["id"]}"><div class="xhead"><span class="tag vt">{E(V[e["verdict"]])}</span>'
            f'<span class="muted small">{nd(e["date"])}</span></div><h3>{E(e["title"])}</h3>'
            f'<dl class="xd"><dt>Hypothesis</dt><dd>{E(e["question"])}</dd>'
            f'<dt>Result</dt><dd>{E(e["result"])}</dd>'
            f'<dt>Uncertainty</dt><dd>{E(e["interval"])}</dd>'
            f'<dt>Decision</dt><dd>{E(e["decision"])}</dd>'
            f'<dt>What it taught</dt><dd>{E(e["lesson"])}</dd></dl>{plot}'
            f'<details class="more"><summary>Setup and evidence</summary><p><b>Setup.</b> {E(e["setup"])}</p>{det}<p class="evl">Evidence: {ev}</p></details></article>')


def body(S: dict) -> str:
    C = S["content"]
    T, V = C["text"], C["values"]
    out = ['<p class="eyebrow">How it was built</p><h1>How the agent was built, evaluated and improved</h1>',
           f'<p class="lede">{E(T["lede"])}</p><p>{E(T["best"])}</p><p>{E(T["scope"])}</p>'
           f'<details class="more"><summary>Terms used on this page</summary><p>{E(T["glossary"])}</p></details>']
    vs = C["verdicts"]
    facts = (f'<div class="facts"><div class="fact"><div class="n">{V["c_gate"]} of {V["c_mut"]}</div><p>faulty designs flagged by the CDC gate; the tool&#39;s own report flagged {V["c_tool"]}.</p></div>'
             f'<div class="fact"><div class="n">{V["exp_n"]}</div><p>experiments written up below: ' + ", ".join(f'{V["v_" + k]} {vs[k].lower()}' for k in vs if V["v_" + k]) + ".</p></div>"
             f'<div class="fact"><div class="n">{V["findings_n"]}</div><p>faults with a recorded fix, in {V["causes_n"]} cause classes, from the improvement loop.</p></div></div>')
    out.append(facts)
    out.append('<nav class="jump" aria-label="On this page"><a href="#lessons">Lessons</a><a href="#experiments">Experiments</a><a href="#method">Method</a>'
               '<a href="#loop">Improvement loop</a><a href="#timeline">Timeline</a></nav>')
    out.append('<h2 id="lessons">What the measurements say about building agents</h2><ul class="lessons">' + "".join(
        f'<li><b>{E(l["claim"])}</b> {E(l["evidence"])} <span class="evl">{link_chips(l["links"])}</span></li>' for l in C["lessons"]) + "</ul>"
        f'<p>The full list, with what each claim does not show, is in <a href="{REPO}/blob/main/docs/agent_lessons.md">docs/agent_lessons.md</a>.</p>')
    out.append('<h2 id="experiments">Experiments, nulls included</h2>')
    out.append('<div class="vstrip" aria-label="Experiments by outcome">' + "".join(
        f'<a class="tag vt v-{k}" href="#{e["id"]}">{E(vs[k])}: {E(e["title"])}</a>' for e in sorted(C["experiments"], key=lambda e: (e["date"], e["order"])) for k in [e["verdict"]]) + "</div>")
    out.append('<div class="xcards">' + "".join(card(e, C) for e in sorted(C["experiments"], key=lambda e: (e["date"], e["order"]))) + "</div>")
    out.append(f'<p class="small muted">{E(T["fine_tune"])}</p>')
    out.append('<h2 id="method">The method, in plain words</h2><div class="mgrid">' + "".join(
        f'<div class="mcard"><h3>{E(m["title"])}</h3><p>{E(m["text"])}</p></div>' for m in C["method"]) + "</div>")
    out.append('<h2 id="loop">The improvement loop</h2><p>Every fault found in a run or a review becomes a recorded finding: the cause class, the fix, and the pull request. '
               'Reading single runs generates hypotheses; the experiments above decide. A fault in the measuring instrument is fixed on one case, with no statistics.</p>')
    out.append(ledger(C))
    out.append('<h2 id="timeline">Timeline of the design</h2><p>The order the agent was built in. Each step says what changed, why, and what the evidence showed.</p>')
    out.append(pr_bars(C["by_day"]))
    out.append('<ol class="tl">')
    for t in C["timeline"]:
        x = f' <a href="#{t["experiment"]}">See the experiment card.</a>' if t["experiment"] else ""
        ev = " ".join(y for y in (pr_chips(t["prs"]), link_chips(t["links"])) if y)
        out.append(f'<li id="{t["id"]}"><div class="tld">{nd(t["date"])}</div><div><h3>{E(t["title"])}</h3>'
                   f'<p><b>Changed.</b> {E(t["changed"])}</p><p><b>Why.</b> {E(t["why"])}</p><p><b>What the evidence showed.</b> {E(t["showed"])}{x}</p>'
                   f'<p class="evl">Evidence: {ev}</p></div></li>')
    out.append("</ol>")
    out.append(f'<h2 id="limits">Limits</h2><p>{E(T["limits"])}</p>')
    return "".join(out)
