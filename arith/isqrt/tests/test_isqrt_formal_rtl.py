"""Formal checks of the square-root RTL (brief 139b): SymbiYosys with the slang front end, harness formal/isqrt_fv.sv. Each variant against the
characterisation root^2 + rem = x, rem <= 2 root; pairs of pipelined variants against each other; seeded faults the proof must catch."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from arith.common import formal, sim
from arith.isqrt import model as M

D = Path(__file__).resolve().parents[1]
FV = D / "formal" / "isqrt_fv.sv"
RTL = sorted((D / "rtl").glob("*.sv"))
RECORD: dict = {"jobs": []}


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        RECORD["summary"] = formal.summarise(RECORD)
        (Path(d) / "isqrt_formal_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def job(kind: str, name: str, files: list[Path], params: dict, engine: str, depth: int) -> dict:
    r = formal.run("isqrt_fv", files, params, engine, depth)
    RECORD["jobs"].append({"kind": kind, "name": name, "params": params, "engine": engine, "depth": depth, "status": r["status"], "seconds": r["seconds"],
                           "claim": ("proved for all input sequences" if engine == "pdr" else f"bounded: no counterexample within {depth} cycles") if r["status"] == "PASS" else r["status"]})
    return r


def test_each_variant_equals_the_characterisation_unbounded() -> None:
    sim.need("sby")
    cases = [(0, 6, 1), (0, 7, 1)] + [(v, w, p) for v in (1, 2) for w, p in ((6, 1), (7, 2), (8, 4), (9, 3), (10, 5))]
    for v, w, p in cases:
        r = job("reference", f"{M.VARIANTS[v]} W={w} PIPE={p}", RTL + [FV], {"VARIANT": v, "W": w, "PIPE": p, "LAT": M.latency(v, w, p)}, "pdr", 40)
        assert r["status"] == "PASS", (v, w, p, r)
    _flush()


def test_pipelined_variants_agree_with_each_other() -> None:
    sim.need("sby")
    for w, p in ((6, 1), (8, 2), (9, 3)):
        r = job("pair", f"restoring_pipe vs nonrestoring_pipe W={w} PIPE={p}", RTL + [FV],
                {"VARIANT": 1, "VARIANT_B": 2, "W": w, "PIPE": p, "PIPE_B": p, "LAT": M.latency(1, w, p), "REF": 0}, "pdr", 40)
        assert r["status"] == "PASS", (w, p, r)
    _flush()


def test_formal_catches_seeded_faults() -> None:
    sim.need("sby")
    ms = yaml.safe_load((D / "verif" / "mutants.yaml").read_text())["mutants"]
    picked = [m for m in ms if m["id"] in ("M01", "M02", "M05", "M09", "M12", "M14")]
    assert len(picked) == 6
    for m in picked:
        tmp = Path(tempfile.mkdtemp(prefix="arith_fm_"))
        files = formal.with_mutant(D / "rtl", tmp, m["file"], m["find"], m["replace"], m["id"]) + [FV]
        c = m["config"]
        r = job("mutant", m["id"], files, {"VARIANT": c["variant"], "W": c["w"], "PIPE": c["pipe"], "LAT": M.latency(c["variant"], c["w"], c["pipe"])}, "bmc", 16)
        assert r["status"] == "FAIL", (m["id"], r)
        RECORD["jobs"][-1]["claim"] = "counterexample found (the fault is caught)"
    _flush()
