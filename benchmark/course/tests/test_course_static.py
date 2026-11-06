"""Course tier checks that need no simulator (CI python job): every public task is well formed, the split reproduces, the manifest verifies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent.graph.spec_schema import validate

COURSE = Path(__file__).resolve().parents[1]
ROOT = COURSE.parents[1]
TASKS = sorted(d for d in (COURSE / "tasks").iterdir() if d.is_dir())


@pytest.mark.parametrize("task", TASKS, ids=lambda d: d.name)
def test_task_well_formed(task: Path) -> None:
    assert (task / "spec.md").read_text().strip()
    spec = yaml.safe_load((task / "hidden" / "spec.yaml").read_text())
    assert validate(spec) == [], validate(spec)
    assert spec["name"] == task.name and spec["top"] == f"{task.name}_top"
    bench = yaml.safe_load((task / "hidden" / "bench.yaml").read_text())
    assert bench["toplevel"] == spec["top"] and len(bench.get("phrases") or []) >= 3
    text = " ".join((task / "spec.md").read_text().split()).lower()
    for ph in bench["phrases"]:
        assert " ".join(ph.split()).lower() in text, f"phrase not verbatim in spec.md: {ph!r}"
    for f in ("model.py", "acceptance.py", "selfcheck.py", "reference_qor.md", "mutants.yaml"):
        assert (task / "hidden" / f).exists(), f
    assert list((task / "ref" / "rtl").glob("*.sv"))
    assert (task / "ref" / "rtl" / f"{task.name}_top.sv").exists()
    m = yaml.safe_load((task / "hidden" / "mutants.yaml").read_text())
    assert len(m["mutants"]) >= 3
    for e in m["mutants"]:
        assert (task / "ref" / "rtl" / e["file"]).read_text().count(e["find"]) == 1, f"{e['name']}: {e['find']!r} must occur once"


def test_split_is_reproducible_and_public_has_no_held_out() -> None:
    from benchmark.tools.split import draw
    s = yaml.safe_load((COURSE / "split.yaml").read_text())
    ids = [i for t in s["tiers"].values() for i in t["held_out"] + t["dev"]]
    assert len(ids) == 19
    again = draw(ids, s["seed"])
    assert s["seed"] == 20261106
    for t, v in s["tiers"].items():
        assert again["tiers"][t]["held_out"] == v["held_out"]
        assert len(v["held_out"]) == round(v["n"] / 3)
    held = {i for t in s["tiers"].values() for i in t["held_out"]}
    public = {d.name for d in TASKS}
    assert not public & held, f"held-out tasks in the public repo: {public & held}"
    dev = {i for t in s["tiers"].values() for i in t["dev"]}
    assert public <= dev, f"public tasks that are not development tasks: {public - dev}"
    assert dev == public, f"development tasks without a public task or the other way round: {dev ^ public}"
    assert not (COURSE / "PENDING.yaml").exists(), "every split id has a task since course v1.1"


def test_manifest_verifies() -> None:
    r = subprocess.run([sys.executable, str(COURSE / "tools" / "freeze.py"), "verify"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
