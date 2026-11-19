"""Brief 96E: the build parameters in every build.yaml of this design against what the design records.

The formal proof of the default path (results/b96c/eqy_default) treats the XPM crossings as wires, so a crossing parameter such as GO_REG is invisible to it (96C follow-up).
This is the structural check that closes that gap: lat_all3's `build.yaml` must set GO_REG exactly as its `variant.json` says, the base must keep the 97C defaults, and no build may set a
parameter the core does not have.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

DESIGN = Path(__file__).resolve().parents[1]


def _bit(v: str) -> int:
    return int(re.search(r"1'b([01])", str(v)).group(1))


def _generics(path: Path) -> dict:
    return {k: _bit(v) for k, v in yaml.safe_load(path.read_text()).get("generics", {}).items() if "'b" in str(v)}


def test_lat_all3_go_reg_matches_variant_json() -> None:
    rec = json.loads((DESIGN / "lat_all3" / "variant.json").read_text())["generics"]
    got = _generics(DESIGN / "lat_all3" / "build.yaml")
    assert got.get("GO_REG") == rec["GO_REG"] == 0
    assert got.get("RATE_MATCH") == rec["RATE_MATCH"] == 0


def test_base_build_keeps_the_97c_defaults() -> None:
    got = _generics(DESIGN / "build.yaml")
    assert got["RATE_MATCH"] == 0 and got.get("GO_REG", 1) == 1 and got.get("RM_OWN", 0) == 0


def test_every_build_sets_only_parameters_the_core_has() -> None:
    top = (DESIGN / "rtl" / "kr260_10g_top.sv").read_text()
    params = set(re.findall(r"parameter\s+(?:bit|logic\s*\[[^\]]*\]|int)\s+(\w+)", top))
    for f in DESIGN.glob("*/build.yaml"):
        for k in _generics(f):
            assert k in params, (f, k)


def test_rm_gp_is_the_own_buffer_on_the_base() -> None:
    got = _generics(DESIGN / "rm_gp" / "build.yaml")
    assert got["RATE_MATCH"] == 1 and got["RM_OWN"] == 1 and got.get("RM_DIRECT", 0) == 0
    assert "rate_match_gp.sv" in (DESIGN / "rm_gp" / "build.yaml").read_text()
    assert "rate_match_gp.xdc" not in (DESIGN / "rm_gp" / "build.yaml").read_text()


def test_rm_gp_direct_is_the_direct_read_variant_with_its_constraint() -> None:
    got = _generics(DESIGN / "rm_gp_direct" / "build.yaml")
    assert got["RATE_MATCH"] == 1 and got["RM_OWN"] == 1 and got["RM_DIRECT"] == 1
    assert "rate_match_gp.xdc" in (DESIGN / "rm_gp_direct" / "build.yaml").read_text()
