"""How the host reaches a design on its board (brief 209a), chosen from the board file's ``host_access``.

    uart      the board has a USB-UART: the test shell (shell/) is built in and flow/bringup.py talks to it (the Nexys A7, the
              Arty and ZedBoard files: a ``uart:`` block in board.yaml)
    jtag_bus  the board has no PL UART (the KR260: ``host_access: JTAG cable (BSCANE2 USER4 register bus ...); no PL UART pins``):
              the design carries the JTAG register bus (ip_lib/jtag_regs, from designs/b58a_trigger/rtl/jtag_bus.sv) and the host
              reads and writes 32-bit registers through ``Bus.rd`` / ``Bus.wr``

The common register map of a JTAG-bus design (every design has these three; the build stamp is what the bring-up compares with the build's):

    0x000 ID       RO   the design ID
    0x004 BUILD    RO   the bitstream's USR_ACCESS word (USR_ACCESSE2), the build stamp
    0x008 SCRATCH  RW   32 bits, reads back what was written, resets to 0

A design's ``hw_checks.py`` (JTAG-bus form) holds ``DESIGN_ID``, ``make_mock()`` (a :class:`MockBus` with the design's own registers,
written from the spec and the model, so every check runs in CI with no board) and ``run(bus)`` (a list of ``(name, ok, detail)``).
:func:`run_checks` adds the three common-map checks. ``python -m flow.host_transport <design>`` runs the checks against the mock.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[1]
VIVADO = os.environ.get("FDA_VIVADO", "/opt/Xilinx/2025.2/Vivado/bin/vivado")
REG_ID, REG_BUILD, REG_SCRATCH = 0x000, 0x004, 0x008
M32 = 0xFFFFFFFF
TRANSPORTS = ("uart", "jtag_bus")
SENTINEL = 0x5EED_F0B0


def transport(board: dict[str, Any]) -> str:
    """``jtag_bus`` for a board file with no ``uart:`` block whose ``host_access`` names the JTAG register bus, else ``uart``."""
    ha = str(board.get("host_access") or "").lower()
    if not board.get("uart") and "jtag" in ha and ("bscane" in ha or "register bus" in ha or "no pl uart" in ha):
        return "jtag_bus"
    return "uart"


def board_transport(name: str | None, root: Path = ROOT) -> str:
    """The transport of ``boards/<name>/board.yaml``; ``uart`` when the board or the file is not known (the historical default)."""
    import yaml
    f = Path(root) / "boards" / str(name) / "board.yaml"
    if not name or not f.is_file():
        return "uart"
    return transport(yaml.safe_load(f.read_text()) or {})


class Bus(Protocol):
    def rd(self, addr: int) -> int: ...
    def wr(self, addr: int, value: int) -> None: ...


class MockBus:
    """A register bus with no board. Subclass it for a design: set ``ID``, override ``read(addr)`` / ``write(addr, value)`` for the
    design's registers (addresses from 0x010); the common map is done here. ``BUILD`` is what the mock's USR_ACCESS word reads."""
    ID = 0
    BUILD = 0x1234ABCD

    def __init__(self, **faults: Any) -> None:
        self.f = faults
        self.scratch = 0
        self.log: list[tuple[str, int, int]] = []

    def rd(self, a: int) -> int:
        v = {REG_ID: self.ID, REG_BUILD: self.f.get("build", self.BUILD), REG_SCRATCH: self.scratch}.get(a)
        v = self.read(a) if v is None else v
        self.log.append(("rd", a, v & M32))
        return v & M32

    def wr(self, a: int, v: int) -> None:
        v &= M32
        self.log.append(("wr", a, v))
        if a == REG_SCRATCH:
            self.scratch = v
        elif a not in (REG_ID, REG_BUILD):
            self.write(a, v)

    def read(self, a: int) -> int:          # unmapped addresses read 0 (the register bus's rule)
        return 0

    def write(self, a: int, v: int) -> None:  # and ignore writes
        pass


class VivadoBus:
    """The real bus: a ``vivado -mode tcl`` child holding the hardware manager open on one cable (selected by serial, never "the first
    target"), through designs/b58a_trigger/host/jtag_regs.tcl. Needs the board; never used in CI."""

    def __init__(self, cable_serial: str) -> None:
        self.p = subprocess.Popen([VIVADO, "-mode", "tcl", "-nojournal", "-nolog"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, bufsize=1)
        self.cmd(f"source {ROOT}/designs/b58a_trigger/host/jtag_regs.tcl")
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
        self.cmd(f"b58a_wr {addr:#x} {value & M32:#x}")

    def close(self) -> None:
        try:
            self.cmd("b58a_close")
        finally:
            self.p.terminate()


def load_hw_checks(design: Path) -> Any:
    """The design's hw_checks.py by file path (an agent design lives under runs/<id>/)."""
    f = Path(design) / "hw_checks.py"
    spec = importlib.util.spec_from_file_location(f"hw_checks_{Path(design).name}", f)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {f}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    sys.path.insert(0, str(Path(design)))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def run_checks(mod: Any, bus: Bus, expected_build: int | None = None) -> list[tuple[str, bool, str]]:
    """The common-map checks, then the design's own ``run(bus)``. ``expected_build``: the build's stamp (USR_ACCESS) the bring-up
    knows; ``None`` skips the comparison (the mock's own value is then only read, never compared)."""
    out: list[tuple[str, bool, str]] = []
    ident = bus.rd(REG_ID)
    out.append(("id_register", ident == mod.DESIGN_ID, f"read {ident:#010x}, expected {mod.DESIGN_ID:#010x}"))
    b = bus.rd(REG_BUILD)
    out.append(("build_stamp", expected_build is None or b == expected_build,
                f"read {b:#010x}" + ("" if expected_build is None else f", expected {expected_build:#010x}")))
    sc = []
    for v in (0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 0x0):
        bus.wr(REG_SCRATCH, v)
        sc.append(bus.rd(REG_SCRATCH) == v)
    out.append(("scratch_register", all(sc), "read back four patterns" if all(sc) else f"patterns that failed: {sc}"))
    out += [(str(n), bool(ok), str(d)) for n, ok, d in mod.run(bus)]
    return out


def run_mock(design: Path) -> dict[str, Any]:
    """Every check of the design's hw_checks.py against its own mock bus; the record the flow gates on."""
    mod = load_hw_checks(design)
    for need in ("DESIGN_ID", "make_mock", "run"):
        if not hasattr(mod, need):
            return {"ok": False, "error": f"hw_checks.py has no {need}"}
    bus = mod.make_mock()
    res = run_checks(mod, bus)
    bad = [f"{n}: {d}" for n, ok, d in res if not ok]
    return {"ok": not bad, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in res], "error": "; ".join(bad)[:1500],
            "bus_accesses": len(getattr(bus, "log", []))}


def main(argv: list[str] | None = None) -> int:
    import json
    a = sys.argv[1:] if argv is None else argv
    r = run_mock(Path(a[0]).resolve())
    print(json.dumps(r))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
