"""``freeze.py refreeze --private-manifest`` (v1 and course): only the named public/shared entries change.

The private manifest here is synthetic, built in a temporary directory from the public manifest plus invented
held-out and probe entries. No benchmark_private/ content is read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmark.course.tools import freeze as CF
from benchmark.tools import freeze as F

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
STALE = "0" * 64
HELD = {"id": "held_fake", "kind": "task", "tier": "T1", "split": "held_out", "where": "private", "files": 2,
        "digest": "1" * 64, "file_hashes": {"spec.md": "2" * 64, "hidden/t.py": "3" * 64}}
PROBE = {"id": "probe_fake", "kind": "probe", "where": "private", "files": 1, "digest": "4" * 64,
         "file_hashes": {"spec.md": "5" * 64}}

TIERS = {
    "v1": (F, BENCH / "MANIFEST.json", "shared:tools/run_task.py", "t1_bcd_updown"),
    "course": (CF, BENCH / "course" / "MANIFEST.json", "shared:benchmark/tools/run_task.py", "c16_ntt_engine"),
}


def _public_units(mod) -> dict:
    us = mod.units(None)
    us = us[0] if isinstance(us, tuple) else us
    return {u["id"]: u for u in us if u["where"] == "public"}


def _synthetic(tier: str, tmp: Path, stale: list[str]) -> tuple[Path, str]:
    """Public manifest entries with full file lists, the named ones given a stale digest, plus held-out and probe entries."""
    mod, pub, _, _ = TIERS[tier]
    m = json.loads(pub.read_text())
    for r in m["units"]:
        if r["where"] == "private":
            r["file_hashes"] = {"spec.md": "6" * 64}
        if r["id"] in stale:
            r["digest"] = STALE
            r["files"] = 1
            r["file_hashes"] = {"old.txt": "7" * 64}
    m["units"] = [HELD] + m["units"] + [PROBE]
    p = tmp / "MANIFEST_full.json"
    text = json.dumps(m, indent=1) + "\n"
    p.write_text(text)
    return p, text


def _expect(mod, ids: list[str]) -> dict:
    pu = _public_units(mod)
    return {i: mod.digest(mod.files_of(pu[i]["path"])) for i in ids}


@pytest.mark.parametrize("tier", TIERS)
def test_only_named_units_change(tier: str, tmp_path: Path, capsys) -> None:
    mod, _, shared, task = TIERS[tier]
    ids = [task, shared]
    p, before = _synthetic(tier, tmp_path, ids + ["x"])
    rc = F.refreeze_private(ids, _public_units(mod), p)
    assert rc == 0
    out = capsys.readouterr().out
    want = _expect(mod, ids)
    for i in ids:
        assert STALE in out and want[i] in out, "old and new digests are printed"
    a, b = json.loads(before), json.loads(p.read_text())
    assert [r["id"] for r in a["units"]] == [r["id"] for r in b["units"]]
    for ra, rb in zip(a["units"], b["units"]):
        if rb["id"] in ids:
            assert rb["digest"] == want[rb["id"]] != ra["digest"]
            f = mod.files_of(_public_units(mod)[rb["id"]]["path"])
            assert rb["file_hashes"] == f and rb["files"] == len(f)
        else:
            assert ra == rb
    # every non-named entry serialises identically, so the rewrite touched nothing else
    keep = lambda d: [json.dumps(r, indent=1) for r in d["units"] if r["id"] not in ids]  # noqa: E731
    assert keep(a) == keep(b)
    assert {k: v for k, v in a.items() if k != "units"} == {k: v for k, v in b.items() if k != "units"}


@pytest.mark.parametrize("tier", TIERS)
def test_digest_matches_public_refreeze(tier: str, tmp_path: Path) -> None:
    """The private digest equals what the public refreeze records for the same unit."""
    mod, pub, shared, task = TIERS[tier]
    p, _ = _synthetic(tier, tmp_path, [task])
    F.refreeze_private([task], _public_units(mod), p)
    got = next(r for r in json.loads(p.read_text())["units"] if r["id"] == task)
    assert got["digest"] == next(r for r in json.loads(pub.read_text())["units"] if r["id"] == task)["digest"]


@pytest.mark.parametrize("tier", TIERS)
def test_dry_run_writes_nothing(tier: str, tmp_path: Path, capsys) -> None:
    mod, _, _, task = TIERS[tier]
    p, before = _synthetic(tier, tmp_path, [task])
    assert F.refreeze_private([task], _public_units(mod), p, dry_run=True) == 0
    assert p.read_text() == before
    out = capsys.readouterr().out
    assert STALE in out and "dry run" in out


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("bad", ["held_fake", "probe_fake", "no_such_unit", "shared:not/a/shared.py"])
def test_refuses_non_public_ids(tier: str, bad: str, tmp_path: Path) -> None:
    mod, _, _, task = TIERS[tier]
    p, before = _synthetic(tier, tmp_path, [task])
    with pytest.raises(SystemExit) as e:
        F.refreeze_private([task, bad], _public_units(mod), p)
    assert bad in str(e.value)
    assert p.read_text() == before, "nothing is written when any id is refused (the good one included)"


def test_refuses_private_record_even_if_id_is_public(tmp_path: Path) -> None:
    """A manifest entry marked private is never touched, even if a public unit has the same id."""
    mod, _, _, task = TIERS["v1"]
    p, _ = _synthetic("v1", tmp_path, [task])
    m = json.loads(p.read_text())
    next(r for r in m["units"] if r["id"] == task)["where"] = "private"
    p.write_text(json.dumps(m, indent=1) + "\n")
    before = p.read_text()
    with pytest.raises(SystemExit):
        F.refreeze_private([task], _public_units(mod), p)
    assert p.read_text() == before


def test_refuses_noncanonical_manifest_and_empty_or_duplicate(tmp_path: Path) -> None:
    mod, _, _, task = TIERS["v1"]
    p, text = _synthetic("v1", tmp_path, [task])
    with pytest.raises(SystemExit):
        F.refreeze_private([], _public_units(mod), p)
    with pytest.raises(SystemExit):
        F.refreeze_private([task, task], _public_units(mod), p)
    p.write_text(text.replace('{\n "benchmark"', '{"benchmark"', 1) if '{\n "benchmark"' in text else text.rstrip() + "\n\n")
    with pytest.raises(SystemExit):
        F.refreeze_private([task], _public_units(mod), p)


@pytest.mark.parametrize("script,tier", [("benchmark/tools/freeze.py", "v1"), ("benchmark/course/tools/freeze.py", "course")])
def test_cli(script: str, tier: str, tmp_path: Path) -> None:
    _, _, shared, task = TIERS[tier]
    p, before = _synthetic(tier, tmp_path, [task])
    cmd = [sys.executable, str(ROOT / script), "refreeze", task, shared, "--private-manifest", str(p)]
    r = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and "dry run" in r.stdout and p.read_text() == before, r.stderr
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and p.read_text() != before, r.stderr
    r = subprocess.run([sys.executable, str(ROOT / script), "refreeze", "held_fake", "--private-manifest", str(p)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0
