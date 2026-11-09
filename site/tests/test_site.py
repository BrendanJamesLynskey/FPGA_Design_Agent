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


def test_no_held_out_split_names_in_site():
    import re
    held = set()
    for f in (SITE.parent / "benchmark" / "split.yaml", SITE.parent / "benchmark" / "course" / "split.yaml",
              SITE.parent / "benchmark" / "course" / "split_c9_c12.yaml"):
        if not f.exists():
            continue
        txt = f.read_text()
        for blk in re.findall(r"held_out:\n((?:\s+- \S+\n)+)", txt):
            held |= set(re.findall(r"- (\S+)", blk))
    assert held
    for p in list((SITE / "public").glob("*.html")) + list((SITE / "data").glob("*.json")):
        t = p.read_text()
        for h in held:
            assert h not in t, (p.name, "held-out task name")
