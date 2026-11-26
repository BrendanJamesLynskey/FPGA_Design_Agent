"""Drawers for the long pages (brief 237): each top-level section (an <h2> and what follows it) becomes one <details> drawer.

Nothing is removed or rewritten: the section's own HTML moves inside the drawer, its <h2> moves into the <summary> (so the
page outline and the heading ids stay), and a one-sentence teaser, copied from the section's first paragraph, shows under the
title while the drawer is closed. The <details> takes the heading's id, so a link such as page.html#experiments still lands on
the section, and site/src/app.js opens the drawer (and any drawer around a deeper id) when the URL hash points into it.
Works without script (native <details>); with script, "Expand all" and "Collapse all" appear.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

BLOCK = {"div", "section", "article", "details", "figure", "table", "nav", "ul", "ol", "li", "p", "tbody", "thead", "tr", "td", "th", "svg", "dl", "pre"}


class _Depth(HTMLParser):
    """Records the nesting depth of every <h2>; a drawer can only be made where that is 0."""

    def __init__(self):
        super().__init__()
        self.depth, self.h2 = 0, []

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.h2.append(self.depth)
        if tag in BLOCK:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self.depth -= 1

    def handle_startendtag(self, tag, attrs):
        if tag == "h2":
            self.h2.append(self.depth)


def slug(text: str, used: set) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", html.unescape(re.sub(r"<[^>]+>", "", text)).lower()).strip("-")[:48] or "section"
    base, n = s, 2
    while s in used:
        s, n = f"{base}-{n}", n + 1
    used.add(s)
    return s


def teaser(rest: str, limit: int = 230, want: int = 90) -> str:
    """One or two sentences from the section's own paragraphs (tag lines and tables are skipped), enough to say what the section shows."""
    sents = []
    for m in re.finditer(r"<p(?![^>]*class=\"(?:tags|next|evl|eyebrow)\")[^>]*>(.*?)</p>", rest, re.S):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
        if len(t) < 25 or "{" in t or " \u00b7 " in t:
            continue
        sents += [x for x in re.findall(r".+?[.!?](?=\s|$)", t)] or [t]
        if sum(len(x) for x in sents) >= want:
            break
    if sum(len(x) for x in sents) < want:        # no paragraph: a caption, a list item, a definition or a table row says what the section shows
        for m in re.finditer(r"<(?:figcaption|li|dd)[^>]*>(.*?)</(?:figcaption|li|dd)>|<tr>(.*?)</tr>", rest, re.S):
            if m.group(1) is None and "<td" not in (m.group(2) or ""):
                continue
            raw = m.group(1) or re.sub(r"</t[hd]>\s*<t[hd][^>]*>", ": ", m.group(2) or "")
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw))).strip()
            if len(t) >= 25 and "{" not in t:
                sents += re.findall(r".+?[.!?](?=\s|$)", t) or [t]
                break
    out = ""
    for x in sents:
        if out and len(out) >= want:
            break
        if len(out) + len(x) + 1 > limit and out:
            break
        out = (out + " " + x.strip()).strip()
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:") + " ..."
    return out


def sectionize(body: str, open_ids=(), only=None, teasers=True, toc=True, controls=True, summary_of=None, no_teaser=()) -> str:
    """`open_ids`: drawers open on load. `only`: make drawers of just these headings (ids or slugs), leaving the rest as they are.
    `summary_of(rest) -> str`: an optional replacement for the teaser (the traceability page shows each design's verdict)."""
    p = _Depth()
    p.feed(body)
    if any(d != 0 for d in p.h2):
        raise ValueError("an <h2> is nested inside another element, so the page cannot be split into drawers")
    parts = re.split(r"(?=<h2[ >])", body)
    intro, secs = parts[0], parts[1:]
    if not secs:
        return body
    used = set(re.findall(r'\bid="([^"]+)"', body))
    out, items = [intro], []
    for sec in secs:
        m = re.match(r"<h2([^>]*)>(.*?)</h2>(.*)", sec, re.S)
        attrs, title, rest = m.group(1), m.group(2), m.group(3)
        idm = re.search(r'id="([^"]+)"', attrs)
        sid = idm.group(1) if idm else slug(title, used)
        if only is not None and sid not in only:
            out.append(sec)
            continue
        tt = (summary_of(rest) if summary_of else teaser(rest)) if teasers and sid not in no_teaser else ""
        op = " open" if sid in open_ids else ""
        plain = html.unescape(re.sub(r"<[^>]+>", "", title))
        items.append((sid, plain))
        out.append(f'<details class="area sec" id="{sid}"{op}><summary><h2 class="sech">{title}</h2>'
                   + (f'<span class="as">{html.escape(tt)}</span>' if tt else "") + f'</summary><div class="abody">{rest}</div></details>')
    ctl = ""
    if controls:
        ctl = ('<div class="areactl" id="areactl" hidden><button type="button" id="expand-all">Expand all</button>'
               '<button type="button" id="collapse-all">Collapse all</button></div>')
    toc_html = ""
    if toc and len(items) > 5:
        toc_html = ('<nav class="toc" aria-label="Sections of this page"><span>On this page:</span>'
                    + "".join(f'<a href="#{i}">{html.escape(t)}</a>' for i, t in items) + "</nav>")
    out.insert(1, toc_html + ctl)
    return "".join(out)


def articles(body: str, open_ids=()) -> str:
    """For a page whose sections are <article class="card" id=...><h2>title</h2>...</article> (the "Beyond the flow" page): each card becomes a drawer."""
    out = []
    pos = 0
    for m in re.finditer(r'<article class="card" id="([^"]+)">\s*<h2>(.*?)</h2>(.*?)</article>', body, re.S):
        sid, title, rest = m.group(1), m.group(2), m.group(3)
        op = " open" if sid in open_ids else ""
        tt = teaser(rest)
        out.append(body[pos:m.start()])
        out.append(f'<details class="area sec" id="{sid}"{op}><summary><h2 class="sech">{title}</h2>'
                   + (f'<span class="as">{html.escape(tt)}</span>' if tt else "") + f'</summary><div class="abody">{rest}</div></details>')
        pos = m.end()
    out.append(body[pos:])
    ctl = ('<div class="areactl" id="areactl" hidden><button type="button" id="expand-all">Expand all</button>'
           '<button type="button" id="collapse-all">Collapse all</button></div>')
    first = out[0]
    return first + ctl + "".join(out[1:]) if len(out) > 1 else body
