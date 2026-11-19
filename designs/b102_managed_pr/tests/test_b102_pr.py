"""b102_managed_pr: the manifest facts the design depends on (no Vivado here: the placement and build records are in results/102_managed_pr/)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.core import managed as M  # noqa: E402

D = ROOT / "designs" / "b102_managed_pr"


def test_the_manifest_loads_and_the_checkpoint_hash_matches():
    p = M.load(D)
    blk = p.component("blk")
    assert blk.level == "placed_routed" and blk.ownership == "frozen"
    assert M.provenance_gaps(p, blk) == []                        # origin, version, licence, contract and the file's SHA-256


def test_build_yaml_builds_every_component():
    cfg = yaml.safe_load((D / "build.yaml").read_text())
    assert M.build_coverage_problems(M.load(D), cfg) == []
    assert cfg["netlists"] == [{"file": "designs/b102_managed_pr/ext/pcs_unit_p0.dcp", "format": "checkpoint", "cell": "u_blk"}]


def test_the_keepout_contains_the_recorded_footprint_and_the_constraints_respect_it():
    p = M.load(D)
    region = M.slice_rect(p.component("blk").placement["region"])
    footprint = (27, 72, 34, 90)                                  # RECT of results/102_managed_pr/import_check.json
    assert region[0] <= footprint[0] and region[1] <= footprint[1] and footprint[2] <= region[2] and footprint[3] <= region[3]
    M.ManagedPolicy(p).check_xdc("design.xdc", (D / "design.xdc").read_text())      # the committed constraints are inside the rules
