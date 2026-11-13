#!/usr/bin/env python3
"""Register-map single source (brief 64A): one YAML file generates the AXI4-Lite register block (SystemVerilog), the C
header, the Python host driver and the markdown documentation, so hardware, software and documentation cannot drift.

    python3 -m hwsw.regmap validate hwsw/examples/demo_accel.yaml          # schema and layout checks only
    python3 -m hwsw.regmap gen hwsw/examples/demo_accel.yaml --out DIR      # write the four outputs
    python3 -m hwsw.regmap check hwsw/examples/demo_accel.yaml --out DIR    # outputs current, and all four agree

`check` regenerates every output and compares it with the file on disk (drift), then reads each output back on its
own terms and compares what it says with the YAML (agreement): the C header through a probe program compiled with the
host C compiler, the Python driver by importing it, the markdown by parsing its tables, and the SystemVerilog by its
port list and its address and reset constants. What the register block *does* (access types, byte strobes, reset
values, unmapped responses, the interrupt) is checked in simulation: hwsw/tests/test_64a_regmap_rtl.py drives it with
the generated Python driver and a C driver over a model bus, with the brief 59A AXI4-Lite checker on the wires.

The format, the access types and the generated names are in docs/hwsw.md. Plain Python and PyYAML; `check` also needs
a C compiler (gcc or cc) for the header probe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pprint
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FORMAT = "regmap/1"
ACCESS = ("RW", "RO", "W1C", "W1S", "W1P")
ACCESS_TEXT = {
    "RW": "read/write: software writes the value; hardware sees it on an output",
    "RO": "read-only: the value comes from a hardware input (or is a constant); writes are ignored",
    "W1C": "write 1 to clear: hardware sets bits with a pulse input; software clears a bit by writing 1 to it; a set "
           "and a clear in the same clock leave the bit set (no event is lost)",
    "W1S": "write 1 to set: software sets bits by writing 1 (a doorbell); hardware clears them with a pulse input; a "
           "set and a clear in the same clock leave the bit set",
    "W1P": "write 1 to pulse: each bit written as 1 gives a one-clock pulse on an output; reads return 0",
}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
C_RESERVED = {"OFFSET", "RESET", "RW_MASK", "RO_MASK", "W1C_MASK", "W1S_MASK", "W1P_MASK"}   # register-level suffixes
MODEL_KEYS = {"regmap", "name", "version", "summary", "data_width", "addr_width", "unmapped", "interrupt", "registers"}
REG_KEYS = {"name", "offset", "summary", "fields"}
FIELD_KEYS = {"name", "lsb", "width", "access", "reset", "const", "summary"}


class RegmapError(ValueError):
    """The YAML breaks a rule of the format; the message lists every problem found."""


@dataclass(frozen=True)
class Field:
    name: str
    lsb: int
    width: int
    access: str
    reset: int = 0            # value after reset (RW, W1C, W1S); the constant for a RO constant; 0 otherwise
    const: bool = False       # RO only: the value is the constant `reset`, not a hardware input
    summary: str = ""

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.lsb

    @property
    def msb(self) -> int:
        return self.lsb + self.width - 1

    @property
    def hw_input(self) -> bool:
        return self.access == "RO" and not self.const


@dataclass(frozen=True)
class Register:
    name: str
    offset: int
    fields: tuple[Field, ...]
    summary: str = ""

    def mask(self, access: str) -> int:
        m = 0
        for f in self.fields:
            if f.access == access:
                m |= f.mask
        return m

    @property
    def reset(self) -> int:
        """What a read returns after reset with every hardware input low: RW/W1C/W1S reset values and RO constants."""
        v = 0
        for f in self.fields:
            if f.access in ("RW", "W1C", "W1S") or (f.access == "RO" and f.const):
                v |= f.reset << f.lsb
        return v


@dataclass(frozen=True)
class RegMap:
    name: str
    version: str
    summary: str
    addr_width: int
    unmapped: str
    registers: tuple[Register, ...]
    interrupt: dict | None = None
    data_width: int = 32
    sha256: str = field(default="", compare=False)

    @property
    def window_bytes(self) -> int:
        return 1 << self.addr_width

    def reg(self, name: str) -> Register:
        for r in self.registers:
            if r.name == name:
                return r
        raise KeyError(name)

    def canonical(self) -> dict:
        """The model as plain data, in a fixed order: what the hash covers and what every output must agree with."""
        return {
            "format": FORMAT, "name": self.name, "version": self.version, "data_width": self.data_width,
            "addr_width": self.addr_width, "unmapped": self.unmapped, "interrupt": self.interrupt,
            "registers": [{"name": r.name, "offset": r.offset, "reset": r.reset,
                           "fields": [{"name": f.name, "lsb": f.lsb, "width": f.width, "access": f.access,
                                       "reset": f.reset, "const": f.const} for f in r.fields]}
                          for r in self.registers],
        }


# ---- reading and validating ----------------------------------------------------------------------------------------
def _int(v, what: str, errs: list[str]) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        errs.append(f"{what}: {v!r} is not an integer")
        return None
    return v


def load(path: str | Path) -> RegMap:
    """Read and validate a regmap YAML file. Raises RegmapError with every problem found."""
    p = Path(path)
    try:
        d = yaml.safe_load(p.read_text())
    except yaml.YAMLError as ex:
        raise RegmapError(f"{p}: not valid YAML: {ex}") from None
    return from_dict(d, source=str(p))


def from_dict(d, source: str = "<dict>") -> RegMap:
    errs: list[str] = []
    if not isinstance(d, dict):
        raise RegmapError(f"{source}: the top level must be a mapping")
    extra = set(d) - MODEL_KEYS
    if extra:
        errs.append(f"unknown top-level keys {sorted(extra)}")
    if d.get("regmap") != 1:
        errs.append("regmap: must be 1 (the format version)")
    name = d.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        errs.append(f"name: {name!r} must be a lower-case identifier (letters, digits, _), starting with a letter")
        name = "invalid"
    if d.get("data_width", 32) != 32:
        errs.append("data_width: only 32 is supported")
    aw = _int(d.get("addr_width"), "addr_width", errs)
    if aw is not None and not 4 <= aw <= 32:
        errs.append(f"addr_width: {aw} must be 4..32 (the window is 2**addr_width bytes)")
    unmapped = d.get("unmapped", "slverr")
    if unmapped not in ("slverr", "okay"):
        errs.append(f"unmapped: {unmapped!r} must be slverr or okay")
    regs_in = d.get("registers")
    if not isinstance(regs_in, list) or not regs_in:
        errs.append("registers: must be a non-empty list")
        regs_in = []
    regs: list[Register] = []
    seen_off: dict[int, str] = {}
    seen_port: dict[str, str] = {}
    for i, r in enumerate(regs_in):
        if not isinstance(r, dict):
            errs.append(f"registers[{i}]: not a mapping")
            continue
        rn = r.get("name")
        where = f"register {rn or i}"
        extra = set(r) - REG_KEYS
        if extra:
            errs.append(f"{where}: unknown keys {sorted(extra)}")
        if not isinstance(rn, str) or not REG_RE.match(rn):
            errs.append(f"{where}: name must be upper-case (letters, digits, _), starting with a letter")
            rn = f"R{i}"
        if any(x.name == rn for x in regs):
            errs.append(f"{where}: duplicate register name")
        off = _int(r.get("offset"), f"{where}.offset", errs)
        if off is not None:
            if off % 4:
                errs.append(f"{where}: offset 0x{off:x} is not a multiple of 4 (32-bit registers)")
            if aw is not None and not 0 <= off <= (1 << aw) - 4:
                errs.append(f"{where}: offset 0x{off:x} outside the 0x{1 << aw:x}-byte window (addr_width {aw})")
            # with 32-bit registers two registers overlap exactly when their words overlap
            if off // 4 in seen_off:
                errs.append(f"{where}: offset 0x{off:x} overlaps register {seen_off[off // 4]}")
            seen_off[off // 4] = rn
        fl = r.get("fields")
        if not isinstance(fl, list) or not fl:
            errs.append(f"{where}: fields must be a non-empty list")
            fl = []
        fields: list[Field] = []
        used = 0
        for j, f in enumerate(fl):
            if not isinstance(f, dict):
                errs.append(f"{where}.fields[{j}]: not a mapping")
                continue
            fn = f.get("name")
            fw = f"{where} field {fn or j}"
            extra = set(f) - FIELD_KEYS
            if extra:
                errs.append(f"{fw}: unknown keys {sorted(extra)}")
            if not isinstance(fn, str) or not REG_RE.match(fn):
                errs.append(f"{fw}: name must be upper-case (letters, digits, _), starting with a letter")
                fn = f"F{j}"
            if fn in C_RESERVED or any(fn.endswith("_" + s) for s in C_RESERVED):
                errs.append(f"{fw}: name clashes with a generated register-level name ({', '.join(sorted(C_RESERVED))})")
            if any(x.name == fn for x in fields):
                errs.append(f"{fw}: duplicate field name in the register")
            lsb = _int(f.get("lsb"), f"{fw}.lsb", errs)
            width = _int(f.get("width"), f"{fw}.width", errs)
            acc = f.get("access")
            if acc not in ACCESS:
                errs.append(f"{fw}: access {acc!r} must be one of {', '.join(ACCESS)}")
            const = f.get("const")
            if lsb is None or width is None:
                continue
            if width < 1 or lsb < 0 or lsb + width > 32:
                errs.append(f"{fw}: bits [{lsb + width - 1}:{lsb}] are not inside [31:0]")
                continue
            m = ((1 << width) - 1) << lsb
            if used & m:
                other = [x.name for x in fields if x.mask & m]
                errs.append(f"{fw}: bits [{lsb + width - 1}:{lsb}] overlap field {', '.join(other)}")
            used |= m
            reset = f.get("reset", 0)
            is_const = False
            if const is not None:
                if acc != "RO":
                    errs.append(f"{fw}: const is allowed only on a RO field")
                if "reset" in f:
                    errs.append(f"{fw}: give const or reset, not both (a constant's value is its reset)")
                reset, is_const = const, True
            elif acc == "RO" and "reset" in f:
                errs.append(f"{fw}: a RO field without const reads a hardware input; it has no reset value")
            if acc == "W1P" and f.get("reset", 0) != 0:
                errs.append(f"{fw}: a W1P field reads 0; its reset must be 0")
            rv = _int(reset, f"{fw}.{'const' if is_const else 'reset'}", errs)
            if rv is None:
                continue
            if not 0 <= rv < (1 << width):
                errs.append(f"{fw}: value 0x{rv:x} does not fit in {width} bit{'s' if width > 1 else ''}")
                continue
            if acc in ACCESS:
                fields.append(Field(fn, lsb, width, acc, rv, is_const, str(f.get("summary", ""))))
                port = f"{rn}_{fn}".lower()
                if port in seen_port:
                    errs.append(f"{fw}: port name {port} is also made by {seen_port[port]}")
                seen_port[port] = f"{rn}.{fn}"
        if off is not None:
            regs.append(Register(rn, off, tuple(sorted(fields, key=lambda x: x.lsb)), str(r.get("summary", ""))))
    # the C header's names: a register's and a field's names must not meet (register A_B field C, register A field B_C)
    cnames: dict[str, str] = {}
    for r in regs:
        own = [f"{r.name}_{x}" for x in ("OFFSET", "RESET", *(f"{a}_MASK" for a in ACCESS))]
        own += [f"{r.name}_{f.name}_{x}" for f in r.fields for x in ("SHIFT", "WIDTH", "MASK", "RESET", "ACCESS")]
        for n in own:
            if n in cnames and cnames[n] != r.name:
                errs.append(f"register {r.name}: the C name {m_name(name)}_{n} is also made by register {cnames[n]}")
            cnames.setdefault(n, r.name)
    irq = d.get("interrupt")
    if irq is not None:
        if not isinstance(irq, dict) or set(irq) != {"status", "enable"}:
            errs.append("interrupt: must be {status: <W1C register>, enable: <RW register>}")
            irq = None
        else:
            st = next((r for r in regs if r.name == irq["status"]), None)
            en = next((r for r in regs if r.name == irq["enable"]), None)
            if st is None or en is None:
                errs.append(f"interrupt: register {irq['status'] if st is None else irq['enable']} not declared")
            else:
                if any(f.access != "W1C" for f in st.fields):
                    errs.append(f"interrupt: every field of status register {st.name} must be W1C")
                if any(f.access != "RW" for f in en.fields):
                    errs.append(f"interrupt: every field of enable register {en.name} must be RW")
                if st.mask("W1C") & ~en.mask("RW"):
                    errs.append(f"interrupt: status bits 0x{st.mask('W1C') & ~en.mask('RW'):08x} of {st.name} have no "
                                f"enable bit in {en.name} (the same bit positions)")
            irq = {"status": irq["status"], "enable": irq["enable"]}
    if errs:
        raise RegmapError(f"{source}:\n  " + "\n  ".join(errs))
    m = RegMap(name, str(d.get("version", "0.0.0")), str(d.get("summary", "")), aw, unmapped,
               tuple(sorted(regs, key=lambda x: x.offset)), irq)
    h = hashlib.sha256(json.dumps(m.canonical(), sort_keys=True).encode()).hexdigest()
    return RegMap(m.name, m.version, m.summary, m.addr_width, m.unmapped, m.registers, m.interrupt, 32, h)


# ---- names ---------------------------------------------------------------------------------------------------------
def m_name(name: str) -> str:
    return name.upper()


def port(r: Register, f: Field) -> tuple[str, str, int]:
    """(direction, name, width) of a field's hardware port, or ('', '', 0) for a RO constant."""
    base = f"{r.name}_{f.name}".lower()
    if f.access == "RW":
        return ("output", f"{base}_o", f.width)
    if f.access == "RO":
        return ("", "", 0) if f.const else ("input", f"{base}_i", f.width)
    if f.access == "W1C":
        return ("input", f"{base}_set_i", f.width)
    if f.access == "W1S":
        return ("input", f"{base}_clr_i", f.width)
    return ("output", f"{base}_pulse_o", f.width)


