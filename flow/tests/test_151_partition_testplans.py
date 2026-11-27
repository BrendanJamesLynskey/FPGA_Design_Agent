"""Brief 151: every name in the three partitioning entries' testplans resolves: a test function in the named file, a formal task in
the entry's .sby files, a seeded fault in faults.yaml. No simulator needed."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENTRIES = ["pipe_reg", "credit_chan", "axi_reg_slice", "sg_dma"]


def plan(e):
    return yaml.safe_load((ROOT / "ip_lib" / e / "verif" / "testplan.yaml").read_text())


@pytest.mark.parametrize("e", ENTRIES)
def test_plan_names_resolve(e):
    p = plan(e)
    faults = {f["name"] for f in yaml.safe_load((ROOT / "ip_lib" / e / "faults.yaml").read_text())["faults"]}
    sby = ""
    for f in (ROOT / "ip_lib" / e / "formal").glob("*.sby"):
        sby += f.read_text()
    tasks = set(re.findall(r"(?m)^(\w+) (?:prove|cover|bmc)\s*$", sby))
    used_faults = set()
    ids = [r["id"] for r in p["requirements"]]
    assert len(ids) == len(set(ids))
    for r in p["requirements"]:
        assert r["requirement"].strip(), r
        assert r["tests"] or r["formal"], f"{r['id']} has no test and no formal task"
        for t in r["tests"]:
            path, fn = t.split("::")
            assert re.search(rf"(?m)^def {fn}\(", (ROOT / path).read_text()), t
        for t in r["formal"]:
            assert t in tasks, (r["id"], t)
        for f in r["faults"]:
            assert f in faults, (r["id"], f)
            used_faults.add(f)
    assert used_faults == faults, f"faults not traced to a requirement: {faults - used_faults}"
