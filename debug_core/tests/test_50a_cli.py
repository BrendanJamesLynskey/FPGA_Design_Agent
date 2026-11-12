"""Brief 50A: the no-board 'try it' commands in docs/debug.md run as written (golden captures, structured intent)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = "debug_core/tests/fixtures/golden"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "debug_core", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def test_answer_view_query_and_plan_without_a_board(tmp_path: Path) -> None:
    a = run("answer", f"{GOLD}/t1_count_write/capture.json")
    assert a.returncode == 0 and "count was 0x0003 from cycle -16 to 0, then 0x1234 from cycle 1 to 32." in a.stdout
    v = run("view", f"{GOLD}/t1_pwm_period/capture.json", "-o", str(tmp_path / "view.html"))
    assert v.returncode == 0 and (tmp_path / "view.html").stat().st_size > 10000
    q = run("query", f"{GOLD}/t1_count_write/capture.json", '{"op": "first", "channel": "count", "cmp": "==", "value": "0x1234"}')
    assert q.returncode == 0 and json.loads(q.stdout)["cycle"] == 1
    p = run("plan", "designs/t1_dimmer_counter", "--intent", "debug_core/tests/fixtures/intent_count_write.json",
            "-o", str(tmp_path / "plan.json"))
    assert p.returncode == 0 and "Can be built (probe set" in p.stdout
    assert json.loads((tmp_path / "plan.json").read_text())["probeset"]


def test_the_docs_list_these_commands() -> None:
    doc = (ROOT / "docs" / "debug.md").read_text()
    for cmd in (f"python -m debug_core answer {GOLD}/t1_count_write/capture.json",
                "--intent debug_core/tests/fixtures/intent_count_write.json"):
        assert cmd in doc
