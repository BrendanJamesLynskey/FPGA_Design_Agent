"""The leading-zero count and normaliser RTL against its model (brief 139b): lint, exhaustive small widths, random large widths, latency
at every pipeline depth, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.lzc_norm import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_lzc_norm.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, pipe: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, count, seed)
    r = sim.run_stream("tb_lzc_norm", RTL, {"VARIANT": var, "W": w, "PIPE": pipe}, vin, vexp, w, w + M.lw(w), M.latency(var, w, pipe), gap_pct=gap,
                       seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "pipe": pipe, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None,
                            "latency": M.latency(var, w, pipe), "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "lzc_norm_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w in (2, 3, 8, 13, 16, 32):
            for p in ((1, 2, 40) if v == 2 else (1,)):
                ok, log = sim.lint("lznorm_sel", RTL, {"VARIANT": v, "W": w, "PIPE": p})
                if not ok:
                    bad.append((M.VARIANTS[v], w, p, log[:300]))
    assert not bad, bad


def test_exhaustive_small_widths() -> None:
    """Every input at W = 2 to 16 (powers of two and not), every variant, with gaps; count, normalised word, order and latency checked."""
    for v in M.VARIANTS:
        for w in range(2, 17):
            pipe = max(1, M.k_stages(w) // 2)
            r = run(v, w, pipe, None)
            assert sim.ok(r) and r["checked"] == 1 << w, (M.VARIANTS[v], w, pipe, r)
    _flush()


def test_random_large_widths() -> None:
    """3000 values per case at W = 24, 32, 33, 48, 64 and 100 (inputs of every magnitude, so every count is common)."""
    for v in M.VARIANTS:
        for w in (24, 32, 33, 48, 64, 100):
            r = run(v, w, 2, 3000, seed=w)
            assert sim.ok(r), (M.VARIANTS[v], w, r)
    _flush()


def test_latency_matches_the_formula_at_every_pipeline_depth() -> None:
    for w in (9, 16):
        for p in range(1, M.k_stages(w) + 2):
            r = run(2, w, p, None, gap=0)                 # PIPE beyond K is one combinational block and one register
            assert sim.ok(r), (w, p, r)
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, p = cfg["variant"], cfg["w"], cfg["pipe"]
    vin, vexp = M.stream(w)
    return {"params": {"VARIANT": v, "W": w, "PIPE": p}, "vin": vin, "vexp": vexp, "in_w": w, "out_w": w + M.lw(w), "lat": M.latency(v, w, p)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_lzc_norm", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 12 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
