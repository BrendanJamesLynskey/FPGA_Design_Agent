"""Register-bus transports for the brief 209 pilot host checks.

`Bus` is anything with rd(addr) -> int and wr(addr, value). `VivadoBus` is the real one: a `vivado -mode tcl` child holding the
hardware manager open on one cable (selected by serial, never "the first target"), using designs/b58a_trigger/host/jtag_regs.tcl
(the BSCANE2 USER4 bus, measured on the KR260 on 2026-11-17). The mocks in pilots/209/tests stand in for it, so the check logic is tested without a board.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Protocol

REPO = Path(__file__).resolve().parents[3]
VIVADO = os.environ.get("FDA_VIVADO", "/opt/Xilinx/2025.2/Vivado/bin/vivado")


class Bus(Protocol):
    def rd(self, addr: int) -> int: ...
    def wr(self, addr: int, value: int) -> None: ...


class Clock:
    """Real time. The mocks use a virtual one with the same two methods, so a ten-minute soak runs instantly in a test."""
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, s: float) -> None:
        time.sleep(s)


class VivadoBus:
    def __init__(self, cable_serial: str) -> None:
        self.p = subprocess.Popen([VIVADO, "-mode", "tcl", "-nojournal", "-nolog"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.cmd(f"source {REPO}/designs/b58a_trigger/host/jtag_regs.tcl")
        self.cmd(f"b58a_open {cable_serial}")

    def cmd(self, line: str) -> str:
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write("if {[catch {" + line + "} __r]} {puts \"__ERR__ $__r\"} else {puts \"__RES__ $__r\"}\nputs __DONE__\n")
        self.p.stdin.flush()
        out, res, err = [], None, None
        while True:
            l = self.p.stdout.readline()
            if not l:
                raise RuntimeError("vivado closed")
            t = l.rstrip()
            if t.endswith("__DONE__"):
                break
            if t.startswith("__RES__"):
                res = t[8:]
            elif t.startswith("__ERR__"):
                err = t[8:]
            else:
                out.append(t)
        if err is not None:
            raise RuntimeError(f"vivado: {line}: {err}")
        return "\n".join(out + ([res] if res else []))

    def rd(self, addr: int) -> int:
        return int(self.cmd(f"format %08x [b58a_rd {addr:#x}]").strip().splitlines()[-1], 16)

    def wr(self, addr: int, value: int) -> None:
        self.cmd(f"b58a_wr {addr:#x} {value & 0xFFFFFFFF:#x}")

    def close(self) -> None:
        try:
            self.cmd("b58a_close")
        finally:
            self.p.terminate()
