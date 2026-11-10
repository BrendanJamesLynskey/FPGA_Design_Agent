"""Site checks: data is current, pages are current, the number assertion works, the eval-1 section renders from a fixture."""
import json
import subprocess
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
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
