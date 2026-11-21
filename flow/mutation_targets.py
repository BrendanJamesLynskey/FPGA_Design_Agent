#!/usr/bin/env python3
"""The targets of flow/mutation_score.py (brief 143b): what is mutated, how the bench is run on a mutant, what the formal filter compares.

A target is a dict:  name, design, what, rtl_dir (where the RTL is), rtl_files (the files the generator mutates), bench (a function
``bench(mutant_dir, timeout_s) -> "pass" | "fail" | "timeout" | "invalid"``), bench_text (a plain description of that bench), and for the formal filter
top, clocks, reset, assume, qualifiers, extra_sources, configs.  ``pass`` means the bench found nothing wrong with the mutant (it survived), ``fail`` that
it did (killed), ``invalid`` that the copy did not build (the bench produced no result: excluded, never a kill).

The four targets of the brief:
  b96_rate_match_gp   designs/b96_kr260_10g/rtl/rate_match_gp.sv   the cocotb bench test_rate_match_gp_cocotb (against its Python twin), Icarus
  b119_tcp_fast       designs/b119_tcp_fast/rtl/tcp_fast.sv        the cocotb bench test_all_benches (against the Python reference), Icarus
  arith_lzc_norm      arith/lzc_norm/rtl/*.sv                      the function's exhaustive stream bench at the configurations of its own mutant check
  arith_isqrt         arith/isqrt/rtl/*.sv                         the same, for the square root
The two arith targets read the arithmetic library as it is on branch b139b-arith-previvado (PR 263, not on main when this was written): the tree is
extracted with ``git archive`` into build/arith_b139b/ and the record names the commit.  They move to the plain ``arith/`` path when that PR merges.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_CHECKOUT = Path.home() / "Claude_sandbox" / "FPGA_Design_Agent"
ARITH_BRANCH = os.environ.get("MUTATION_ARITH_REF", "origin/b139b-arith-previvado")
ARITH_ROOT = ROOT / "build" / "arith_b139b"


def python() -> str:
    """The interpreter with cocotb: $MUTATION_PYTHON, else the checkout's .venv (a worktree has none), else this one."""
    for c in (os.environ.get("MUTATION_PYTHON"), str(ROOT / ".venv" / "bin" / "python"), str(MAIN_CHECKOUT / ".venv" / "bin" / "python")):
        if c and Path(c).exists():
            return c
    return sys.executable


def _run(argv: list[str], env: dict, timeout: float) -> tuple[int, str]:
    import signal
    p = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return 124, ""


def _suite_env() -> dict:
    from flow import mutation_equiv
    e = dict(os.environ)
    b = mutation_equiv.suite_bin()
    if b:
        e["PATH"] = f"{b}:{e['PATH']}"
    return e


# ---- cocotb benches (b96, b119): the pytest entry with the mutated copy swapped in ----------------------------------------------

def pytest_bench(test_id, result_xml: str, swap_env) -> "callable":
    """A bench function that runs one pytest node against a mutant directory. ``swap_env(dir)`` gives the environment that points the test at the copy; the
    run's results.xml (under its own build root) tells a build failure (no file: invalid) from a failing test (killed)."""
    def bench(d: Path, timeout_s: float) -> str:
        root = Path(tempfile.mkdtemp(prefix="mt_sim_"))
        try:
            env = _suite_env() | {"FDA_SIM_BUILD_ROOT": str(root), "PYTHONPATH": str(ROOT)} | swap_env(d)
            argv = test_id if isinstance(test_id, list) else [python(), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test_id]
            rc, _ = _run(argv, env, timeout_s)
            if rc == 124:
                return "timeout"
            if rc == 0:
                return "pass"
            return "fail" if (root / result_xml).is_file() else "invalid"
        finally:
            shutil.rmtree(root, ignore_errors=True)
    return bench


B96_TESTS = ["same_clocks", "partner_faster", "ordered_sets_and_errors_pass", "lock_loss_discards", "clear_wins_over_a_count"]


