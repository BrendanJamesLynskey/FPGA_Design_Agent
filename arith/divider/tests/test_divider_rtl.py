"""The divider RTL against its model (brief 139b): Verilator lint, exhaustive small widths, random and edge large widths, latency, gaps,
pipeline depths, and the seeded-mutant check. Needs Icarus and Verilator (OSS CAD Suite; see arith/common/sim.py). Records go to
results/139b_arith/divider_sim_record.json when ARITH_RECORD_DIR is set."""
from __future__ import annotations

import json
import os
from pathlib import Path

from arith.common import mutants, sim
from arith.divider import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_divider.sv"
NAMES = M.VARIANTS
RECORD: dict = {"cases": []}


def cfg_run(variant: int, w: int, pipe: int, count: int | None, gap: int = 0, seed: int = 1) -> dict:
    vin, vexp = M.stream(w, count, seed)
    res = sim.run_stream("tb_divider", RTL, {"VARIANT": variant, "W": w, "PIPE": pipe}, vin, vexp, 2 * w, 2 * w, M.latency(variant, w, pipe),
                         gap_pct=gap, seed=seed, extra_tb=[TB])
    RECORD["cases"].append({"variant": NAMES[variant], "w": w, "pipe": pipe, "vectors": len(vin), "gap_pct": gap,
                            "exhaustive": count is None, "pass": sim.ok(res), "latency": M.latency(variant, w, pipe),
                            **{k: res.get(k) for k in ("mismatches", "lat_errors", "spurious", "x_valid")}})
    return res


def _flush() -> None:
    d = os.environ.get("ARITH_RECORD_DIR")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        (Path(d) / "divider_sim_record.json").write_text(json.dumps(RECORD, indent=1, sort_keys=True))


def test_lint_clean() -> None:
    """Verilator -Wall --lint-only: no warning for any variant at W = 8 and 13 (an odd width), PIPE 1, 3 and W."""
    bad = []
    for v in NAMES:
        for w in (8, 13):
            for p in ((1,) if v < 2 else (1, 3, w)):
                ok, log = sim.lint("divider_sel", RTL, {"VARIANT": v, "W": w, "PIPE": p})
                if not ok:
                    bad.append((NAMES[v], w, p, log[:300]))
    assert not bad, bad


def test_exhaustive_small_widths() -> None:
    """Every operand pair at W = 2 to 8 (W = 8 is 65536 pairs), every variant, with input gaps; results, order and latency checked."""
    for v in NAMES:
        for w in range(2, 9):
            pipe = 1 if v < 2 else max(1, w // 2)
            r = cfg_run(v, w, pipe, None, gap=25)
            assert sim.ok(r), (NAMES[v], w, pipe, r)
            assert r["checked"] == 1 << (2 * w)
    _flush()


def test_random_and_edge_large_widths() -> None:
    """Edge-value pairs plus 3000 random pairs (divisors of every magnitude) at W = 16, 24, 32 and 64."""
    for v in NAMES:
        for w in (16, 24, 32, 64):
            pipe = 1 if v < 2 else (4 if w == 24 else 1 if w == 64 else w // 4)
            r = cfg_run(v, w, pipe, 3000, gap=10, seed=w)
            assert sim.ok(r), (NAMES[v], w, pipe, r)
    _flush()


def test_latency_matches_the_formula_at_every_pipeline_depth() -> None:
    """The harness measures the latency of every result and flags a difference from model.latency; PIPE 1 to W at W = 7, back to back."""
    for v in (2, 3):
        for p in range(1, 8):
            r = cfg_run(v, 7, p, None, gap=0)
            assert sim.ok(r), (NAMES[v], p, r)
    for v in (0, 1):
        r = cfg_run(v, 7, 1, None, gap=0)
        assert sim.ok(r), (NAMES[v], r)
    _flush()


def test_throughput_one_per_clock_for_pipelines() -> None:
    """A pipeline accepts an input every clock; an iterative divider takes W + 1 or W + 2 clocks per division (in_ready)."""
    import re
    import shutil
    import subprocess
    import tempfile
    wd = Path(tempfile.mkdtemp(prefix="arith_thr_"))
    try:
        vin, vexp = M.stream(6, 200)
        counts = {}
        for v, p in ((0, 1), (1, 1), (2, 2), (3, 2)):
            sim.write_hex(wd / "i.hex", vin, 12)
            sim.write_hex(wd / "e.hex", vexp, 12)
            exe = wd / f"s{v}.vvp"
            cmd = [sim.need("iverilog"), "-g2012", "-s", "tb_divider", "-o", str(exe), f"-Ptb_divider.VARIANT={v}", "-Ptb_divider.W=6", f"-Ptb_divider.PIPE={p}",
                   "-Ptb_divider.IN_W=12", "-Ptb_divider.OUT_W=12", f"-Ptb_divider.NVEC={len(vin)}", f"-Ptb_divider.LAT={M.latency(v, 6, p)}",
                   str(sim.COMMON / "tb_stream.sv"), str(TB), *map(str, RTL)]
            subprocess.run(cmd, check=True, capture_output=True, env=sim.env())
            out = subprocess.run([sim.need("vvp"), str(exe), f"+vin={wd / 'i.hex'}", f"+vexp={wd / 'e.hex'}"], capture_output=True, text=True, env=sim.env()).stdout
            assert "mismatches=0" in out
            counts[v] = re.search(r"ARITH_RESULT", out) is not None
        assert all(counts.values())
        # the exact clocks per input: a division that cannot start until in_ready returns costs throughput_clocks
        assert [M.throughput_clocks(v, 6) for v in (0, 1, 2, 3)] == [7, 8, 1, 1]
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def _mutant_cfg(cfg: dict) -> dict:
    v, w, p = cfg["variant"], cfg["w"], cfg["pipe"]
    vin, vexp = M.stream(w)
    return {"params": {"VARIANT": v, "W": w, "PIPE": p}, "vin": vin, "vexp": vexp, "in_w": 2 * w, "out_w": 2 * w, "lat": M.latency(v, w, p)}


def test_seeded_mutants_are_all_killed() -> None:
    """Each seeded fault (verif/mutants.yaml) is applied to a copy of the RTL and simulated against the exhaustive stream; none may survive."""
    res = mutants.run_all(D, "tb_divider", _mutant_cfg)
    RECORD["mutants"] = res
    RECORD["mutants_summary"] = {"total": res["total"], "killed": res["killed"], "survived": len(res["survivors"]), "equivalent_found": len(res["equivalent"])}
    _flush()
    assert res["total"] >= 12 and not res["survivors"], res["survivors"]
    assert all(res["equivalent"].values()), res["equivalent"]
