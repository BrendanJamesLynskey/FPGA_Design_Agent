"""The high-radix divider RTL against its model (brief 139c): lint, exhaustive small widths, random and edge large widths, latency at every
pipeline depth, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.divider_hr import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_divider_hr.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, k: int, pipe: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, k, count, seed)
    lat = M.latency(var, w, k, pipe)
    r = sim.run_stream("tb_divider_hr", RTL, {"VARIANT": var, "W": w, "K": k, "PIPE": pipe}, vin, vexp, 2 * w, M.out_width(w, k), lat, gap_pct=gap, seed=seed,
                       extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "k": k, "pipe": pipe, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None,
                            "latency": lat, "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "divider_hr_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w, k in ((7, 1), (8, 4), (16, 8), (24, 13), (32, 16), (64, 32)):
            for p in ((1,) if v < 2 else (1, 3, 40)):
                ok, log = sim.lint("divider_hr_sel", RTL, {"VARIANT": v, "W": w, "K": k, "PIPE": p})
                if not ok:
                    bad.append((M.VARIANTS[v], w, k, p, log[:300]))
    assert not bad, bad


def test_exhaustive_small_widths() -> None:
    """Every pair of normalised operands at W = 7 (K = 1, 3, 4), W = 8 (K = 2, 4, 5) and W = 9 (K = 4, 5), every variant, with input gaps: quotient, remainder, order and latency."""
    for v in M.VARIANTS:
        for w, ks in ((7, (1, 3, 4)), (8, (2, 4, 5)), (9, (4, 5))):
            for k in ks:
                pipe = 1 if v < 2 else max(1, (k + 1) // 2)
                r = run(v, w, k, pipe, None)
                assert sim.ok(r) and r["checked"] == 1 << (2 * (w - 1)), (M.VARIANTS[v], w, k, pipe, r)
    _flush()


def test_random_and_edge_large_widths() -> None:
    """3000 pairs per case at W = 12, 16, 24, 32 and 48 (K = ceil((W-1)/2), one other K each), with ratios close to the digit-selection boundaries 1/2, 2/3, 1, 4/3, 5/3, 2."""
    for v in M.VARIANTS:
        for w, k in ((12, 6), (16, 8), (16, 3), (24, 12), (24, 14), (32, 16), (48, 24)):
            pipe = 1 if v < 2 else (3 if w % 2 else 4)
            r = run(v, w, k, pipe, 3000, seed=w * 100 + k)
            assert sim.ok(r), (M.VARIANTS[v], w, k, pipe, r)
    _flush()


def test_latency_matches_the_formula_at_every_pipeline_depth() -> None:
    for p in range(1, 8):
        r = run(2, 8, 5, p, 2500, gap=0)                  # K + 1 = 6 steps: PIPE 1 to 7 (PIPE above 6 behaves as 6)
        assert sim.ok(r), (p, r)
    for v in (0, 1):
        r = run(v, 8, 5, 1, 2500, gap=0)
        assert sim.ok(r), (v, r)
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, k, p = cfg["variant"], cfg["w"], cfg["k"], cfg["pipe"]
    vin, vexp = M.stream(w, k, None if w <= 8 else 4000, seed=2)
    return {"params": {"VARIANT": v, "W": w, "K": k, "PIPE": p}, "vin": vin, "vexp": vexp, "in_w": 2 * w, "out_w": M.out_width(w, k), "lat": M.latency(v, w, k, p)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_divider_hr", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 20 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
