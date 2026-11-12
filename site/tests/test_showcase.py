"""Brief 61: the Showcase section, its data contract (docs/showcase_pages.md) and the graphics kit."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SITE = Path(__file__).resolve().parents[1]
FIX = SITE / "tests" / "fixtures" / "showcase"
sys.path.insert(0, str(SITE))

import build  # noqa: E402
import showcase  # noqa: E402


def test_committed_data_is_the_yaml():
    assert json.loads((SITE / "data" / "showcase.json").read_text()) == showcase.build()


def test_unpublished_projects_carry_no_numbers_and_no_page():
    S = showcase.build()
    assert S["counts"]["in_progress"] >= 1
    for p in S["projects"]:
        if p["status"] != "published":
            assert "values" not in p and "headline" not in p
            for k in ("title", "one_line", "what_it_will_show"):
                assert not showcase._numbers(p.get(k, "")), (p["id"], k)
            assert not (SITE / "public" / "showcase" / f'{p["id"]}.html').exists()
    page = (SITE / "public" / "showcase.html").read_text()
    for p in S["projects"]:
        assert p["title"] in page
    assert 'href="showcase.html"' in (SITE / "public" / "index.html").read_text()


def _preview(tmp_path):
    out = tmp_path / "pub"
    d = build.load_data(None)
    d["showcase"] = showcase.build(FIX)
    pages, bad = build.build(out, d)
    return d, pages, bad


def test_fixture_pages_render_every_kind_and_pass_the_number_check(tmp_path):
    d, pages, bad = _preview(tmp_path)
    assert not bad, bad[:5]
    for kind in showcase.KINDS:
        fn = f"showcase/demo_{'hist' if kind == 'hist' else kind}.html"
        page = pages[fn]
        assert f'data-kit="{kind}"' in page and 'data-key="showcase_hero"' in page
        blob = page.split('data-key="showcase_hero">')[1].split("</script>")[0]
        hero = json.loads(blob)
        assert hero == [p for p in d["showcase"]["projects"] if p["id"] == f"demo_{kind}"][0]["hero"]["data"]
        for sec in ('id="problem"', 'id="how"', 'id="results"', 'id="agent"', 'id="evidence"', 'id="limits"'):
            assert sec in page, (fn, sec)
        for t in showcase.EVIDENCE.values():
            assert t in page
        assert page.count('class="ag scarch"') == 2          # the architecture diagram, wide and narrow


def _write(tmp_path, y, name="x.yaml"):
    (tmp_path / name).write_text(yaml.safe_dump(y))
    return tmp_path


def _demo():
    return yaml.safe_load((FIX / "demo_hist.yaml").read_text())


@pytest.mark.parametrize("break_it, msg", [
    (lambda y: y.update(headline="It ran at 250 MHz on {n} samples."), "typed number"),
    (lambda y: y.update(evidence=[e for e in y["evidence"] if e["kind"] != "conditions"]), "evidence lacks"),
    (lambda y: y["hero"].update(kind="pie"), "hero.kind"),
    (lambda y: y.pop("limits"), "missing"),
    (lambda y: y["story"]["architecture"]["links"].append(["src", "nowhere", "x"]), "unknown block"),
    (lambda y: y.update(headline="{nothing}"), "no value named"),
])
def test_contract_refuses(tmp_path, break_it, msg):
    y = _demo()
    break_it(y)
    with pytest.raises(showcase.ContractError, match=msg):
        showcase.build(_write(tmp_path, y))


def test_in_progress_with_a_number_is_refused(tmp_path):
    y = yaml.safe_load((SITE / "showcase" / "nl_debug.yaml").read_text())
    y["what_it_will_show"] += " Capture depth 4096 samples."
    with pytest.raises(showcase.ContractError, match="typed number"):
        showcase.build(_write(tmp_path, y))


def test_shmoo_point_off_the_grid_is_refused(tmp_path):
    src = json.loads((FIX / "synthetic_heroes.json").read_text())
    src["shmoo"]["points"].append({"x": 999, "y": 1.0, "v": "pass"})
    p = SITE.parent / "build" / "b61_test_heroes.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(src))
    try:
        y = yaml.safe_load((FIX / "demo_shmoo.yaml").read_text())
        y["hero"]["source"] = "build/b61_test_heroes.json"
        with pytest.raises(showcase.ContractError, match="off the grid"):
            showcase.build(_write(tmp_path, y))
    finally:
        p.unlink()


def test_kit_draws_every_kind():
    js = (SITE / "src" / "app.js").read_text()
    kit = js.split("var KIT = {")[1].split("function mountKit")[0]
    for kind in showcase.KINDS:
        assert f"{kind}: function (art," in kit
    assert "if (reduce) pl.goto(k.n - 1);" in js          # reduced motion: nothing plays, the whole result is shown


def test_portfolio_pack_sources_resolve():
    P = json.loads((SITE / "portfolio" / "portfolio.json").read_text())
    d = build.load_data(None)
    assert P["url"].startswith("https://") and P["title"] and P["description"]
    assert len(P["facts"]) == 3
    for f in P["facts"]:
        for key in ("source", "of"):
            if key not in f:
                continue
            assert f[key].startswith("site/data:"), f
            v = build.lookup(d, f[key].split(":", 1)[1])
            assert build.fmt(abs(v)) in f["text"], (f, v)
    for k in ("still_1200x630", "still_square", "animation"):
        p = SITE / "portfolio" / P["media"][k]
        assert p.exists(), k
    assert (SITE / "portfolio" / P["media"]["animation"]).stat().st_size < 2_000_000


@pytest.mark.skipif(shutil.which("node") is None or not Path("/home/brendan/Claude_sandbox/node_modules/puppeteer").exists()
                    or not Path("/usr/bin/google-chrome").exists(), reason="puppeteer and Chrome not installed (run locally)")
@pytest.mark.skipif("FDA_E2E" not in __import__("os").environ, reason="browser test: set FDA_E2E=1 (a heavy job; take a slot)")
def test_e2e_pages_render_without_errors_or_overflow(tmp_path):
    out = tmp_path / "pub"
    d = build.load_data(None)
    d["showcase"] = showcase.build(FIX)
    pages, _ = build.build(out, d)
    for f, p in pages.items():
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        (out / f).write_text(p)
    pages_arg = "index.html,agent.html,results.html,showcase.html,showcase/demo_hist.html,showcase/demo_shmoo.html,showcase/demo_wave.html"
    r = subprocess.run(["node", str(SITE / "tests" / "e2e_render.js"), str(out), pages_arg], capture_output=True, text=True,
                       env={**__import__("os").environ, "NODE_PATH": "/home/brendan/Claude_sandbox/node_modules"}, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr


def test_home_visit_strip_counts_match_the_record():
    """The loop replay's strip of stage visits (app.js, mountLoop) counts visits and repairs as loop.py does."""
    L = json.loads((SITE / "data" / "loop.json").read_text())
    V, key = [], None
    for f in L["tour"]:
        if f.get("stage") is None:
            continue
        k = (f["stage"], f["visit"])
        if k != key:
            V.append({"stage": f["stage"], "rep": bool(V) and f["stage"] <= V[-1]["stage"]})
            key = k
    assert len(V) == L["tour_info"]["visits"] and sum(v["rep"] for v in V) == L["tour_info"]["repairs"]
    js = (SITE / "src" / "app.js").read_text()
    assert "rep: V.length > 0 && f.stage <= V[V.length - 1].stage" in js


def test_home_runs_chart_has_every_outcome():
    d = json.loads((SITE / "data" / "dev.json").read_text())
    js = (SITE / "src" / "app.js").read_text()
    lanes = js.split("var LANES = [")[1].split("];")[0]
    for o in {r["outcome"] for r in d["runs_list"]}:
        assert f'"{o}"' in lanes, o
    assert 'id="home-runs"' in (SITE / "public" / "index.html").read_text()
