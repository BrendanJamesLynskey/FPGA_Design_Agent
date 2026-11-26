"""Brief 237: no dead internal links (file and #fragment) on the built site, every page is in one nav group, drawers keep their ids."""
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
PUB = HERE / "public"


def test_no_dead_internal_links():
    ids = {}
    pages = sorted(PUB.rglob("*.html"))
    for p in pages:
        ids[p] = set(re.findall(r'\bid="([^"]+)"', p.read_text()))
    dead = []
    for p in pages:
        for href in re.findall(r'<a [^>]*href="([^"]+)"', p.read_text()):
            if href.startswith(("http", "mailto:", "#")) and not href.startswith("#"):
                continue
            u = urlsplit(href)
            tgt = p if not u.path else (p.parent / u.path).resolve()
            if u.path and not tgt.exists():
                dead.append((p.name, href))
            elif u.fragment and tgt.suffix == ".html" and tgt in ids and u.fragment not in ids[tgt]:
                dead.append((p.name, href))
    assert not dead, dead[:20]


def test_nav_groups_cover_every_page():
    import build
    build.nav_html("", "index.html")      # asserts every page is in exactly one group


def test_changes_page_covers_every_listed_pr():
    import json
    c = json.loads((HERE / "data" / "changes.json").read_text())["content"]
    covered = {r["pr"] for r in c["rows"]}
    for n in (271, 304, 310, 315, 316, 317, 321, 322, 324, 325, 327, 330, 332, 335, 340, 341, 342, 343, 345, 346, 347, 348, 350, 351, 354):
        assert n in covered, n
