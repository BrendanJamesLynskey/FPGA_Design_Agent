"""HTML for the areas-of-expertise page (brief 23), from site/data/expertise.json. Native <details>, no script needed."""
from __future__ import annotations

import html

e = html.escape


def _seg(n: int) -> str:
    return '<span class="seg" aria-hidden="true">' + "".join(f'<i class="{"on" if i < n else ""}"></i>' for i in range(4)) + "</span>"


def levels(x: dict) -> str:
    rows = "".join(f'<tr><td><span class="tag lvl">{_seg(i + 1)} {e(l["label"])}</span></td><td>{e(l["means"])}</td><td class="num">{l["areas"]}</td></tr>'
                   for i, l in enumerate(x["levels"]))
    return ('<div class="tablewrap" tabindex="0"><table><thead><tr><th>Evidence level</th><th>What it means</th><th class="num">Areas</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def ladder(x: dict) -> str:
    li = "".join(f'<li><a href="#{a["id"]}">{e(a["name"])}</a>{_seg(a["level_n"])}<span class="lv">{e(a["level_label"])}</span></li>' for a in x["areas"])
    return f'<ol class="ladder" aria-label="Evidence level of each area">{li}</ol>'


def _links(srcs) -> str:
    return "; ".join(f'<a href="{e(s["url"])}"><code>{e(s["path"])}</code></a>' for s in srcs)


def drawer(a: dict) -> str:
    c = a["counts"]
    head = (f'<summary><span class="an">{e(a["name"])}</span><span class="as">{e(a["summary"])}</span>'
            f'<span class="ac">{c["skills"]} skills, {c["checks"]} flow checks</span>'
            f'<span class="tag lvl">{_seg(a["level_n"])} {e(a["level_label"])}</span></summary>')
    know = "".join(
        f'<h4><code>{e(g["unit"])}/{e(g["section"])}</code></h4><ul class="sk">' +
        "".join(f'<li><code>{e(s["name"])}</code> {e(s["description"])}</li>' for s in g["items"]) + "</ul>"
        for g in a["skills"])
    chk = ("<ul>" + "".join(
        f'<li><a href="{e(k["url"])}"><code>{e(k["file"])}</code></a>' + (f' (<code>{e(k["gate"])}</code>)' if k["gate"] else "") +
        f' <span class="tag {"built" if k["enforced"] else "plan"}">{"gate" if k["enforced"] else "tool"}</span> {e(k["what"])}</li>'
        for k in a["checks"]) + "</ul>") if a["checks"] else "<p>No flow check is specific to this area.</p>"
    ev = ("<ul>" + "".join(f'<li><span class="tag">{ {"measured": "measured", "agent": "agent runs", "example": "example"}[x["kind"]] }</span> {e(x["text"])}'
                           f' <span class="small muted">Source: {_links(x["sources"])}</span></li>' for x in a["evidence"]) + "</ul>") \
        if a["evidence"] else "<p>No committed result yet.</p>"
    cards = ("<ul>" + "".join(f'<li><a href="{e(k["href"])}">{e(k["label"])}</a></li>' for k in a["cards"]) + "</ul>") if a["cards"] else "<p>None yet.</p>"
    gaps = "<ul>" + "".join(f"<li>{e(g)}</li>" for g in a["gaps"]) + "</ul>"
    cap = f'<p class="note small">Level held at this point because: {e(a["cap_reason"])}</p>' if a["cap_reason"] else ""
    body = (f'<div class="abody">{cap}<dl class="kv">'
            f'<dt>Knows</dt><dd><p class="small muted">Skills of the knowledge bank at its pin, by unit and section, with the one-line description from each skill.</p>{know}</dd>'
            f"<dt>Flow checks</dt><dd>{chk}</dd><dt>Evidence</dt><dd>{ev}</dd><dt>See also</dt><dd>{cards}</dd><dt>Known gaps</dt><dd>{gaps}</dd></dl></div>")
    return f'<details class="area" id="{e(a["id"])}">{head}{body}</details>'


def drawers(x: dict) -> str:
    ctl = ('<div class="areactl" id="areactl" hidden><button type="button" id="expand-all">Expand all</button>'
           '<button type="button" id="collapse-all">Collapse all</button></div>')
    return ctl + "".join(drawer(a) for a in x["areas"])
