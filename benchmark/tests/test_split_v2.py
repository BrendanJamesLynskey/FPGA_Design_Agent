"""Benchmark v2 split tool (brief 10 B0): the draw is deterministic, the ledger is append-only, v1 splits unchanged."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from benchmark.tools import split as S

BENCH = Path(__file__).resolve().parents[1]
SEEDS = {"zedboard": {"T1": 7}, "kr260": {"T1": 9}}


def _fill(path: Path, n: int, board="zedboard", tier="T1", priv=None) -> list[dict]:
    return [S.assign(board, tier, f"t_{board}_{i}", seeds=SEEDS, path=path, private_dir=priv) for i in range(n)]


def test_draw_is_deterministic_and_a_third(tmp_path) -> None:
    a = [S.draw_v2(7, "zedboard", "T1", i) for i in range(30)]
    assert a == [S.draw_v2(7, "zedboard", "T1", i) for i in range(30)]
    assert a.count("held_out") == 10                       # exactly one per block of three
    for b in range(10):
        assert a[3 * b:3 * b + 3].count("held_out") == 1
    assert a != [S.draw_v2(8, "zedboard", "T1", i) for i in range(30)]       # the seed matters
    assert a != [S.draw_v2(7, "kr260", "T1", i) for i in range(30)]          # so does the cell
    e1 = _fill(tmp_path / "a.jsonl", 9, priv=tmp_path / "pa")
    e2 = _fill(tmp_path / "b.jsonl", 9, priv=tmp_path / "pb")
    assert [x["assignment"] for x in e1] == [x["assignment"] for x in e2] == a[:9]


def test_held_out_entries_carry_no_task_id(tmp_path) -> None:
    led = tmp_path / "l.jsonl"
    es = _fill(led, 6, priv=tmp_path / "p")
    text = led.read_text()
    priv = [json.loads(x) for x in (tmp_path / "p" / "v2_private.jsonl").read_text().splitlines()]
    assert len(priv) == sum(e["assignment"] == "held_out" for e in es) == 2
    for r in priv:
        assert r["task"] not in text
        assert S.commitment(r["board"], r["tier"], r["task"], r["nonce"]) == r["commit"]
    assert not S.verify_ledger(led, SEEDS)
    held_first = next(i for i in range(6) if S.draw_v2(9, "kr260", "T1", i) == "held_out")
    for i in range(held_first):                            # dev draws before the first held-out slot need no private dir
        S.assign("kr260", "T1", f"d{i}", seeds=SEEDS, path=tmp_path / "n.jsonl")
    with pytest.raises(SystemExit):                        # a held-out draw without a private place is refused
        S.assign("kr260", "T1", "x", seeds=SEEDS, path=tmp_path / "n.jsonl")


def test_ledger_is_append_only_and_tamper_evident(tmp_path) -> None:
    led = tmp_path / "l.jsonl"
    _fill(led, 4, priv=tmp_path / "p")
    before = led.read_text()
    S.move_dev("t1_combo_lock", "seen", path=led)
    after = led.read_text()
    assert after.startswith(before) and after != before    # growth only appends
    assert not S.verify_ledger(led, SEEDS)
    lines = after.splitlines()
    for flip in range(len(lines)):                          # editing any line breaks the chain
        t = [json.loads(x) for x in lines]
        t[flip]["assignment" if "assignment" in t[flip] else "reason"] = "held_out" if t[flip].get("assignment") == "dev" else "edited"
        led.write_text("\n".join(json.dumps(x, sort_keys=True) for x in t) + "\n")
        assert S.verify_ledger(led, SEEDS), f"edit of line {flip} not detected"
    led.write_text("\n".join(lines[:1] + lines[2:]) + "\n")  # dropping or reordering a line is detected
    assert S.verify_ledger(led, SEEDS)


def test_a_task_cannot_be_drawn_twice_or_without_a_seed(tmp_path) -> None:
    led = tmp_path / "l.jsonl"
    S.assign("zedboard", "T1", "dup", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    with pytest.raises(SystemExit):
        S.assign("zedboard", "T1", "dup", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    with pytest.raises(SystemExit):
        S.assign("zedboard", "T9", "x", seeds=SEEDS, path=led, private_dir=tmp_path / "p")
    S.move_dev("a", "r", path=led)
    with pytest.raises(SystemExit):
        S.move_dev("a", "r", path=led)


def test_committed_ledger_and_seen_five() -> None:
    assert not S.verify_ledger()
    moved = {e["task"] for e in S.read_ledger() if e["kind"] == "move"}
    assert moved == set(S.SEEN) and len(moved) == 5
    eff = S.effective()
    held = {i for v in eff.values() for i in v["held_out"]}
    dev = {i for v in eff.values() for i in v["dev"]}
    assert not moved & held and moved <= dev


def test_v1_splits_are_unchanged() -> None:
    s = yaml.safe_load((BENCH / "split.yaml").read_text())
    ids = [i for t in s["tiers"].values() for i in t["held_out"] + t["dev"]]
    again = S.draw(ids, s["seed"])                           # the v1 draw still gives the v1 split
    for t, v in s["tiers"].items():
        assert again["tiers"][t]["held_out"] == v["held_out"] and again["tiers"][t]["dev"] == v["dev"]
    assert "t1_combo_lock" in s["tiers"]["T1"]["held_out"]
    m = json.loads((BENCH / "MANIFEST.json").read_text())
    assert hashlib.sha256((BENCH / "split.yaml").read_bytes()).hexdigest() == m["split_sha256"]
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "freeze.py"), "verify"], cwd=BENCH.parent,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for t in ("T1", "T2"):                                   # the old cli still draws the same split
        assert len(s["tiers"][t]["held_out"]) == round(s["tiers"][t]["n"] / 3)


def test_seeds_published_for_every_board_and_tier() -> None:
    seeds = S.load_seeds()
    assert {"nexys_a7_100t", "zedboard", "kr260"} <= set(seeds)
    flat = [v for b in seeds.values() for v in b.values()]
    assert len(flat) == len(set(flat))                       # one seed per cell, none reused
