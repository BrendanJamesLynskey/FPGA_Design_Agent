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
SEEDS = {"A": {"T1": 7, "drill": 5}, "B": {"T1": 9}}


def _m(i: int) -> str:
    return hashlib.sha256(f"manifest-{i}".encode()).hexdigest()


def _fill(path: Path, n: int, domain="A", tier="T1", priv=None, start=0, board="zedboard") -> list:
    return [S.submit(board, domain, tier, _m(start + i), f"task_{domain}_{start + i}", seeds=SEEDS, path=path, private_dir=priv)
            for i in range(n)]


def test_blocks_are_drawn_only_when_complete(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    rs = _fill(led, 2, priv=priv)
    assert [d for _, d in rs] == [None, None]                     # two pending: no draw, no assignment
    assert not any(e["kind"] == "draw" for e in S.read_ledger(led))
    assert len(S.pending(S.read_ledger(led))[("A", "T1")]) == 2
    _, d = S.submit("kr260", "A", "T1", _m(2), "task_A_2", seeds=SEEDS, path=led, private_dir=priv)
    assert d and d["block"] == 0 and len(d["dev"]) == 2 and not S.pending(S.read_ledger(led))
    assert not S.verify_ledger(led, SEEDS)


def test_draw_depends_on_the_manifests_and_is_deterministic(tmp_path) -> None:
    picks = {S.held_index(7, "A", "T1", 0, [_m(i), _m(i + 1), _m(i + 2)]) for i in range(40)}
    assert picks == {0, 1, 2}                                     # the slot varies with the manifests
    ms = [_m(0), _m(1), _m(2)]
    assert S.held_index(7, "A", "T1", 0, ms) == S.held_index(7, "A", "T1", 0, ms[::-1])    # order of submission is irrelevant
    assert S.held_index(7, "A", "T1", 0, ms) == S.held_index(7, "A", "T1", 0, ms)
    assert S.held_index(7, "A", "T1", 1, ms) is not None
    a = _fill(tmp_path / "a.jsonl", 3, priv=tmp_path / "pa")[-1][1]
    b = _fill(tmp_path / "b.jsonl", 3, priv=tmp_path / "pb")[-1][1]
    assert a["held_out"] == b["held_out"]


def test_held_out_never_names_its_task(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    _fill(led, 6, priv=priv)
    text = led.read_text()
    held = [e["held_out"] for e in S.read_ledger(led) if e["kind"] == "draw"]
    assert len(held) == 2 and all("task" not in h for h in held)
    for r in (json.loads(x) for x in (priv / "v2_private.jsonl").read_text().splitlines()):
        assert (r["task"] in text) == (r["manifest"] not in {h["manifest"] for h in held})
        if r["manifest"] in {h["manifest"] for h in held}:
            assert r["task"] not in text
    assert all("task" not in e for e in S.read_ledger(led) if e["kind"] == "submit")


def test_pending_tasks_are_excluded(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    _fill(led, 4, priv=priv)                                      # one block drawn, one task pending
    eff = S.effective(path=led)
    pend = eff["pending"]["A/T1"]
    assert pend == [_m(3)]
    v2 = eff["v2:A/T1"]
    assert _m(3) not in v2["held_out"] and "task_A_3" not in v2["dev"]
    assert len(v2["held_out"]) == 1 and len(v2["dev"]) == 2


def test_per_domain_thirds_are_exact_for_complete_blocks(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    for dom, n in (("A", 12), ("B", 6)):
        _fill(led, n, domain=dom, priv=priv, start=100 * (dom == "B"), board="zedboard" if n == 12 else "kr260")
    eff = S.effective(path=led)
    assert len(eff["v2:A/T1"]["held_out"]) == 4 and len(eff["v2:A/T1"]["dev"]) == 8
    assert len(eff["v2:B/T1"]["held_out"]) == 2 and len(eff["v2:B/T1"]["dev"]) == 4
    assert not S.verify_ledger(led, SEEDS)


def test_ledger_is_append_only_and_tamper_evident(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    _fill(led, 4, priv=priv)
    before = led.read_text()
    S.move_dev("t1_combo_lock", "seen", path=led)
    after = led.read_text()
    assert after.startswith(before) and after != before
    assert not S.verify_ledger(led, SEEDS)
    lines = after.splitlines()
    for flip in range(len(lines)):
        t = [json.loads(x) for x in lines]
        t[flip]["domain" if "domain" in t[flip] else "reason"] = "edited"
        led.write_text("\n".join(json.dumps(x, sort_keys=True) for x in t) + "\n")
        assert S.verify_ledger(led, SEEDS), f"edit of line {flip} not detected"
    led.write_text("\n".join(lines[:1] + lines[2:]) + "\n")
    assert S.verify_ledger(led, SEEDS)


def test_a_task_cannot_be_submitted_twice_or_without_a_seed(tmp_path) -> None:
    led, priv = tmp_path / "l.jsonl", tmp_path / "p"
    S.submit("zedboard", "A", "T1", _m(0), "dup", seeds=SEEDS, path=led, private_dir=priv)
    with pytest.raises(SystemExit):
        S.submit("zedboard", "A", "T1", _m(0), "other", seeds=SEEDS, path=led, private_dir=priv)    # same manifest
    with pytest.raises(SystemExit):
        S.submit("zedboard", "A", "T1", _m(1), "dup", seeds=SEEDS, path=led, private_dir=priv)      # same id
    with pytest.raises(SystemExit):
        S.submit("zedboard", "Z", "T1", _m(2), "x", seeds=SEEDS, path=led, private_dir=priv)        # no seed
    S.move_dev("a", "r", path=led)
    with pytest.raises(SystemExit):
        S.move_dev("a", "r", path=led)


def test_committed_ledger_and_seen_five() -> None:
    assert not S.verify_ledger()
    moved = {e["task"] for e in S.read_ledger() if e["kind"] == "move"}
    assert moved == set(S.SEEN) and len(moved) == 5
    eff = S.effective()
    held = {i for k, v in eff.items() if k != "pending" for i in v["held_out"]}
    dev = {i for k, v in eff.items() if k != "pending" for i in v["dev"]}
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


def test_seeds_published_for_every_domain_and_tier() -> None:
    seeds = S.load_seeds()
    assert sorted(seeds) == list("ABCDEFGHIJKLMNOPQRST")
    assert all(sorted(v) == ["T1", "T2", "T3", "T4", "drill"] for v in seeds.values())
    flat = [v for d in seeds.values() for v in d.values()]
    assert len(flat) == 100 and len(set(flat)) == 100
