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


FAMILY_LABEL = {"7series": "7-series (Artix-7, Zynq-7000 PL)", "ultrascale_plus": "UltraScale+ (K26 PL)",
                "zynq7000_ps": "Zynq-7000 PS", "zynqmp_ps": "Zynq UltraScale+ PS", "common": "All families (tool guides)"}


KIND_LEAD = {"measured": "Measured.", "agent": "In agent runs.", "example": "Hand-built examples."}


def _src(srcs) -> str:
    """A small source link after an evidence sentence; the path is in the link's label and title, not the sentence."""
    return " ".join(f'<a class="evsrc" href="{e(s["url"])}" title="{e(s["path"])}" aria-label="Source: {e(s["path"])}">source</a>' for s in srcs)


def drawer(a: dict) -> str:
    """One area: a plain opening paragraph, what has been shown (by kind of evidence, each sentence with its source link),
    what is not yet shown, related cards; skills, checks and family differences in a nested Details drawer, closed."""
    c = a["counts"]
    head = (f'<summary><span class="an">{e(a["name"])}</span><span class="as">{e(a["summary"])}</span>'
            f'<span class="ac">{c["skills"]} skills, {c["checks"]} flow check{"" if c["checks"] == 1 else "s"}</span>'
            f'<span class="tag lvl">{_seg(a["level_n"])} {e(a["level_label"])}</span></summary>')
    shown = ""
    for kind in ("measured", "agent", "example"):
        items = [x for x in a["evidence"] if x["kind"] == kind]
        if items:
            shown += (f'<p><strong>{KIND_LEAD[kind]}</strong> ' +
                      " ".join(f'{e(x["text"])} {_src(x["sources"])}' for x in items) + "</p>")
    if not shown:
        shown = "<p><strong>Measured.</strong> Nothing yet for this area.</p>"
    gaps = " ".join(e(g) for g in a["gaps"])
    cap = f' {e(a["cap_reason"])}' if a["cap_reason"] else ""
    notyet = f"<p><strong>Not yet shown.</strong> {gaps}{cap}</p>"
    cards = (f'<p class="small">Related: ' + "; ".join(f'<a href="{e(k["href"])}">{e(k["label"])}</a>' for k in a["cards"]) + "</p>") if a["cards"] else ""
    know = "".join(
        f'<h4><code>{e(g["unit"])}/{e(g["section"])}</code></h4><ul class="sk">' +
        "".join(f'<li><code>{e(s["name"])}</code> {e(s["description"])}</li>' for s in g["items"]) + "</ul>"
        for g in a["skills"])
    chk = ("<ul>" + "".join(
        f'<li><a href="{e(k["url"])}"><code>{e(k["file"])}</code></a>' + (f' (<code>{e(k["gate"])}</code>)' if k["gate"] else "") +
        f' <span class="tag {"built" if k["enforced"] else "plan"}">{"gate" if k["enforced"] else "tool"}</span> {e(k["what"])}</li>'
        for k in a["checks"]) + "</ul>") if a["checks"] else "<p>No flow check is specific to this area.</p>"
    fam = a.get("family") or {"rows": [], "docs": {}}
    fl = ("<ul>" + "".join(f'<li><strong>{e(r["topic"])}</strong>: {e(r["summary"])} <span class="tag">{"tool-checked" if r["confirmed"] == "tool" else "from the guides"}</span></li>'
                           for r in fam["rows"]) + "</ul>"
          f'<p class="small"><a href="#{e(a["id"])}-docs">Documents to read for this area, by family</a></p>'
          f'<details class="docs" id="{e(a["id"])}-docs"><summary>Documents by family</summary>' +
          "".join(f'<h4>{e(FAMILY_LABEL.get(f, f))}</h4><ul>' +
                  "".join(f'<li><strong>{e(d["doc"])}</strong>: {e(d["use"])}</li>' for d in lst) + "</ul>"
                  for f, lst in fam["docs"].items()) + "</details>") if fam["rows"] else "<p>No family difference recorded yet.</p>"
    details = (f'<details class="more"><summary>Details: skills, flow checks and differences between device families</summary><dl class="kv">'
               f'<dt>Knows</dt><dd><p class="small muted">Skills of the knowledge bank at its pin, by unit and section, with the one-line description from each skill.</p>{know}</dd>'
               f"<dt>Flow checks</dt><dd>{chk}</dd><dt>Differs by family</dt><dd>{fl}</dd></dl></details>")
    body = f'<div class="abody"><p>{e(a["about"])}</p>{shown}{notyet}{cards}{details}</div>'
    return f'<details class="area" id="{e(a["id"])}">{head}{body}</details>'


def drawers(x: dict) -> str:
    ctl = ('<div class="areactl" id="areactl" hidden><button type="button" id="expand-all">Expand all</button>'
           '<button type="button" id="collapse-all">Collapse all</button></div>')
    return ctl + "".join(drawer(a) for a in x["areas"])
