"""The host side of the brief 59A transactor: load a program, run it, read back verdicts, violations, coverage,
performance and the transaction log, and arm a capture around the first violation.

Every operation is a generator of register accesses, so one piece of code drives both the board (through the UART test
shell, :class:`SyncHost`) and the RTL in a cocotb simulation (:func:`arun` over the window bus): the same program, the
same register traffic. A generator yields ``("w", offset, value)`` or ``("r", offset)`` (offsets are window offsets;
the shell address is 0x80 + offset) and receives the read value.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Generator

from axi_tx.host import model, regs
from axi_tx.host.program import Program

Op = Generator[tuple, Any, Any]


def _rd(off: int) -> Op:
    return (yield ("r", off))


def _sel(sel: int, data: int, idx: int) -> Op:
    yield ("w", sel, idx)
    return (yield ("r", data))


def setup(prog: Program) -> Op:
    """Target select, seeded bugs (none for a clean run), the program words. Returns the instruction count."""
    v = yield ("r", regs.VERSION)
    if v != regs.VERSION_VALUE:
        raise RuntimeError(f"axi_tx core version 0x{v:08x}, expected 0x{regs.VERSION_VALUE:08x}")
    ctrl = regs.TARGETS[prog.target] | (regs.LITE_BUGS[prog.lite_bug] << 4) | (regs.STREAM_BUGS[prog.stream_bug] << 8)
    yield ("w", regs.SYS_CTRL, ctrl | regs.TARGET_RESET)       # reset the targets around the switch
    yield ("w", regs.SYS_CTRL, ctrl)
    yield ("w", regs.PROG_ADDR, 0)
    for word in prog.words:
        yield ("w", regs.PROG_DATA, word)
    yield ("w", regs.PROG_ADDR, 0)                               # read back the first and the last instruction word
    first = yield ("r", regs.PROG_DATA)
    yield ("w", regs.PROG_ADDR, len(prog.words) - 4)
    last = yield ("r", regs.PROG_DATA)
    if first != prog.words[0] or last != prog.words[-4]:
        raise RuntimeError("program RAM read-back differs from the words written")
    return prog.n_instr


def arm_capture(pre: int = 64) -> Op:
    """Arm the logic analyser to trigger on the first rule episode (sample bit 31), keeping `pre` samples before it."""
    la = regs.LA_BASE
    yield ("w", la + 2, 1 << 31)     # MASK
    yield ("w", la + 3, 1 << 31)     # VALUE
    yield ("w", la + 4, pre)         # PRE
    yield ("w", la + 0, 1)           # CTRL: arm, level trigger


def start() -> Op:
    yield ("w", regs.CTRL, regs.CTRL_START)


def status() -> Op:
    s = yield ("r", regs.STATUS)
    flags = [n for b, n in regs.STATUS_BITS.items() if s >> b & 1]
    hang = [n for b, n in regs.HANG_BITS.items() if s >> (8 + b) & 1]
    return {"raw": s, "flags": flags, "hang_channels": hang, "pc": (s >> 16) & 0x3FF}


def wait_done(max_polls: int = 100_000, sleep: Callable[[], Any] | None = None) -> Op:
    for _ in range(max_polls):
        s = yield ("r", regs.STATUS)
        if not s & 1:
            return s
        if sleep:
            yield ("sleep", sleep)
    raise TimeoutError("the transactor is still running")


def read_capture() -> Op:
    la = regs.LA_BASE
    st = yield ("r", la + 1)
    if not st & 4:
        return {"triggered": False}
    depth = yield ("r", la + 5)
    pre = yield ("r", la + 4)
    samples = []
    for k in range(depth):
        yield ("w", la + 6, k)
        samples.append((yield ("r", la + 7)))
    rows = [{name: regs.field(s, hi, lo) for name, hi, lo in regs.CAPTURE_FIELDS} for s in samples]
    return {"triggered": True, "pre": pre, "depth": depth, "trigger_index": pre, "samples": samples, "rows": rows}


def results(log_entries: int | None = None, counters: bool = True) -> Op:
    """Everything the run left: verdicts, rule logs, sink, counters (named), the transaction log."""
    r: dict[str, Any] = {"status": (yield from status())}
    names = {regs.CYCLES: "cycles", regs.N_TXN: "n_txn", regs.DIGEST: "digest", regs.SB_CHECKED: "sb_checked",
             regs.SB_MISM: "sb_mism", regs.SB_UNCHECKED: "sb_unchecked", regs.EXP_MISM: "exp_mism",
             regs.RESP_MISM: "resp_mism", regs.FM_ADDR: "first_mismatch_addr", regs.FM_EXP: "first_mismatch_expected",
             regs.FM_GOT: "first_mismatch_got", regs.FM_TXN: "first_mismatch_txn"}
    for off, n in names.items():
        r[n] = yield ("r", off)
    for key, sel, data, rules in (("lite_rules", regs.LCHK_SEL, regs.LCHK_DATA, regs.LITE_RULES),
                                  ("stream_rules", regs.SCHK_SEL, regs.SCHK_DATA, regs.STREAM_RULES)):
        d: dict[str, Any] = {"counts": {}}
        for i, (rn, _, _) in enumerate(rules):
            d["counts"][rn] = yield from _sel(sel, data, i)
        for n, idx in regs.LOG_SEL.items():
            d[n] = yield from _sel(sel, data, idx)
        for n in ("first", "last"):
            v = d[n]
            d[n] = rules[v & 0xFF][0] if v >> 31 else None
        r[key] = d
    r["sink"] = {}
    for i, n in enumerate(regs.SINK):
        r["sink"][n] = yield from _sel(regs.SINK_SEL, regs.SINK_DATA, i)
    if counters:
        r["lite_mon"], r["stream_mon"] = {}, {}
        for i, n in enumerate(regs.lite_mon_names()):
            r["lite_mon"][n] = yield from _sel(regs.LMON_SEL, regs.LMON_DATA, i)
        for i, n in enumerate(regs.stream_mon_names()):
            r["stream_mon"][n] = yield from _sel(regs.SMON_SEL, regs.SMON_DATA, i)
    n = min(r["n_txn"], 256) if log_entries is None else min(log_entries, r["n_txn"], 256)
    raw = []
    for e in range(n):
        ws = []
        for k in range(3):
            yield ("w", regs.LOG_ADDR, (e << 2) | k)
            ws.append((yield ("r", regs.LOG_DATA)))
        raw.append(tuple(ws))
    r["log_raw"] = raw
    r["log"] = model.decode_log(raw)
    if r["n_txn"] <= 256:
        r["digest_check"] = (model.digest(raw) == r["digest"])
    return r


def run_program(prog: Program, capture: bool = True, log_entries: int | None = None, counters: bool = True,
                sleep: Callable[[], Any] | None = None) -> Op:
    """setup, arm the capture, start, wait, results (and the capture if it triggered)."""
    yield from setup(prog)
    if capture:
        yield from arm_capture()
    yield from start()
    yield from wait_done(sleep=sleep)
    r = yield from results(log_entries, counters)
    if capture:
        r["capture"] = yield from read_capture()
    return r


# ---------------------------------------------------------------------------------------------------- executors
class SyncHost:
    """Run a host generator over the UART test shell (shell.host.fpga_shell.FpgaShell or anything with read/write)."""
    def __init__(self, sh: Any) -> None:
        self.sh, self.accesses = sh, 0

    def run(self, gen: Op) -> Any:
        val = None
        try:
            while True:
                op = gen.send(val)
                val = None
                if op[0] == "w":
                    self.sh.write(regs.WINDOW + op[1], op[2] & 0xFFFF_FFFF)
                elif op[0] == "r":
                    val = self.sh.read(regs.WINDOW + op[1])
                elif op[0] == "sleep":
                    time.sleep(0.01)
                self.accesses += op[0] in ("w", "r")
        except StopIteration as e:
            return e.value


async def arun(gen: Op, bfm: Any) -> Any:
    """Run a host generator in cocotb over shell/tests/window_bfm.WindowBfm (window offsets)."""
    val = None
    try:
        while True:
            op = gen.send(val)
            val = None
            if op[0] == "w":
                await bfm.write(op[1], op[2] & 0xFFFF_FFFF)
            elif op[0] == "r":
                val = await bfm.read(op[1])
    except StopIteration as e:
        return e.value
