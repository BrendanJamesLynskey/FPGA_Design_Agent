"""Red Pitaya register windows and the register maps of the two custom instruments (brief 225). Standard library only: the owner copies this file to the board.

The shell gives a design one 1 MiB slot of the PS AXI GP0 window (slot 7: ``0x40700000``, see ``boards/redpitaya_stemlab_125_14/README.md``). A
:class:`Window` reads and writes 32-bit words in it by byte offset. Two implementations:

* :class:`MemWindow` maps ``/dev/mem`` on the board (the same mapping Red Pitaya's own ``monitor`` utility makes). It exists only on the board; building one
  anywhere else fails with a plain message, and nothing in the agent or the tests ever builds one.
* :class:`MockWindow` stands in for it from a behavioural model (``hil/redpitaya_models.py``). Readings through it are never evidence.

Neither reads an address the map does not list: a read of an unmapped word in the shell answers with a bus error, and what the PS does with that error is not
documented, so the check scripts stay inside the map.

The register maps below are the single source of the instruments' register tables: the spec text, the check scripts, the mock models and the datasheet
text (:func:`datasheet`) are made from them, and a test compares each against the others.
"""

from __future__ import annotations

import mmap
import os
import struct
from dataclasses import dataclass
from typing import Callable, Protocol

SLOT_BASE = 0x40700000          # system-bus slot 7 of shell v0.94: the first byte of the user block
SLOT_BASES = {7: 0x40700000, 6: 0x40600000}      # slot 6 is the second block position of tools/rp_shell.py
SLOT_SIZE = 0x100000            # 1 MiB per slot


class WindowError(RuntimeError):
    """An access outside the register map, or a window that cannot be opened here."""


class Window(Protocol):
    def read(self, offset: int) -> int: ...
    def write(self, offset: int, value: int) -> None: ...


