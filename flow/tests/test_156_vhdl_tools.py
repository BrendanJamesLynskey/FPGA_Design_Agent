"""Brief 156: the VHDL simulator comparison, coverage and PSL harnesses (results/156_vhdl_tools). Light checks that do not need NVC:
every design's files exist, every hand-written fault applies exactly once, the benches compile, the PSL probe texts are well formed, and
(where GHDL and cocotb are installed) one small bench runs end to end and fails on its fault."""
from __future__ import annotations

import importlib.util
import os
import py_compile
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "results" / "156_vhdl_tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, D / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


R = _load("run_sims")


def test_every_design_file_exists_and_has_a_bench_and_a_fault():
    for name, d in R.DESIGNS.items():
        assert all(Path(f).is_file() for f in d["files"]), name
        assert (D / "benches" / f"{d['bench']}.py").is_file(), name
        assert name in R.MUTANTS, name


def test_each_fault_applies_exactly_once(tmp_path):
    for name, d in R.DESIGNS.items():
        m = R.mutated(name, d, tmp_path)
        assert all(Path(f).is_file() for f in m["files"])
        changed = [f for f, o in zip(m["files"], d["files"]) if Path(f).read_text() != Path(o).read_text()]
        assert len(changed) == 1, name


def test_the_benches_compile(tmp_path):
    for p in (D / "benches").glob("*.py"):
        py_compile.compile(str(p), doraise=True, cfile=str(tmp_path / (p.stem + ".pyc")))


def test_psl_probes_are_unique_and_have_an_expected_verdict():
    P = _load("psl_probe")
    names = [p[0] for p in P.PROBES]
    assert len(names) == len(set(names))
    assert all(p[1] in ("true", "false", "cover", "cover-unreachable") for p in P.PROBES)
    assert all("always" in p[2] or "never" in p[2] or "cover" in p[2] or "assert" in p[2] for p in P.PROBES)


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL is not installed")
def test_one_bench_passes_and_its_fault_is_caught(tmp_path):
    pytest.importorskip("cocotb")
    sim = R.Sim("ghdl-on-path", shutil.which("ghdl"), dict(os.environ), "ghdl-mcode")
    d = R.DESIGNS["sync_fifo_regs"]
    ok = R.one(sim, "sync_fifo_regs", d, 300, tmp_path)
    assert ok["build_ok"] and ok["work_xml"]["fail"] == 0 and ok["work_xml"]["tests"] == 1
    bad = R.one(sim, "sync_fifo_regs", R.mutated("sync_fifo_regs", d, tmp_path), 300, tmp_path, tag="__m")
    assert bad["work_xml"]["fail"] == 1


def test_the_labelled_sv_twin_is_the_reference_file_with_labels_and_covers_added():
    """results/156_vhdl_tools/psl/sv/gray_stepper.sv is what the SymbiYosys job reads (brief 202: the assertions need labels and antecedent covers for the
    143c rigour check); nothing else may differ from the benchmark reference file it twins."""
    import re
    ref = (ROOT / "benchmark/tasks/t1_gray_stepper/ref/rtl/gray_stepper.sv").read_text()
    mine = (D / "psl/sv/gray_stepper.sv").read_text()
    mine = re.sub(r"    // brief 202:.*?\n    end\n", "", mine, flags=re.S)
    for label in ("req01_one_bit", "inv_gray_of_bin"):
        mine = mine.replace(f" {label}: assert", " assert")
    assert mine == ref
