"""site/verified.html (brief 144): the body of the 'Verified by construction' page, drawn from site/data/verified.json."""
from __future__ import annotations

import html

from story_page import REPO

E = html.escape
STATE = {"met": "met", "unmet": "not met", "not_measured": "not yet measured (counts as not met)"}
KIND = {"designs": "design", "arith": "arithmetic function", "ip_lib": "IP-library entry"}


def link(path: str, text: str) -> str:
    return f'<a class="evsrc" href="{REPO}/blob/main/{E(path)}">{E(text)}</a>'


def panel(r: dict | None) -> str:
    """The verification panel of one design on the Traceability page: its label, the criteria, and a link to the record."""
    if not r:
        return ""
    rows = "".join(f'<li><b>{E(k["title"])}</b>: {E(STATE[k["state"]])}. <span class="muted small">{E(k["detail"])}</span></li>' for k in r["criteria"])
    return (f'<div class="panel" id="{E(r["name"])}-verified"><p class="eyebrow">Verification record</p><p><b>{E(r["label"][0].upper() + r["label"][1:])}.</b> '
            f'{link(r["path"] + "/VERIFIED.md", "VERIFIED.md")} lists every requirement, its evidence, who agreed it, the limits and the hash of every file it covers.</p>'
            f'<details class="more"><summary>What was checked for the label</summary><ul>{rows}</ul></details></div>')


def body(S: dict) -> str:
    C = S["content"]
    recs = C["records"]
    withplan = [r for r in recs if r["label_kind"] != "not_assessed"]
    without = [r for r in recs if r["label_kind"] == "not_assessed"]
    out = ['<p class="eyebrow">The defining property</p><h1>Verified by construction</h1>',
           '<p class="lede">Every design, arithmetic function and IP-library entry the agent produces ships a verification record: a generated, hash-pinned statement of what '
           'is verified, who agreed the requirements, which evidence covers each one, how fresh it is and where it stops. The label on top is computed, never typed, '
           'and it is earned only when every criterion below is met. Otherwise it says <i>verified except</i> and names what is missing.</p>',
           '<h2>The label</h2><div class="tablewrap" tabindex="0"><table class="mx"><thead><tr><th scope="col">Label</th><th scope="col">When</th></tr></thead><tbody>'
           '<tr><th scope="row">verified</th><td>every criterion is met</td></tr>'
           '<tr><th scope="row">verified except: &hellip;</th><td>at least one requirement is verified, none fails, and the listed criteria are not met</td></tr>'
           '<tr><th scope="row">not verified: &hellip;</th><td>a requirement fails, or no requirement has passing evidence</td></tr>'
           '<tr><th scope="row">not assessed</th><td>no requirements are recorded for it yet, so nothing is traced to a requirement; its own declared status is quoted apart from the label</td></tr>'
           '</tbody></table></div>',
           '<h2>The criteria</h2><ol>' + "".join(f"<li>{E(c['title'])}</li>" for c in C["criteria"]) + '</ol>',
           '<p>A criterion whose evidence has not been measured yet is shown as <i>not yet measured</i> and counts as not met: a label never claims what was not measured. '
           'The method-mix, mutation, formal-rigour and fresh-run criteria are being added by the verification improvements the owner approved on 2026-11-21, '
           'so the lists below get shorter as they land.</p>',
           '<h2>What &ldquo;verified&rdquo; never means</h2><ul>' + "".join(f"<li>{E(x)}</li>" for x in C["limits"]) + '</ul>',
           '<h2>Where each product stands</h2>']
    b = C["by_label"]
    out.append(f'<div class="facts"><div class="fact"><div class="n">{b["verified"]}</div><p>verified</p></div>'
               f'<div class="fact"><div class="n">{b["verified_except"]}</div><p>verified except a stated list</p></div>'
               f'<div class="fact"><div class="n">{b["not_verified"]}</div><p>not verified</p></div>'
               f'<div class="fact"><div class="n">{b["not_assessed"]}</div><p>not assessed yet (no requirements recorded)</p></div></div>')
    rows = "".join(f'<tr><th scope="row">{link(r["path"] + "/VERIFIED.md", r["path"])}</th><td>{E(KIND[r["kind"]])}</td><td>{E(r["label"])}</td>'
                   f'<td>{r["counts"].get("requirements", 0)}</td><td>{r["counts"].get("verified", 0)}</td>'
                   f'<td>{r["counts"].get("agreed_human", 0)} human, {r["counts"].get("agreed_delegated", 0)} delegated</td></tr>' for r in withplan)
    out.append('<div class="tablewrap" tabindex="0"><table class="mx"><thead><tr><th scope="col">Product</th><th scope="col">Kind</th><th scope="col">Label</th>'
               '<th scope="col">Requirements</th><th scope="col">With passing evidence</th><th scope="col">Agreed</th></tr></thead>'
               f'<tbody>{rows}</tbody></table></div>')
    if without:
        items = "".join(f'<li>{link(r["path"] + "/VERIFIED.md", r["path"])} ({E(KIND[r["kind"]])})</li>' for r in without)
        out.append(f'<details class="more"><summary>{len(without)} products with no requirements recorded yet</summary><ul>{items}</ul></details>')
    out.append(f'<p>Definition: <a href="{REPO}/blob/main/docs/verified.md">docs/verified.md</a>. Generator: {link("flow/verified.py", "flow/verified.py")}, '
               'which reads the traceability collector; the specification-to-evidence matrices are on the <a href="traceability.html">Traceability</a> page.</p>')
    return "".join(out)
