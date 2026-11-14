"""The leak guard must not be beaten by cosmetic changes (brief 83), and must pass unrelated tasks."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
sys.path.insert(0, str(BENCH / "tools"))
import leak_norm as N  # noqa: E402

TASKS = sorted((BENCH / "v2" / "tasks").iterdir())


def _guard(secret: Path, target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BENCH / "tools" / "task_leak.py"), "--secret", str(secret), "--target", str(target),
                           "--corpus", str(BENCH / "v2" / "tasks"), str(BENCH / "tasks"), *extra],
                          cwd=ROOT, capture_output=True, text=True)


def _dress(text: str) -> str:
    """The cosmetic changes the guard must see through: renamed identifiers, a unique comment on every line."""
    names = sorted(set(re.findall(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b", text)), key=len, reverse=True)
    for i, n in enumerate(names):
        if n in ("always_ff", "always_comb", "posedge", "negedge", "end", "else"):
            continue
        text = re.sub(rf"\b{n}\b", f"zz{i}_q", text)
    return "\n".join(f"{ln}  // note {i} {hash(ln) & 0xffff}" if ln.strip() else ln for i, ln in enumerate(text.splitlines()))


def test_strip_removes_comments_and_strings() -> None:
    assert N.strip_text("a = b; // why\n/* x */ c = \"//no\";", ".sv") == 'a = b; c = "" ;'
    assert "note" not in N.strip_text("x = 1  # note\ns = '#' ", ".py")
    assert N.strip_text("a <= b; -- hi\nC <= '1';", ".vhd") == 'a <= b; c <= "" ;'
    assert N.code_tokens("wire [7:0] foo = 8'hFF; // c", ".sv") == N.code_tokens("wire [7:0] bar = 8'h00; /* d */", ".sv")


def test_comments_and_renames_do_not_change_the_token_stream() -> None:
    src = next(next(TASKS[0].glob("ref/rtl")).glob("*.sv")).read_text()
    assert N.code_tokens(src, ".sv") == N.code_tokens(_dress(src), ".sv")


@pytest.mark.parametrize("variant", ["plain", "dressed"])
def test_a_copied_held_out_snippet_is_caught(tmp_path: Path, variant: str) -> None:
    secret, other = TASKS[0], TASKS[1]
    sec = tmp_path / "sec"
    tgt = tmp_path / "tgt"
    shutil.copytree(secret, sec / secret.name)
    shutil.copytree(other, tgt / other.name)
    rtl = next((tgt / other.name / "ref" / "rtl").glob("*.sv"))
    donor = (secret / "ref" / "rtl" / "bit_count.sv").read_text()
    rtl.write_text(rtl.read_text() + "\n" + (donor if variant == "plain" else _dress(donor)) + "\n")
    r = _guard(sec, tgt)
    assert r.returncode == 1, r.stdout


def test_unrelated_tasks_pass(tmp_path: Path) -> None:
    # tick_gen against bit_count: different domains, built apart
    a = next(t for t in TASKS if t.name.endswith("tick_gen"))
    b = next(t for t in TASKS if t.name.endswith("bit_count"))
    (tmp_path / "s").mkdir()
    (tmp_path / "t").mkdir()
    shutil.copytree(a, tmp_path / "s" / a.name)
    shutil.copytree(b, tmp_path / "t" / b.name)
    r = _guard(tmp_path / "s", tmp_path / "t")
    assert r.returncode == 0, r.stdout


def test_guard_refuses_no_tasks(tmp_path: Path) -> None:
    r = _guard(tmp_path, tmp_path)
    assert r.returncode != 0 and "no secret or no target" in r.stderr


def test_site_guard_sees_through_trailing_comments(tmp_path: Path) -> None:
    secret = next((BENCH / "v2" / "tasks").glob("*/ref/rtl/bit_count.sv"))
    priv = tmp_path / "priv" / "v2" / "t1"
    (priv / "ref").mkdir(parents=True)
    (priv / "spec.md").write_text("x")
    (priv / "ref" / "bit_count.sv").write_text(secret.read_text())
    tgt = tmp_path / "tgt"
    tgt.mkdir()
    (tgt / "copy.sv").write_text("\n".join(f"{ln}  // unique {i}" for i, ln in enumerate(secret.read_text().splitlines())))
    r = subprocess.run([sys.executable, str(ROOT / "site" / "leak_guard.py"), "--private", str(tmp_path / "none"),
                        "--private-v2", str(tmp_path / "priv" / "v2"), str(tgt)], capture_output=True, text=True)
    assert r.returncode == 1 and "LEAK window" in r.stdout, r.stdout


def _leak_into(tmp_path: Path, name: str, content: str, extra_copies: int = 0) -> subprocess.CompletedProcess:
    secret, other = TASKS[0], TASKS[1]
    sec, tgt = tmp_path / "sec", tmp_path / "tgt"
    shutil.copytree(secret, sec / secret.name)
    shutil.copytree(other, tgt / other.name)
    (tgt / other.name / "ref" / "rtl" / name).write_text(content, encoding="latin-1")
    for i in range(extra_copies):                       # padding: the same leak in more tasks under test
        shutil.copytree(tgt / other.name, tgt / f"pad{i}" )
    return _guard(sec, tgt)


def _core() -> str:
    return (TASKS[0] / "ref" / "rtl" / "bit_count.sv").read_text()


@pytest.mark.parametrize("name,wrap", [
    ("c1.sv", lambda t: "/*\n" + t.replace("*/", "* /") + "\n*/"),
    ("c2.sv", lambda t: "\n".join("// " + ln for ln in t.splitlines())),
    ("c3.sv", lambda t: 'string s = "' + t.replace('"', "'").replace("\n", " ") + '";'),
    ("c4.sv.bak", lambda t: t),
    ("c5.svp", lambda t: t),
    ("Makefile", lambda t: t),
    ("c6.sv", lambda t: t + "\n// caf\xe9"),
    ("c7.sv", lambda t: "\n".join(ln + "\n  zz = 1'b0;" for ln in t.splitlines())),
])
def test_hiding_places_are_caught(tmp_path: Path, name: str, wrap) -> None:
    r = _leak_into(tmp_path, name, wrap(_core()))
    assert r.returncode == 1, (name, r.stdout)


def test_a_few_extra_copies_of_a_leak_do_not_exempt_it(tmp_path: Path) -> None:
    assert _leak_into(tmp_path, "c.sv", _core(), extra_copies=2).returncode == 1