def _b96_run(mdir: Path) -> None:
    """The bench of test_rate_match_gp_cocotb (same sources, parameters and Python twin) with the two 5000-frame/400 ppm cases left out
    (partner_slower, minimum_gap_partner_faster): the full bench takes over 40 minutes a run, too long for a sweep. Run inside the swap environment."""
    from flow import cocotb_run
    D = ROOT / "designs" / "b96_kr260_10g"
    srcs = [D / "rtl" / "rate_match.sv", D / "rtl" / "rate_match_gp.sv", D / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match_gp", "tb_rate_match", srcs, "ratematch_cocotb", D / "tests", parameters={"IMPL": 1, "HI": 1}, testcase=[rf"\.{t}$" for t in B96_TESTS],
                   extra_env={"PYTHONPATH": str(ROOT), "B96_RM_IMPL": "gp", "B96_RM_HI": "1"})


def _b96_swap(d: Path) -> dict:
    return {"FDA_MUTANT_ORIG": str((ROOT / "designs/b96_kr260_10g/rtl").resolve()), "FDA_MUTANT_DIR": str(d.resolve())}


def _b119_swap(d: Path) -> dict:
    return {"B119_RTL_DIR": str(d.resolve())}


def b96_formal_bench(d: Path) -> str:
    """The design's own SymbiYosys property bench (brief 115, rm_gp.sby, task safety_bmc: overflow, underflow, pointer views, gray, idle policy, entry integrity) run
    against the mutant: ``killed`` when an assertion fails, ``passed`` when none does, ``timeout``/``error`` otherwise."""
    from flow import mutation_equiv
    if mutation_equiv.suite_bin() is None:
        return "error"
    base = Path(tempfile.mkdtemp(prefix="mt_fb_"))
    try:
        fdir = base / "x" / "y" / "formal"
        shutil.copytree(ROOT / "designs/b96_kr260_10g/verif/formal", fdir)
        (base / "x" / "rtl").mkdir(parents=True)
        shutil.copy(d / "rate_match_gp.sv", base / "x" / "rtl" / "rate_match_gp.sv")
        rc, out = mutation_equiv.run_cmd(["sby", "-f", "rm_gp.sby", "safety_bmc"], fdir, 400)
        if rc == 124:
            return "timeout"
        if "DONE (FAIL" in out:
            return "killed"
        return "passed" if "DONE (PASS" in out else "error"
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- arith benches ---------------------------------------------------------------------------------------------------------------

def arith_root() -> Path:
    """build/arith_b139b: the arith/ tree of the branch (git archive), made once. Returns its root (the directory that holds ``arith/``)."""
    if not (ARITH_ROOT / "arith").is_dir():
        ARITH_ROOT.mkdir(parents=True, exist_ok=True)
        repo = MAIN_CHECKOUT if (MAIN_CHECKOUT / ".git").exists() else ROOT
        p = subprocess.run(f"git -C {repo} archive {ARITH_BRANCH} arith | tar -x -C {ARITH_ROOT}", shell=True, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"cannot extract arith/ from {ARITH_BRANCH}: {p.stderr[-300:]}")
    return ARITH_ROOT


def arith_commit() -> str:
    repo = MAIN_CHECKOUT if (MAIN_CHECKOUT / ".git").exists() else ROOT
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", ARITH_BRANCH], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


#: widths: the bench is exhaustive at every width from 3 to 12 (the library's own exhaustive-small-widths test runs 3 to 16 and random larger ones; 12 keeps a mutant
#: run to seconds); the formal filter decides each survivor at a spread of widths of both parities
ARITH_BENCH_WIDTHS = {"lzc_norm": range(3, 13), "isqrt": range(3, 13)}
ARITH_FORMAL_WIDTHS = {"lzc_norm": (5, 8, 12, 16), "isqrt": (6, 9, 12, 16)}
ARITH_VARIANTS = {"lzc_norm": (0, 1, 2, 3), "isqrt": (0, 1, 2)}


