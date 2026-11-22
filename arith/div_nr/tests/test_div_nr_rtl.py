"""The reciprocal-multiply divider RTL against its model (brief 139c): lint, every pair at small widths, random and edge pairs at large widths, latency at every
iteration count, and the seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.div_nr import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_div_nr.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, a: int, it: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, a, it, var, count, seed)
    lat = M.latency(var, it)
    r = sim.run_stream("tb_div_nr", RTL, {"VARIANT": var, "W": w, "A": a, "IT": it}, vin, vexp, 2 * w, w, lat, gap_pct=gap, seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "a": a, "it": it, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None, "latency": lat, "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "div_nr_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w, a, it in ((8, 3, 1), (10, 4, 2), (16, 7, 2), (16, 7, 3), (24, 9, 2), (32, 10, 1)):
            ok, log = sim.lint("div_nr_sel", RTL, {"VARIANT": v, "W": w, "A": a, "IT": it})
            if not ok:
                bad.append((M.VARIANTS[v], w, a, it, log[:300]))
    assert not bad, bad


def test_every_pair_at_small_widths() -> None:
    """Every pair of normalised operands at W = 8 (A = 2 to 6, IT = 1 to 3) and W = 9 (A = 4, IT = 2), both variants, with input gaps: value, order and latency."""
    for v in M.VARIANTS:
        for a in range(2, 7):
            for it in (1, 2, 3):
                r = run(v, 8, a, it, None)
                assert sim.ok(r) and r["checked"] == 1 << 14, (M.VARIANTS[v], 8, a, it, r)
        r = run(v, 9, 4, 2, None)
        assert sim.ok(r) and r["checked"] == 1 << 16, (M.VARIANTS[v], r)
    _flush()


def test_random_and_edge_large_widths() -> None:
    """4000 pairs per case at W = 12, 16, 20, 24 and 32, with the extremes of both operands."""
    for v in M.VARIANTS:
        for w, a, it in ((12, 5, 2), (16, 7, 2), (16, 7, 1), (16, 5, 3), (20, 8, 2), (24, 9, 2), (32, 10, 2)):
            r = run(v, w, a, it, 4000, seed=w * 10 + a)
            assert sim.ok(r), (M.VARIANTS[v], w, a, it, r)
    _flush()


def test_latency_matches_the_formula_at_every_iteration_count() -> None:
    for v in M.VARIANTS:
        for it in (1, 2, 3, 4):
            r = run(v, 8, 3, it, 3000, gap=0)             # back to back: one result per clock, every result at the stated latency
            assert sim.ok(r), (M.VARIANTS[v], it, r)
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, a, it = cfg["variant"], cfg["w"], cfg["a"], cfg["it"]
    vin, vexp = M.stream(w, a, it, v, None)
    return {"params": {"VARIANT": v, "W": w, "A": a, "IT": it}, "vin": vin, "vexp": vexp, "in_w": 2 * w, "out_w": w, "lat": M.latency(v, it)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_div_nr", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 14 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