def ports(m: RegMap) -> list[tuple[str, str, int]]:
    """Every field port, in register then bit order; W1C and W1S fields also drive their value out."""
    out = []
    for r in m.registers:
        for f in r.fields:
            p = port(r, f)
            if p[1]:
                out.append(p)
            if f.access in ("W1C", "W1S"):
                out.append(("output", f"{r.name}_{f.name}".lower() + "_o", f.width))
    if m.interrupt:
        out.append(("output", "irq_o", 1))
    return out


def file_names(m: RegMap) -> dict[str, str]:
    return {k: f"{m.name}_regs.{k}" for k in ("sv", "h", "py", "md")}


def _banner(m: RegMap, c: str) -> str:
    return (f"{c} Generated by hwsw/regmap.py ({FORMAT}) from regmap {m.name} {m.version}; model sha256 {m.sha256}.\n"
            f"{c} Do not edit: change the YAML and run python3 -m hwsw.regmap gen.\n")


def _w(width: int) -> str:
    return "" if width == 1 else f"[{width - 1}:0] "


# ---- SystemVerilog -------------------------------------------------------------------------------------------------
def emit_sv(m: RegMap) -> str:
    aw = m.addr_width
    resp_unmapped = "2'b10" if m.unmapped == "slverr" else "2'b00"
    L = [_banner(m, "//").rstrip("\n"),
         f"// {m.name}_regs: AXI4-Lite register block. {m.summary}".rstrip(),
         "//",
         "// AXI4-Lite slave, 32-bit data, one outstanding read and one outstanding write. AW and W are captured",
         "// independently (either may come first); the write commits when both are held, then BVALID stays high until",
         "// BREADY. Byte strobes (WSTRB) are honoured bit by bit. Read data is registered at the AR handshake.",
         f"// Unmapped addresses: {'SLVERR' if m.unmapped == 'slverr' else 'OKAY'} on both channels, reads return 0.",
         f"// Only address bits [{aw - 1}:2] are decoded: the window repeats every 0x{m.window_bytes:x} bytes.",
         "// Writes to read-only bits are ignored with OKAY. Reset: synchronous, active low (aresetn).",
         "",
         f"module {m.name}_regs (",
         "    input  logic        aclk,",
         "    input  logic        aresetn,",
         f"    input  logic [{aw - 1}:0] s_axil_awaddr,",
         "    input  logic [2:0]  s_axil_awprot,",
         "    input  logic        s_axil_awvalid,",
         "    output logic        s_axil_awready,",
         "    input  logic [31:0] s_axil_wdata,",
         "    input  logic [3:0]  s_axil_wstrb,",
         "    input  logic        s_axil_wvalid,",
         "    output logic        s_axil_wready,",
         "    output logic [1:0]  s_axil_bresp,",
         "    output logic        s_axil_bvalid,",
         "    input  logic        s_axil_bready,",
         f"    input  logic [{aw - 1}:0] s_axil_araddr,",
         "    input  logic [2:0]  s_axil_arprot,",
         "    input  logic        s_axil_arvalid,",
         "    output logic        s_axil_arready,",
         "    output logic [31:0] s_axil_rdata,",
         "    output logic [1:0]  s_axil_rresp,",
         "    output logic        s_axil_rvalid,",
         "    input  logic        s_axil_rready" + ("," if ports(m) else "")]
    pl = ports(m)
    for i, (d, n, w) in enumerate(pl):
        L.append(f"    {d:6} logic {_w(w):8}{n}{',' if i < len(pl) - 1 else ''}")
    L += [");", ""]
    L.append("    // the address map and reset values (python3 -m hwsw.regmap check reads these back)")
    for r in m.registers:
        L.append(f"    localparam logic [{aw - 3}:0] ADDR_{r.name} = {aw - 2}'h{r.offset >> 2:x};   // byte offset 0x{r.offset:03x}")
    L.append("    /* verilator lint_off UNUSEDPARAM */   // registers with only RO or W1P fields have no stored reset")
    for r in m.registers:
        L.append(f"    localparam logic [31:0] RESET_{r.name} = 32'h{r.reset:08x};")
    L.append("    /* verilator lint_on UNUSEDPARAM */")
    L += ["    localparam logic [1:0] RESP_OKAY = 2'b00;",
          f"    localparam logic [1:0] RESP_UNMAPPED = {resp_unmapped};",
          "",
          "    // ---- write channel: capture AW and W independently, commit when both are held ----",
          "    logic            aw_got, w_got;",
          f"    logic [{aw - 3}:0]  aw_word;",
          "    logic [31:0]     w_data, w_bits;",
          "    logic [3:0]      w_strb;",
          "    logic            wr_commit, wr_hit;",
          "    assign s_axil_awready = !aw_got && !s_axil_bvalid;",
          "    assign s_axil_wready  = !w_got && !s_axil_bvalid;",
          "    assign wr_commit      = aw_got && w_got && !s_axil_bvalid;",
          "    // the bits this write may change: its byte lanes",
          "    assign w_bits = {{8{w_strb[3]}}, {8{w_strb[2]}}, {8{w_strb[1]}}, {8{w_strb[0]}}};",
          "",
          "    always_ff @(posedge aclk) begin",
          "        if (!aresetn) begin",
          "            aw_got <= 1'b0;",
          "            w_got <= 1'b0;",
          "            aw_word <= '0;",
          "            w_data <= '0;",
          "            w_strb <= '0;",
          "            s_axil_bvalid <= 1'b0;",
          "            s_axil_bresp <= RESP_OKAY;",
          "        end else begin",
          "            if (s_axil_awvalid && s_axil_awready) begin",
          "                aw_got <= 1'b1;",
          f"                aw_word <= s_axil_awaddr[{aw - 1}:2];",
          "            end",
          "            if (s_axil_wvalid && s_axil_wready) begin",
          "                w_got <= 1'b1;",
          "                w_data <= s_axil_wdata;",
          "                w_strb <= s_axil_wstrb;",
          "            end",
          "            if (wr_commit) begin",
          "                aw_got <= 1'b0;",
          "                w_got <= 1'b0;",
          "                s_axil_bvalid <= 1'b1;",
          "                s_axil_bresp <= wr_hit ? RESP_OKAY : RESP_UNMAPPED;",
          "            end else if (s_axil_bvalid && s_axil_bready) begin",
          "                s_axil_bvalid <= 1'b0;",
          "            end",
          "        end",
          "    end",
          ""]
    # write decode
    L.append("    // write decode: one strobe per register")
    wregs = [r for r in m.registers if any(f.access != "RO" for f in r.fields)]
    for r in wregs:
        L.append(f"    logic wr_{r.name.lower()};")
    L.append("    always_comb begin")
    L.append("        wr_hit = 1'b0;")
    for r in wregs:
        L.append(f"        wr_{r.name.lower()} = 1'b0;")
    L.append("        if (wr_commit) begin")
    L.append("            case (aw_word)")
    for r in m.registers:
        if r in wregs:
            L.append(f"                ADDR_{r.name}: begin wr_hit = 1'b1; wr_{r.name.lower()} = 1'b1; end")
        else:
            L.append(f"                ADDR_{r.name}: wr_hit = 1'b1;   // read-only: the write is ignored")
    L.append("                default: wr_hit = 1'b0;")
    L.append("            endcase")
    L.append("        end")
    L.append("    end")
    L.append("")
    # field storage
    L.append("    // ---- field storage ----")
    for r in m.registers:
        for f in r.fields:
            base = f"{r.name}_{f.name}".lower()
            sl = f"[{f.msb}:{f.lsb}]"
            wr = f"wr_{r.name.lower()}"
            rst = f"RESET_{r.name}{sl}"
            if f.access == "RO":
                continue
            L.append(f"    // {r.name}.{f.name} {sl} {f.access}" + (f": {f.summary}" if f.summary else ""))
            if f.access == "RW":
                L += [f"    always_ff @(posedge aclk) begin",
                      f"        if (!aresetn) {base}_o <= {rst};",
                      f"        else if ({wr}) {base}_o <= ({base}_o & ~w_bits{sl}) | (w_data{sl} & w_bits{sl});",
                      f"    end"]
            elif f.access == "W1C":
                L += [f"    always_ff @(posedge aclk) begin",
                      f"        if (!aresetn) {base}_o <= {rst};",
                      f"        else {base}_o <= ({base}_o & ~({wr} ? w_data{sl} & w_bits{sl} : {f.width}'h0)) | {base}_set_i;",
                      f"    end"]
            elif f.access == "W1S":
                L += [f"    always_ff @(posedge aclk) begin",
                      f"        if (!aresetn) {base}_o <= {rst};",
                      f"        else {base}_o <= ({base}_o & ~{base}_clr_i) | ({wr} ? w_data{sl} & w_bits{sl} : {f.width}'h0);",
                      f"    end"]
            elif f.access == "W1P":
                L += [f"    always_ff @(posedge aclk) begin",
                      f"        if (!aresetn) {base}_pulse_o <= {f.width}'h0;",
                      f"        else {base}_pulse_o <= {wr} ? w_data{sl} & w_bits{sl} : {f.width}'h0;",
                      f"    end"]
    L.append("")
    # read values
    L.append("    // ---- read path: the value of each register as software sees it ----")
    for r in m.registers:
        terms = []
        for f in r.fields:
            base = f"{r.name}_{f.name}".lower()
            if f.access == "RO":
                src = f"{f.width}'h{f.reset:x}" if f.const else f"{base}_i"
            elif f.access == "W1P":
                continue
            else:
                src = f"{base}_o"
            terms.append((f.lsb, f.width, src))
        L.append(f"    logic [31:0] rd_{r.name.lower()};")
        L.append("    always_comb begin")
        L.append(f"        rd_{r.name.lower()} = 32'h0;")
        for lsb, w, src in terms:
            L.append(f"        rd_{r.name.lower()}[{lsb + w - 1}:{lsb}] = {src};")
        L.append("    end")
    L += ["    logic [31:0] rd_value;",
          "    logic        rd_hit;",
          "    always_comb begin",
          "        rd_hit = 1'b1;",
          f"        case (s_axil_araddr[{aw - 1}:2])"]
    for r in m.registers:
        L.append(f"            ADDR_{r.name}: rd_value = rd_{r.name.lower()};")
    L += ["            default: begin rd_value = 32'h0; rd_hit = 1'b0; end",
          "        endcase",
          "    end",
          "    assign s_axil_arready = !s_axil_rvalid;",
          "    always_ff @(posedge aclk) begin",
          "        if (!aresetn) begin",
          "            s_axil_rvalid <= 1'b0;",
          "            s_axil_rdata <= 32'h0;",
          "            s_axil_rresp <= RESP_OKAY;",
          "        end else if (s_axil_arvalid && s_axil_arready) begin",
          "            s_axil_rvalid <= 1'b1;",
          "            s_axil_rdata <= rd_value;",
          "            s_axil_rresp <= rd_hit ? RESP_OKAY : RESP_UNMAPPED;",
          "        end else if (s_axil_rvalid && s_axil_rready) begin",
          "            s_axil_rvalid <= 1'b0;",
          "        end",
          "    end"]
    if m.interrupt:
        st, en = m.interrupt["status"], m.interrupt["enable"]
        L += ["",
              f"    // ---- interrupt: level, registered: any {st} bit whose {en} bit is set ----",
              "    always_ff @(posedge aclk) begin",
              "        if (!aresetn) irq_o <= 1'b0;",
              f"        else irq_o <= |(rd_{st.lower()} & rd_{en.lower()});",
              "    end"]
    L += ["",
          "    // AxPROT is accepted and not used; the unused address bits [1:0] are word-aligned by the protocol",
          "    logic unused_ok;",
          "    assign unused_ok = ^{s_axil_awprot, s_axil_arprot, s_axil_awaddr[1:0], s_axil_araddr[1:0]};",
          "endmodule", ""]
    return "\n".join(L)


