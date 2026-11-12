"""Site checks: data is current, pages are current, the number assertion works, the eval-1 section renders from a fixture."""
import json
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SITE.parent))
import build  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


def test_data_and_pages_current():
    assert run(str(SITE / "export.py"), "--check").returncode == 0
    r = run(str(SITE / "build.py"), "--check")
    assert r.returncode == 0, r.stdout


def test_number_assertion_catches_an_unsourced_number():
    d = build.load_data(None)
    pages, bad = build.build(SITE / "public", d)
    assert not bad
    tampered = pages["index.html"].replace("<h1>", "<h1>987654 ")
    assert any(t == "987654" for t in build.visible_numbers(tampered))
    ok = build.data_tokens(d) | build.allow_tokens()
    assert "987654" not in ok


def test_eval1_section_stub_and_fixture():
    d = build.load_data(None)
    assert "eval1" not in d, "site/data/eval1.json is the planner's file; the fixture must never be committed there"
    fx = SITE / "tests" / "fixtures" / "eval1_synthetic.json"
    d2 = build.load_data(fx)
    pages, bad = build.build(SITE / "public", d2)
    assert not bad and '"synthetic_task_a"' in pages["results.html"]
    assert '"synthetic_task_a"' not in build.build(SITE / "public", d)[0]["results.html"]


def _held_out_ids():
    import re
    held = set()
    for f in (SITE.parent / "benchmark" / "split.yaml", SITE.parent / "benchmark" / "course" / "split.yaml",
              SITE.parent / "benchmark" / "course" / "split_c9_c12.yaml"):
        for blk in re.findall(r"held_out:\n((?:\s+- \S+\n)+)", f.read_text()):
            held |= set(re.findall(r"- (\S+)", blk))
    assert held
    return held


def test_held_out_ids_only_in_the_index_listing():
    """v1 and course held-out ids (public in the split files) appear only in the held-out list of problems.html and in
    catalogue.json's held_out/moved lists; nowhere else in the pages or the data."""
    import re
    held = _held_out_ids()
    for p in list((SITE / "public").rglob("*.html")) + list((SITE / "data").rglob("*.json")):
        t = p.read_text()
        if p.name == "problems.html":
            t = re.sub(r'(?s)<h2 id="held-out">.*?<h3>Benchmark v2</h3>', "", t)
        if p.name == "catalogue.json":
            c = json.loads(t)
            assert all(set(h) == {"id", "set", "tier", "status"} for h in c["held_out"] + c["moved"]), "held-out entries carry only id, set, tier, status"
            c.pop("held_out"); c.pop("moved"); t = json.dumps(c)
        for h in held:
            assert h not in t, (str(p.relative_to(SITE)), "held-out id outside the held-out listing")


def test_no_held_out_task_has_a_page_or_data():
    held = _held_out_ids()
    pages = {p.stem for p in (SITE / "public" / "problems").glob("*.html")}
    data = {p.stem for p in (SITE / "data" / "tasks").glob("*.json")}
    dirs = {p.name for p in (SITE / "public" / "problems").iterdir() if p.is_dir()}
    assert pages and pages == data == dirs
    assert not held & (pages | data | dirs)


def test_v2_held_out_is_counts_only():
    c = json.loads((SITE / "data" / "catalogue.json").read_text())
    for cell in c["v2_cells"]:
        assert set(cell) == {"domain", "tier", "dev", "held_out"} and isinstance(cell["held_out"], int)


def test_every_trace_is_valid_and_from_its_model():
    sys.path.insert(0, str(SITE))
    import traces
    for p in (SITE / "data" / "tasks").glob("*.json"):
        t = json.loads(p.read_text())
        traces.validate(t["id"], t["trace"])


def test_flow_notes_tear_model():
    """Brief 14: the synchroniser model. Gray and no-extra-cycle never tear; a binary bus with the extra cycle does, and the
    page's frames show it; held bits only appear with the extra cycle and never two cycles in a row."""
    import flow_model as m
    d = json.loads((SITE / "data" / "flow_notes.json").read_text())
    st = {(s["bus"], s["extra_cycle"]): s["torn_cycles"] for s in d["tear"]["stats"]}
    assert st[("gray", True)] == 0 and st[("gray", False)] == 0 and st[("binary", False)] == 0 and st[("binary", True)] > 0
    fr = d["tear"]["configs"]["binary_extra"]
    assert any(f["torn"] for f in fr)
    assert fr == m.run("binary", True, m.FRAMES)
    for key, frames in d["tear"]["configs"].items():
        for a, b in zip(frames, frames[1:]):
            assert not any(x and y for x, y in zip(a["held"], b["held"]))
        if key.endswith("plain"):
            assert not any(any(f["held"]) for f in frames)
    # a Gray source changes one bit at a time
    g = d["tear"]["configs"]["gray_extra"]
    for a, b in zip(g, g[1:]):
        assert sum(x != y for x, y in zip(a["src"], b["src"])) <= 1


