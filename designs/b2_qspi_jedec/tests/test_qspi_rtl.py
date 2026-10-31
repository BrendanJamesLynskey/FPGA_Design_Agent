"""The QSPI self-check can only read the flash's ID.

1. Source checks on designs/b2_qspi_jedec/rtl/*.sv: the only opcode is the constant RDID = 8'h9F;
   no 8-bit hex literal anywhere in the RTL equals a write, erase, program, register-write, OTP,
   protection or reset opcode of the S25FL128S/S25FL127S; the command shifter is loaded only from
   RDID; DQ0 is driven only from that shifter; qspi_rdid has no multi-bit input (nothing can carry
   a command in).
2. Simulation (cocotb + Icarus) against a flash model that decodes every command it receives.
"""

from __future__ import annotations

import re
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
RTL = sorted((DESIGN / "rtl").glob("*.sv"))

# Every opcode in S25FL128S Table 53 (Rev. *P) and S25FL127S (Rev. 11) that writes, erases, programs,
# changes a register or protection, or resets the device. Read-only opcodes (03, 05, 07, 0B, 35, 9F,
# ...) are not listed.
FORBIDDEN = {
    0x01: "WRR", 0x02: "PP", 0x04: "WRDI", 0x06: "WREN", 0x12: "4PP", 0x15: "ABWR", 0x17: "BRWR",
    0x20: "P4E", 0x21: "4P4E", 0x2F: "ASPP", 0x30: "CLSR", 0x32: "QPP", 0x34: "4QPP", 0x38: "QPP",
    0x42: "OTPP", 0x43: "PNVDLR", 0x4A: "WVDLR", 0x60: "BE", 0x75: "ERSP", 0x7A: "ERRS", 0x85: "PGSP",
    0x8A: "PGRS", 0xA6: "PLBWR", 0xB9: "BRAC", 0xC7: "BE", 0xD8: "SE", 0xDC: "4SE", 0xE1: "DYBWR",
    0xE3: "PPBP", 0xE4: "PPBE", 0xE8: "PASSP", 0xE9: "PASSU", 0xF0: "RESET", 0xFF: "MBR",
}


def strip_comments(text: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)


def code() -> dict[str, str]:
    return {f.name: strip_comments(f.read_text()) for f in RTL}


def test_only_opcode_is_rdid() -> None:
    src = code()["qspi_rdid.sv"]
    assert re.findall(r"localparam\s+logic\s*\[7:0\]\s*(\w+)\s*=\s*8'h([0-9A-Fa-f]{2})", src) == [("RDID", "9F")]


def test_no_forbidden_opcode_literal_anywhere() -> None:
    for name, src in code().items():
        for lit in re.findall(r"8'h([0-9A-Fa-f]{2})", src):
            assert int(lit, 16) not in FORBIDDEN, f"{name}: 8'h{lit} is {FORBIDDEN[int(lit, 16)]}"


def test_command_shifter_and_dq0_sources() -> None:
    src = code()["qspi_rdid.sv"]
    loads = re.findall(r"cmd_sh\s*<=\s*([^;]+);", src)
    assert loads and set(x.strip() for x in loads) <= {"RDID", "'0", "{cmd_sh[6:0], 1'b0}"}, loads
    assert re.findall(r"assign\s+dq0\s*=\s*([^;]+);", src) == ["cmd_sh[7]"]
    top = code()["b2_qspi_jedec_top.sv"]
    assert re.findall(r"assign\s+QSPI_DQ0\s*=\s*([^;]+);", top) == ["dq0"]


def test_qspi_rdid_has_no_multibit_input() -> None:
    src = code()["qspi_rdid.sv"]
    ports = re.search(r"module\s+qspi_rdid\s*#\(.*?\)\s*\((.*?)\);", src, re.S).group(1)
    inputs = re.findall(r"input\s+logic\s*(\[[^\]]+\])?\s*(\w+)", ports)
    assert inputs and all(w == "" for w, _ in inputs), inputs
    assert sorted(n for _, n in inputs) == ["clk", "dq1", "go", "rst"]


def test_qspi_regs_against_flash_model() -> None:
    sources = [s for s in RTL if not s.name.endswith("_top.sv")] + [HERE / "tb_qspi.sv"]
    cocotb_run.run("b2_qspi_jedec", "tb_qspi", sources, "qspi_cocotb", HERE, parameters={"HALF": 4})
