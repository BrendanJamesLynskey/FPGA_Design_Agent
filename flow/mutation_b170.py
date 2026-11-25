#!/usr/bin/env python3
"""Mutation target of brief 170: the ITCH/OUCH trading path under the independent UVM bench.

    python3 -m flow.mutation_b170 run b170_itch_path --seed 1 --count 30 --jobs 2 --json results/170_itch_uvm/mutation_seed1.json
    (also: show, redecide, rebench, targets, as in flow/mutation_score.py)

It registers one target with flow/mutation_targets.py and hands the command line to flow/mutation_score.py (the fixed tool of brief 152). What is mutated: the eleven RTL files of the
path (brief 110's mold_rx, itch_dec, book_core, risk_glue, ouch_enter and build rm_gp_itch's udp_strip, order_seg, itch_top, itch_path, tx_mux; the two MACs and the wrappers are not
mutated). The bench: designs/b96_kr260_10g/rm_gp_itch/verif/uvm built against the mutated copy and run test by test until one fails (scripts/mutant_bench.sh). The mutants are made by
flow/mutation_blind.py from the RTL text and a seed only, so the bench's authors have no hand in which bugs are tried. The RTL files sit in two directories, so they are staged into one
(build/b170_rtl) for the generator."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from flow import mutation_score as S
from flow import mutation_targets as T

ROOT = Path(__file__).resolve().parents[1]
B110 = ROOT / "designs" / "b110_itch_ouch" / "rtl"
VAR = ROOT / "designs" / "b96_kr260_10g" / "rm_gp_itch" / "rtl"
UVM = ROOT / "designs" / "b96_kr260_10g" / "rm_gp_itch" / "verif" / "uvm"
STAGE = ROOT / "build" / "b170_rtl"
FILES = [(B110, n) for n in ("mold_rx.sv", "itch_dec.sv", "book_core.sv", "risk_glue.sv", "ouch_enter.sv")] + [(VAR, n) for n in ("udp_strip.sv", "order_seg.sv", "itch_top.sv", "itch_path.sv", "tx_mux.sv")]
TESTS = "t_smoke t_mold t_tail t_badfcs t_book t_risk t_hdr t_bp t_mix:1 t_rand:1 t_rand:2"


def stage() -> Path:
    STAGE.mkdir(parents=True, exist_ok=True)
    for d, n in FILES:
        shutil.copy(d / n, STAGE / n)
    return STAGE


def bench(d: Path, timeout_s: float) -> str:
    """pass = the mutant survived every test; fail = a test failed (killed); invalid = the mutated RTL does not build; timeout = cut."""
    build = Path(tempfile.mkdtemp(prefix="b170_mut_"))
    try:
        rc, out = T._run(["bash", str(UVM / "scripts" / "mutant_bench.sh"), str(build), str(d.resolve())], T._suite_env() | {"MUT_TESTS": TESTS}, timeout_s)
        if rc == 124:
            return "timeout"
        last = (out.strip().splitlines() or [""])[-1]
        return {"PASS": "pass", "FAIL": "fail", "INVALID": "invalid"}.get(last, "invalid")
    finally:
        shutil.rmtree(build, ignore_errors=True)


def _target() -> dict:
    st = stage()
    names = [n for _, n in FILES]
    return {"name": "b170_itch_path", "design": "designs/b96_kr260_10g/rm_gp_itch", "what": "the ITCH/OUCH trading path (brief 110's blocks with build rm_gp_itch's adapter, builder and multiplexer)",
            "rtl_dir": st, "rtl_dir_rel": "build/b170_rtl", "rtl_source": "the files of designs/b110_itch_ouch/rtl and designs/b96_kr260_10g/rm_gp_itch/rtl named in rtl (staged into one directory)",
            "rtl_files": names, "copy_files": names, "bench": bench,
            "bench_text": (f"the independent UVM 1.2 bench of brief 170 in xsim 2026.1 (reference model written from the specifications; scoreboard, assertions, functional coverage), tests {TESTS.replace(' ', ', ')}, "
                           "stopped at the first failing test; build and run of each mutant from the mutated copy"),
            "top": "itch_top", "clocks": ["clk"], "reset": {"port": "rst", "clock": "clk", "cycles": 4, "active": 1}, "assume": [], "qualifiers": {},
            "extra_sources": [str(B110 / "itch_pkg.sv"), str(VAR / "itch_pkg2.sv")], "compared_text": "every output, every clock",
            "configs": [{"label": "N_INST=2 LEVELS=4 ORD_AW=4", "params": {"N_INST": 2, "LEVELS": 4, "ORD_AW": 4}}]}


def main(argv: list[str] | None = None) -> int:
    T.BUILDERS["b170_itch_path"] = _target
    T.TARGETS["b170_itch_path"] = {"what": "the ITCH/OUCH trading path under the independent UVM bench"}
    return S.main(argv)


if __name__ == "__main__":
    sys.exit(main())
