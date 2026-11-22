"""Formal checks of the reciprocal-multiply divider RTL (brief 139c): SymbiYosys with the slang front end, harness formal/div_nr_fv.sv. Each variant against the
error characterisation (two products, no shared code) by k-induction: the datapath is a feed-forward pipeline, so an induction depth above the latency is an
unbounded proof for all input sequences from reset; seeded faults the proof must catch (bounded model checking)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.div_nr import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "div_nr_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}

# (variant, W, A, IT): the bound used is the spec's: Newton 0 <= e < 3/2 + 2**(W - 2**IT * (A+1) + 1); Goldschmidt -1/2 < e < the same.
CASES = [(0, 8, 3, 1), (0, 8, 3, 2), (0, 8, 4, 2), (1, 8, 3, 1), (1, 8, 3, 2), (1, 8, 4, 2)]
FAULT_PICKS = ("M01", "M03", "M05", "M06", "M10", "M12")


def bound_params(v: int, w: int, a: int, it: int) -> dict:
    e0 = w - (1 << it) * (a + 1) + 1                           # e < 3/2 + 2**e0
    if e0 >= 0:
        den, up = 4, 6 + 4 * (1 << e0)
    else:
        k = -e0
        den, up = 1 << k, 3 * (1 << (k - 1)) + 1
    return {"DEN": den, "UP_NUM": up, "LO_NUM": 0 if v == 0 else den // 2}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "div_nr_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("div_nr_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" + (" (k-induction, depth %d)" % depth if engine == "kind" else "") if engine in ("pdr", "kind")
                                     else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_meets_its_error_bound_for_all_input_sequences() -> None:
    sim.need("sby")
    for v, w, a, it in CASES:
        lat = M.latency(v, it)
        r = job("reference", f"{M.VARIANTS[v]} W={w} A={a} IT={it}", RTL + [FV], {"VARIANT": v, "W": w, "A": a, "IT": it, "LAT": lat, **bound_params(v, w, a, it)}, "kind", lat + 3)
        assert r["status"] == "PASS", (v, w, a, it, r)
    _flush()


def test_a_bound_that_is_too_tight_is_refuted() -> None:
    """The harness is not vacuous: state an upper bound of 1 ulp for Newton at W = 8, A = 3, IT = 1 (measured maximum 1.78 ulp) and the check fails."""
    sim.need("sby")
    p = {"VARIANT": 0, "W": 8, "A": 3, "IT": 1, "LAT": M.latency(0, 1), "DEN": 4, "UP_NUM": 4, "LO_NUM": 0}
    r = job("mutant", "BOUND: newton W=8 A=3 IT=1 against an upper bound of 1 ulp", RTL + [FV], p, "bmc", M.latency(0, 1) + 3)
    assert r["status"] == "FAIL", r
    RECORD["jobs"][-1]["claim"] = "counterexample found (a bound below the measured maximum is refuted)"
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = {m["id"]: m for m in yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]}
    for mid in FAULT_PICKS:
        m = ms[mid]
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        v, w, a, it = c["variant"], c["w"], c["a"], c["it"]
        r = job("mutant", mid, files, {"VARIANT": v, "W": w, "A": a, "IT": it, "LAT": M.latency(v, it), **bound_params(v, w, a, it)}, "bmc", M.latency(v, it) + 3)
        assert r["status"] == "FAIL", (mid, r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
