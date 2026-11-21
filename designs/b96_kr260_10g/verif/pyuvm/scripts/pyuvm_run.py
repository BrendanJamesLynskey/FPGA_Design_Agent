"""Build and run the pyuvm bench (brief 123) with the cocotb runner and Icarus. Used by run_regress.py, the pytest entry and by hand:

    pyuvm_run.py build <build_dir> [<rtl_dir>]                 compile the RTL (default: the design's rtl/) and the top
    pyuvm_run.py run <build_dir> <test> <seed> [<out_dir>]     one UVM test, one seed; exit 0 = pass

PYUVM_WAVES=1 builds and runs with a waveform dump (Icarus writes <build_dir>/tb_pyuvm_top.fst, viewable with GTKWave).
The Python environment needs cocotb 2.0.1, pyuvm and cocotb-coverage (see ../README.md, Reproduce)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYUVM = HERE.parent
DESIGN = PYUVM.parents[1]
ROOT = DESIGN.parents[1]
RTL_FILES = ["b96_pkg.sv", "pcs_tx.sv", "pcs_rx.sv", "mac64_tx.sv", "mac64_rx.sv"]


def runner():
    from cocotb_tools.runner import get_runner
    return get_runner(os.environ.get("SIM", "icarus"))


def _built(build_dir: Path, rtl_dir: Path | None, always: bool):
    rtl_dir = rtl_dir or DESIGN / "rtl"
    r = runner()
    r.build(sources=[rtl_dir / n for n in RTL_FILES] + [PYUVM / "tb" / "tb_pyuvm_top.sv"], hdl_toplevel="tb_pyuvm_top", build_dir=build_dir,
            build_args=["-g2012"], always=always, waves=bool(os.environ.get("PYUVM_WAVES")))
    return r


def build(build_dir: Path, rtl_dir: Path | None = None) -> float:
    t0 = time.time()
    _built(build_dir, rtl_dir, True)
    return time.time() - t0


def run(build_dir: Path, test: str, seed: int, out_dir: Path | None = None, rtl_dir: Path | None = None) -> tuple[bool, float, Path]:
    """Returns (passed, wall seconds, results.xml). The simulator process runs the one cocotb test named `test` with SEED=seed."""
    from cocotb_tools.runner import get_results
    env = {"SEED": str(seed), "PYTHONPATH": str(ROOT), "COCOTB_RANDOM_SEED": str(seed)}
    if out_dir:
        env["PYUVM_OUT"] = str(out_dir)
    xml = build_dir / f"results_{test}_{seed}.xml"
    t0 = time.time()
    try:
        _built(build_dir, rtl_dir, False).test(hdl_toplevel="tb_pyuvm_top", test_module="designs.b96_kr260_10g.verif.pyuvm.tests.pcs_mac_pyuvm_cocotb", testcase=test, build_dir=build_dir,
                      test_dir=build_dir, results_xml=xml, extra_env=env, seed=seed, test_args=[], waves=bool(os.environ.get("PYUVM_WAVES")))
    except (Exception, SystemExit) as e:           # the runner raises (or exits) when a test fails
        print(f"runner: {type(e).__name__}: {e}", file=sys.stderr)
        wall = time.time() - t0
        return False, wall, xml
    wall = time.time() - t0
    if not xml.exists():
        return False, wall, xml
    num, fail = get_results(xml)
    return (fail == 0 and num >= 1), wall, xml


if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 3 and a[1] == "build":
        print(f"build {build(Path(a[2]), Path(a[3]) if len(a) > 3 else None):.1f} s")
    elif len(a) >= 5 and a[1] == "run":
        ok, wall, xml = run(Path(a[2]), a[3], int(a[4]), Path(a[5]) if len(a) > 5 else None)
        print(f"{'PASS' if ok else 'FAIL'} {a[3]} seed {a[4]} {wall:.1f} s")
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(2)
