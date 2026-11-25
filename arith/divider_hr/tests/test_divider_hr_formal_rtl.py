"""Formal checks of the high-radix divider RTL (brief 139c): SymbiYosys with the slang front end.
  lemma      the step lemmas L1 to L5 of formal/divider_hr_lemma_fv.sv for ALL inputs at a fixed width (combinational, complete), which with the induction on
             the number of digit steps (the same for every K) is the correctness argument of the recurrence;
  reference  each variant against the characterisation a * 4**K = quo * b + rem, 0 <= rem < b (formal/divider_hr_fv.sv), unbounded (abc pdr) at W = 7, K = 1
             (a larger K does not finish: the nonlinear relation between the quotient register and the remainder is not found by abc pdr), and bounded at W = 7, K = 3;
  pair       the carry-save and the carry-propagate iterative variants against each other (unbounded);
  mutant     seeded faults the proofs must catch."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.divider_hr import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "divider_hr_fv.sv"
LEMMA = D / "formal" / "divider_hr_lemma_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "divider_hr_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def claim(engine: str, depth: int, status: str) -> str:
    if status != "PASS":
        return status
    return {"pdr": "proved for all input sequences", "comb": "proved for all inputs (combinational lemma: a depth-1 check is complete)"}.get(engine, f"bounded: no counterexample within {depth} cycles")


def job(kind: str, name: str, top: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run(top, files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"], "claim": claim(engine, depth, r["status"])})
    return r


def test_step_lemmas_hold_for_all_inputs() -> None:
    sim.need("sby")
    for w in (7, 8, 9, 10, 12, 16):
        r = job("lemma", f"L1-L5 at W={w}", "divider_hr_lemma_fv", RTL + [LEMMA], {"W": w, "QW": 9 if w < 10 else 13}, "comb", 1)
        assert r["status"] == "PASS", (w, r)
    _flush()


def test_each_variant_equals_the_characterisation_unbounded_at_k1() -> None:
    sim.need("sby")
    for v in M.VARIANTS:
        r = job("reference", f"{M.VARIANTS[v]} W=7 K=1", "divider_hr_fv", RTL + [FV], {"VARIANT": v, "W": 7, "K": 1, "PIPE": 1, "LAT": M.latency(v, 7, 1, 1)}, "pdr", 40)
        assert r["status"] == "PASS", (v, r)
    _flush()


def test_each_variant_equals_the_characterisation_bounded_at_k3() -> None:
    sim.need("sby")
    for v, p in ((0, 1), (1, 1), (2, 2)):
        lat = M.latency(v, 7, 3, p)
        r = job("reference", f"{M.VARIANTS[v]} W=7 K=3 (bounded)", "divider_hr_fv", RTL + [FV], {"VARIANT": v, "W": 7, "K": 3, "PIPE": p, "LAT": lat}, "bmc", 2 * lat + 4)
        assert r["status"] == "PASS", (v, r)
    _flush()


def test_carry_save_and_carry_propagate_agree() -> None:
    sim.need("sby")
    r = job("pair", "srt4_iter vs srt4_cpa W=7 K=1", "divider_hr_fv", RTL + [FV], {"VARIANT": 0, "VARIANT_B": 1, "W": 7, "K": 1, "LAT": M.latency(0, 7, 1), "REF": 0}, "pdr", 40)
    assert r["status"] == "PASS", r
    r = job("pair", "srt4_iter vs srt4_cpa W=7 K=3 (bounded)", "divider_hr_fv", RTL + [FV], {"VARIANT": 0, "VARIANT_B": 1, "W": 7, "K": 3, "LAT": M.latency(0, 7, 3), "REF": 0}, "bmc", 2 * M.latency(0, 7, 3) + 4)
    assert r["status"] == "PASS", r
    _flush()


LEMMA_FAULTS = ("M05", "M07", "M08", "M13", "M16", "M26")          # datapath faults: the step lemmas refute them
DUT_FAULTS = ("M20", "M32")                                         # control faults: the characterisation refutes them (bounded)


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = {m["id"]: m for m in yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]}
    for mid in LEMMA_FAULTS:
        m = ms[mid]
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [LEMMA]
        r = job("mutant", mid, "divider_hr_lemma_fv", files, {"W": 8, "QW": 9}, "comb", 1)
        assert r["status"] == "FAIL", (mid, r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (a step lemma refutes the fault)"
    for mid in DUT_FAULTS:
        m = ms[mid]
        c = m["config"]
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        lat = M.latency(c["variant"], 7, 3, c["pipe"])
        r = job("mutant", mid, "divider_hr_fv", files, {"VARIANT": c["variant"], "W": 7, "K": 3, "PIPE": c["pipe"], "LAT": lat}, "bmc", lat + 4)
        assert r["status"] == "FAIL", (mid, r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
