"""The radix-4 square-root RTL against its model (brief 139c): lint, exhaustive small widths, random and near-square large widths, latency at
every pipeline depth, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.sqrt_r4 import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_sqrt_r4.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, pipe: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, count, seed)
    r = sim.run_stream("tb_sqrt_r4", RTL, {"VARIANT": var, "W": w, "PIPE": pipe}, vin, vexp, w, 2 * M.rw(w) + 1, M.latency(var, w, pipe), gap_pct=gap,
                       seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "pipe": pipe, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None,
                            "latency": M.latency(var, w, pipe), "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "sqrt_r4_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w in (5, 6, 8, 13, 32, 64):
            for p in ((1,) if v == 0 else (1, 2, 40)):
                ok, log = sim.lint("sqrt_r4_sel", RTL, {"VARIANT": v, "W": w, "PIPE": p})
                if not ok:
                    bad.append((M.VARIANTS[v], w, p, log[:300]))
    assert not bad, bad


def test_exhaustive_small_widths() -> None:
    """Every radicand at W = 3 to 16 (odd and even), every variant, with gaps; the root, the remainder, the order and the latency are checked."""
    for v in M.VARIANTS:
        for w in range(5, 17):
            pipe = 1 if v == 0 else max(1, M.steps(w) // 2)
            r = run(v, w, pipe, None)
            assert sim.ok(r) and r["checked"] == 1 << w, (M.VARIANTS[v], w, pipe, r)
    _flush()


def test_random_and_near_square_large_widths() -> None:
    """3000 values per case at W = 24, 31, 32, 48 and 64, with values on and next to perfect squares (remainders 0 and 2*root)."""
    for v in M.VARIANTS:
        for w in (24, 31, 32, 48, 64):
            pipe = 1 if v == 0 else (3 if w % 2 else 2)
            r = run(v, w, pipe, 3000, seed=w)
            assert sim.ok(r), (M.VARIANTS[v], w, pipe, r)
    _flush()


def test_latency_matches_the_formula_at_every_pipeline_depth() -> None:
    for p in range(1, 6):
        r = run(1, 13, p, None, gap=0)                    # RW = 7, RP = 4: PIPE 1 to 5 (every stage count, PIPE above RP behaves as RP)
        assert sim.ok(r), (p, r)
    assert sim.ok(run(0, 13, 1, None, gap=0))
    r = run(1, 24, 3, 600, gap=0)                         # RP = 6, PIPE 3 -> two stages; PIPE 4 -> two stages of 4 and 2 steps
    assert sim.ok(r), r
    assert sim.ok(run(1, 24, 4, 600, gap=0))
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, p = cfg["variant"], cfg["w"], cfg["pipe"]
    vin, vexp = M.stream(w)
    return {"params": {"VARIANT": v, "W": w, "PIPE": p}, "vin": vin, "vexp": vexp, "in_w": w, "out_w": 2 * M.rw(w) + 1, "lat": M.latency(v, w, p)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_sqrt_r4", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 16 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
