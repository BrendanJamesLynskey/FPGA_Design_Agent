"""The hook for brief 119's tcp_fast (brief 127): order_seg_tcpfast.sv has the same ports as the stand-in and compiles with tcp_fast in the ITCH path. Runs only where tcp_fast's source is available
(B119_RTL=<path to tcp_fast.sv>, or designs/b119_tcp_fast/rtl/tcp_fast.sv once PR #245 is merged)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
B96 = DESIGN.parent
B110 = B96.parent / "b110_itch_ouch"
ROOT = B96.parents[1]
TF = Path(os.environ.get("B119_RTL") or ROOT / "designs/b119_tcp_fast/rtl/tcp_fast.sv")


def ports(path: Path, module: str) -> list[str]:
    t = path.read_text()
    head = t[t.index(f"module {module}"):]
    head = head[:head.index(");")]
    return sorted(re.findall(r"\b(\w+)\s*(?:,|$)", re.sub(r"\[[^\]]*\]|//[^\n]*|input|output|logic", "", head).replace("(", " ")))


def test_hook_and_stand_in_have_the_same_ports() -> None:
    assert ports(DESIGN / "rtl/order_seg.sv", "order_seg") == ports(DESIGN / "rtl/order_seg_tcpfast.sv", "order_seg")


@pytest.mark.skipif(not (TF.exists() and shutil.which("iverilog")), reason="needs brief 119's tcp_fast.sv (B119_RTL) and Icarus")
def test_hook_compiles_with_tcp_fast() -> None:
    srcs = [B96 / "rtl/b96_pkg.sv", B110 / "rtl/itch_pkg.sv", DESIGN / "rtl/itch_pkg2.sv", *[B110 / f"rtl/{n}.sv" for n in ("mold_rx", "itch_dec", "book_core", "risk_glue", "ouch_enter")], TF,
            DESIGN / "rtl/udp_strip.sv", DESIGN / "rtl/order_seg_tcpfast.sv", DESIGN / "rtl/itch_top.sv", DESIGN / "rtl/itch_path.sv"]
    r = subprocess.run(["iverilog", "-g2012", "-o", os.devnull, *map(str, srcs)], capture_output=True, text=True)
    assert r.returncode == 0 and "error" not in r.stderr.lower(), r.stderr[-1500:]