# ---- C header ------------------------------------------------------------------------------------------------------
def emit_c(m: RegMap) -> str:
    P = m.name.upper()
    g = f"{P}_REGS_H"
    L = ["/*", _banner(m, " *").rstrip("\n"), f" * {m.name}: {m.summary}".rstrip(), " *",
         f" * Register offsets are bytes from the block's base address. For a field F of register R:",
         f" *   {P}_R_F_SHIFT, _WIDTH, _MASK (in place), _RESET (field value), _ACCESS ({P}_ACCESS_*).",
         f" * Register masks by access type: {P}_R_RW_MASK, _RO_MASK, _W1C_MASK, _W1S_MASK, _W1P_MASK.",
         " * Read-modify-write rule: write back only the RW bits of what you read (value & R_RW_MASK), then OR in the",
         " * W1C/W1S/W1P bits you mean to act on; writing back a W1C bit read as 1 clears an event you have not handled.",
         f" * Bus access goes through {P}_IO_READ32/{P}_IO_WRITE32 (volatile 32-bit loads and stores unless defined",
         " * before this header is included, e.g. by a co-simulation harness).",
         " */",
         f"#ifndef {g}", f"#define {g}", "", "#include <stdint.h>", "",
         f"#define {P}_REGMAP_SHA256 \"{m.sha256}\"",
         f"#define {P}_WINDOW_BYTES 0x{m.window_bytes:x}u", "",
         f"#define {P}_ACCESS_RW  0u", f"#define {P}_ACCESS_RO  1u", f"#define {P}_ACCESS_W1C 2u",
         f"#define {P}_ACCESS_W1S 3u", f"#define {P}_ACCESS_W1P 4u", ""]
    for r in m.registers:
        R = f"{P}_{r.name}"
        L.append(f"/* {r.name} @ 0x{r.offset:03x}" + (f": {r.summary}" if r.summary else "") + " */")
        L.append(f"#define {R}_OFFSET 0x{r.offset:03x}u")
        L.append(f"#define {R}_RESET 0x{r.reset:08x}u")
        for a in ACCESS:
            L.append(f"#define {R}_{a}_MASK 0x{r.mask(a):08x}u")
        for f in r.fields:
            F = f"{R}_{f.name}"
            L.append(f"#define {F}_SHIFT {f.lsb}u")
            L.append(f"#define {F}_WIDTH {f.width}u")
            L.append(f"#define {F}_MASK 0x{f.mask:08x}u")
            L.append(f"#define {F}_RESET 0x{f.reset:x}u")
            L.append(f"#define {F}_ACCESS {P}_ACCESS_{f.access}")
        L.append("")
    L += [f"/* field helpers: {P}_GET(R, F, word) extracts a field; {P}_PUT(R, F, v) places v in a field */",
          f"#define {P}_GET(R, F, word) (((uint32_t)(word) & {P}_##R##_##F##_MASK) >> {P}_##R##_##F##_SHIFT)",
          f"#define {P}_PUT(R, F, v) (((uint32_t)(v) << {P}_##R##_##F##_SHIFT) & {P}_##R##_##F##_MASK)",
          "",
          f"#ifndef {P}_IO_READ32",
          f"#define {P}_IO_READ32(addr) (*(volatile uint32_t *)(uintptr_t)(addr))",
          "#endif",
          f"#ifndef {P}_IO_WRITE32",
          f"#define {P}_IO_WRITE32(addr, v) (*(volatile uint32_t *)(uintptr_t)(addr) = (uint32_t)(v))",
          "#endif",
          "",
          f"static inline uint32_t {m.name}_read(uintptr_t base, uint32_t offset)",
          f"{{ return {P}_IO_READ32(base + offset); }}",
          f"static inline void {m.name}_write(uintptr_t base, uint32_t offset, uint32_t value)",
          f"{{ {P}_IO_WRITE32(base + offset, value); }}",
          "",
          f"#endif /* {g} */", ""]
    return "\n".join(L)


