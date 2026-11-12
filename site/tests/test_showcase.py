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
    d["showcase"] = showcase.build(FIX, allow_fixtures=True)
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
        showcase.build(_write(tmp_path, y), allow_fixtures=True)


def test_in_progress_with_a_number_is_refused(tmp_path):
    y = yaml.safe_load((SITE / "showcase" / "axi_transactor.yaml").read_text())
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
            showcase.build(_write(tmp_path, y), allow_fixtures=True)
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
    for f in P["facts"]:
        for src in f.get("interval", []):
            assert build.fmt(abs(build.lookup(d, src.split(":", 1)[1]))) in f["text"], (f, src)
    killed = 0
    for T in d["tasks"].values():
        mk = (T.get("check") or {}).get("mutants", {})
        killed += sum(1 for m in T["mutants"] if mk.get(m["name"], {}).get("killed"))
    assert killed == d["catalogue"]["counts"]["mutants"]           # fact 2: "every one caught"
    ab = d["board"]["agent_board"]
    assert f'{ab["uart_passed"]} of {ab["uart_tests"]} serial-link tests' in P["status"] and not ab["pass"]
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
    d["showcase"] = showcase.build(FIX, allow_fixtures=True)
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


# The correctness review's probe (PR #133 review, 38 cases): every case but the baseline and the number words must be refused.
def _setp(path, v):
    def m(y):
        o = y
        for k in path[:-1]:
            o = o[k]
        o[path[-1]] = v
    return m


PROBE = [
    ("baseline", lambda y: None, True),
    ("typed num headline", _setp(["headline"], "Caught a bug in 3.2 s"), False),
    ("typed num results", lambda y: y["story"]["results"].append("Latency 42 ns"), False),
    ("typed num problem", _setp(["story", "problem"], "At 125 MHz it fails"), False),
    ("typed num agent", _setp(["story", "agent", "plan"], "Run 3 seeds"), False),
    ("typed num limits", _setp(["limits", "next"], ["Try 10 boards"]), False),
    ("typed num evidence text", lambda y: y["evidence"][1].update(text="die 45 C"), False),
    ("typed num title", _setp(["title"], "Checker caught bug in 3.2 s"), False),
    ("typed num evidence label", lambda y: y["evidence"][1].update(label="die at 45 C, VCCINT 0.95 V"), False),
    ("typed num arch block", lambda y: y["story"]["architecture"]["blocks"].append(["x", "FIFO 512 deep at 250 MHz"]), False),
    ("typed num arch link label", lambda y: y["story"]["architecture"]["links"].append(["src", "chk", "1.6 Gb/s"]), False),
    ("typed num agent key", lambda y: y["story"]["agent"].update({"took 37 minutes": "x"}), False),
    ("vivado 2025.2", _setp(["vivado"], "2025.2"), False),
    ("board with number", _setp(["board"], "Board rev 3 at 125 MHz"), False),
    ("part arbitrary", _setp(["part"], "speed 99"), False),
    ("try_it note num", lambda y: y["try_it"].update(note="Takes 12 s"), False),
    ("caption num", lambda y: y["hero"].update(caption="42 samples"), False),
    ("desc num", _setp(["description"], "3 of 3 passed"), False),
    ("missing evidence record", lambda y: y.update(evidence=[e for e in y["evidence"] if e["kind"] != "record"]), False),
    ("missing evidence conditions", lambda y: y.update(evidence=[e for e in y["evidence"] if e["kind"] != "conditions"]), False),
    ("missing evidence versions", lambda y: y.update(evidence=[e for e in y["evidence"] if e["kind"] != "versions"]), False),
    ("missing evidence requirements", lambda y: y.update(evidence=[e for e in y["evidence"] if e["kind"] != "requirements"]), False),
    ("evidence bad path", lambda y: y["evidence"][0].update(path="results/nope.json"), False),
    ("evidence record no path", lambda y: y["evidence"][0].pop("path"), False),
    ("missing limits", lambda y: y.pop("limits"), False),
    ("empty limits", _setp(["limits"], {}), False),
    ("missing story.agent", lambda y: y["story"].pop("agent"), False),
    ("empty agent", _setp(["story", "agent"], {}), False),
    ("empty results", _setp(["story", "results"], []), False),
    ("hero kind bad", lambda y: y["hero"].update(kind="eye"), False),
    ("hero src missing", lambda y: y["hero"].update(source="results/none.json"), False),
    ("value src missing", lambda y: y["values"]["n"].update(source="results/none.json"), False),
    ("unknown placeholder", _setp(["headline"], "got {zz}"), False),
    ("in_progress with number", lambda y: y.update(status="in_progress", what_it_will_show="3.2 s of traffic"), False),
    ("in_progress num in part", lambda y: y.update(status="in_progress", what_it_will_show="x", part="3.2 s"), False),
    ("in_progress with headline num", lambda y: y.update(status="in_progress", what_it_will_show="x", headline="3 of 3 passed"), False),
    ("number words", _setp(["headline"], "three of three passed, twelve ns"), True),
    ("percent word", _setp(["headline"], "Saved a third; 1e3 runs"), False),
]


