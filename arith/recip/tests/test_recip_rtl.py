"""The reciprocal RTL against its model (brief 139c): lint, every input at small widths, random and edge inputs at large widths, latency, and the
seeded-mutant check. Needs Icarus and Verilator."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.recip import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_recip.sv"
RECORD: dict = {"cases": []}


def run(var: int, w: int, a: int, count: int | None, gap: int = 20, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, a, var, count, seed)
    r = sim.run_stream("tb_recip", RTL, {"VARIANT": var, "W": w, "A": a}, vin, vexp, w, w + 1, M.latency(var), gap_pct=gap, seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": M.VARIANTS[var], "w": w, "a": a, "vectors": len(vin), "gap_pct": gap, "exhaustive": count is None, "latency": M.latency(var), "pass": sim.ok(r)})
    return r


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "recip_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    bad = []
    for v in M.VARIANTS:
        for w, a in ((8, 3), (10, 4), (16, 7), (24, 9), (32, 10)):
            ok, log = sim.lint("recip_sel", RTL, {"VARIANT": v, "W": w, "A": a})
            if not ok:
                bad.append((M.VARIANTS[v], w, a, log[:300]))
    assert not bad, bad


def test_every_input_at_small_widths() -> None:
    """Every normalised b at W = 8 to 14 with several A (2 to W - 2 at W = 8 and 9; three values above), every variant, with input gaps; value, order and latency."""
    for v in M.VARIANTS:
        for w in range(8, 15):
            for a in (range(2, w - 1) if w <= 9 else (3, w // 2, w - 3)):
                r = run(v, w, a, None)
                assert sim.ok(r) and r["checked"] == 1 << (w - 1), (M.VARIANTS[v], w, a, r)
    _flush()


def test_random_and_boundary_large_widths() -> None:
    """3000 inputs per case at W = 16, 20, 24 and 32: random and the boundaries of the seed table's intervals."""
    for v in M.VARIANTS:
        for w, a in ((16, 7), (16, 4), (20, 8), (24, 9), (32, 10)):
            r = run(v, w, a, 3000, seed=w * 10 + a)
            assert sim.ok(r), (M.VARIANTS[v], w, a, r)
    _flush()


def test_latency_is_the_formula_and_throughput_one_per_clock() -> None:
    for v in M.VARIANTS:
        r = run(v, 10, 4, None, gap=0)                    # back to back: one result per clock, every result at the stated latency
        assert sim.ok(r), (v, r)
    _flush()


def _mutant_cfg(cfg: dict) -> dict:
    v, w, a = cfg["variant"], cfg["w"], cfg["a"]
    vin, vexp = M.stream(w, a, v, None)
    return {"params": {"VARIANT": v, "W": w, "A": a}, "vin": vin, "vexp": vexp, "in_w": w, "out_w": w + 1, "lat": M.latency(v)}


def test_seeded_mutants_are_all_killed() -> None:
    res = mutants.run_all(D, "tb_recip", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 12 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