# ---- Python host driver --------------------------------------------------------------------------------------------
def emit_py(m: RegMap) -> str:
    table = {r.name: {"offset": r.offset, "reset": r.reset, "summary": r.summary,
                      "fields": {f.name: {"lsb": f.lsb, "width": f.width, "access": f.access, "reset": f.reset,
                                          "const": f.const} for f in r.fields}} for r in m.registers}
    cls = "".join(w.capitalize() for w in m.name.split("_")) + "Regs"
    body = f'''{_banner(m, "#")}"""Host driver for {m.name}: {m.summary}

Self-contained (standard library only), so it can be copied to the board. A bus is any object with
read32(offset) -> int and write32(offset, value), offsets in bytes from the block's base. {cls} is the
blocking driver; Async{cls} is the same driver over a bus whose methods are coroutines (a simulation bus).
MmapBus maps a UIO device or /dev/mem window.

Access rules (the same in the RTL, the C header and the documentation):
{chr(10).join(f"  {a:4} {t}" for a, t in ACCESS_TEXT.items())}
"""
from __future__ import annotations

NAME = {m.name!r}
REGMAP_SHA256 = {m.sha256!r}
WINDOW_BYTES = 0x{m.window_bytes:x}
UNMAPPED = {m.unmapped!r}
INTERRUPT = {m.interrupt!r}
REGISTERS = {pprint.pformat(table, sort_dicts=False, width=110)}


class RegisterError(Exception):
    """A request the register map does not allow (unknown name, read-only field, value too wide)."""


def field_mask(reg: str, field: str) -> int:
    f = _field(reg, field)
    return ((1 << f["width"]) - 1) << f["lsb"]


def access_mask(reg: str, access: str) -> int:
    """The bits of a register with one access type (RW, RO, W1C, W1S, W1P)."""
    m = 0
    for f in _reg(reg)["fields"].values():
        if f["access"] == access:
            m |= ((1 << f["width"]) - 1) << f["lsb"]
    return m


def get_field(reg: str, field: str, word: int) -> int:
    f = _field(reg, field)
    return (word >> f["lsb"]) & ((1 << f["width"]) - 1)


def put_field(reg: str, field: str, value: int, word: int = 0) -> int:
    """word with the field replaced by value (no bus access)."""
    f = _field(reg, field)
    if not 0 <= value < (1 << f["width"]):
        raise RegisterError(f"{{reg}}.{{field}}: {{value:#x}} does not fit in {{f['width']}} bits")
    m = field_mask(reg, field)
    return (word & ~m) | (value << f["lsb"])


def _reg(reg: str) -> dict:
    try:
        return REGISTERS[reg]
    except KeyError:
        raise RegisterError(f"{{NAME}} has no register {{reg!r}}") from None


def _field(reg: str, field: str) -> dict:
    try:
        return _reg(reg)["fields"][field]
    except KeyError:
        raise RegisterError(f"{{NAME}}.{{reg}} has no field {{field!r}}") from None


def _plan(reg: str, field: str, value: int, want: str) -> tuple[bool, int]:
    """(needs_read, bits): the write for an action on one field. RW bits of the same register must be written
    back unchanged, so a write to a register that holds RW bits starts from a read of it; W1C/W1S/W1P bits of
    other fields are written as 0, so nothing else is cleared, set or pulsed."""
    f = _field(reg, field)
    if f["access"] != want:
        raise RegisterError(f"{{reg}}.{{field}} is {{f['access']}}, not {{want}}")
    return access_mask(reg, "RW") != 0, put_field(reg, field, value)


class {cls}:
    """Blocking driver: every call is one or two bus accesses."""

    def __init__(self, bus, base: int = 0):
        self.bus, self.base = bus, base

    def read(self, reg: str) -> int:
        return self.bus.read32(self.base + _reg(reg)["offset"])

    def write(self, reg: str, value: int) -> None:
        """Write a whole register word (no read first)."""
        self.bus.write32(self.base + _reg(reg)["offset"], value & 0xFFFFFFFF)

    def get(self, reg: str, field: str) -> int:
        return get_field(reg, field, self.read(reg))

    def set(self, reg: str, field: str, value: int) -> None:
        """Change one RW field, keeping the register's other RW fields."""
        need, bits = _plan(reg, field, value, "RW")
        cur = self.read(reg) if need else 0
        self.write(reg, (cur & access_mask(reg, "RW") & ~field_mask(reg, field)) | bits)

    def _w1(self, reg, field, bits, want):
        f = _field(reg, field)
        need, word = _plan(reg, field, ((1 << f["width"]) - 1) if bits is None else bits, want)
        cur = self.read(reg) & access_mask(reg, "RW") if need else 0
        self.write(reg, cur | word)

    def clear(self, reg: str, field: str, bits: int | None = None) -> None:
        """W1C: clear the given bits of the field (all of them by default)."""
        self._w1(reg, field, bits, "W1C")

    def ring(self, reg: str, field: str, bits: int | None = None) -> None:
        """W1S: set the given bits of the field (a doorbell)."""
        self._w1(reg, field, bits, "W1S")

    def pulse(self, reg: str, field: str, bits: int | None = None) -> None:
        """W1P: one-clock pulse on the given bits of the field."""
        self._w1(reg, field, bits, "W1P")


class Async{cls}:
    """The same driver over a bus whose read32/write32 are coroutines (for example a cocotb AXI4-Lite master)."""

    def __init__(self, bus, base: int = 0):
        self.bus, self.base = bus, base

    async def read(self, reg: str) -> int:
        return await self.bus.read32(self.base + _reg(reg)["offset"])

    async def write(self, reg: str, value: int) -> None:
        await self.bus.write32(self.base + _reg(reg)["offset"], value & 0xFFFFFFFF)

    async def get(self, reg: str, field: str) -> int:
        return get_field(reg, field, await self.read(reg))

    async def set(self, reg: str, field: str, value: int) -> None:
        need, bits = _plan(reg, field, value, "RW")
        cur = await self.read(reg) if need else 0
        await self.write(reg, (cur & access_mask(reg, "RW") & ~field_mask(reg, field)) | bits)

    async def _w1(self, reg, field, bits, want):
        f = _field(reg, field)
        need, word = _plan(reg, field, ((1 << f["width"]) - 1) if bits is None else bits, want)
        cur = (await self.read(reg)) & access_mask(reg, "RW") if need else 0
        await self.write(reg, cur | word)

    async def clear(self, reg: str, field: str, bits: int | None = None) -> None:
        await self._w1(reg, field, bits, "W1C")

    async def ring(self, reg: str, field: str, bits: int | None = None) -> None:
        await self._w1(reg, field, bits, "W1S")

    async def pulse(self, reg: str, field: str, bits: int | None = None) -> None:
        await self._w1(reg, field, bits, "W1P")


class MmapBus:
    """32-bit accesses to a mapped window: a UIO device (/dev/uioN, map 0) or /dev/mem at a physical base.
    Each access is one aligned 4-byte load or store through a memoryview cast; check on the target that the
    compiler keeps it a single access (the C header is the reference path)."""

    def __init__(self, path: str = "/dev/uio0", size: int = WINDOW_BYTES, phys_base: int = 0):
        import mmap
        import os
        flags = os.O_RDWR | getattr(os, "O_SYNC", 0)
        self._fd = os.open(path, flags)
        self._mm = mmap.mmap(self._fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=phys_base)
        self._w = memoryview(self._mm).cast("I")

    def read32(self, offset: int) -> int:
        return int(self._w[offset >> 2])

    def write32(self, offset: int, value: int) -> None:
        self._w[offset >> 2] = value & 0xFFFFFFFF

    def close(self) -> None:
        import os
        self._w.release()
        self._mm.close()
        os.close(self._fd)
'''
    return body


