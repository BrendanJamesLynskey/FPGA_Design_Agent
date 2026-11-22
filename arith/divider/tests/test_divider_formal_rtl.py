"""Formal checks of the divider RTL (brief 139b): SymbiYosys with the slang front end, harness formal/divider_fv.sv. Each variant against an
independent reference (`/` and `%`), pairs of pipelined variants against each other, and seeded faults the proof must catch. Unbounded where
`abc pdr` closes (stated per job in the record), bounded (BMC, depth given) where a job uses it."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.divider import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "divider_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "divider_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("divider_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" if engine == "pdr" else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_equals_the_reference_unbounded() -> None:
    """P1 (timing) and P2 (value against `/` and `%`) by PDR: restoring and non-restoring, iterative and pipelined (PIPE 1, 2, 3, W), W = 4 and 5, plus W = 6 for the pipelines."""
    sim.need("sby")
    cases = [(0, 4, 1), (0, 5, 1), (1, 4, 1), (1, 5, 1)] + [(v, w, p) for v in (2, 3) for w, p in ((4, 1), (4, 2), (4, 4), (5, 3), (6, 2))]
    for v, w, p in cases:
        r = job("reference", f"{M.VARIANTS[v]} W={w} PIPE={p}", RTL + [FV], {"VARIANT": v, "W": w, "PIPE": p, "LAT": M.latency(v, w, p)}, "pdr", 40)
        assert r["status"] == "PASS", (v, w, p, r)
    _flush()


def test_pipelined_variants_agree_with_each_other() -> None:
    """P3: the restoring and the non-restoring pipeline see the same inputs and produce the same outputs (no reference involved), PDR."""
    sim.need("sby")
    for w, p in ((4, 2), (5, 1), (6, 3)):
        r = job("pair", f"restoring_pipe vs nonrestoring_pipe W={w} PIPE={p}", RTL + [FV],
                {"VARIANT": 2, "VARIANT_B": 3, "W": w, "PIPE": p, "PIPE_B": p, "LAT": M.latency(2, w, p), "REF": 0}, "pdr", 40)
        assert r["status"] == "PASS", (w, p, r)
    _flush()


def test_formal_catches_seeded_faults() -> None:
    """Six of the simulation mutants (one per file) are applied and the same proof must FAIL (BMC finds the counterexample)."""
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M04", "M06", "M09", "M13", "M16")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        r = job("mutant", m["id"], files, {"VARIANT": c["variant"], "W": c["w"] if c["w"] <= 6 else 6, "PIPE": c["pipe"], "LAT": M.latency(c["variant"], min(c["w"], 6), c["pipe"])},
                "bmc", 16)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
