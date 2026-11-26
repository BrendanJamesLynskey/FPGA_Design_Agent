"""HTML for the "What's new" page (brief 237), from site/data/changes.json. Native <details>; the section drawers come from site/drawers.py."""
from __future__ import annotations

import html

REPO = "https://github.com/BrendanJamesLynskey/FPGA_Design_Agent"
e = html.escape


def _prs(prs):
    return ", ".join(f'<a class="evsrc" href="{REPO}/pull/{p["n"]}" title="{e(p["title"])}">#{p["n"]}</a>' for p in prs)


def _ev(evidence):
    return " ".join(f'<a class="evsrc" href="{e(x["url"])}" title="{e(x["path"])}">{e(x["path"].split("/")[-1] if x["path"].endswith(".md") or "." in x["path"].split("/")[-1] else x["path"])}</a>' for x in evidence)


def _first(text):
    s = text.split(". ")[0]
    return s if s.endswith(".") else s + "."


def item(it):
    pages = "".join(f'<li><a href="{e(p["href"])}">{e(p["label"])}</a></li>' for p in it["pages"])
    more = f'<p class="evl">Also on this site: <ul class="inl">{pages}</ul></p>' if pages else ""
    return (f'<details class="area" id="{e(it["id"])}"><summary><span class="an">{e(it["title"])}</span><span class="as">{e(_first(it["changed"]))}</span></summary>'
            f'<div class="abody"><h4>What changed</h4><p>{e(it["changed"])}</p><h4>What a record shows</h4><p>{e(it["result"])}</p>'
            f'<h4>What it does not show</h4><p>{e(it["limits"])}</p>'
            f'<p class="evl">Pull request: {_prs(it["prs"])}. Evidence: {_ev(it["evidence"])}</p>{more}</div></details>')


def body(C: dict) -> str:
    T = C["text"]
    hero = (f'<p class="eyebrow">What changed</p><h1>The agent since 23 November</h1><p class="lede">{e(T["intro"])}</p>'
            f'<p>{e(T["how_to_read"])}</p>')
    out = [hero]
    for g in C["groups"]:
        out.append(f'<h2 id="{e(g["id"])}">{e(g["title"])}</h2><p>{e(g["intro"])}</p>' + "".join(item(i) for i in g["items"]))
    S = C["smaller"]
    li = "".join(f'<li>{e(s["text"])} <span class="evl">Pull request: {_prs(s["prs"])}. Evidence: {_ev(s["evidence"])}</span></li>' for s in S["items"])
    out.append(f'<h2 id="smaller">Smaller changes</h2><p>{e(S["intro"])}</p><ul class="fixes">{li}</ul>')
    where = {}
    for g in C["groups"]:
        for i in g["items"]:
            where[i["id"]] = i["title"]
    rows = []
    for r in C["rows"]:
        if r["group"] == "smaller":
            sec = '<a href="#smaller">Smaller changes</a>'
        else:
            sec = f'<a href="#{e(r["item"])}">{e(where[r["item"]])}</a>'
        other = ", ".join(f'<a href="{e(p["href"])}">{e(p["label"])}</a>' for p in r["pages"]) or ""
        rows.append(f'<tr><td class="num"><a href="{REPO}/pull/{r["pr"]}">#{r["pr"]}</a></td><td>{sec}</td><td>{other}</td></tr>')
    out.append('<h2 id="index">Index: each pull request and where it is covered</h2><div class="tablewrap" tabindex="0"><table><thead><tr><th class="num">Pull request</th>'
               '<th>Covered on this page</th><th>Also covered on</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")
    return "".join(out)