# ---- markdown ------------------------------------------------------------------------------------------------------
def emit_md(m: RegMap) -> str:
    L = [f"# {m.name} registers", "", f"<!-- {_banner(m, '').strip()} -->".replace("\n", " "), "",
         m.summary, "",
         f"AXI4-Lite, 32-bit registers, a 0x{m.window_bytes:x}-byte window (address bits [{m.addr_width - 1}:2] "
         f"decoded). Unmapped addresses answer {'SLVERR' if m.unmapped == 'slverr' else 'OKAY'} and read 0. "
         f"Version {m.version}; model sha256 `{m.sha256[:16]}`.", "",
         "## Register map", "",
         "| Offset | Register | Reset | Summary |", "|---|---|---|---|"]
    for r in m.registers:
        L.append(f"| 0x{r.offset:03x} | {r.name} | 0x{r.reset:08x} | {r.summary} |")
    L += ["", "Reset is what a read returns after reset with every hardware input low.", "",
          "## Access types", "", "| Access | Meaning |", "|---|---|"]
    for a, t in ACCESS_TEXT.items():
        L.append(f"| {a} | {t} |")
    L.append("")
    for r in m.registers:
        L += [f"## {r.name} (0x{r.offset:03x})", ""]
        if r.summary:
            L += [r.summary, ""]
        L += ["| Bits | Field | Access | Reset | Summary |", "|---|---|---|---|---|"]
        for f in sorted(r.fields, key=lambda x: -x.lsb):
            bits = f"{f.msb}" if f.width == 1 else f"{f.msb}:{f.lsb}"
            rst = "hw" if f.hw_input else ("0" if f.access == "W1P" else f"0x{f.reset:x}")
            acc = "RO const" if f.const else f.access
            L.append(f"| {bits} | {f.name} | {acc} | {rst} | {f.summary} |")
        L.append("")
    if m.interrupt:
        L += ["## Interrupt", "",
              f"`irq_o` is a level output, registered: high while any bit of {m.interrupt['status']} is set and the "
              f"same bit of {m.interrupt['enable']} is set. Clear the cause by writing 1 to the {m.interrupt['status']} "
              "bit (W1C); the line drops one clock after the clear.", ""]
    L += ["## Hardware ports", "", "| Port | Direction | Width |", "|---|---|---|"]
    for d, n, w in ports(m):
        L.append(f"| `{n}` | {d} | {w} |")
    L.append("")
    return "\n".join(L)