def test_flow_notes_counts_match_the_mutant_table():
    d = json.loads((SITE / "data" / "flow_notes.json").read_text())
    c = d["counts"]
    assert (c["ported"], c["gate_flags"], c["report_cdc_flags"], c["correct"], c["correct_pass"]) == (10, 10, 5, 12, 12)
    assert [m["id"] for m in d["mutants"] if m["gate"] is None] == ["M9", "M11"]


# ---- brief 23: areas of expertise (drawers) -------------------------------------------------------------------------------

import copy  # noqa: E402
import re  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

import expertise  # noqa: E402


def _yaml():
    return yaml.safe_load((SITE / "data" / "expertise.yaml").read_text())


def test_skills_are_the_skills_at_the_pin():
    doc = json.loads((SITE / "data" / "skills.json").read_text())
    assert doc["pin"] == expertise.pin()
    counts = {}
    for s in doc["skills"]:
        counts[(s["unit"], s["section"])] = counts.get((s["unit"], s["section"]), 0) + 1
    assert counts == expertise.packs_section_counts(), "skills.json differs from the sections and counts of knowledge/PACKS.md"
    assert len({(s["unit"], s["name"]) for s in doc["skills"]}) == len(doc["skills"])
    assert all(s["description"] and len(s["description"]) < 260 for s in doc["skills"])


@pytest.mark.skipif(expertise.kb_checkout() is None, reason="the private knowledge bank is not checked out here")
def test_skills_json_matches_the_bank():
    assert expertise.skills_from_bank(expertise.kb_checkout()) == json.loads((SITE / "data" / "skills.json").read_text())["skills"]


def test_every_drawer_skill_exists_at_the_pin():
    have = {(s["unit"], s["name"], s["section"]) for s in json.loads((SITE / "data" / "skills.json").read_text())["skills"]}
    x = json.loads((SITE / "data" / "expertise.json").read_text())
    for a in x["areas"]:
        for g in a["skills"]:
            for s in g["items"]:
                assert (g["unit"], s["name"], g["section"]) in have, (a["id"], s["name"])


def test_areas_and_required_drawers():
    x = json.loads((SITE / "data" / "expertise.json").read_text())
    ids = [a["id"] for a in x["areas"]]
    assert 12 <= len(ids) <= 20 and len(set(ids)) == len(ids)
    for need in ("fsm", "memory", "mixed", "cdc", "constraints"):
        assert need in ids
    assert all(a["counts"]["skills"] > 0 and a["gaps"] for a in x["areas"])


def test_no_number_is_typed_into_prose_or_templates():
    for a in _yaml()["areas"]:
        for t in [a["name"], a["summary"], a["about"], *a["gaps"], *[c["what"] for c in a.get("checks", [])]]:
            assert not expertise.prose_numbers(t), (a["id"], t)
        for it in a.get("evidence", []):
            tmpl = expertise.PROSE_OK.sub(" ", re.sub(r"\{\d+\}", " ", it["text"]))
            assert not expertise.NUM.findall(tmpl), (a["id"], it["text"])


def test_a_typed_number_in_an_evidence_template_is_refused(monkeypatch):
    y = _yaml()
    y["areas"][0]["evidence"][0]["text"] += " Slack was 9.999 ns."
    real = yaml.safe_load
    monkeypatch.setattr(expertise.yaml, "safe_load", lambda t: y if t.startswith("# Areas of expertise") else real(t))
    with pytest.raises(AssertionError):
        expertise.build()


def test_direct_values_are_in_their_source_files():
    """A get: or re: value must occur, as a number, in the source file it is read from; counts are derived and exempt."""
    for a in _yaml()["areas"]:
        for it in a.get("evidence", []):
            for ex in it.get("values", []):
                if not ex.startswith(("get:", "re:")):
                    continue
                v = expertise.evaluate(ex, it)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    continue
                nums = set()
                for p in expertise.files_of(it):
                    for tok in re.findall(r"-?\d[\d,]*(?:\.\d+)?", p.read_text()):
                        nums.add(float(tok.replace(",", "")))
                assert float(v) in nums, (a["id"], ex, v)


