"""The scoring-adjacent tools must fail loudly, not report success on missing input (quality review 12, area 2)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from benchmark.tools import split as S

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
SEEDS = {"A": {"T1": 5}}


def _m(i: int) -> str:
    return f"{i:064x}"


def test_bank_grep_refuses_a_missing_bank(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "bank_grep.py"), "--bank", str(tmp_path / "nope"),
                        str(BENCH / "tasks")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "no text files" in r.stderr


def test_bank_grep_flags_a_leaked_phrase(tmp_path: Path) -> None:
    task = next((BENCH / "v2" / "tasks").iterdir())
    import yaml
    ph = yaml.safe_load((task / "hidden" / "bench.yaml").read_text())["phrases"][0]
    bank = tmp_path / "bank"
    bank.mkdir()
    (bank / "note.md").write_text(f"x\n{ph.upper()}\ny")
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "bank_grep.py"), "--bank", str(bank), str(task.parent)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and task.name in r.stdout


def test_similarity_code_refuses_a_missing_corpus(tmp_path: Path) -> None:
    rtl = next((BENCH / "tasks").iterdir()) / "ref" / "rtl"
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "similarity.py"), "code", str(rtl), "--ref", str(tmp_path / "nope")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "no reference fingerprints" in r.stderr


def test_a_block_completing_submit_with_a_wrong_private_dir_writes_nothing(tmp_path: Path) -> None:
    led = tmp_path / "l.jsonl"
    S.submit("b", "A", "T1", _m(0), "t0", seeds=SEEDS, path=led, private_dir=tmp_path / "p1")
    S.submit("b", "A", "T1", _m(1), "t1", seeds=SEEDS, path=led, private_dir=tmp_path / "p1")
    before = led.read_text()
    with pytest.raises(SystemExit):
        S.submit("b", "A", "T1", _m(2), "t2", seeds=SEEDS, path=led, private_dir=tmp_path / "other")
    assert led.read_text() == before, "the ledger was appended although the draw could not be completed"
    e, d = S.submit("b", "A", "T1", _m(2), "t2", seeds=SEEDS, path=led, private_dir=tmp_path / "p1")
    assert d is not None and not S.verify_ledger(led, SEEDS)


def test_move_dev_refuses_a_task_no_split_file_holds_out(tmp_path: Path) -> None:
    led = tmp_path / "l.jsonl"
    with pytest.raises(SystemExit):
        S.move_dev("t1_bcd_updown", "r", path=led)                  # a development task
    with pytest.raises(SystemExit):
        S.move_dev("no_such_task", "r", path=led)
    S.move_dev("t1_breathe_rgb", "r", path=led)                     # a v1 held-out id
    S.move_dev("v2_private_x", "r", path=led, check=False)          # --unlisted
    assert [e["task"] for e in S.read_ledger(led)] == ["t1_breathe_rgb", "v2_private_x"]


def test_verify_ledger_reports_an_unknown_domain_instead_of_crashing(tmp_path: Path) -> None:
    led = tmp_path / "l.jsonl"
    S.submit("b", "A", "T1", _m(0), "t0", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    S.submit("b", "A", "T1", _m(1), "t1", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    S.submit("b", "A", "T1", _m(2), "t2", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    assert not S.verify_ledger(led, SEEDS)
    assert any("no published seed" in b for b in S.verify_ledger(led, {"B": {"T1": 1}}))
