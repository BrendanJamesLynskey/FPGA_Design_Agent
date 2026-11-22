"""Shared plumbing of the arithmetic library (arith brief 139a): spec loading, the one way a variant is simulated, edge-value generation,
and where the OSS CAD Suite is. Nothing here knows an arithmetic function; each function's own model.py and cocotb module do.

    spec = load_spec("adder")                         # arith/adder/spec.yaml
    run_point("adder", "ripple", {"WIDTH": 8}, "exhaustive")   # Icarus + cocotb, raises AssertionError on a mismatch
"""
from __future__ import annotations

import json
import os
import random
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ARITH = ROOT / "arith"
FUNCTIONS = ("adder", "multiplier", "mac", "fp_add", "fp_mul", "fp_fma")
FFT_FUNCTIONS = ("fft_cmul", "fft_twiddle", "fft_reorder", "fft_window", "fft", "fft_real", "fft_axis", "fft_bfp")      # the frequency-domain suite (brief 148): no packaged harness, see arith/README.md
ALL_FUNCTIONS = FUNCTIONS + FFT_FUNCTIONS
PARTS = {"a7": "xc7a100tcsg324-1", "k26": "xck26-sfvc784-2LV-c"}      # the two parts of the brief: Artix-7 (xc7a100t) and Kria K26 (xck26)


def load_spec(fn: str) -> dict:
    return yaml.safe_load((ARITH / fn / "spec.yaml").read_text())


def rtl_files(fn: str, vd: dict) -> list[Path]:
    """The variant's file and the shared files it needs (spec.yaml ``deps``, paths relative to arith/), in the order the simulator and the linter read them."""
    return [ARITH / fn / vd["file"]] + [ARITH / d for d in vd.get("deps", [])]


def latency_of(spec: dict, variant: str, params: dict) -> int:
    """The variant's latency in clocks for a parameter set, from the expression in spec.yaml (e.g. "STAGES")."""
    return int(eval(str(spec["variants"][variant]["latency"]), {"max": max, "min": min}, dict(params)))


def merged_params(spec: dict, variant: str, params: dict) -> dict:
    return {**spec["variants"][variant].get("params", {}), **params}


def oss_bin() -> str:
    """The bin directory of the OSS CAD Suite the repo's CI pins (FDA_OSS_CAD, then ~/.local/opt/oss-cad-suite, then PATH); '' if none."""
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "yosys").exists():
            return str(Path(c) / "bin")
    w = shutil.which("yosys")
    return str(Path(w).parent) if w else ""


def tool(name: str) -> str | None:
    b = oss_bin()
    if b and (Path(b) / name).exists():
        return str(Path(b) / name)
    return shutil.which(name)


def run_point(fn: str, variant: str, params: dict, mode: str, rtl_dir: Path | None = None, seed: int = 1, n: int = 3000,
              build_root: Path | None = None, name: str | None = None, lat: int | None = None) -> None:
    """Simulate one variant at one parameter set with Icarus and the function's cocotb bench; ``mode`` is the cocotb test to run
    ('exhaustive' or 'randomised'). ``rtl_dir`` swaps in a mutated copy of the variant's file (same file name). Raises AssertionError
    when the bench fails (flow/cocotb_run.py)."""
    from flow import cocotb_run
    spec = load_spec(fn)
    v = spec["variants"][variant]
    p = merged_params(spec, variant, params)
    files = rtl_files(fn, v)
    if rtl_dir is not None:                                  # a mutated copy of any one of the variant's files replaces the original of the same name
        files = [Path(rtl_dir) / f.name if (Path(rtl_dir) / f.name).exists() else f for f in files]
    tests = ARITH / fn / "tests"
    tag = name or f"{fn}_{variant}_{mode}{'_lat' + str(lat) if lat is not None else ''}_" + "_".join(f"{k}{x}" for k, x in sorted(p.items()))
    env = {"PYTHONPATH": str(ROOT), "ARITH_PARAMS": json.dumps(p), "ARITH_LAT": str(latency_of(spec, variant, p) if lat is None else lat),
           "ARITH_SEED": str(seed), "ARITH_N": str(n), "ARITH_VARIANT": variant}
    cocotb_run.run(tag, v["module"], files, f"{fn}_cocotb", tests, parameters=p, testcase=mode, extra_env=env, build_root=build_root)


# ---- vectors -----------------------------------------------------------------------------------------------
def edge_values(w: int) -> list[int]:
    """Values of a w-bit field where arithmetic breaks: 0, 1, 2, the largest and smallest signed, all ones, alternating bits, powers of two."""
    m = (1 << w) - 1
    vals = {0, 1, 2 & m, m, (m - 1) & m, 1 << (w - 1), ((1 << (w - 1)) - 1) & m, ((1 << (w - 1)) + 1) & m, 0x5555555555555555 & m, 0xAAAAAAAAAAAAAAAA & m}
    vals |= {(1 << i) & m for i in range(w)} | {((1 << i) - 1) & m for i in range(1, w + 1)}
    return sorted(vals)


def rand_value(rng: random.Random, w: int, edges: list[int]) -> int:
    """A random w-bit value: a third of the draws are an edge value, a third have a random run of ones or zeros (carry chains), the rest uniform."""
    r = rng.random()
    if r < 0.30:
        return rng.choice(edges)
    if r < 0.60:
        lo = rng.randrange(w)
        hi = rng.randrange(lo, w) + 1
        v = ((1 << (hi - lo)) - 1) << lo
        return v if rng.random() < 0.5 else ((1 << w) - 1) ^ v
    return rng.getrandbits(w)
