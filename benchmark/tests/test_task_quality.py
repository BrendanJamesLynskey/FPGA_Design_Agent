"""Grader and ledger hygiene for every public development task of v1, the course tier and v2 (quality review 12, area 2).

No simulator needed. These checks close gaps the v1 static tests left: v2 tasks had no static test and no CI run, and
nothing compared a mutant's edit, a trap's must_fail names or the committed v2 manifests with the task they describe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from agent.graph.spec_schema import validate
from benchmark.tools import split as S
from benchmark.v2.freeze_v2 import unit as v2_unit

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
V1 = sorted(d for d in (BENCH / "tasks").iterdir() if d.is_dir())
COURSE = sorted(d for d in (BENCH / "course" / "tasks").iterdir() if d.is_dir())
V2 = sorted(d for d in (BENCH / "v2" / "tasks").iterdir() if d.is_dir())
ALL = V1 + COURSE + V2

# A mutant that "dies" because the copy does not compile proves nothing about the tests. Known case, listed for the planner
# (needs a dated amendment of c16_ntt_engine/hidden/mutants.yaml); a new one must fail this test.
KNOWN_BUILD_KILLS = {("c16_ntt_engine", "forward_scaled")}


def _tests_in(task: Path) -> set[str]:
    return set(re.findall(r"async def (test_\w+)", (task / "hidden" / "acceptance.py").read_text()))


@pytest.mark.parametrize("task", ALL, ids=lambda d: d.name)
def test_mutants_and_trap_are_well_formed(task: Path) -> None:
    m = yaml.safe_load((task / "hidden" / "mutants.yaml").read_text())
    names = [x["name"] for x in m["mutants"]]
    assert len(names) >= 3 and len(set(names)) == len(names), "mutant names must be unique"
    rtl = task / "ref" / "rtl"
    for x in m["mutants"]:
        assert x["find"] != x["replace"], f"{x['name']}: the edit changes nothing"
        assert x.get("why"), f"{x['name']}: no reason given"
        assert (rtl / x["file"]).read_text().count(x["find"]) == 1, f"{x['name']}: find must occur once in {x['file']}"
    trap = m.get("trap")
    if trap:
        assert trap["must_fail"], "a trap with an empty must_fail passes whatever the tests do"
        assert set(trap["must_fail"]) <= _tests_in(task), f"must_fail names a test acceptance.py does not define: {trap['must_fail']}"
        for e in trap["edits"]:
            assert e["find"] != e["replace"] and (rtl / e["file"]).read_text().count(e["find"]) == 1


def test_no_new_mutant_is_killed_only_by_a_build_failure() -> None:
    seen = set()
    for f in sorted(BENCH.rglob("results/**/*__icarus.json")):
        r = json.loads(f.read_text())
        for x in r.get("mutants", []):
            if x["killed"] and not x["built"]:
                seen.add((r["task"], x["name"]))
    assert seen <= KNOWN_BUILD_KILLS, f"mutants that die by not compiling: {sorted(seen - KNOWN_BUILD_KILLS)}"


@pytest.mark.parametrize("task", V2, ids=lambda d: d.name)
def test_v2_task_well_formed(task: Path) -> None:
    assert (task / "spec.md").read_text().strip()
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    assert validate(spec) == [], validate(spec)
    assert spec["name"] == task.name and spec["top"] == f"{task.name}_top"
    bench = yaml.safe_load((task / "hidden" / "bench.yaml").read_text())
    assert bench["toplevel"] == spec["top"] and len(bench.get("phrases") or []) >= 3
    text = " ".join((task / "spec.md").read_text().split()).lower()
    for ph in bench["phrases"]:
        assert " ".join(ph.split()).lower() in text, f"phrase not verbatim in spec.md: {ph!r}"
    assert (task / "hidden" / "model.py").exists() and list((task / "ref" / "rtl").glob("*.sv"))


def _manifest_path(task: Path) -> Path:
    return BENCH / "v2" / "manifests" / f"{task.name}.json"


@pytest.mark.parametrize("task", V2, ids=lambda d: d.name)
def test_v2_manifest_matches_the_task_and_the_ledger(task: Path) -> None:
    """A published v2 task is exactly what was frozen: its files hash to the manifest, and the manifest's SHA-256 is the one
    the ledger recorded at submit and draw (so the task cannot change after its draw without a test failing)."""
    mp = _manifest_path(task)
    rec = json.loads(mp.read_text())["units"][0]
    now = v2_unit(task)
    assert rec["id"] == task.name and rec["file_hashes"] == now["file_hashes"] and rec["digest"] == now["digest"], \
        f"{task.name} differs from its freeze manifest"
    msha = hashlib.sha256(mp.read_bytes()).hexdigest()
    dev = {d["task"]: d["manifest"] for e in S.read_ledger() if e["kind"] == "draw" for d in e["dev"]}
    assert dev.get(task.name) == msha, f"{task.name}: manifest SHA-256 is not the one in the ledger's draw entry"


def test_public_v2_tasks_are_exactly_the_ledger_development_tasks() -> None:
    dev = {d["task"] for e in S.read_ledger() if e["kind"] == "draw" for d in e["dev"]}
    assert {d.name for d in V2} == dev, "benchmark/v2/tasks must hold the development tasks the ledger names, and no others"
    assert {p.stem for p in (BENCH / "v2" / "manifests").glob("*.json")} == dev


def test_ledger_only_grows_against_the_base_commit() -> None:
    """verify_ledger checks the chain, but a whole ledger rewritten with recomputed hashes passes it. Compare with the
    pull-request base (PR_BASE_SHA in CI) or origin/main: every earlier line must be unchanged."""
    base = os.environ.get("PR_BASE_SHA") or "origin/main"
    r = subprocess.run(["git", "show", f"{base}:benchmark/v2/ledger.jsonl"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"no ledger at {base} in this checkout")
    old = r.stdout.splitlines()
    new = (BENCH / "v2" / "ledger.jsonl").read_text().splitlines()
    if os.environ.get("GITHUB_EVENT_NAME") in ("push", "schedule"):
        pytest.skip("main compares against itself")
    assert new[:len(old)] == old, "an earlier ledger line was changed, removed or reordered"