class MemWindow:
    """The user block's slot through ``/dev/mem`` (root, on the Red Pitaya, with the design loaded). Not constructible off the board."""

    def __init__(self, base: int = SLOT_BASE, size: int = 0x1000, dev: str = "/dev/mem") -> None:
        if not os.path.exists(dev):
            raise WindowError(f"{dev} does not exist: MemWindow works only on the Red Pitaya itself, as root")
        self._fd = os.open(dev, os.O_RDWR | os.O_SYNC)
        self._map = mmap.mmap(self._fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
        self.size = size

    def read(self, offset: int) -> int:
        if offset % 4 or not 0 <= offset < self.size:
            raise WindowError(f"offset {offset:#x} is not a word inside the mapped {self.size:#x} bytes")
        return struct.unpack_from("<I", self._map, offset)[0]

    def write(self, offset: int, value: int) -> None:
        if offset % 4 or not 0 <= offset < self.size:
            raise WindowError(f"offset {offset:#x} is not a word inside the mapped {self.size:#x} bytes")
        struct.pack_into("<I", self._map, offset, value & 0xFFFFFFFF)

    def close(self) -> None:
        self._map.close()
        os.close(self._fd)


class MockWindow:
    """A window backed by a model with ``read(offset)`` and ``write(offset, value)``. ``log`` keeps every access, in order, for a test or a dry-run record."""

    mock = True

    def __init__(self, model) -> None:
        self.model, self.log = model, []

    def read(self, offset: int) -> int:
        v = self.model.read(offset)
        self.log.append(("r", offset, v))
        return v

    def write(self, offset: int, value: int) -> None:
        self.log.append(("w", offset, value & 0xFFFFFFFF))
        self.model.write(offset, value & 0xFFFFFFFF)


@dataclass(frozen=True)
class Reg:
    name: str
    offset: int
    access: str                  # RO, RW (W1P: a write of 1 to a bit acts once and the bit reads 0 afterwards, described in ``doc``)
    reset: int
    doc: str


@dataclass(frozen=True)
class RegMap:
    block: str                   # block name, as in the spec
    block_id: int                # value of the ID register
    regs: tuple[Reg, ...]
    notes: tuple[str, ...]       # behaviour a user could guess wrong, one per line (the datasheet prints them)

    def by_name(self, n: str) -> Reg:
        return next(r for r in self.regs if r.name == n)

    def offsets(self) -> list[int]:
        return [r.offset for r in self.regs]


COMMON_NOTES = (
    "Registers are 32 bits on 4-byte steps from the base of the slot the block sits in: 0x40700000 for slot 7 and 0x40600000 for slot 6 (the shell build says which); the offsets below are from that base.",
    "An offset with no register, and any offset from the end of the map to 0xFFFFF, answers with a bus error (the shell's err line) and reads 0. Do not read them from Linux: "
    "what the PS does with the error is not documented. A write to a read-only register is ignored and answers with an error.",
    "Reset (the shell's adc_rstn, released some cycles after the PLL locks) returns every register to its reset value. A power cycle or a reload of the factory image ends the design.",
    "Reads have no side effects. A write takes effect on the next adc_clk cycle (125 MHz); the register bus runs on the same clock, so no read-back delay is needed.",
    "Every signed 14-bit register (thresholds, levels, pattern samples) takes the low 14 bits of the 32-bit write as a two's-complement number and reads back sign-extended to 32 bits; a write of the 32-bit word -4000 (0xFFFFF060) and of 0x00003060 are the same. Bits 31 to 14 of a write are ignored.",
)

FREQCOUNT = RegMap("rp_freqcount", 0xFDA10101, (
    Reg("ID", 0x00, "RO", 0xFDA10101, "block identifier"),
    Reg("SCRATCH", 0x04, "RW", 0, "32 bits, reads back what was written"),
    Reg("CTRL", 0x08, "RW", 0, "bit 0 START (W1P: a write of 1 starts one gate when not BUSY, ignored while BUSY; reads 0); bit 1 CONT (a new gate starts as soon as one ends)"),
    Reg("GATE_LEN", 0x0C, "RW", 125_000_000, "gate length in adc_clk cycles; a write below 1000 stores 1000; the change applies to the next gate"),
    Reg("THR_HIGH", 0x10, "RW", 256, "Schmitt trigger upper threshold, signed 14 bit (low 14 bits of the write, read back sign-extended): +-8192 is +-full scale"),
    Reg("THR_LOW", 0x14, "RW", 0xFFFFFF00, "Schmitt trigger lower threshold, signed 14 bit; reset -256"),
    Reg("STATUS", 0x18, "RO", 0, "bit 0 BUSY; bit 1 DONE (cleared by START, set with the result registers); bit 2 FEW_EDGES (fewer than 2 edges in the last gate: SPAN is not valid); "
                                 "bit 3 BAD_THRESH (THR_HIGH <= THR_LOW: no edge is counted)"),
    Reg("EDGES", 0x1C, "RO", 0, "rising edges (a crossing of THR_HIGH after the signal was at or below THR_LOW) counted on IN1 in the last completed gate"),
    Reg("GATE_ACTUAL", 0x20, "RO", 0, "adc_clk cycles in the last completed gate; equals the GATE_LEN in force when it started"),
    Reg("SPAN", 0x24, "RO", 0, "adc_clk cycles from the first to the last counted rising edge of the last gate (valid when EDGES >= 2)"),
    Reg("MEAS_DONE", 0x28, "RO", 0, "number of completed gates since reset (wraps)"),
), COMMON_NOTES + (
    "The input is IN1 of the shell, 14-bit signed. On jumper LV full scale is +-1 V (one count is about 122 uV); on HV +-20 V. Thresholds are in counts, not volts.",
    "Gate counting: f = EDGES / (GATE_ACTUAL / 125 MHz). Reciprocal: f = (EDGES - 1) * 125 MHz / SPAN. Both are as accurate as the board's 125 MHz oscillator, whose error is not stated by the vendor.",
    "A START while BUSY is ignored; STATUS.DONE stays set from the end of one gate to the START of the next; with CONT set DONE stays set and the registers change at the end of each gate "
    "(read EDGES, GATE_ACTUAL and SPAN of one gate together by checking MEAS_DONE before and after: they must match).",
))

PATGEN = RegMap("rp_patgen", 0xFDA10201, (
    Reg("ID", 0x00, "RO", 0xFDA10201, "block identifier"),
    Reg("SCRATCH", 0x04, "RW", 0, "32 bits, reads back what was written"),
    Reg("CTRL", 0x08, "RW", 0, "bit 0 START (W1P: starts the sequence when not RUNNING; ignored while RUNNING); bit 1 STOP (W1P: ends the sequence at once and returns OUT1 to 0); bit 2 CONT (repeat until STOP)"),
    Reg("MODE", 0x0C, "RW", 0, "0 pulse: LEVEL_HI for WIDTH cycles then LEVEL_LO for the rest of each PERIOD; 1 pattern: PAT_LEN samples, each held SAMPLE_DIV cycles, repeated; other values store as 0"),
    Reg("PERIOD", 0x10, "RW", 1250, "pulse period in adc_clk cycles, 2 to 2^32-1 (a write below 2 stores 2); default 1250 is 100 kHz"),
    Reg("WIDTH", 0x14, "RW", 625, "cycles of LEVEL_HI in each period, 1 to PERIOD-1 (a write outside stores the nearest legal value at the next START)"),
    Reg("LEVEL_HI", 0x18, "RW", 2048, "signed 14 bit, counts: the low 14 bits of the write are the two's-complement value (write -4000 as 0x00003060, or any word whose low 14 bits are that), read back sign-extended to 32 bits; +-8192 is +-1 V into 50 ohm on OUT1; reset +2048 (+0.25 V)"),
    Reg("LEVEL_LO", 0x1C, "RW", 0, "signed 14 bit, counts, same write and read-back convention as LEVEL_HI; reset 0"),
    Reg("COUNT", 0x20, "RW", 1, "periods (pulse) or pattern passes (pattern) to emit when CONT is 0, 1 to 65535 (a write of 0 stores 1)"),
    Reg("LIMIT", 0x24, "RW", 4096, "ceiling on the magnitude of every level and sample sent to OUT1, in counts; a write above 7372 (0.9 V) stores 7372; reset 4096 (0.5 V)"),
    Reg("STATUS", 0x28, "RO", 0, "bit 0 RUNNING; bit 1 DONE (cleared by START, set when COUNT periods have been emitted or STOP was written); bit 2 CLAMPED (a level or sample exceeded LIMIT since START and was cut to it)"),
    Reg("PERIODS_DONE", 0x2C, "RO", 0, "periods or passes completed since START"),
    Reg("PAT_LEN", 0x30, "RW", 16, "pattern samples used, 1 to 16 (a write of 0 stores 1, above 16 stores 16)"),
    Reg("SAMPLE_DIV", 0x34, "RW", 1, "adc_clk cycles each pattern sample is held, 1 to 65535 (a write of 0 stores 1)"),
) + tuple(Reg(f"PAT{i}", 0x40 + 4 * i, "RW", 0, f"pattern sample {i}, signed 14 bit counts, same write and read-back convention as LEVEL_HI") for i in range(16)), COMMON_NOTES + (
    "OUT1 is the shell's DAC channel A; OUT2 (channel B) is not driven by this block (the factory ASG and PID are idle in this image), so it stays at 0.",
    "Every level and every pattern sample is cut to +-LIMIT on its way to the DAC, whatever the registers hold; the cut sets STATUS.CLAMPED. The output is 0 at reset, after STOP and when the sequence is done.",
    "Counts to volts: the DAC takes 14 bits for +-1 V into 50 ohm (8192 counts per volt). Into a high-impedance input the original generation's swing is not stated: start small and look.",
    "START with WIDTH, PERIOD or LEVEL values outside their limits does not fail: the nearest legal value is used and nothing is reported except through the registers' read-back.",
))

MAPS = {"rp_freqcount": FREQCOUNT, "rp_patgen": PATGEN}


def sext14(v: int) -> int:
    v &= 0x3FFF
    return v - 0x4000 if v & 0x2000 else v


def datasheet(m: RegMap) -> str:
    """The register table and the behaviour notes of a block, as Markdown, made from the map (so the text cannot drift from the maps the tests use)."""
    out = [f"### {m.block}: registers (offsets from the block's slot base: 0x40700000 for slot 7, 0x40600000 for slot 6)", "", "| Offset | Name | Access | Reset | Meaning |", "|---|---|---|---|---|"]
    for r in m.regs:
        out.append(f"| 0x{r.offset:02X} | {r.name} | {r.access} | 0x{r.reset:08X} | {r.doc} |")
    out += ["", "Behaviour a user could guess wrong:", ""] + [f"- {n}" for n in m.notes]
    return "\n".join(out) + "\n"


def read_all(w: Window, m: RegMap) -> dict[str, int]:
    return {r.name: w.read(r.offset) for r in m.regs}
