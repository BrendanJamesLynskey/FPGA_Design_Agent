"""The shell fingerprint, the v2 ledger's shell_freeze and amend entries, and the run_task name-collision guard (brief 15).

No simulator needed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchmark.tools import run_task
from benchmark.tools import shell_freeze as SF
from benchmark.tools import split as S

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
RECORDS = [BENCH / "GRADER_DEPS.json", BENCH / "course" / "GRADER_DEPS.json"]


def _copy_shell(tmp_path: Path) -> Path:
    dst = tmp_path / "frozen"
    shutil.copytree(ROOT / "shell", dst / "shell", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst


@pytest.mark.parametrize("rec", RECORDS, ids=lambda p: p.parent.name + "/" + p.name)
def test_recorded_shell_is_the_current_shell(rec: Path) -> None:
    r = json.loads(rec.read_text())
    assert SF.verify_record(r, None) == [], "shell/ differs from the fingerprint recorded in " + str(rec.relative_to(ROOT))
    assert r["shell_sha256"] == SF.fingerprint()


def test_v1_course_and_v2_record_the_same_shell() -> None:
    hashes = {json.loads(p.read_text())["shell_sha256"] for p in RECORDS}
    e = S.latest_shell_freeze(S.read_ledger())
    assert e is not None and S.verify_shell() == []
    assert hashes == {e["shell_sha256"]}, "the three records disagree; record a new shell freeze in all of them"


def test_file_list_covers_what_the_graders_import() -> None:
    names = set(SF.files())
    assert {"shell/host/protocol.py", "shell/tests/uart_bfm.py"} <= names
    assert {f"shell/rtl/{p.name}" for p in (ROOT / "shell" / "rtl").glob("*.sv")} <= names
    # every shell module that benchmark code imports is in the fingerprint
    imports: set[tuple[str, ...]] = set()
    for f in list((BENCH / "lib").glob("*.py")) + list((BENCH / "tools").glob("*.py")) + list(BENCH.glob("**/hidden/*.py")):
        for line in f.read_text().splitlines():
            m = re.match(r"\s*(?:from (shell[\w.]*) import (\w+)|import (shell[\w.]*))", line)
            if m:
                imports.add(tuple(x for x in m.groups() if x))
    assert imports, "found no shell imports: the scan is broken"
    for imp in imports:
        mods = [imp[0] + "." + imp[1], imp[0]] if len(imp) == 2 else [imp[0]]       # "from a.b import c": a.b.c, else the module a.b itself
        assert any(r in names for m in mods for r in (m.replace(".", "/") + ".py", m.replace(".", "/") + "/__init__.py")), \
            f"{imp} is imported by the benchmark but its file is not in the shell fingerprint"


def test_a_changed_shell_file_is_noticed_and_a_frozen_copy_is_accepted(tmp_path: Path) -> None:
    rec = json.loads(RECORDS[0].read_text())
    frozen = _copy_shell(tmp_path)
    assert SF.verify_record(rec, frozen) == [], "an untouched copy of shell/ must verify"
    with (frozen / "shell" / "rtl" / "uart_rx.sv").open("a") as f:
        f.write("// edit\n")
    bad = SF.verify_record(rec, frozen)
    assert bad and "uart_rx.sv" in bad[0]
    # a pass on the real tree is unaffected by what happens in the copy
    assert SF.verify_record(rec, None) == []


def test_an_added_or_removed_shell_file_is_noticed(tmp_path: Path) -> None:
    rec = json.loads(RECORDS[0].read_text())
    frozen = _copy_shell(tmp_path)
    (frozen / "shell" / "rtl" / "extra.sv").write_text("module extra; endmodule\n")
    assert any("extra.sv" in x for x in SF.verify_record(rec, frozen))
    (frozen / "shell" / "rtl" / "extra.sv").unlink()
    (frozen / "shell" / "host" / "protocol.py").unlink()
    assert any("protocol.py" in x for x in SF.verify_record(rec, frozen))


def test_freeze_verify_fails_on_a_different_shell_unless_a_frozen_copy_is_given(tmp_path: Path) -> None:
    frozen = _copy_shell(tmp_path)
    (frozen / "shell" / "tests" / "uart_bfm.py").write_text((frozen / "shell" / "tests" / "uart_bfm.py").read_text() + "\n# edit\n")
    for tool in (BENCH / "tools" / "freeze.py", BENCH / "course" / "tools" / "freeze.py"):
        r = subprocess.run([sys.executable, str(tool), "verify", "--grader-shell", str(frozen)], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 1 and "uart_bfm.py" in r.stdout, r.stdout + r.stderr
        ok = subprocess.run([sys.executable, str(tool), "verify", "--grader-shell", str(_copy_shell(tmp_path / tool.parent.parent.name))],
                            cwd=ROOT, capture_output=True, text=True)
        assert ok.returncode == 0, ok.stdout + ok.stderr


def test_split_verify_checks_the_shell_too(tmp_path: Path) -> None:
    frozen = _copy_shell(tmp_path)
    (frozen / "shell" / "rtl" / "sync2.sv").write_text((frozen / "shell" / "rtl" / "sync2.sv").read_text() + "\n// edit\n")
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "split.py"), "verify", "--grader-shell", str(frozen)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "sync2.sv" in r.stdout
    assert S.verify_shell(grader_shell=None) == []


def test_a_ledger_without_a_shell_freeze_fails_verify_shell(tmp_path: Path) -> None:
    led = tmp_path / "l.jsonl"
    assert S.verify_shell(S.read_ledger(led)) == ["no shell_freeze entry in the ledger"]


def test_shell_freeze_entry_is_chained_and_its_file_list_must_match_its_hash(tmp_path: Path) -> None:
    led = tmp_path / "l.jsonl"
    e = S.shell_freeze("test", path=led)
    assert S.verify_ledger(led, {}) == [] and S.verify_shell(S.read_ledger(led)) == []
    lines = led.read_text().splitlines()
    bad = json.loads(lines[0])
    bad["shell_sha256"] = "0" * 64
    led.write_text(json.dumps(bad, sort_keys=True) + "\n")
    problems = S.verify_ledger(led, {})
    assert any("hash" in p for p in problems), problems
    assert e["shell_sha256"] == SF.fingerprint()


def _seed_dev_task(led: Path, priv: Path) -> None:
    seeds = {"A": {"T1": 7}}
    out = [S.submit("zedboard", "A", "T1", S.hashlib.sha256(f"m{i}".encode()).hexdigest(), f"task_A_{i}", seeds=seeds, path=led,
                    private_dir=priv) for i in range(3)]
    assert out[-1][1] is not None


def test_amend_is_chained_old_must_match_and_only_development_tasks(tmp_path: Path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    seeds = {"A": {"T1": 7}}
    _seed_dev_task(led, priv)
    dev = [d for e in S.read_ledger(led) if e["kind"] == "draw" for d in e["dev"]]
    t, first = dev[0]["task"], dev[0]["manifest"]
    new1, new2 = "a" * 64, "b" * 64
    a1 = S.amend(t, new1, "spec gap", digest="d1", path=led)
    assert a1["old_manifest"] == first and S.current_manifests(S.read_ledger(led))[t] == new1
    a2 = S.amend(t, new2, "second", digest="d2", path=led)
    assert a2["old_manifest"] == new1                       # the chain, not the draw's hash
    assert S.verify_ledger(led, seeds) == []
    with pytest.raises(SystemExit):
        S.amend(t, new2, "again", digest="d2", path=led)    # already at this hash
    with pytest.raises(SystemExit):
        S.amend("not_a_task", new1, "x", digest="d", path=led)
    with pytest.raises(SystemExit):
        S.amend(t, "c" * 64, " ", digest="d", path=led)     # a reason is required
    # a forged amendment (old hash not the current one) fails verify
    forged = json.loads(led.read_text().splitlines()[-1])
    forged.pop("hash")
    forged["old_manifest"] = "e" * 64
    forged["seq"] += 1
    forged["prev"] = S.read_ledger(led)[-1]["hash"]
    forged["new_manifest"] = "f" * 64
    forged["hash"] = S.entry_hash(forged["prev"], forged)
    with led.open("a") as f:
        f.write(json.dumps(forged, sort_keys=True) + "\n")
    assert any("current manifest" in p for p in S.verify_ledger(led, seeds))


def test_the_amend_entry_never_names_a_held_out_task(tmp_path: Path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    _seed_dev_task(led, priv)
    held = next(e["held_out"]["manifest"] for e in S.read_ledger(led) if e["kind"] == "draw")
    with pytest.raises(SystemExit):
        S.amend("task_A_9", "a" * 64, "no such dev task", digest="d", path=led)
    assert held not in S.current_manifests(S.read_ledger(led)).values()


def test_run_task_refuses_a_file_that_shares_a_name_with_a_shell_file(tmp_path: Path) -> None:
    task = BENCH / "tasks" / "t1_bcd_updown"
    rtl = tmp_path / "rtl"
    shutil.copytree(task / "ref" / "rtl", rtl)
    assert run_task.sources(task, rtl)                                   # the reference is fine
    (rtl / "sync2.sv").write_text("module sync2; endmodule\n")
    with pytest.raises(ValueError, match="sync2.sv"):
        run_task.sources(task, rtl)
    if shutil.which("iverilog"):                                          # the Python CI job has no simulator
        r = run_task.run(task, rtl, tag="collision", build_root=tmp_path / "b")
        assert r["pass"] is False and "sync2.sv" in r["error"] and not r["built"]


def test_no_reference_design_collides_with_the_shell() -> None:
    shell_names = {p.name for p in (ROOT / "shell" / "rtl").glob("*.sv")}
    for d in list((BENCH / "tasks").glob("*/ref/rtl")) + list((BENCH / "course" / "tasks").glob("*/ref/rtl")) + \
            list((BENCH / "v2" / "tasks").glob("*/ref/rtl")):
        assert not shell_names & {p.name for p in d.iterdir()}, d


def test_grader_shell_env_var_selects_the_compiled_shell(tmp_path: Path, monkeypatch) -> None:
    frozen = _copy_shell(tmp_path)
    monkeypatch.setattr(run_task, "SHELL_ROOT", frozen)
    task = BENCH / "tasks" / "t1_bcd_updown"
    srcs = run_task.sources(task, task / "ref" / "rtl")
    assert any(str(frozen) in str(s) for s in srcs) and not any(str(ROOT / "shell") in str(s) for s in srcs)