def test_level_is_computed_from_the_items():
    y = {a["id"]: a for a in _yaml()["areas"]}
    for a in json.loads((SITE / "data" / "expertise.json").read_text())["areas"]:
        kinds = {e["kind"] for e in a["evidence"]}
        n = expertise.LEVELS.index(a["level"])
        if n >= 3:
            assert "agent" in kinds or y[a["id"]].get("cap"), a["id"]
        if a["level"] == "agent":
            assert "agent" in kinds
        if a["level"] == "checked":
            assert a["counts"]["enforced"] > 0
        if a["level"] == "measured":
            assert "measured" in kinds and a["counts"]["enforced"] == 0 and "agent" not in kinds
        if a["level"] == "knowledge":
            assert not kinds - {"example"} and a["counts"]["enforced"] == 0
    assert y["constraints"]["cap"]["level"] == "checked"


def test_checks_and_links_point_at_real_files():
    x = json.loads((SITE / "data" / "expertise.json").read_text())
    for a in x["areas"]:
        for c in a["checks"]:
            assert (SITE.parent / c["file"]).exists(), c["file"]
        for e in a["evidence"]:
            for s in e["sources"]:
                assert (SITE.parent / s["path"].split("*")[0].rstrip("/").rsplit("/", 1)[0]).exists() or (SITE.parent / s["path"]).exists()


def test_expertise_page_is_native_details_and_linked():
    d = build.load_data(None)
    pages, bad = build.build(SITE / "public", d)
    assert not bad
    p = pages["expertise.html"]
    x = d["expertise"]
    assert p.count('<details class="area"') == len(x["areas"])
    for a in x["areas"]:
        assert f'id="{a["id"]}"' in p and f'href="#{a["id"]}"' in p
    assert 'href="expertise.html"' in pages["index.html"] and 'href="expertise.html"' in p
    assert 'id="expand-all"' in p and 'id="collapse-all"' in p
    assert not re.search(r"<script[^>]*>[^<]*openHash", p.split("<script>")[0])


import os  # noqa: E402
from html import escape as html_escape  # noqa: E402


# ---- brief 31: "Differs by family" per drawer, from the bank's family matrix ----------------------------------------------

def test_every_drawer_lists_the_matrix_rows_for_its_area():
    fd = json.loads((SITE / "data" / "family_diffs.json").read_text())
    x = json.loads((SITE / "data" / "expertise.json").read_text())
    for a in x["areas"]:
        want = fd["areas"][a["id"]]
        assert a["family"]["rows"] == want["rows"] and a["family"]["rows"], a["id"]
        assert a["family"]["docs"] == want["docs"], a["id"]
        for r in a["family"]["rows"]:
            assert set(r) == {"topic", "summary", "confirmed"} and r["confirmed"] in ("tool", "doc")
    html = (SITE / "public" / "expertise.html").read_text()
    for a in x["areas"]:
        assert f'id="{a["id"]}-docs"' in html and f'href="#{a["id"]}-docs"' in html, a["id"]
        for r in a["family"]["rows"]:
            assert html_escape(r["topic"]) in html, (a["id"], r["topic"])


def _matrix_kb():
    p = Path(os.environ.get("FDA_FAMILY_MATRIX_KB", os.environ.get("FDA_KNOWLEDGE_REPO", "~/Claude_sandbox/FPGA_Design_Agent_Knowledge"))).expanduser()
    return p if (p / "tools" / "family_matrix.py").exists() and (p / "family_matrix" / "areas").is_dir() else None


