"""Formal checks of the rounding RTL (brief 139b): SymbiYosys with the slang front end, harness formal/fxp_round_fv.sv. Each variant against a
reference written from the definitions with wide signed arithmetic (the RTL folds rounding into a carry; the reference does not), the fold form
against the increment-after form, and seeded faults the proof must catch."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.fxp_round import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "fxp_round_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}
CONFIGS = [(8, 2, 6, 2, 1), (8, 3, 5, 1, 0), (8, 0, 8, 0, 1), (8, 7, 2, 2, 1), (8, 1, 7, 2, 0), (8, 4, 3, 1, 1), (9, 3, 10, 2, 1), (7, 5, 2, 0, 1)]


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "fxp_round_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("fxp_round_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" if engine == "pdr" else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_equals_the_reference_unbounded() -> None:
    sim.need("sby")
    for v in M.VARIANTS:
        for w, s, wo, mode, sat in CONFIGS:
            r = job("reference", f"{M.VARIANTS[v]} W_IN={w} S={s} W_OUT={wo} MODE={mode} SAT={sat}", RTL + [FV],
                    {"VARIANT": v, "W_IN": w, "S": s, "W_OUT": wo, "MODE": mode, "SAT": sat, "LAT": M.latency(v)}, "pdr", 20)
            assert r["status"] == "PASS", (v, w, s, wo, mode, sat, r)
    _flush()


def test_fold_and_inc_variants_agree() -> None:
    """The carry-in fold (variant 0) against the shift-then-increment form (variant 1): same function, different structure."""
    sim.need("sby")
    for w, s, wo, mode, sat in CONFIGS:
        r = job("pair", f"fold vs inc W_IN={w} S={s} W_OUT={wo} MODE={mode} SAT={sat}", RTL + [FV],
                {"VARIANT": 0, "VARIANT_B": 1, "W_IN": w, "S": s, "W_OUT": wo, "MODE": mode, "SAT": sat, "LAT": 1}, "pdr", 20)
        assert r["status"] == "PASS", (w, s, wo, mode, sat, r)
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M02", "M05", "M09", "M10", "M13")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        r = job("mutant", m["id"], files, {"VARIANT": c["variant"], "W_IN": c["w"], "S": c["s"], "W_OUT": c["w_out"], "MODE": c["mode"], "SAT": c["sat"], "LAT": M.latency(c["variant"])},
                "bmc", 8)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
