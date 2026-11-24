"""Formal checks of the radix-4 square-root RTL (brief 139c): SymbiYosys with the slang front end. Each variant against the characterisation
root^2 + rem = x, rem <= 2 root (unbounded); the radix-4 pipeline against arith/isqrt's restoring pipeline (a different algorithm, written
for the same specification: unbounded); seeded faults the proof must catch (bounded)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.isqrt import model as I
from arith.sqrt_r4 import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "sqrt_r4_fv.sv"
FV_ISQRT = D / "formal" / "sqrt_r4_vs_isqrt_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
ISQRT_RTL = sorted((D.parent / "isqrt" / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "sqrt_r4_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, top: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run(top, files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" if engine == "pdr" else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_equals_the_characterisation_unbounded() -> None:
    sim.need("sby")
    cases = [(0, w, 1) for w in (6, 7, 8, 10, 12)] + [(1, w, p) for w, p in ((6, 1), (8, 2), (9, 1), (10, 2), (12, 3), (14, 2))]
    for v, w, p in cases:
        r = job("reference", f"{M.VARIANTS[v]} W={w} PIPE={p}", "sqrt_r4_fv", RTL + [FV], {"VARIANT": v, "W": w, "PIPE": p, "LAT": M.latency(v, w, p)}, "pdr", 40)
        assert r["status"] == "PASS", (v, w, p, r)
    _flush()


def test_radix4_pipeline_agrees_with_the_radix2_pipeline_of_isqrt() -> None:
    sim.need("sby")
    for w, pa, pb in ((8, 1, 1), (10, 2, 2), (12, 1, 3)):
        r = job("pair", f"sqrt_r4 pipe vs isqrt restoring_pipe W={w} PIPE={pa}/{pb}", "sqrt_r4_vs_isqrt_fv", RTL + ISQRT_RTL + [FV_ISQRT],
                {"W": w, "PIPE_A": pa, "PIPE_B": pb, "LAT_A": M.latency(1, w, pa), "LAT_B": I.latency(1, w, pb)}, "pdr", 40)
        assert r["status"] == "PASS", (w, pa, pb, r)
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M03", "M05", "M08", "M14", "M17")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        r = job("mutant", m["id"], "sqrt_r4_fv", files, {"VARIANT": c["variant"], "W": c["w"], "PIPE": c["pipe"], "LAT": M.latency(c["variant"], c["w"], c["pipe"])}, "bmc", 16)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
