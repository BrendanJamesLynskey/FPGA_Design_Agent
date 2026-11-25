"""Brief 193: the "Why FPGA Guild" page is built from the committed records, with no typed number."""
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
import build  # noqa: E402
import why  # noqa: E402


def _pages():
    pages, bad = build.build(SITE / "public", build.load_data(None))
    assert not bad
    return pages


def test_why_data_is_current():
    assert json.loads((SITE / "data" / "why.json").read_text()) == json.loads(json.dumps(why.build()))


def test_drawers_have_every_part_and_the_numbers_are_values():
    W = why.build()["content"]
    assert 8 <= len(W["drawers"]) <= 10
    for d in W["drawers"]:
        assert d["claim"] and d["means"] and d["example"]["text"] and d["not_yet"] and d["link"]["href"]
        assert 2 <= len(d["means"]) <= 4 or len(d["means"]) == 2, d["id"]
        assert d["example"]["sources"], d["id"]
        for s in d["example"]["sources"]:
            assert (why.ROOT / s["path"].split("*")[0]).exists(), s
        assert "{" not in d["example"]["text"] and "{" not in d["not_yet"]
        assert re.search(r"\d", d["example"]["text"]), d["id"]       # the example carries its numbers
    srcs = yaml.safe_load((why.DIR / "why.yaml").read_text())
    for d in srcs["drawers"]:                                        # the authored text itself holds no digit outside a placeholder
        for t in [d["claim"], d["not_yet"], d["example"]["text"], *d["means"]]:
            assert not why._fill("t", t, {k: 1 for k in re.findall(r"\{(\w+)\}", t)}) is None


def test_drawers_are_closed_by_default_and_deep_linkable():
    p = _pages()["why.html"]
    ids = [d["id"] for d in why.build()["content"]["drawers"]]
    for i in ids:
        assert re.search(rf'<details class="area why" id="{i}">', p), i          # no open attribute
    assert "<details class=\"area why\" id=\"verification\">" in p
    assert 'id="expand-all"' in p
    app = (SITE / "src" / "app.js").read_text()
    assert "location.hash" in app and "details.area" in app          # the shared script opens the drawer a hash names


def test_why_is_the_first_nav_item_everywhere_and_linked_from_the_landing_page():
    pages = _pages()
    for fn, p in pages.items():
        nav = re.search(r'<nav aria-label="Pages">(.*?)</nav>', p, re.S).group(1)
        assert nav.startswith('<a href="' + ("../" if "/" in fn else "") + 'why.html"'), fn
    home = pages["index.html"]
    assert 'id="why-cta"' in home and home.index('id="why-cta"') < home.index('id="premise"')


def test_every_drawer_link_is_a_page_the_site_builds():
    names = {p[0] for p in build.PAGES}
    for d in why.build()["content"]["drawers"]:
        assert d["link"]["href"].split("#")[0] in names, d


def test_a_typed_number_fails_the_build(tmp_path, monkeypatch):
    y = yaml.safe_load((why.DIR / "why.yaml").read_text())
    y["drawers"][0]["example"]["text"] += " It was 42 times better."
    monkeypatch.setattr(why.yaml, "safe_load", lambda *_: y)
    with pytest.raises(why.ContractError, match="typed number"):
        why.build()


def test_a_reordered_list_fails_the_pin(monkeypatch):
    y = yaml.safe_load((why.DIR / "why.yaml").read_text())
    y["values"]["b96_req"]["expect"]["is"] = "some_other_design"
    monkeypatch.setattr(why.yaml, "safe_load", lambda *_: y)
    with pytest.raises(why.ContractError, match="list order"):
        why.build()


def test_page_holds_nothing_the_rules_exclude():
    p = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", _pages()["why.html"]).lower()
    for w in ("wavelet", "dwt", "edwards", "preston", "glow"):
        assert w not in p, w
    assert "2025.2" not in p and "vivado 2026.1" in p
