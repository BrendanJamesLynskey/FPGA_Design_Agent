"""Benchmark v1 checks that need no simulator (CI python job): every public task and pool spec is well formed, the
split and the manifest verify, the pool does not resemble the benchmark."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent.graph.spec_schema import validate

BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
TASKS = sorted(d for d in (BENCH / "tasks").iterdir() if d.is_dir())
POOL = sorted(d for d in (BENCH / "pool").iterdir() if d.is_dir()) if (BENCH / "pool").exists() else []


@pytest.mark.parametrize("task", TASKS + POOL, ids=lambda d: d.name)
def test_task_well_formed(task: Path) -> None:
    assert (task / "spec.md").read_text().strip()
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    assert validate(spec) == [], validate(spec)
    assert spec["name"] == task.name and spec["top"] == f"{task.name}_top"
    bench = yaml.safe_load((task / "hidden" / "bench.yaml").read_text())
    assert bench["toplevel"] and len(bench.get("phrases") or []) >= 3
    text = " ".join((task / "spec.md").read_text().split()).lower()
    for ph in bench["phrases"]:
        assert " ".join(ph.split()).lower() in text, f"phrase not verbatim in spec.md: {ph!r}"
    assert (task / "hidden" / "model.py").exists()
    assert (task / "hidden" / f"{bench.get('module', 'acceptance')}.py").exists()


@pytest.mark.parametrize("task", TASKS, ids=lambda d: d.name)
def test_task_has_reference_and_mutants(task: Path) -> None:
    assert list((task / "ref" / "rtl").glob("*.sv"))
    m = yaml.safe_load((task / "hidden" / "mutants.yaml").read_text())
    assert len(m["mutants"]) >= 3
    for e in m["mutants"] + (m.get("trap") or {}).get("edits", []):
        f = task / "ref" / "rtl" / e["file"]
        assert f.read_text().count(e["find"]) == 1, f"{e['file']}: {e['find']!r} must occur once"
    assert (task / "hidden" / "selfcheck.py").exists()


def test_split_is_reproducible() -> None:
    from benchmark.tools.split import draw
    s = yaml.safe_load((BENCH / "split.yaml").read_text())
    ids = [i for t in s["tiers"].values() for i in t["held_out"] + t["dev"]]
    again = draw(ids, s["seed"])
    for t, v in s["tiers"].items():
        assert again["tiers"][t]["held_out"] == v["held_out"]
    public = {d.name for d in TASKS}
    held = {i for t in s["tiers"].values() for i in t["held_out"]}
    assert not public & held, f"held-out tasks in the public repo: {public & held}"
    assert public == {i for t in s["tiers"].values() for i in t["dev"]}


def test_manifest_verifies() -> None:
    r = subprocess.run([sys.executable, str(BENCH / "tools" / "freeze.py"), "verify"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not POOL, reason="no pool")
def test_pool_does_not_resemble_benchmark() -> None:
    from benchmark.tools.similarity import cmd_specs
    r = cmd_specs([BENCH / "pool"], [BENCH / "tasks"], 0.45)
    assert r["pass"], r["pairs"][:3]