EMIT = {"sv": emit_sv, "h": emit_c, "py": emit_py, "md": emit_md}


def generate(m: RegMap, out: str | Path) -> dict[str, Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for k, name in file_names(m).items():
        p = out / name
        p.write_text(EMIT[k](m))
        paths[k] = p
    return paths


# ---- reading the outputs back (agreement) --------------------------------------------------------------------------
def _expect(m: RegMap) -> dict:
    """What every output must say: per register offset and reset; per field lsb, width, access, reset."""
    return {r.name: {"offset": r.offset, "reset": r.reset,
                     "fields": {f.name: {"lsb": f.lsb, "width": f.width, "access": f.access, "reset": f.reset}
                                for f in r.fields}} for r in m.registers}


def read_c(m: RegMap, header: Path, cc: str | None = None) -> dict:
    """Compile a probe that prints every generated macro, run it, and rebuild the table from its output."""
    cc = cc or shutil.which("gcc") or shutil.which("cc")
    if not cc:
        raise RuntimeError("no C compiler (gcc or cc) on PATH: the header cannot be probed")
    P = m.name.upper()
    lines = ["#include <stdio.h>", f'#include "{header.name}"', "int main(void) {"]
    for r in m.registers:
        R = f"{P}_{r.name}"
        lines.append(f'  printf("R {r.name} %u %u\\n", (unsigned){R}_OFFSET, (unsigned){R}_RESET);')
        for a in ACCESS:
            lines.append(f'  printf("M {r.name} {a} %u\\n", (unsigned){R}_{a}_MASK);')
        for f in r.fields:
            F = f"{R}_{f.name}"
            lines.append(f'  printf("F {r.name} {f.name} %u %u %u %u %u\\n", (unsigned){F}_SHIFT, (unsigned){F}_WIDTH, '
                         f'(unsigned){F}_MASK, (unsigned){F}_RESET, (unsigned){F}_ACCESS);')
    lines += [f'  printf("W %u\\n", (unsigned){P}_WINDOW_BYTES);', "  return 0;", "}"]
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "probe.c"
        src.write_text("\n".join(lines) + "\n")
        exe = Path(td) / "probe"
        p = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(header.parent), str(src), "-o", str(exe)],
                           capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(f"the header probe does not compile:\n{p.stderr[-2000:]}")
        outp = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    got: dict = {}
    masks: dict = {}
    for ln in outp.splitlines():
        t = ln.split()
        if t[0] == "R":
            got[t[1]] = {"offset": int(t[2]), "reset": int(t[3]), "fields": {}}
        elif t[0] == "M":
            masks.setdefault(t[1], {})[t[2]] = int(t[3])
        elif t[0] == "F":
            sh, w, mk, rs, ac = map(int, t[3:])
            got[t[1]]["fields"][t[2]] = {"lsb": sh, "width": w, "access": ACCESS[ac], "reset": rs}
            if mk != ((1 << w) - 1) << sh:
                got[t[1]]["fields"][t[2]]["mask_mismatch"] = mk
        elif t[0] == "W":
            got["__window__"] = int(t[1])
    for rn, ms in masks.items():
        for a, v in ms.items():
            calc = 0
            for f in got[rn]["fields"].values():
                if f["access"] == a:
                    calc |= ((1 << f["width"]) - 1) << f["lsb"]
            if v != calc:
                got[rn][f"{a}_mask_mismatch"] = v
    return got


