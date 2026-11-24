"""The rounding and saturation RTL against its model (brief 139b): lint, exhaustive over x at small widths for a grid of (S, W_OUT, mode,
saturation), random and tie-heavy values at large widths, latency, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.fxp_round import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_fxp_round.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, s: int, wo: int, mode: int, sat: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, s, wo, mode, sat, count, seed)
    r = sim.run_stream("tb_fxp_round", RTL, {"VARIANT": var, "W_IN": w, "S": s, "W_OUT": wo, "MODE": mode, "SAT": sat}, vin, vexp, w, wo, M.latency(var),
                       gap_pct=gap, seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w_in": w, "s": s, "w_out": wo, "mode": M.MODES[mode], "sat": sat, "vectors": len(vin),
                            "exhaustive": count is None, "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "fxp_round_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    """Verilator -Wall --lint-only for every variant over the corner configurations: S = 0, S = 1, S = W_IN - 1, W_OUT 2, narrower, equal and wider than the rounded value."""
    bad = []
    for v in M.VARIANTS:
        for w, s, wo in ((16, 4, 12), (8, 0, 8), (8, 1, 7), (8, 7, 2), (9, 3, 3), (12, 5, 12), (8, 2, 12)):
            for mode in range(3):
                for sat in (0, 1):
                    ok, log = sim.lint("fxp_round_sel", RTL, {"VARIANT": v, "W_IN": w, "S": s, "W_OUT": wo, "MODE": mode, "SAT": sat})
                    if not ok:
                        bad.append((M.VARIANTS[v], w, s, wo, mode, sat, log[:200]))
    assert not bad, bad[:3]


def test_exhaustive_small_widths() -> None:
    """Every x at W_IN = 5 and 8 for every S, three W_OUT around the rounded width plus W_OUT = 2, three modes, wrap and saturate, three variants."""
    n = 0
    for var in M.VARIANTS:
        for w in (5, 8):
            for s in range(w):
                for wo in sorted({2, max(2, w - s - 1), max(2, w - s), w - s + 1 if w - s + 1 >= 2 else 2, w - s + 3}):
                    for mode in range(3):
                        for sat in (0, 1):
                            r = run(var, w, s, wo, mode, sat, None)
                            assert sim.ok(r), (M.VARIANTS[var], w, s, wo, mode, sat, r)
                            n += 1
    assert n == 954
    _flush()


def test_random_and_tie_heavy_large_widths() -> None:
    """3000 values per configuration (edge values, random, and values whose low S bits are exactly a tie) at W_IN = 16, 24, 32, 48."""
    import random
    rng = random.Random(5)
    for var in M.VARIANTS:
        for w in (16, 24, 32, 48):
            for _ in range(6):
                s = rng.randint(0, w - 1)
                wo = rng.choice([2, 8, max(2, w - s), w - s + 1, w])
                mode, sat = rng.randint(0, 2), rng.randint(0, 1)
                r = run(var, w, s, wo, mode, sat, 3000, seed=w + s)
                assert sim.ok(r), (M.VARIANTS[var], w, s, wo, mode, sat, r)
    _flush()


def test_latency_one_clock_for_fold_and_inc_two_for_the_two_stage() -> None:
    """The stream harness measures each result's latency and fails on any difference from model.latency (1, 1, 2)."""
    assert [M.latency(v) for v in M.VARIANTS] == [1, 1, 2]
    for var in M.VARIANTS:
        r = run(var, 6, 2, 5, 2, 1, None, gap=0)
        assert sim.ok(r) and r["lat_errors"] == 0, r
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, s, wo, mode, sat = (cfg[k] for k in ("variant", "w", "s", "w_out", "mode", "sat"))
    vin, vexp = M.stream(w, s, wo, mode, sat)
    return {"params": {"VARIANT": v, "W_IN": w, "S": s, "W_OUT": wo, "MODE": mode, "SAT": sat}, "vin": vin, "vexp": vexp, "in_w": w, "out_w": wo, "lat": M.latency(v)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_fxp_round", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 10 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