def arith_cfgs(fn: str, widths) -> list[tuple[int, int, int]]:
    """(variant, width, pipeline depth) as the library's own exhaustive test chooses the depth: lzc_norm half the stage count; isqrt 1 for the iterative one, else half the root width."""
    sys.path[:0] = [str(arith_root())]
    if fn == "isqrt":
        from arith.isqrt import model as M
        pipe = lambda v, w: 1 if v == 0 else max(1, M.rw(w) // 2)
    else:
        from arith.lzc_norm import model as M
        pipe = lambda v, w: max(1, M.k_stages(w) // 2)
    return [(v, w, pipe(v, w)) for v in ARITH_VARIANTS[fn] for w in widths]


def _arith_one(fn: str, mdir: Path) -> str:
    """Runs inside a subprocess with the arith tree on the path: every configuration's exhaustive stream (25 % gaps) through the mutated RTL."""
    from arith.common import sim
    if fn == "isqrt":
        from arith.isqrt import model as M
        top, tb = "tb_isqrt", ROOT / "build" / "arith_b139b" / "arith" / "isqrt" / "tb" / "tb_isqrt.sv"
        out_w = lambda w: 2 * M.rw(w) + 1
    else:
        from arith.lzc_norm import model as M
        top, tb = "tb_lzc_norm", ROOT / "build" / "arith_b139b" / "arith" / "lzc_norm" / "tb" / "tb_lzc_norm.sv"
        out_w = lambda w: w + M.lw(w)
    files = sorted(mdir.glob("*.sv"))
    for v, w, p in arith_cfgs(fn, ARITH_BENCH_WIDTHS[fn]):
        vin, vexp = M.stream(w)
        try:
            r = sim.run_stream(top, files, {"VARIANT": v, "W": w, "PIPE": p}, vin, vexp, w, out_w(w), M.latency(v, w, p), gap_pct=25, extra_tb=[tb])
        except subprocess.TimeoutExpired:
            return "timeout"
        if r.get("compile_error"):
            return "invalid"
        if not sim.ok(r):
            return "fail"
    return "pass"


def arith_bench(fn: str):
    def bench(d: Path, timeout_s: float) -> str:
        env = _suite_env() | {"PYTHONPATH": f"{arith_root()}:{ROOT}"}
        rc, out = _run([sys.executable, "-m", "flow.mutation_targets", "arith-bench", fn, str(d)], env, timeout_s)
        if rc == 124:
            return "timeout"
        last = (out.strip().splitlines() or [""])[-1]
        return last if last in ("pass", "fail", "invalid", "timeout") else "invalid"
    return bench


def _arith_target(fn: str, top: str, text: str) -> dict:
    root = arith_root()
    d = root / "arith" / fn / "rtl"
    allf = sorted(p.name for p in d.glob("*.sv"))
    files = [n for n in allf if not n.endswith("_ooc.sv")]      # the Vivado out-of-context wrapper is not mutated (the bench never instantiates it)
    return {"name": f"arith_{fn}", "design": f"arith/{fn}", "what": text, "rtl_dir": d, "rtl_dir_rel": f"build/arith_b139b/arith/{fn}/rtl",
            "rtl_source": f"{ARITH_BRANCH} at {arith_commit()[:10]} (PR 263; not on main)", "rtl_files": files, "copy_files": allf, "bench": arith_bench(fn),
            "bench_text": (f"the function's exhaustive stream bench (Icarus, every input of each width, 25% idle gaps, latency and order checked) at "
                           f"every variant at widths 3 to 12 (pipeline depth as the library's exhaustive test chooses it), {len(arith_cfgs(fn, ARITH_BENCH_WIDTHS[fn]))} configurations"),
            "top": top, "clocks": ["clk"], "reset": {"port": "rst", "clock": "clk", "cycles": 3, "active": 1},
            "assume": ["!in_valid || g_in_ready"], "qualifiers": {"out_data": "out_valid"},
            "compared_text": "in_ready always; out_valid always; out_data when out_valid is high (the stream interface's contract)",
            "configs": [{"label": f"VARIANT={v} W={w} PIPE={p}", "params": {"VARIANT": v, "W": w, "PIPE": p}} for v, w, p in arith_cfgs(fn, ARITH_FORMAL_WIDTHS[fn])]}


def _b96() -> dict:
    D = ROOT / "designs" / "b96_kr260_10g"
    return {"name": "b96_rate_match_gp", "design": "designs/b96_kr260_10g", "what": "the receive elastic buffer rate_match_gp (own gray-pointer FIFO, two clock domains)",
            "rtl_dir": D / "rtl", "rtl_dir_rel": "designs/b96_kr260_10g/rtl", "rtl_files": ["rate_match_gp.sv"], "copy_files": ["rate_match_gp.sv"],
            "bench": pytest_bench([python(), "-m", "flow.mutation_targets", "b96-bench"], "b96_rate_match_gp/results.xml", _b96_swap),
            "bench_text": f"test_rate_match_gp_cocotb's bench without its two longest cases: {', '.join(B96_TESTS)} (cocotb + Icarus, output for output against the Python twin, frame checks, 300 frames at 0 and +400 ppm)",
            "top": "rate_match_gp", "clocks": ["wclk", "rclk"], "reset": None, "assume": [], "qualifiers": {},
            "extra_sources": [str(D / "verif/formal/xpm_formal.sv")], "compared_text": "every output of the block, at every step (both clocks free)",
            "formal_bench": b96_formal_bench,
            "configs": [{"label": "AW=4 HI=1 (the bench's)", "params": {"AW": 4, "HI": 1}}, {"label": "AW=2 HI=1", "params": {"AW": 2, "HI": 1}}]}


def _b119() -> dict:
    D = ROOT / "designs" / "b119_tcp_fast"
    return {"name": "b119_tcp_fast", "design": "designs/b119_tcp_fast", "what": "the TCP fast path (software owns the connection, hardware emits the order segment)",
            "rtl_dir": D / "rtl", "rtl_dir_rel": "designs/b119_tcp_fast/rtl", "rtl_files": ["tcp_fast.sv"], "copy_files": ["tcp_fast.sv"],
            "bench": pytest_bench("designs/b119_tcp_fast/tests/test_b119_rtl.py::test_all_benches", "b119_all/results.xml", _b119_swap),
            "bench_text": "test_all_benches: every cocotb test of the b119 bench in one Icarus run, against the Python reference (checksums, timing, aborts, refusals, register semantics, end-to-end)",
            "top": "tcp_fast", "clocks": ["clk"], "reset": {"port": "rst", "clock": "clk", "cycles": 3, "active": 1}, "assume": [], "qualifiers": {},
            "extra_sources": [str(ROOT / "designs/b110_itch_ouch/rtl/ouch_enter.sv")],
            "compared_text": "every output, every clock", "configs": [{"label": "default parameters", "params": {}}]}


BUILDERS = {"b96_rate_match_gp": _b96, "b119_tcp_fast": _b119,
            "arith_lzc_norm": lambda: _arith_target("lzc_norm", "lznorm_sel", "leading-zero count and normaliser, four variants (arith library, brief 139b)"),
            "arith_isqrt": lambda: _arith_target("isqrt", "isqrt_sel", "integer square root with remainder, three variants (arith library, brief 139b)")}
TARGETS = {n: {"what": {"b96_rate_match_gp": "receive elastic buffer rate_match_gp", "b119_tcp_fast": "TCP fast path tcp_fast",
                        "arith_lzc_norm": "arith leading-zero count / normaliser", "arith_isqrt": "arith integer square root"}[n]} for n in BUILDERS}


def get(name: str) -> dict:
    if name not in BUILDERS:
        raise SystemExit(f"unknown target {name!r}; known: {', '.join(BUILDERS)}")
    return BUILDERS[name]()


if __name__ == "__main__":
    if sys.argv[1:2] == ["b96-bench"]:
        _b96_run(Path(os.environ["FDA_MUTANT_DIR"]))
    if len(sys.argv) == 4 and sys.argv[1] == "arith-bench":
        print(_arith_one(sys.argv[2], Path(sys.argv[3])))