def read_py(m: RegMap, module: Path) -> dict:
    spec = importlib.util.spec_from_file_location(f"_regmap_probe_{m.name}", module)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    got = {n: {"offset": r["offset"], "reset": r["reset"],
               "fields": {fn: {k: f[k] for k in ("lsb", "width", "access", "reset")} for fn, f in r["fields"].items()}}
           for n, r in mod.REGISTERS.items()}
    got["__window__"] = mod.WINDOW_BYTES
    if mod.REGMAP_SHA256 != m.sha256:
        got["__sha__"] = mod.REGMAP_SHA256
    return got


def read_md(md: Path) -> dict:
    got: dict = {}
    cur = None
    for ln in md.read_text().splitlines():
        mt = re.match(r"^\| 0x([0-9a-f]+) \| ([A-Z][A-Z0-9_]*) \| 0x([0-9a-f]{8}) \|", ln)
        if mt:
            got[mt.group(2)] = {"offset": int(mt.group(1), 16), "reset": int(mt.group(3), 16), "fields": {}}
            continue
        mh = re.match(r"^## ([A-Z][A-Z0-9_]*) \(0x([0-9a-f]+)\)$", ln)
        if mh:
            cur = mh.group(1)
            continue
        mf = re.match(r"^\| (\d+)(?::(\d+))? \| ([A-Z][A-Z0-9_]*) \| (RW|RO|RO const|W1C|W1S|W1P) \| (hw|0|0x[0-9a-f]+) \|", ln)
        if mf and cur:
            hi = int(mf.group(1))
            lo = int(mf.group(2)) if mf.group(2) is not None else hi
            rst = 0 if mf.group(5) in ("hw", "0") else int(mf.group(5), 16)
            got[cur]["fields"][mf.group(3)] = {"lsb": lo, "width": hi - lo + 1,
                                               "access": "RO" if mf.group(4) == "RO const" else mf.group(4), "reset": rst}
    return got