@pytest.mark.parametrize("name, mut, ok", PROBE, ids=[p[0] for p in PROBE])
def test_review_probe(tmp_path, name, mut, ok):
    y = _demo()
    mut(y)
    d = _write(tmp_path, y)
    if ok:
        showcase.build(d, allow_fixtures=True)
    else:
        with pytest.raises(showcase.ContractError):
            showcase.build(d, allow_fixtures=True)


def test_fixture_and_hero_source_rules(tmp_path):
    y = _demo()
    with pytest.raises(showcase.ContractError, match="fixture page"):
        showcase.build(_write(tmp_path, y))                      # the production build never takes a fixture
    y.pop("fixture")
    with pytest.raises(showcase.ContractError, match="under results/"):
        showcase.build(_write(tmp_path, y))                      # a real page's hero comes from results/, not test data


def _typed_page(tmp_path, mut):
    """Build the site with one fixture page whose YAML was changed by mut (bypassing the contract, to test build.py alone)."""
    y = _demo()
    mut(y)
    d = build.load_data(None)
    S = showcase.build(FIX, allow_fixtures=True)
    P = showcase.resolve("t.yaml", _demo(), allow_fixtures=True)
    P2 = dict(P)
    if "try_it" in y:
        P2["try_it"] = y["try_it"]
    P2["story"] = dict(P["story"], problem=y["story"]["problem"])
    S["projects"] = [p for p in S["projects"] if p["id"] != P["id"]] + [P2]
    d["showcase"] = S
    _, bad = build.build(tmp_path / "pub", d)
    return {t for f, t in bad if f == f'showcase/{P["id"]}.html'}


@pytest.mark.parametrize("mut, token", [
    (lambda y: y["try_it"].update(command="python3 run.py --budget 61.73"), "61.73"),
    (lambda y: y["story"].update(problem="Worst slack was -0.4377 ns."), "-0.4377"),
    (lambda y: y["story"].update(problem="The FIFO holds 8191 words."), "8191"),
])
def test_showcase_number_check_is_not_circular(tmp_path, mut, token):
    """A number that appears only in the project's own text (here slipped past the contract on purpose) must fail
    build.py's number check: the project's text is never part of the data the check accepts."""
    bad = _typed_page(tmp_path, mut)
    assert token in bad or token.lstrip("-") in bad, bad


@pytest.mark.parametrize("text", ["-0.4 ns", "x37", "#37", "{n}.5", "M37", "UG37", "PR #37", "Brief 37", "it exceeded-by-37-ns",
                                  "Vivado 2025.2", "٣ items"])
def test_typed_number_patterns_are_refused(tmp_path, text):
    y = _demo()
    y["story"]["problem"] = text
    with pytest.raises(showcase.ContractError, match="typed number"):
        showcase.build(_write(tmp_path, y), allow_fixtures=True)


@pytest.mark.parametrize("text", ["Digilent Nexys A7-100T (xc7a100tcsg324-1)", "xck26-sfvc784-2LV-c on the KR260",
                                  "AXI4-Lite and AXI4-Stream over UART", "Vivado 2026.1", "three of three, twelve ns"])
def test_names_with_digits_are_allowed(tmp_path, text):
    y = _demo()
    y["story"]["problem"] = text
    showcase.build(_write(tmp_path, y), allow_fixtures=True)



def test_readme_headline_numbers_are_the_data():
    """The README's measured paragraph (typed by hand) must match site/data."""
    d = build.load_data(None)
    t = " ".join((SITE.parent / "README.md").read_text().split())
    dev, ab = d["dev"], d["board"]["agent_board"]
    assert f'On {dev["tasks"]} development tasks, {dev["hidden_pass"]} of {dev["runs"]} runs with' in t
    assert f'In {dev["escapes"]} more' in t
    assert f'passed ({ab["uart_passed"]} of {ab["uart_tests"]}) and its logic-analyser captures failed' in t and not ab["pass"]


def test_nl_debug_portfolio_card_sources_resolve():
    """The showcase project 'Debugging in plain English' (brief 50A): every fact's number is the value at its source."""
    P = json.loads((SITE / "portfolio" / "nl_debug" / "portfolio.json").read_text())
    d = build.load_data(None)
    assert P["url"].startswith("https://") and len(P["facts"]) == 3
    for f in P["facts"]:
        for key in ("source", "of"):
            if key in f:
                assert f[key].startswith("site/data:"), f
                assert build.fmt(abs(build.lookup(d, f[key].split(":", 1)[1]))) in f["text"], (f, key)
    for k in ("still_1200x630", "animation"):
        assert (SITE / "portfolio" / "nl_debug" / P["media"][k]).exists(), k
    assert (SITE / "portfolio" / "nl_debug" / P["media"]["animation"]).stat().st_size < 2_000_000


# --- brief 50A page round: the staged wave option, the run table, the drawers, the agent order -----------------------