@pytest.mark.skipif(_matrix_kb() is None, reason="no knowledge-bank checkout with family_matrix/ here")
def test_family_diffs_match_the_bank_matrix(tmp_path):
    kb = _matrix_kb()
    out = tmp_path / "fd.json"
    r = subprocess.run([sys.executable, str(kb / "tools" / "family_matrix.py"), "--site-json", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text()) == json.loads((SITE / "data" / "family_diffs.json").read_text())


# ---- brief 43: the agent page (graph drawn from the code) ---------------------------------------------------------------

def _agent():
    return json.loads((SITE / "data" / "agent_graph.json").read_text())


def test_agent_graph_equals_the_code():
    """The graph in agent_graph.json is the graph the code compiles, and every node and edge has its words."""
    import agent_arch
    nodes, edges = agent_arch.graph_from_code()
    A = _agent()
    assert [n["id"] for n in A["graph"]["nodes"]] == nodes
    assert sorted((e["source"], e["target"], e["conditional"], e["key"]) for e in A["graph"]["edges"]) == edges
    assert set(agent_arch.NODE_WORDS) == set(nodes)
    assert set(agent_arch.EDGE_WORDS) == {(s, t) for s, t, _, _ in edges}
    inner = agent_arch.inner_from_code()
    assert inner == {k: (v if k != "edges" else [tuple(x) for x in v]) for k, v in A["inner"].items()}


def test_drawn_graph_equals_the_data():
    """The LangGraph figure on agent.html (both layouts) has exactly the data's nodes and edges."""
    A = _agent()
    page = (SITE / "public" / "agent.html").read_text()
    figs = re.findall(r'<svg class="ag lg".*?</svg>', page, re.S)
    assert len(figs) == 2
    want_e = {f'{e["source"]}~{e["target"]}' for e in A["graph"]["edges"]}
    want_n = {n["id"] for n in A["graph"]["nodes"]}
    for f in figs:
        assert set(re.findall(r'data-e="([^"]+)"', f)) == want_e
        assert set(re.findall(r'data-n="([^"]+)"', f)) == want_n
    import agent_page
    for lay in ("wide", "narrow"):
        assert set(agent_page.GPOS[lay]) == want_n


def test_every_gate_and_stage_has_words():
    import agent_arch
    from agent.graph.stages import MACHINE
    assert {g for st in MACHINE for g in st.gates} <= set(agent_arch.GATE_WORDS)
    assert len(agent_arch.STAGE_WORDS) == len(MACHINE)


def test_role_stages_match_the_recorded_traces():
    """Every (stage, role) a recorded run's turn trace shows is one ROLE_STAGES says node_work runs."""
    import agent_arch
    from agent.graph.stages import MACHINE
    n_of = {st.name: st.n for st in MACHINE}
    seen = 0
    for p in (SITE.parent / "results" / "f2").glob("agent_*.json"):
        r = json.loads(p.read_text())
        for t in r.get("turn_trace", []) if isinstance(r, dict) else []:
            n = n_of[t["stage"]]
            assert t["role"] in agent_arch.ROLE_STAGES.get(n, ["rtl"]), (p.name, t["stage"], t["role"])
            seen += 1
    assert seen


def test_replays_follow_their_records():
    A = _agent()
    pas, giv = A["replays"]
    rec = json.loads((SITE.parent / giv["source"]).read_text())
    assert [v["stage"] for v in giv["visits"]] == rec["stages_visited"]
    calls = sum(sum(r["tools"].values()) for v in giv["visits"] for r in v["roles"])
    assert calls == sum(sum(t["tools"].values()) for t in rec["turn_trace"])
    assert giv["visits"][-1]["next"]["kind"] == "end" and pas["visits"][-1]["next"]["kind"] == "end"
    rp = json.loads((SITE / "data" / "replay.json").read_text())
    assert [(v["stage"], v["visit"]) for v in pas["visits"]] == [(s["stage_no"], s["visit"]) for s in rp["steps"]]
    assert all(a["status"] == "not yet measured" for a in A["arms"])


def test_agent_page_is_second_and_linked():
    names = [p[0] for p in build.PAGES]
    assert names[1] == "agent.html"
    for f in ("index.html", "how.html"):
        assert 'href="agent.html"' in re.sub(r"(?s)<header.*?</header>", "", (SITE / "public" / f).read_text()), f


# ---- brief 47: the feedback loop on the home page, and the harness section ----------------------------------------------

def _loop():
    return json.loads((SITE / "data" / "loop.json").read_text())


def _hero_svgs():
    page = (SITE / "public" / "index.html").read_text()
    figs = re.findall(r'<svg class="ag loop".*?</svg>', page, re.S)
    assert len(figs) == 2
    return figs


def test_loop_labels_come_from_data():
    """Each label on a returning arrow, in both layouts, is the data's text; every number in it occurs in its source record."""
    import html as h
    L = _loop()
    for f in _hero_svgs():
        for s in L["stations"]:
            if not s["fb"]:
                assert f'data-fb="{s["id"]}"' not in f
                continue
            g = re.search(rf'<g class="fb" data-fb="{s["id"]}"[^>]*>(.*?)</g>', f, re.S).group(1)
            shown = [h.unescape(x) for x in re.findall(r"<text[^>]*>([^<]*)</text>", g)]
            assert shown[-len(s["fb"]["values"]):] == s["fb"]["values"]
            assert " ".join(shown[:-len(s["fb"]["values"])]) == "returns " + s["fb"]["kind"]
    for s in L["stations"]:
        if s["fb"] and s["fb"]["src"]:
            src = (SITE.parent / s["fb"]["src"]["record"]).read_text()
            have = set(re.findall(r"\d+(?:\.\d+)?", src))
            for v in s["fb"]["values"]:
                for n in re.findall(r"\d+(?:\.\d+)?", v):
                    assert n.lstrip("+") in have or n.rstrip("0").rstrip(".") in have, (s["id"], v, n)
        elif s["fb"]:
            assert all(not re.search(r"\d", v) for v in s["fb"]["values"]), "a label with no source carries no number"


def test_loop_legs_evidence_resolves_and_counts():
    import loop
    L = _loop()
    y = yaml.safe_load((SITE / "data" / "loop_legs.yaml").read_text())["legs"]
    assert [x["id"] for x in L["legs"]] == [x["id"] for x in y]
    for x in L["legs"]:
        assert x["status"] in loop.STATUS
        assert x["evidence"] or x["status"] != "automated", x["id"]
        for p in x["evidence"]:
            assert (SITE.parent / p).is_file(), (x["id"], p)
    c = L["counts"]
    assert c["automated"] == sum(x["status"] == "automated" for x in L["legs"]) and c["total"] == len(L["legs"])
    page = (SITE / "public" / "index.html").read_text()
    assert f'{c["automated"]} of {c["total"]}' in page
    src = (SITE / "src" / "index.html").read_text()
    assert "{{loop.counts.automated}} of {{loop.counts.total}}" in src, "the count is filled from data, never typed"


def test_drawn_legs_match_their_status():
    status = {x["id"]: x["status"] for x in _loop()["legs"]}
    for f in _hero_svgs():
        legs = set(re.findall(r'data-leg="([^"]+)"', f))
        assert legs <= set(status) and {"repair", "approve", "wiring", "instruments", "hil_gate"} <= legs
        for cls, leg in re.findall(r'<(?:path|rect) class="[^"]*lg-(\w+)[^"]*"[^>]*data-leg="([^"]+)"', f):
            assert cls == status[leg], leg
        for leg in re.findall(r'data-person="([^"]+)"', f):
            assert status[leg] == "person"
        for p in ("f-spec", "f-sim", "f-viv", "f-board", "f-instr", "o-sim", "o-vivado", "o-board", "r-board"):
            assert f'data-p="{p}"' in f


def test_tour_follows_its_record():
    L = _loop()
    import loop
    rec = json.loads((SITE.parent / loop.TOUR_RUN).read_text())
    work = [(f["stage"], f["visit"]) for f in L["tour"] if f["ph"] == "work"]
    assert [s for s, _ in work] == rec["stages_visited"]
    figs = _hero_svgs()
    for f in L["tour"]:
        for pid, _ in f["path"]:
            assert all(f'data-p="{pid}"' in g for g in figs), pid
    board = json.loads((SITE.parent / loop.TOUR_BOARD).read_text())["run_as_written"]
    assert [f["ph"] for f in L["tour"][-5:]] == ["approve", "act", "observe", "decide", "end"]
    assert L["tour"][-2]["gate"] == ("pass" if board["pass"] else "fail")


def test_harness_section_equals_the_code():
    import agent_arch
    A = _agent()
    inner = agent_arch.inner_from_code()
    assert A["harness"]["settings"] == agent_arch.harness_settings()
    assert [m["name"] for m in A["harness"]["middleware"]] == inner["middleware"]
    assert set(inner["middleware"]) <= set(agent_arch.MIDDLEWARE_WORDS)
    if not (SITE.parent / "results" / "42_workflows").exists():
        assert all(a["status"] == "not yet measured" for a in A["harness"]["arms"])
    assert [a["id"] for a in A["harness"]["arms"]] == [f"H{k}" for k in range(1, 9)]
    page = (SITE / "public" / "agent.html").read_text()
    assert 'id="harness"' in page and page.count('svg class="ag harn"') == 2
    for f in ("index.html", "how.html", "results.html"):
        assert 'href="agent.html#harness"' in (SITE / "public" / f).read_text(), f
    how = (SITE / "public" / "how.html").read_text()
    for t in ("term-harness", "term-middleware", "term-eviction", "term-caching"):
        assert f'id="{t}"' in how


# Brief 49 (owner, 2026-11-11: "all published material from now on should refer only to this Vivado release"): no built
# page may name a Vivado release other than 2026.1. AMD's release tokens are YYYY.N (N 1-4), with or without a "v";
# raw evidence (results/, run records, fixtures) keeps its own version but is never a built page, so nothing is allowed here.
import re  # noqa: E402

RELEASE = re.compile(r"(?<![\d.])v?((?:19|20)\d\d\.[1-4])(?![\d])")
ALLOWED_RELEASES = {"2026.1"}


def release_tokens(text):
    return {m.group(1) for m in RELEASE.finditer(text)} - ALLOWED_RELEASES


def test_built_pages_name_only_vivado_2026_1():
    d = build.load_data(None)
    pages, bad = build.build(SITE / "public", d)
    found = {name: sorted(release_tokens(html)) for name, html in pages.items() if release_tokens(html)}
    assert not found, f"pages name another Vivado release: {found}"
    for p in (SITE / "public").rglob("*.html"):            # the committed pages too (what the owner deploys)
        assert not release_tokens(p.read_text()), p


def test_release_guard_catches_an_old_release():
    assert release_tokens("built with Vivado 2025.2") == {"2025.2"}
    assert release_tokens("UG901 v2025.2 (synthesis)") == {"2025.2"}
    assert release_tokens("Vivado 2026.1, 2,026.1 ns, 12026.15, DS181 v1.27.1, 2026-02-06") == set()


# Brief 49 review (rule 3): published pages, README and docs link only 2026.1 records. A results folder whose README says
# "superseded by" is a 2025.2 record; a link into it is allowed only to the entries its README lists as "Still current:".
ROOT = SITE.parent
RESULT_REF = re.compile(r"results/([A-Za-z0-9_.-]+)(/[^\s\"'`)\]<>|,;]*)?")


def superseded_folders():
    out = {}
    for readme in (ROOT / "results").glob("*/README.md"):
        t = readme.read_text()
        if "superseded by" in t.split("\n## ", 1)[0]:
            m = re.search(r"^Still current: (.*)$", t, re.M)
            out[readme.parent.name] = re.findall(r"`([^`]+)`", m.group(1)) if m else []
    return out


PUBLISHED = ["README.md", "flow/README.md", "docs/**/*.md", "cloud/*.md", "ip_lib/*/README.md", "site/src/*.html",
             "site/data/*.yaml", "site/*.py", "site/public/**/*.html"]
FROZEN_RECORDS = {"docs/eval/eval1_preregistration.md"}       # a pre-registration is a record, kept as written


def published_files():
    seen = set()
    for g in PUBLISHED:
        for p in ROOT.glob(g):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and rel not in FROZEN_RECORDS and rel not in seen:
                seen.add(rel)
                yield rel, p


def stale_links():
    old = superseded_folders()
    bad = []
    for rel, p in published_files():
        for m in RESULT_REF.finditer(p.read_text(errors="replace")):
            folder, rest = m.group(1), (m.group(2) or "").lstrip("/")
            partly_current = bool(old.get(folder)) and rest in ("", "README.md")    # the folder of a partly superseded record
            if folder in old and not partly_current and not any(rest.startswith(ok) or rest == ok.rstrip("/") for ok in old[folder]):
                bad.append(f"{rel}: results/{folder}/{rest}")
    return bad


def test_published_material_links_no_superseded_result():
    assert superseded_folders(), "no superseded folder found: the README marker changed?"
    bad = stale_links()
    assert not bad, "links into superseded 2025.2 records:\n" + "\n".join(sorted(set(bad)))


def test_readmes_and_docs_name_only_vivado_2026_1():
    found = {rel: sorted(release_tokens(p.read_text(errors="replace"))) for rel, p in published_files()
             if not rel.startswith("site/") and release_tokens(p.read_text(errors="replace"))}
    assert not found, f"README/docs name another Vivado release: {found}"
