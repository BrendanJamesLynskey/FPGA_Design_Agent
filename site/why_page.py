"""HTML for the "Why FPGA Guild" page (brief 193), from site/data/why.json. Native <details>, no script needed for the drawers;
the expertise page's script (expand all, collapse all, a hash link opens its drawer) is reused, so why.html#verification opens that drawer."""
from __future__ import annotations

import html

e = html.escape

# (id, label, sub-label, who): who is "you" for the two boxes the person owns
STEPS = [("spec", "You specify", "ports, clocks, rules", "you"),
         ("agent", "Agent implements", "model, tests, RTL", "agent"),
         ("gates", "Gates decide", "Vivado, sims, formal", "agent"),
         ("board", "Board measures", "instruments attached", "agent"),
         ("judge", "You judge", "evidence vs. spec", "you")]


def _arrow(x1, y1, x2, y2):
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    hx, hy = x2 - 7 * math.cos(a), y2 - 7 * math.sin(a)
    nx, ny = -math.sin(a) * 4, math.cos(a) * 4
    return (f'<line class="ink" x1="{x1}" y1="{y1}" x2="{hx:.1f}" y2="{hy:.1f}"/>'
            f'<path class="fillink" d="M{x2} {y2} L{hx + nx:.1f} {hy + ny:.1f} L{hx - nx:.1f} {hy - ny:.1f} Z"/>')


def _box(x, y, w, h, label, sub, who):
    inv = who == "you"
    return (f'<rect class="{"boxyou" if inv else "boxink"}" x="{x}" y="{y}" width="{w}" height="{h}"/>'
            f'<text class="big{" inv" if inv else ""}" x="{x + 10}" y="{y + 24}">{e(label)}</text>'
            f'<text class="{"inv" if inv else ""}" x="{x + 10}" y="{y + 44}">{e(sub)}</text>')


def diagram_wide() -> str:
    w, h, gap, y = 176, 58, 30, 58
    xs = [5 + i * (w + gap) for i in range(len(STEPS))]
    out = []
    for i, (_, lab, sub, who) in enumerate(STEPS):
        out.append(_box(xs[i], y, w, h, lab, sub, who))
        if i:
            out.append(_arrow(xs[i - 1] + w + 4, y + h / 2, xs[i] - 3, y + h / 2))
    # a failed gate goes back to the agent (above the row); a gap or a wrong specification goes back to you (below the row)
    gx, ax = xs[2] + w / 2, xs[1] + w / 2
    out.append(f'<path class="ink" d="M{gx} {y} C{gx} {y - 30}, {ax} {y - 30}, {ax} {y - 4}" fill="none" stroke-dasharray="5 4"/>')
    out.append(_arrow(ax, y - 10, ax, y - 1))
    out.append(f'<text x="{(gx + ax) / 2}" y="{y - 36}" text-anchor="middle">a failed gate goes back to the agent</text>')
    jx, sx = xs[4] + w / 2, xs[0] + w / 2
    by = y + h
    out.append(f'<path class="ink" d="M{jx} {by} C{jx} {by + 40}, {sx} {by + 40}, {sx} {by + 4}" fill="none" stroke-dasharray="5 4"/>')
    out.append(_arrow(sx, by + 10, sx, by + 1))
    out.append(f'<text x="{(jx + sx) / 2}" y="{by + 50}" text-anchor="middle">a gap in the evidence, or a wrong specification, goes back to you</text>')
    return (f'<svg viewBox="0 0 1010 {y + h + 62}" role="img" aria-labelledby="whyw1 whyw2"><title id="whyw1">Who does what</title>'
            f'<desc id="whyw2">You specify; the agent implements; gates decide; the board measures; you judge the evidence. A failed gate goes back to the agent. '
            f'A gap in the evidence or a wrong specification goes back to you.</desc>{"".join(out)}</svg>')


def diagram_narrow() -> str:
    w, h, gap, x = 300, 58, 26, 10
    out = []
    for i, (_, lab, sub, who) in enumerate(STEPS):
        y = 6 + i * (h + gap)
        out.append(_box(x, y, w, h, lab, sub, who))
        if i:
            out.append(_arrow(x + w / 2, y - gap + 3, x + w / 2, y - 3))
    return (f'<svg viewBox="0 0 320 {6 + len(STEPS) * (h + gap)}" role="img" aria-labelledby="whyn1 whyn2"><title id="whyn1">Who does what</title>'
            f'<desc id="whyn2">You specify; the agent implements; gates decide; the board measures; you judge the evidence.</desc>{"".join(out)}</svg>')


def figure(caption: str) -> str:
    return (f'<figure class="whyfig"><div class="agfig"><div class="lay-w">{diagram_wide()}</div><div class="lay-n">{diagram_narrow()}</div></div>'
            f"<figcaption>{e(caption)}</figcaption></figure>")


def drawer(d: dict) -> str:
    head = f'<summary><span class="an">{e(d["title"])}</span><span class="as">{e(d["claim"])}</span></summary>'
    means = "".join(f"<p>{e(t)}</p>" for t in d["means"])
    src = " ".join(f'<a class="evsrc" href="{e(s["url"])}" title="{e(s["path"])}" aria-label="Record: {e(s["path"])}">record</a>' for s in d["example"]["sources"])
    body = (f'<div class="abody"><h4>What it means</h4>{means}'
            f'<h4>An example from this project</h4><p>{e(d["example"]["text"])} {src}</p>'
            f'<h4>What it does not do yet</h4><p>{e(d["not_yet"])}</p>'
            f'<p class="more-link"><a href="{e(d["link"]["href"])}">{e(d["link"]["label"])} &rarr;</a></p></div>')
    return f'<details class="area why" id="{e(d["id"])}">{head}{body}</details>'


def body(W: dict) -> str:
    ctl = ('<div class="areactl" id="areactl" hidden><button type="button" id="expand-all">Expand all</button>'
           '<button type="button" id="collapse-all">Collapse all</button></div>')
    hero = (f'<section class="hero whyhero"><p class="eyebrow">Why FPGA Guild: the one-page summary</p><h1>{e(W["intro"]["answer"])}</h1>'
            f'<p class="lede">{e(W["intro"]["note"])}</p></section>')
    return hero + figure(W["caption"]) + '<h2 id="drawers">What makes it different</h2>' + ctl + "".join(drawer(d) for d in W["drawers"])