def _staged_hero(tmp_name, mut=None):
    """A copy of the nl_debug hero under build/ (hero sources may sit outside results/ only for fixtures)."""
    src = json.loads((SITE.parent / "results" / "50a_nl_debug" / "hero.json").read_text())
    if mut:
        mut(src)
    p = SITE.parent / "build" / tmp_name
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(src))
    return p


@pytest.mark.parametrize("mut, msg", [
    (lambda h: h["stages"][3].update(phase="before"), "exactly one during"),
    (lambda h: h["stages"][4].update(captions=[]), "'after' stage with a caption"),
    (lambda h: h["marks"].append({"x": 999, "label": "off"}), "not on the x axis"),
    (lambda h: h["marks"].append({"x": 0, "signal": "nosuch", "label": "x"}), "names no signal"),
    (lambda h: h["captions"].pop(), "captions has"),
])
def test_staged_wave_is_checked(tmp_path, mut, msg):
    p = _staged_hero("b50a_test_hero.json", mut)
    try:
        y = yaml.safe_load((FIX / "demo_wave.yaml").read_text())
        y["hero"] = {"kind": "wave", "source": "build/b50a_test_hero.json", "path": "", "caption": "x"}
        with pytest.raises(showcase.ContractError, match=msg):
            showcase.build(_write(tmp_path, y), allow_fixtures=True)
    finally:
        p.unlink()


def test_kit_has_the_staged_wave_option():
    js = (SITE / "src" / "app.js").read_text()
    assert "return stagedWave(art, T);" in js.split("var KIT = {")[1].split("hist: function")[0]
    sw = js.split("function stagedWave")[1].split("function nf(")[0]
    for k in ("stagestrip", "future solid", "kmarkg", "visually-hidden", "aria-label"):
        assert k in sw, k


def test_nl_debug_page_reads_in_order_with_its_table_and_drawers():
    S = showcase.build(SITE / "showcase")
    P = next(p for p in S["projects"] if p["id"] == "nl_debug")
    page = showcase.page_body(P)
    import re
    assert re.findall(r"<dt>([^<]+)</dt>", page) == ["Request", "Plan", "Gates", "Approvals"]
    rows = P["story"]["table"]["rows"]
    assert len(rows) == P["values"]["runs"] and page.count("<tr>") == len(rows) + 1
    for r in rows:
        assert (SITE.parent / r["capture"]).is_file() and r["capture"] in page
    assert page.count('<details class="more"><summary>') >= 5
    assert "No effect found" not in page                   # the FIFO refusal is not a null result
    assert P["values"]["readback_runs"] < P["values"]["runs"] and "where a register was read back" in P["headline"]


def test_table_source_must_be_a_committed_result(tmp_path):
    y = yaml.safe_load((SITE / "showcase" / "nl_debug.yaml").read_text())
    y["story"]["table"]["source"] = "site/data/dev.json"
    with pytest.raises(showcase.ContractError, match="story.table.source"):
        showcase.build(_write(tmp_path, y))


def test_agent_section_follows_the_run_order_whatever_the_yaml_order(tmp_path):
    y = _demo()
    y["story"]["agent"] = dict(reversed(list(y["story"]["agent"].items())))
    P = showcase.build(_write(tmp_path, y), allow_fixtures=True)["projects"][0]
    import re
    assert re.findall(r"<dt>([^<]+)</dt>", showcase.page_body(P)) == ["Request", "Plan", "Gates", "Approvals"]


def test_every_published_text_field_fills_its_placeholders(tmp_path):
    """Brief 59A editor finding: an evidence label rendered '{build_id}' literally. Every field is filled, and the build
    refuses a page with a placeholder left in it."""
    y = _demo()
    y["evidence"][0]["label"] = "Synthetic hero data, {n} samples"
    y["title"] = "Template preview ({n} samples)"
    y["story"]["architecture"]["blocks"][0][1] = "Source of {n}"
    P = showcase.build(_write(tmp_path, y), allow_fixtures=True)["projects"][0]
    page = showcase.page_body(P)
    assert "{n}" not in page and "{n}" not in P["title"]
    assert build.leftover_placeholders('<p>build {build_id}</p><script>var a = {x};</script>') == ["{build_id}"]


@pytest.mark.parametrize("text", ["{n.x} samples", "{ n } samples", "{{n}} samples", "a { stray brace", "stray } brace"])
def test_malformed_placeholders_are_refused(tmp_path, text):
    y = _demo()
    y["one_line"] = text
    with pytest.raises(showcase.ContractError, match="malformed placeholder"):
        showcase.build(_write(tmp_path, y), allow_fixtures=True)


@pytest.mark.parametrize("html_text, found", [("<p>{runs.x}</p>", ["{runs.x}"]), ("<p>{ runs }</p>", ["{ runs }"]),
                                             ("<p>{{runs}}</p>", ["{runs}"]), ("<pre>{y}</pre><p>ok</p>", [])])
def test_leftover_placeholder_scan_catches_malformed_forms(html_text, found):
    assert build.leftover_placeholders(html_text) == found