def read_sv(m: RegMap, sv: Path) -> dict:
    """The port list and the ADDR_/RESET_ constants of the generated block (its behaviour is checked in simulation)."""
    t = sv.read_text()
    got: dict = {}
    for mt in re.finditer(r"localparam logic \[\d+:0\] ADDR_([A-Z0-9_]+) = \d+'h([0-9a-f]+);", t):
        got.setdefault(mt.group(1), {})["offset"] = int(mt.group(2), 16) << 2
    for mt in re.finditer(r"localparam logic \[31:0\] RESET_([A-Z0-9_]+) = 32'h([0-9a-f]+);", t):
        got.setdefault(mt.group(1), {})["reset"] = int(mt.group(2), 16)
    pl = []
    for mt in re.finditer(r"^\s+(input|output)\s+logic\s+(?:\[(\d+):0\]\s+)?(\w+),?$", t, re.M):
        if not mt.group(3).startswith("s_axil_") and mt.group(3) not in ("aclk", "aresetn"):
            pl.append((mt.group(1), mt.group(3), int(mt.group(2)) + 1 if mt.group(2) else 1))
    got["__ports__"] = pl
    mw = re.search(r"input\s+logic \[(\d+):0\] s_axil_awaddr", t)
    got["__window__"] = 1 << (int(mw.group(1)) + 1) if mw else None
    return got


def agreement(m: RegMap, out: Path) -> list[str]:
    """Problems where an output disagrees with the YAML (empty: all four agree)."""
    out = Path(out)
    names = file_names(m)
    exp = _expect(m)
    errs = []

    def cmp(kind: str, got: dict, fields: bool = True):
        for rn, er in exp.items():
            g = got.get(rn)
            if g is None:
                errs.append(f"{kind}: register {rn} missing")
                continue
            for k in ("offset", "reset"):
                if g.get(k) != er[k]:
                    errs.append(f"{kind}: {rn}.{k} is {g.get(k)!r}, the YAML says {er[k]!r}")
            for k in [x for x in g if x.endswith("_mismatch")]:
                errs.append(f"{kind}: {rn} {k.replace('_mismatch', '')} disagrees with its fields (0x{g[k]:08x})")
            if not fields:
                continue
            for fn, ef in er["fields"].items():
                gf = g.get("fields", {}).get(fn)
                if gf is None:
                    errs.append(f"{kind}: field {rn}.{fn} missing")
                    continue
                for k in ("lsb", "width", "access", "reset"):
                    if gf.get(k) != ef[k]:
                        errs.append(f"{kind}: {rn}.{fn}.{k} is {gf.get(k)!r}, the YAML says {ef[k]!r}")
                if "mask_mismatch" in gf:
                    errs.append(f"{kind}: {rn}.{fn} mask 0x{gf['mask_mismatch']:08x} disagrees with its shift and width")
            extra = set(g.get("fields", {})) - set(er["fields"])
            if extra:
                errs.append(f"{kind}: {rn} has fields the YAML does not: {sorted(extra)}")
        extra = {k for k in got if not k.startswith("__")} - set(exp)
        if extra:
            errs.append(f"{kind}: registers the YAML does not declare: {sorted(extra)}")
        if "__window__" in got and got["__window__"] != m.window_bytes:
            errs.append(f"{kind}: window {got['__window__']} bytes, the YAML says {m.window_bytes}")

    try:
        cmp("C header", read_c(m, out / names["h"]))
    except (RuntimeError, KeyError, ValueError, IndexError) as ex:
        errs.append(f"C header: cannot be read back: {ex}")
    try:
        g = read_py(m, out / names["py"])
        if "__sha__" in g:
            errs.append(f"Python driver: model hash {g['__sha__'][:16]} is not the YAML's {m.sha256[:16]}")
        cmp("Python driver", g)
    except Exception as ex:  # noqa: BLE001 (a broken generated module is a finding, not a crash)
        errs.append(f"Python driver: cannot be imported: {type(ex).__name__}: {ex}")
    cmp("markdown", read_md(out / names["md"]))
    sv = read_sv(m, out / names["sv"])
    cmp("SystemVerilog", sv, fields=False)
    if sv["__ports__"] != ports(m):
        want, have = set(ports(m)), set(sv["__ports__"])
        errs.append(f"SystemVerilog: ports differ: missing {sorted(want - have)}, unexpected {sorted(have - want)}")
    return errs


def drift(m: RegMap, out: Path) -> list[str]:
    """Outputs whose text is not what the YAML generates now."""
    errs = []
    for k, name in file_names(m).items():
        p = Path(out) / name
        if not p.exists():
            errs.append(f"{p}: missing (python3 -m hwsw.regmap gen)")
        elif p.read_text() != EMIT[k](m):
            errs.append(f"{p}: differs from what the YAML generates (edited by hand, or the YAML changed): regenerate")
    return errs


def check(path: str | Path, out: str | Path) -> list[str]:
    m = load(path)
    return drift(m, Path(out)) + agreement(m, Path(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hwsw.regmap", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["validate", "gen", "check"])
    ap.add_argument("yaml", nargs="+")
    ap.add_argument("--out", default=None, help="output folder (default: generated/ next to the YAML)")
    a = ap.parse_args(argv)
    rc = 0
    for y in a.yaml:
        out = Path(a.out) if a.out else Path(y).parent / "generated"
        try:
            m = load(y)
        except RegmapError as ex:
            print(ex)
            rc = 1
            continue
        if a.cmd == "validate":
            print(f"{y}: {m.name} {m.version}: {len(m.registers)} registers, "
                  f"{sum(len(r.fields) for r in m.registers)} fields, sha256 {m.sha256[:16]}")
        elif a.cmd == "gen":
            for p in generate(m, out).values():
                print(p)
        else:
            errs = drift(m, out) + agreement(m, out)
            for e in errs:
                print(e)
            print(f"{y}: {'agree' if not errs else f'{len(errs)} problems'} ({', '.join(file_names(m).values())})")
            rc |= 1 if errs else 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
