"""Formal checks of the leading-zero / normaliser RTL (brief 139b): SymbiYosys with the slang front end, harness formal/lzc_norm_fv.sv. Each
variant against the characterisation of the count and the normalised word; variant pairs (including the tree against the priority loop, which
simulation cannot tell apart); seeded faults the proof must catch."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.lzc_norm import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "lzc_norm_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "lzc_norm_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("lzc_norm_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" if engine == "pdr" else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_equals_the_characterisation_unbounded() -> None:
    sim.need("sby")
    cases = [(0, 6, 1), (0, 8, 1), (0, 11, 1), (1, 6, 1), (1, 8, 1), (3, 6, 1), (3, 9, 1)] + [(2, w, p) for w, p in ((5, 1), (8, 1), (8, 2), (9, 2), (12, 3), (8, 3))]
    for v, w, p in cases:
        r = job("reference", f"{M.VARIANTS[v]} W={w} PIPE={p}", RTL + [FV], {"VARIANT": v, "W": w, "PIPE": p, "LAT": M.latency(v, w, p)}, "pdr", 30)
        assert r["status"] == "PASS", (v, w, p, r)
    _flush()


def test_variants_agree_with_each_other() -> None:
    """Tree against loop (same latency 1: a simulation cannot distinguish them), tree against one-block stagewise, two-stage tree against two-group stagewise."""
    sim.need("sby")
    pairs = [(0, 1, 1, 1, 8), (0, 1, 1, 1, 11), (0, 2, 1, 3, 8), (3, 2, 1, 2, 8), (3, 2, 1, 3, 12)]
    for a, b, pa, pb, w in pairs:
        assert M.latency(a, w, pa) == M.latency(b, w, pb)
        r = job("pair", f"{M.VARIANTS[a]} vs {M.VARIANTS[b]} W={w} PIPE_B={pb}", RTL + [FV],
                {"VARIANT": a, "VARIANT_B": b, "W": w, "PIPE": pa, "PIPE_B": pb, "LAT": M.latency(a, w, pa), "REF": 0}, "pdr", 30)
        assert r["status"] == "PASS", (a, b, w, r)
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M04", "M08", "M10", "M12", "M14")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        r = job("mutant", m["id"], files, {"VARIANT": c["variant"], "W": c["w"], "PIPE": c["pipe"], "LAT": M.latency(c["variant"], c["w"], c["pipe"])}, "bmc", 12)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
