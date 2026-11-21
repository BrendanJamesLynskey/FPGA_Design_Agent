"""The square-root RTL against its model (brief 139b): lint, exhaustive small widths, random and near-square large widths, latency at
every pipeline depth, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.isqrt import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_isqrt.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, pipe: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, count, seed)
    r = sim.run_stream("tb_isqrt", RTL, {"VARIANT": var, "W": w, "PIPE": pipe}, vin, vexp, w, 2 * M.rw(w) + 1, M.latency(var, w, pipe), gap_pct=gap,
                       seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "pipe": pipe, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None,
                            "latency": M.latency(var, w, pipe), "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "isqrt_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w in (3, 4, 8, 13, 32):
            for p in ((1,) if v == 0 else (1, 3, 40)):
                ok, log = sim.lint("isqrt_sel", RTL, {"VARIANT": v, "W": w, "PIPE": p})
                if not ok:
                    bad.append((M.VARIANTS[v], w, p, log[:300]))
    assert not bad, bad


def test_exhaustive_small_widths() -> None:
    """Every radicand at W = 3 to 16 (odd and even), every variant, with gaps; the root, the remainder, the order and the latency are checked."""
    for v in M.VARIANTS:
        for w in range(3, 17):
            pipe = 1 if v == 0 else max(1, M.rw(w) // 2)
            r = run(v, w, pipe, None)
            assert sim.ok(r) and r["checked"] == 1 << w, (M.VARIANTS[v], w, pipe, r)
    _flush()


def test_random_and_near_square_large_widths() -> None:
    """3000 values per case at W = 24, 31, 32, 48 and 64, with values on and next to perfect squares (remainders 0 and 2*root)."""
    for v in M.VARIANTS:
        for w in (24, 31, 32, 48, 64):
            pipe = 1 if v == 0 else (3 if w % 2 else 4)
            r = run(v, w, pipe, 3000, seed=w)
            assert sim.ok(r), (M.VARIANTS[v], w, pipe, r)
    _flush()


def test_latency_matches_the_formula_at_every_pipeline_depth() -> None:
    for v in (1, 2):
        for p in range(1, 7):
            r = run(v, 11, p, None, gap=0)                # RW = 6: PIPE 1 to 6 (every stage count)
            assert sim.ok(r), (M.VARIANTS[v], p, r)
    assert sim.ok(run(0, 11, 1, None, gap=0))
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, p = cfg["variant"], cfg["w"], cfg["pipe"]
    vin, vexp = M.stream(w)
    return {"params": {"VARIANT": v, "W": w, "PIPE": p}, "vin": vin, "vexp": vexp, "in_w": w, "out_w": 2 * M.rw(w) + 1, "lat": M.latency(v, w, p)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_isqrt", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 12 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
