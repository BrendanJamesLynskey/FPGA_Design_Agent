"""Verilator -Wall lint of the new blocks of build rm_gp_itch (brief 127): the ITCH path (adapter, brief 110's blocks, segment builder, wrapper) and the transmit multiplexer, each on its own."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
B96 = DESIGN.parent
B110 = B96.parent / "b110_itch_ouch"
VERILATOR = shutil.which("verilator") or str(Path.home() / ".local/opt/oss-cad-suite/bin/verilator")


def lint(top: str, srcs: list[Path]) -> None:
    env = dict(os.environ)
    r = subprocess.run([VERILATOR, "--lint-only", "-Wall", "--top-module", top, str(DESIGN / "lint" / "lint_waivers.vlt"), *map(str, srcs)], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr[-2500:]


@pytest.mark.skipif(not (shutil.which("verilator") or Path(VERILATOR).exists()), reason="Verilator not installed")
def test_itch_path_lint_clean() -> None:
    lint("itch_path", [B96 / "rtl/b96_pkg.sv", B110 / "rtl/itch_pkg.sv", DESIGN / "rtl/itch_pkg2.sv", *[B110 / f"rtl/{n}.sv" for n in ("mold_rx", "itch_dec", "book_core", "risk_glue", "ouch_enter")],
                          *[DESIGN / f"rtl/{n}.sv" for n in ("udp_strip", "order_seg", "itch_top", "itch_path")]])


@pytest.mark.skipif(not (shutil.which("verilator") or Path(VERILATOR).exists()), reason="Verilator not installed")
def test_tx_mux_lint_clean() -> None:
    lint("tx_mux", [DESIGN / "rtl/tx_mux.sv"])
