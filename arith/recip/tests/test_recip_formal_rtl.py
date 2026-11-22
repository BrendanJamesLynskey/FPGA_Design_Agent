"""Formal checks of the reciprocal RTL (brief 139c): SymbiYosys with the slang front end, harness formal/recip_fv.sv. Each variant against the
error characterisation (two products, no shared code) by k-induction: the datapath is a feed-forward pipeline, so an induction depth above the latency is an
unbounded proof for all input sequences from reset; seeded faults the proof must catch (bounded model checking)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.recip import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "recip_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}

# (variant, W, A): the bound used is the spec's: table |e| <= 2**(W-A-1) + 1/2; nr1 0 <= e < 2**(W-2A-2) + 3/2; nr2 0 <= e < 2**(W-4A-4) + 3/2.
CASES = [(0, 8, 3), (0, 10, 5), (1, 8, 3), (1, 10, 4), (1, 12, 5), (2, 8, 3), (2, 10, 4), (2, 12, 5)]


def bound_params(v: int, w: int, a: int) -> dict:
    """The spec's bound as DEN, UP_NUM, LO_NUM, ONE_SIDED for the harness (e < UP_NUM / DEN)."""
    if v == 0:
        return {"DEN": 2, "UP_NUM": (1 << (w - a)) + 1, "LO_NUM": (1 << (w - a)) + 2, "ONE_SIDED": 0}
    p = 2 * a + 2 if v == 1 else 4 * a + 4
    if w >= p:
        return {"DEN": 4, "UP_NUM": 4 * (1 << (w - p)) + 6, "LO_NUM": 0, "ONE_SIDED": 1}
    k = p - w                                                  # 2**(W-p) = 2**-k: e < (1 + 3 * 2**(k-1)) / 2**k
    return {"DEN": 1 << k, "UP_NUM": 1 + 3 * (1 << (k - 1)), "LO_NUM": 0, "ONE_SIDED": 1}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "recip_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("recip_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" + (" (k-induction, depth %d)" % depth if engine == "kind" else "") if engine in ("pdr", "kind")
                                     else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_meets_its_error_bound_for_all_input_sequences() -> None:
    sim.need("sby")
    for v, w, a in CASES:
        r = job("reference", f"{M.VARIANTS[v]} W={w} A={a}", RTL + [FV], {"VARIANT": v, "W": w, "A": a, "LAT": M.latency(v), **bound_params(v, w, a)}, "kind", M.latency(v) + 3)
        assert r["status"] == "PASS", (v, w, a, r)
    _flush()


def test_a_bound_that_is_too_tight_is_refuted() -> None:
    """The harness is not vacuous: state an upper bound of 1 ulp for nr1 at W = 8 (measured maximum 1.556 ulp) and the check fails."""
    sim.need("sby")
    p = {"VARIANT": 1, "W": 8, "A": 3, "LAT": M.latency(1), "DEN": 4, "UP_NUM": 4, "LO_NUM": 0, "ONE_SIDED": 1}      # e < 1 ulp is false (max 1.556)
    r = job("mutant", "BOUND: nr1 W=8 A=3 against a bound of 1 ulp", RTL + [FV], p, "bmc", M.latency(1) + 3)
    assert r["status"] == "FAIL", r
    RECORD["jobs"][-1]["claim"] = "counterexample found (a bound below the measured maximum is refuted)"
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M04", "M05", "M06", "M07", "M11")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        v, w, a = c["variant"], c["w"], c["a"]
        r = job("mutant", m["id"], files, {"VARIANT": v, "W": w, "A": a, "LAT": M.latency(v), **bound_params(v, w, a)}, "bmc", M.latency(v) + 3)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
