"""Simulation, lint and formal helpers shared by the arithmetic library's tests (brief 139b).

Tools are looked up on PATH, then in FDA_OSS_CAD, then in ~/.local/opt/oss-cad-suite (the same pinned suite brief 101 and 115 use).
A test that needs a tool and does not find it skips, unless FDA_REQUIRE_FORMAL=1 (CI sets it), when it fails.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ARITH = Path(__file__).resolve().parents[1]
ROOT = ARITH.parent
COMMON = ARITH / "common"

_RESULT = re.compile(r"ARITH_RESULT (.*)")


def _suite_bin() -> Path | None:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin").is_dir():
            return Path(c) / "bin"
    return None


def tool(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    b = _suite_bin()
    if b and (b / name).exists():
        return str(b / name)
    return None


def env() -> dict[str, str]:
    """Environment for the suite's tools (the suite's own Python and libraries come with its bin directory on PATH)."""
    e = dict(os.environ)
    b = _suite_bin()
    if b:
        e["PATH"] = f"{b}:{e.get('PATH', '')}"
        # the suite's launchers find their libraries relative to themselves; nothing else is needed
    return e


def need(name: str) -> str:
    import pytest
    t = tool(name)
    if t is None:
        if os.environ.get("FDA_REQUIRE_FORMAL") == "1":
            pytest.fail(f"{name} not found and FDA_REQUIRE_FORMAL=1")
        pytest.skip(f"{name} not installed")
    return t


def write_hex(path: Path, words: list[int], width: int) -> None:
    n = (width + 3) // 4
    path.write_text("".join(f"{w & ((1 << width) - 1):0{n}x}\n" for w in words))


def run_stream(tb_top: str, rtl_files: list[Path], params: dict[str, int], vin: list[int], vexp: list[int], in_w: int, out_w: int, lat: int,
               gap_pct: int = 0, seed: int = 1, workdir: Path | None = None, extra_tb: list[Path] | None = None) -> dict[str, int]:
    """Compile with Icarus, run the stream harness over the vectors, return the harness's result line as a dict."""
    iv, vvp = need("iverilog"), need("vvp")
    own = workdir is None
    wd = Path(tempfile.mkdtemp(prefix="arith_")) if own else Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    try:
        write_hex(wd / "vin.hex", vin, in_w)
        write_hex(wd / "vexp.hex", vexp, out_w)
        allp = dict(params) | {"IN_W": in_w, "OUT_W": out_w, "NVEC": len(vin), "LAT": lat, "GAP_PCT": gap_pct, "SEED": seed}
        cmd = [iv, "-g2012", "-s", tb_top, "-o", str(wd / "sim.vvp")]
        for k, v in allp.items():
            cmd += [f"-P{tb_top}.{k}={v}"]
        cmd += [str(COMMON / "tb_stream.sv"), *map(str, extra_tb or []), *map(str, rtl_files)]
        c = subprocess.run(cmd, capture_output=True, text=True, env=env())
        if c.returncode != 0:
            return {"compile_error": 1, "log": c.stderr[-2000:]}
        r = subprocess.run([vvp, str(wd / "sim.vvp"), f"+vin={wd / 'vin.hex'}", f"+vexp={wd / 'vexp.hex'}"], capture_output=True, text=True, env=env(), timeout=900)
        m = _RESULT.search(r.stdout)
        if not m:
            return {"no_result": 1, "log": (r.stdout + r.stderr)[-2000:]}
        res = {k: int(v) for k, v in (kv.split("=") for kv in m.group(1).split())}
        res["log"] = r.stdout[-1500:]
        return res
    finally:
        if own:
            shutil.rmtree(wd, ignore_errors=True)


def ok(res: dict) -> bool:
    return (not res.get("compile_error") and not res.get("no_result") and res.get("done") == 1 and res.get("mismatches") == 0
            and res.get("lat_errors") == 0 and res.get("spurious") == 0 and res.get("x_valid") == 0 and res.get("checked", 0) > 0)


def lint(top: str, files: list[Path], params: dict[str, int] | None = None, waivers: Path | None = None) -> tuple[bool, str]:
    """Verilator -Wall --lint-only; True only with no warning at all."""
    v = need("verilator")
    cmd = [v, "--lint-only", "-Wall", "--top-module", top]
    for k, val in (params or {}).items():
        cmd += [f"-G{k}={val}"]
    if waivers:
        cmd.append(str(waivers))
    cmd += list(map(str, files))
    r = subprocess.run(cmd, capture_output=True, text=True, env=env())
    return (r.returncode == 0 and "%Warning" not in r.stderr), r.stderr[-3000:]
