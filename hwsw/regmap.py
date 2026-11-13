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
import dataclasses
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
# Documentation only (an ip_lib entry whose register block is written by hand, described in its ip.yaml): a register
# that holds what software writes for the hardware and reads as 0. The generator does not make it.
DOC_ACCESS = {"WO": "write-only: the hardware uses the value written; reads return 0"}
# Access types that would change state on a read. Refused: a read must never have a side effect (a debugger, a
# speculative or retried read, or a driver's read-modify-write would then change the block). Pop or acknowledge with
# a W1P bit instead (owner, 2026-11-13).
READ_SIDE_EFFECT = {"RC": "clear on read", "RS": "set on read", "RCLR": "clear on read", "ROC": "clear on read",
                    "RSET": "set on read", "W1CRC": "clear on read", "POP": "pop on read", "RPOP": "pop on read"}


@dataclass(frozen=True)
class Conventions:
    """What a register block does in the cases a driver writer could guess wrong. The generated blocks have the house
    values except `unmapped` (the map's own setting); a hand-written block (an ip_lib entry) states its own in ip.yaml.
    The datasheet sentences are generated from these values (behaviour())."""
    unmapped: str = "okay"             # okay | slverr: the response to an unmapped address inside the block's window
    reserved: str = "zero"             # zero (read 0, writes ignored) | undefined (read undefined; write 0)
    strobes: str = "honoured"          # honoured | ignored (WSTRB)
    reset: str = "aresetn"             # the reset input's name
    reset_active: str = "low"          # low | high
    reset_style: str = "synchronous"   # synchronous | asynchronous
    clock: str = "aclk"                # the clock every field is in


HOUSE = Conventions()
CONV_CHOICES = {"unmapped": ("okay", "slverr"), "reserved": ("zero", "undefined"), "strobes": ("honoured", "ignored"),
                "reset_active": ("low", "high"), "reset_style": ("synchronous", "asynchronous")}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
C_RESERVED = {"OFFSET", "RESET", "RW_MASK", "RO_MASK", "W1C_MASK", "W1S_MASK", "W1P_MASK"}   # register-level suffixes
MODEL_KEYS = {"regmap", "name", "version", "summary", "data_width", "addr_width", "unmapped", "interrupt", "registers",
              "snapshot"}
DOC_MODEL_KEYS = MODEL_KEYS | {"conventions", "staging"}       # documentation-only maps (an ip.yaml register_map)
REG_KEYS = {"name", "offset", "summary", "fields"}
SNAP_KEYS = {"name", "trigger", "fields", "summary"}
STAGING_KEYS = {"name", "registers", "commit", "summary"}
FIELD_KEYS = {"name", "lsb", "width", "access", "reset", "const", "summary"}
# Names the generated block uses for its own signals. A register's per-register signals (wr_<reg>, rd_<reg>) and a
# field's ports must not meet them: a register named HIT would declare wr_hit twice.
PORT_SUFFIXES = ("_o", "_i", "_set_i", "_clr_i", "_pulse_o")
SV_INTERNAL = {"aclk", "aresetn", "aw_got", "w_got", "aw_word", "w_data", "w_bits", "w_strb", "wr_commit", "wr_hit",
               "rd_value", "rd_hit", "irq_o", "unused_ok"}
SNAP_SUFFIX = "_shadow"           # a snapshot field's copy: <register>_<field>_shadow; the group's load strobe: snap_<group>
# Text that would end a comment, a docstring or a table cell in one of the outputs: every summary and the version
# go into SystemVerilog line comments, C block comments, a Python docstring and markdown tables.
TEXT_FORBIDDEN = ("*/", "/*", '"""', "\\", "|")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]*$")


def text_problems(what: str, text) -> list[str]:
    """Why a summary cannot go into the generated outputs as it is ([] = fine)."""
    if not isinstance(text, str):
        return [f"{what}: must be text"]
    errs = []
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text):
        errs.append(f"{what}: a newline or other control character would break a comment line in the outputs")
    bad = [t for t in TEXT_FORBIDDEN if t in text]
    if bad:
        errs.append(f"{what}: {', '.join(repr(t) for t in bad)} would end a comment, docstring or table cell in the "
                    "outputs")
    return errs


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
    hw_reset: bool = False    # documentation-only maps: a RO field whose hardware state resets to `reset`

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
    group: str = ""           # documentation-only maps: the name a `count:` register was expanded from

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
            if f.access in ("RW", "W1C", "W1S") or (f.access == "RO" and (f.const or f.hw_reset)):
                v |= f.reset << f.lsb
        return v


@dataclass(frozen=True)
class Snapshot:
    """A value wider than one register, read consistently: writing 1 to the trigger (a W1P bit) copies every field of
    the group into shadow registers in one clock; reads of those fields return the copy. Fields low part first."""
    name: str
    trigger: tuple[str, str]
    fields: tuple[tuple[str, str], ...]
    summary: str = ""


@dataclass(frozen=True)
class Staging:
    """Documentation-only maps: registers the hardware reads only when a command register is written."""
    name: str
    registers: tuple[str, ...]
    commit: str
    summary: str = ""


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
    snapshots: tuple[Snapshot, ...] = ()
    staging: tuple[Staging, ...] = ()
    doc_only: bool = False
    conventions: Conventions = HOUSE

    @property
    def window_bytes(self) -> int:
        return 1 << self.addr_width

    def reg(self, name: str) -> Register:
        for r in self.registers:
            if r.name == name:
                return r
        raise KeyError(name)

    def field(self, reg: str, name: str) -> Field:
        return next(f for f in self.reg(reg).fields if f.name == name)

    def snapshot_of(self, reg: str, fname: str) -> Snapshot | None:
        """The snapshot group a field belongs to (its reads return the group's copy), or None."""
        return next((s for s in self.snapshots if (reg, fname) in s.fields), None)

    def snapshot_width(self, s: Snapshot) -> int:
        return sum(self.field(r, f).width for r, f in s.fields)

    def canonical(self) -> dict:
        """The model as plain data, in a fixed order: what the hash covers and what every output must agree with."""
        return {
            "format": FORMAT, "name": self.name, "version": self.version, "data_width": self.data_width,
            "addr_width": self.addr_width, "unmapped": self.unmapped, "interrupt": self.interrupt,
            "registers": [{"name": r.name, "offset": r.offset, "reset": r.reset,
                           "fields": [{"name": f.name, "lsb": f.lsb, "width": f.width, "access": f.access,
                                       "reset": f.reset, "const": f.const} for f in r.fields]}
                          for r in self.registers],
            **({"snapshot": [{"name": s.name, "trigger": ".".join(s.trigger), "fields": [".".join(x) for x in s.fields]}
                             for s in self.snapshots]} if self.snapshots else {}),
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


def from_dict(d, source: str = "<dict>", doc_only: bool = False) -> RegMap:
    """Validate a regmap. doc_only: the map documents a hand-written block (an ip_lib entry's ip.yaml register_map),
    so it may also use WO registers, `count:` (DATA0..DATAn-1), RO fields with a known hardware reset, `conventions:`
    and `staging:`; nothing is generated from it but the datasheet."""
    errs: list[str] = []
    if not isinstance(d, dict):
        raise RegmapError(f"{source}: the top level must be a mapping")
    extra = set(d) - (DOC_MODEL_KEYS if doc_only else MODEL_KEYS)
    if extra:
        errs.append(f"unknown top-level keys {sorted(extra)}" +
                    (" (conventions and staging are for documentation-only maps; a generated block has the house "
                     "conventions, docs/hwsw.md)" if extra & {"conventions", "staging"} else ""))
    access_ok = ACCESS + tuple(DOC_ACCESS) if doc_only else ACCESS
    if d.get("regmap") != 1:
        errs.append("regmap: must be 1 (the format version)")
    errs += text_problems("summary", d.get("summary", ""))
    if not VERSION_RE.match(str(d.get("version", "0.0.0"))):
        errs.append(f"version: {d.get('version')!r} must be letters, digits and . + _ - (for example 1.2.0)")
    name = d.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        errs.append(f"name: {name!r} must be a lower-case identifier (letters, digits, _), starting with a letter")
        name = "invalid"
    if d.get("data_width", 32) != 32:
        errs.append("data_width: only 32 is supported")
    aw = _int(d.get("addr_width"), "addr_width", errs)
    if aw is not None and not 4 <= aw <= 32:
        errs.append(f"addr_width: {aw} must be 4..32 (the window is 2**addr_width bytes)")
    unmapped = d.get("unmapped", "okay")
    if unmapped not in ("slverr", "okay"):
        errs.append(f"unmapped: {unmapped!r} must be okay or slverr")
    conv = {"unmapped": unmapped}
    if doc_only and d.get("conventions") is not None:
        c = d["conventions"]
        if not isinstance(c, dict) or set(c) - set(Conventions.__dataclass_fields__) - {"unmapped"}:
            errs.append(f"conventions: keys must be among {sorted(Conventions.__dataclass_fields__)}")
        else:
            for k, v in c.items():
                if k == "unmapped":
                    errs.append("conventions: give unmapped at the top level")
                elif k in CONV_CHOICES and v not in CONV_CHOICES[k]:
                    errs.append(f"conventions.{k}: {v!r} must be one of {', '.join(CONV_CHOICES[k])}")
                elif not isinstance(v, str) or not NAME_RE.match(v) and k in ("reset", "clock"):
                    errs.append(f"conventions.{k}: {v!r} must be a signal name")
            conv.update({k: v for k, v in c.items() if k != "unmapped"})
    regs_in = d.get("registers")
    if not isinstance(regs_in, list) or not regs_in:
        errs.append("registers: must be a non-empty list")
        regs_in = []
    if doc_only:                                   # count: N -> NAME0..NAME<N-1>, 4 bytes apart
        grown = []
        for r in regs_in:
            if isinstance(r, dict) and "count" in r:
                n = r["count"]
                if not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= 256:
                    errs.append(f"register {r.get('name')}: count {n!r} must be 2..256")
                    continue
                base = {k: v for k, v in r.items() if k != "count"}
                off = r.get("offset") if isinstance(r.get("offset"), int) else 0
                grown += [dict(base, name=f"{r.get('name')}{i}", offset=off + 4 * i, _group=r.get("name"),
                               summary=str(r.get("summary", "")).replace("{n}", str(i))) for i in range(n)]
            else:
                grown.append(r)
        regs_in = grown
    regs: list[Register] = []
    seen_off: dict[int, str] = {}
    seen_port: dict[str, str] = {}
    full_port: dict[str, str] = {}
    for i, r in enumerate(regs_in):
        if not isinstance(r, dict):
            errs.append(f"registers[{i}]: not a mapping")
            continue
        rn = r.get("name")
        where = f"register {rn or i}"
        extra = set(r) - REG_KEYS - {"_group"}
        if extra:
            errs.append(f"{where}: unknown keys {sorted(extra)}")
        if not isinstance(rn, str) or not REG_RE.match(rn):
            errs.append(f"{where}: name must be upper-case (letters, digits, _), starting with a letter")
            rn = f"R{i}"
        if any(x.name == rn for x in regs):
            errs.append(f"{where}: duplicate register name")
        clash = sorted({f"wr_{rn.lower()}", f"rd_{rn.lower()}"} & SV_INTERNAL)
        if clash:
            errs.append(f"{where}: the generated block's signal{'s' if len(clash) > 1 else ''} {', '.join(clash)} would meet one of its own "
                        f"(reserved register names: {', '.join(sorted({x[3:].upper() for x in SV_INTERNAL if x[:3] in ('wr_', 'rd_')}))})")
        errs += text_problems(f"{where}.summary", r.get("summary", ""))
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
            extra = set(f) - FIELD_KEYS - {"on_read"}
            if extra:
                errs.append(f"{fw}: unknown keys {sorted(extra)}")
            if not isinstance(fn, str) or not REG_RE.match(fn):
                errs.append(f"{fw}: name must be upper-case (letters, digits, _), starting with a letter")
                fn = f"F{j}"
            if fn in C_RESERVED or any(fn.endswith("_" + s) for s in C_RESERVED):
                errs.append(f"{fw}: name clashes with a generated register-level name ({', '.join(sorted(C_RESERVED))})")
            if any(x.name == fn for x in fields):
                errs.append(f"{fw}: duplicate field name in the register")
            errs += text_problems(f"{fw}.summary", f.get("summary", ""))
            lsb = _int(f.get("lsb"), f"{fw}.lsb", errs)
            width = _int(f.get("width"), f"{fw}.width", errs)
            acc = f.get("access")
            if isinstance(acc, str) and acc.upper() in READ_SIDE_EFFECT:
                errs.append(f"{fw}: access {acc!r} ({READ_SIDE_EFFECT[acc.upper()]}) changes state on a read; reads "
                            "have no side effects in this format: pop or acknowledge with a W1P bit (docs/hwsw.md)")
            elif acc not in access_ok:
                errs.append(f"{fw}: access {acc!r} must be one of {', '.join(access_ok)}")
            if "on_read" in f:
                errs.append(f"{fw}: on_read: a read must not change state; pop or acknowledge with a W1P bit "
                            "(docs/hwsw.md)")
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
            hw_reset = doc_only and acc == "RO" and "reset" in f and const is None
            if const is not None:
                if acc != "RO":
                    errs.append(f"{fw}: const is allowed only on a RO field")
                if "reset" in f:
                    errs.append(f"{fw}: give const or reset, not both (a constant's value is its reset)")
                reset, is_const = const, True
            elif acc == "RO" and "reset" in f and not doc_only:
                errs.append(f"{fw}: a RO field without const reads a hardware input; it has no reset value")
            if acc == "W1P" and f.get("reset", 0) != 0:
                errs.append(f"{fw}: a W1P field reads 0; its reset must be 0")
            rv = _int(reset, f"{fw}.{'const' if is_const else 'reset'}", errs)
            if rv is None:
                continue
            if not 0 <= rv < (1 << width):
                errs.append(f"{fw}: value 0x{rv:x} does not fit in {width} bit{'s' if width > 1 else ''}")
                continue
            if acc in access_ok:
                fields.append(Field(fn, lsb, width, acc, rv, is_const, str(f.get("summary", "")), hw_reset))
                port = f"{rn}_{fn}".lower()
                if {port + s for s in PORT_SUFFIXES} & SV_INTERNAL:
                    errs.append(f"{fw}: port name {port}_* would meet one of the generated block's own signals")
                if port in seen_port:
                    errs.append(f"{fw}: port name {port} is also made by {seen_port[port]}")
                seen_port[port] = f"{rn}.{fn}"
                for s in PORT_SUFFIXES:   # compare the full names: field B's `_set_i` meets field B_SET's `_i`
                    if port + s in full_port and full_port[port + s] != f"{rn}.{fn}":
                        errs.append(f"{fw}: port {port}{s} is also made by {full_port[port + s]}")
                    full_port.setdefault(port + s, f"{rn}.{fn}")
        if off is not None:
            regs.append(Register(rn, off, tuple(sorted(fields, key=lambda x: x.lsb)), str(r.get("summary", "")),
                                 str(r.get("_group", ""))))
    # a register's own signals (wr_<reg>, rd_<reg>) against every field's full port name (register A_O makes wr_a_o,
    # and register WR field A makes the port wr_a_o)
    for r in regs:
        for p in ("wr", "rd"):
            sig = f"{p}_{r.name.lower()}"
            if sig in full_port:
                errs.append(f"register {r.name}: its signal {sig} is also the port made by {full_port[sig]}")
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
    snaps = _snapshots(d.get("snapshot"), regs, cnames, name, errs)
    stag = _staging(d.get("staging"), regs, errs) if doc_only else ()
    if errs:
        raise RegmapError(f"{source}:\n  " + "\n  ".join(errs))
    m = RegMap(name, str(d.get("version", "0.0.0")), str(d.get("summary", "")), aw, unmapped,
               tuple(sorted(regs, key=lambda x: x.offset)), irq, snapshots=snaps, staging=stag, doc_only=doc_only,
               conventions=Conventions(**conv))
    h = hashlib.sha256(json.dumps(m.canonical(), sort_keys=True).encode()).hexdigest()
    return dataclasses.replace(m, sha256=h)


def _ref(text, regs: list[Register], what: str, errs: list[str]) -> tuple[str, str] | None:
    """'REG.FIELD' -> (reg, field) if both exist."""
    if not isinstance(text, str) or text.count(".") != 1:
        errs.append(f"{what}: {text!r} must be REGISTER.FIELD")
        return None
    rn, fn = text.split(".")
    r = next((x for x in regs if x.name == rn), None)
    if r is None or not any(f.name == fn for f in r.fields):
        errs.append(f"{what}: {text} is not a declared field")
        return None
    return rn, fn


def _snapshots(raw, regs: list[Register], cnames: dict, mname: str, errs: list[str]) -> tuple[Snapshot, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        errs.append("snapshot: must be a non-empty list of groups")
        return ()
    out, used, trig_used = [], {}, {}
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            errs.append(f"snapshot[{i}]: not a mapping")
            continue
        sn = s.get("name")
        where = f"snapshot {sn or i}"
        if set(s) - SNAP_KEYS:
            errs.append(f"{where}: unknown keys {sorted(set(s) - SNAP_KEYS)}")
        if not isinstance(sn, str) or not REG_RE.match(sn):
            errs.append(f"{where}: name must be upper-case (letters, digits, _), starting with a letter")
            continue
        if any(x.name == sn for x in out):
            errs.append(f"{where}: duplicate snapshot name")
        errs += text_problems(f"{where}.summary", s.get("summary", ""))
        tr = _ref(s.get("trigger"), regs, f"{where}.trigger", errs)
        if tr:
            tf = next(f for r in regs if r.name == tr[0] for f in r.fields if f.name == tr[1])
            if tf.access != "W1P" or tf.width != 1:
                errs.append(f"{where}.trigger: {'.'.join(tr)} must be a one-bit W1P field (writing 1 takes the copy)")
            if tr in trig_used:
                errs.append(f"{where}.trigger: {'.'.join(tr)} already triggers snapshot {trig_used[tr]}")
            trig_used[tr] = sn
        fl = s.get("fields")
        if not isinstance(fl, list) or not fl:
            errs.append(f"{where}.fields: must be a non-empty list of REGISTER.FIELD, low part first")
            continue
        refs, width = [], 0
        for x in fl:
            ref = _ref(x, regs, f"{where}.fields", errs)
            if not ref:
                continue
            f = next(f for r in regs if r.name == ref[0] for f in r.fields if f.name == ref[1])
            if f.access != "RO" or f.const:
                errs.append(f"{where}.fields: {x} must be a RO field read from a hardware input (not a constant)")
            if ref in used:
                errs.append(f"{where}.fields: {x} is already in snapshot {used[ref]}")
            used[ref] = sn
            refs.append(ref)
            width += f.width
        if width > 64:
            errs.append(f"{where}: {width} bits; at most 64 (the C helper returns a uint64_t)")
        own = [f"SNAP_{sn}_{k}" for k in ("TRIGGER_OFFSET", "TRIGGER_MASK", "WIDTH")]
        for n in own:
            if n in cnames:
                errs.append(f"{where}: the C name {m_name(mname)}_{n} is also made by register {cnames[n]}")
        if tr and refs:
            out.append(Snapshot(sn, tr, tuple(refs), str(s.get("summary", ""))))
    # the generated block's internal names must not meet (snap_<group>, <register>_<field>_shadow)
    names = [f"snap_{s.name.lower()}" for s in out] + [f"{r}_{f}".lower() + SNAP_SUFFIX for s in out for r, f in s.fields]
    dup = sorted({n for n in names if names.count(n) > 1} | (set(names) & SV_INTERNAL))
    if dup:
        errs.append(f"snapshot: generated signal names meet: {', '.join(dup)}")
    return tuple(out)


def _staging(raw, regs: list[Register], errs: list[str]) -> tuple[Staging, ...]:
    if raw is None:
        return ()
    out = []
    for i, s in enumerate(raw if isinstance(raw, list) else [None]):
        if not isinstance(s, dict) or set(s) - STAGING_KEYS or not {"name", "registers", "commit"} <= set(s):
            errs.append(f"staging[{i}]: must be {{name, registers: [..], commit: REGISTER, summary}}")
            continue
        names = {r.name for r in regs}
        missing = [x for x in list(s["registers"]) + [s["commit"]] if x not in names]
        if missing:
            errs.append(f"staging {s['name']}: registers not declared: {missing}")
            continue
        errs += text_problems(f"staging {s['name']}.summary", s.get("summary", ""))
        out.append(Staging(str(s["name"]), tuple(s["registers"]), s["commit"], str(s.get("summary", ""))))
    return tuple(out)


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
         f"// Unmapped addresses: {'SLVERR' if m.unmapped == 'slverr' else 'OKAY'} on both channels, reads return 0. Reads have",
         "// no side effects. A hardware set beats a same-clock W1C clear; a W1S set beats a same-clock hardware clear.",
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
    if m.snapshots:
        L.append("    // ---- snapshot groups: writing 1 to the trigger copies every field of the group in the same clock;")
        L.append("    // ---- reads of those fields return the copy (shadow), so the parts of a wide value agree ----")
    for s in m.snapshots:
        tr = m.field(*s.trigger)
        g = f"snap_{s.name.lower()}"
        L += [f"    logic {g};",
              f"    assign {g} = wr_{s.trigger[0].lower()} && w_data[{tr.lsb}] && w_bits[{tr.lsb}];   // {'.'.join(s.trigger)}"]
        for rn, fn in s.fields:
            f = m.field(rn, fn)
            base = f"{rn}_{fn}".lower()
            L += [f"    logic {_w(f.width)}{base}{SNAP_SUFFIX};",
                  f"    always_ff @(posedge aclk) begin",
                  f"        if (!aresetn) {base}{SNAP_SUFFIX} <= {f.width}'h0;",
                  f"        else if ({g}) {base}{SNAP_SUFFIX} <= {base}_i;",
                  f"    end"]
        L.append("")
    # read values
    L.append("    // ---- read path: the value of each register as software sees it ----")
    for r in m.registers:
        terms = []
        for f in r.fields:
            base = f"{r.name}_{f.name}".lower()
            if f.access == "RO":
                src = (f"{f.width}'h{f.reset:x}" if f.const else
                       f"{base}{SNAP_SUFFIX}" if m.snapshot_of(r.name, f.name) else f"{base}_i")
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
         " * Reads have no side effects; commands, pops and acknowledgements are W1P bits.",
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
    snap_c = []
    for s in m.snapshots:
        tr = m.reg(s.trigger[0])
        S = f"{P}_SNAP_{s.name}"
        snap_c += [f"/* snapshot {s.name}: write 1 to {'.'.join(s.trigger)}, then read the parts (low part first); they "
                   "agree with each other. Without a new snapshot the parts read the last copy (stale). */",
                   f"#define {S}_TRIGGER_OFFSET {P}_{tr.name}_OFFSET",
                   f"#define {S}_TRIGGER_MASK {P}_{s.trigger[0]}_{s.trigger[1]}_MASK",
                   f"#define {S}_WIDTH {m.snapshot_width(s)}u",
                   f"static inline uint64_t {m.name}_snapshot_{s.name.lower()}(uintptr_t base)", "{",
                   "    uint64_t v = 0;"]
        keep = f"({P}_IO_READ32(base + {S}_TRIGGER_OFFSET) & {P}_{tr.name}_RW_MASK) | " if tr.mask("RW") else ""
        snap_c.append(f"    {P}_IO_WRITE32(base + {S}_TRIGGER_OFFSET, {keep}{S}_TRIGGER_MASK);")
        sh = 0
        for rn, fn in s.fields:
            snap_c.append(f"    v |= (uint64_t){P}_GET({rn}, {fn}, {P}_IO_READ32(base + {P}_{rn}_OFFSET)) << {sh};")
            sh += m.field(rn, fn).width
        snap_c += ["    return v;", "}", ""]
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
          "", *snap_c,
          f"#endif /* {g} */", ""]
    return "\n".join(L)


# ---- Python host driver --------------------------------------------------------------------------------------------
def emit_py(m: RegMap) -> str:
    table = {r.name: {"offset": r.offset, "reset": r.reset, "summary": r.summary,
                      "fields": {f.name: {"lsb": f.lsb, "width": f.width, "access": f.access, "reset": f.reset,
                                          "const": f.const} for f in r.fields}} for r in m.registers}
    cls = "".join(w.capitalize() for w in m.name.split("_")) + "Regs"
    snaps = {s.name: {"trigger": list(s.trigger), "fields": [list(x) for x in s.fields]} for s in m.snapshots}
    body = f'''{_banner(m, "#")}"""Host driver for {m.name}: {m.summary}

Self-contained (standard library only), so it can be copied to the board. A bus is any object with
read32(offset) -> int and write32(offset, value), offsets in bytes from the block's base. {cls} is the
blocking driver; Async{cls} is the same driver over a bus whose methods are coroutines (a simulation bus).
MmapBus maps a UIO device or /dev/mem window.

Access rules (the same in the RTL, the C header and the documentation):
{chr(10).join(f"  {a:4} {t}" for a, t in ACCESS_TEXT.items())}
Reads have no side effects. snapshot(group) writes the group's W1P trigger, then reads its parts (low part first).
"""
from __future__ import annotations

NAME = {m.name!r}
REGMAP_SHA256 = {m.sha256!r}
WINDOW_BYTES = 0x{m.window_bytes:x}
UNMAPPED = {m.unmapped!r}
INTERRUPT = {m.interrupt!r}
REGISTERS = {pprint.pformat(table, sort_dicts=False, width=110)}
SNAPSHOTS = {pprint.pformat(snaps, sort_dicts=False, width=110)}


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


def _snap(group: str) -> dict:
    try:
        return SNAPSHOTS[group]
    except KeyError:
        raise RegisterError(f"{{NAME}} has no snapshot group {{group!r}}") from None


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

    def snapshot(self, group: str) -> int:
        """A value wider than one register, consistent: take a snapshot, then read the parts (low part first)."""
        s = _snap(group)
        self.pulse(*s["trigger"])
        v, sh = 0, 0
        for reg, field in s["fields"]:
            v |= self.get(reg, field) << sh
            sh += _field(reg, field)["width"]
        return v


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

    async def snapshot(self, group: str) -> int:
        s = _snap(group)
        await self.pulse(*s["trigger"])
        v, sh = 0, 0
        for reg, field in s["fields"]:
            v |= (await self.get(reg, field)) << sh
            sh += _field(reg, field)["width"]
        return v


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


# ---- the datasheet: what a driver writer could guess wrong, from the map's settings ---------------------------------
def _names(xs) -> str:
    return ", ".join(xs)


def _resp(u: str) -> str:
    return "SLVERR" if u == "slverr" else "OKAY"


def differences(m: RegMap) -> list[str]:
    """Where this block's behaviour differs from the house register conventions (docs/hwsw.md), in plain words."""
    c, h, out = m.conventions, HOUSE, []
    if c.unmapped != h.unmapped:
        out.append(f"unmapped addresses inside the block answer {_resp(c.unmapped)} (house: {_resp(h.unmapped)}, reading 0)")
    if c.reserved != h.reserved:
        out.append("reserved bits read an undefined value (house: they read 0)")
    if c.strobes != h.strobes:
        out.append("byte strobes are ignored, so every write changes the whole word (house: strobes honoured)")
    if (c.reset, c.reset_active, c.reset_style) != (h.reset, h.reset_active, h.reset_style):
        out.append(f"the reset is `{c.reset}`, {c.reset_style}, active {c.reset_active} (house: `{h.reset}`, "
                   f"{h.reset_style}, active {h.reset_active})")
    return out


def convention_sentence(m: RegMap) -> str:
    d = differences(m)
    if not d:
        return "It follows the house register conventions (docs/hwsw.md); the Behaviour section states each one."
    return ("It differs from the house register conventions (docs/hwsw.md) in " + str(len(d)) + " way" +
            ("s" if len(d) > 1 else "") + ": " + "; ".join(d) + ".")


def behaviour(m: RegMap) -> list[tuple[str, str]]:
    """(topic, sentence) for every behaviour a user could reasonably guess wrong, each generated from a setting of the
    map (or of its conventions). hwsw/tests/test_64a_regmap.py checks that each sentence follows its setting."""
    c = m.conventions
    ref = lambda r, f: f"{r.name}.{f.name}"                                    # noqa: E731
    by_acc = lambda a: [ref(r, f) for r in m.registers for f in r.fields if f.access == a]   # noqa: E731
    out = []
    win = f"0x{m.window_bytes:x}-byte window"
    if c.unmapped == "okay":
        out.append(("unmapped", f"**Unmapped addresses.** An address inside this block's {win} that holds no register "
                    "answers OKAY and reads 0; a write there is ignored. Addresses outside the window belong to the "
                    "interconnect (an AXI crossbar answers DECERR there)."))
    else:
        out.append(("unmapped", f"**Unmapped addresses.** An address inside this block's {win} that holds no register "
                    "answers SLVERR and reads 0; a write there is ignored. On a Cortex-A9 or Cortex-A53 a SLVERR on a "
                    "load is an external abort, so a stray access stops the program. Addresses outside the window "
                    "belong to the interconnect (an AXI crossbar answers DECERR there)."))
    if c.reserved == "zero":
        out.append(("reserved", "**Reserved bits.** Bits that belong to no field read 0 and ignore writes. Write them "
                    "as 0, so that a later version can give them a meaning."))
    else:
        out.append(("reserved", "**Reserved bits.** Bits that belong to no field read an undefined value: mask them "
                    "off after a read, and write them as 0."))
    staged = {x for g in m.staging for x in g.registers}
    pops = by_acc("W1P")
    wo = [r.name for r in m.registers if any(f.access == "WO" for f in r.fields) and r.name not in staged]
    act = (f"To start, pop or acknowledge something, write 1 to its W1P bit: {_names(pops)}." if pops else
           f"Actions happen on writes only: a write to {_names(wo)}." if wo else
           "This block has no command bits.")
    out.append(("side_effects", "**Reads have no side effects.** Reading any register changes nothing, so a debugger, "
                "a retried read or a read-modify-write is safe. " + act))
    w1c, w1s = by_acc("W1C"), by_acc("W1S")
    pri = []
    if w1c:
        pri.append(f"W1C bits ({_names(w1c)}): a hardware set in the same clock as a software clear wins, so the bit "
                   "stays set and no event is lost.")
    if w1s:
        pri.append(f"W1S bits ({_names(w1s)}): a software set in the same clock as a hardware clear wins, so the set "
                   "is not lost.")
    out.append(("priority", "**Same-clock priority (the house convention).** " + (" ".join(pri) if pri else
                "None applies: this block has no W1C or W1S bits.")))
    if c.strobes == "honoured":
        out.append(("strobes", "**Partial writes.** Byte strobes (WSTRB) are honoured on every register: a byte whose "
                    "strobe is 0 keeps its value, and in it W1C, W1S and W1P bits count as 0 (nothing is cleared, set "
                    "or pulsed)."))
    else:
        out.append(("strobes", "**Partial writes.** Byte strobes (WSTRB) are ignored on every register: every write "
                    "changes the whole 32-bit word, so a CPU's byte or halfword store overwrites the other bytes. Use "
                    "32-bit stores only."))
    out.append(("access", f"**Access width and alignment.** 32-bit registers on a {m.data_width}-bit AXI4-Lite bus. "
                "AXI4-Lite has no transfer size: a CPU's byte or halfword load reads the whole word, and its store "
                "arrives as a word write with fewer strobes (see Partial writes). Address bits [1:0] are not decoded, "
                f"so an unaligned address reaches the word that holds it; only bits [{m.addr_width - 1}:2] are "
                f"decoded, so the window repeats every 0x{m.window_bytes:x} bytes. Use aligned 32-bit accesses."))
    mw = []
    for s in m.snapshots:
        parts = ", then ".join(".".join(x) for x in s.fields)
        mw.append(f"Snapshot group {s.name} ({m.snapshot_width(s)} bits: {parts}, low part first): write 1 to "
                  f"{'.'.join(s.trigger)} to copy the whole value into shadow registers in one clock, then read the "
                  "parts in any order; they belong to the same instant. A read without a new snapshot returns the copy "
                  "from the last one (stale), not the live value; the copies read 0 after reset.")
    for g in m.staging:
        mw.append(f"Staging group {g.name} ({g.registers[0]} to {g.registers[-1]}, {32 * len(g.registers)} bits): "
                  f"the hardware uses these registers only for a command (a write to {g.commit}). Write them in any "
                  f"order before writing {g.commit}, and leave them unchanged until that command has finished.")
    if m.snapshots:
        mw.append("Every other register is read on its own, so a value split across two of them can tear.")
    elif not m.staging:
        mw.append("No snapshot groups: every register is read on its own, so a value split across two registers (a "
                  "HI and a LO) can tear if it changes between the two reads. Give such a value a snapshot group.")
    out.append(("multiword", "**Values wider than 32 bits.** " + " ".join(mw)))
    hw = [ref(r, f) for r in m.registers for f in r.fields if f.hw_input and not f.hw_reset and not
          m.snapshot_of(r.name, f.name)]
    rs = (f"**Reset.** `{c.reset}`, {c.reset_style}, active {c.reset_active}" +
          (f" (sampled on the rising edge of `{c.clock}`)" if c.reset_style == "synchronous" else "") + ". Every "
          "stored field takes the reset value in its table" + ("; W1P bits read 0" if pops else "") +
          ("; snapshot copies read 0" if m.snapshots else "") + ". ")
    rs += (f"Not reset by this block: the RO fields that read a hardware input ({_names(hw)}); they show their "
           "input's value." if hw else "Every register is reset.")
    out.append(("reset", rs))
    if m.interrupt:
        st, en = m.interrupt["status"], m.interrupt["enable"]
        bits = _names(f.name for f in m.reg(st).fields)
        out.append(("interrupt", f"**Interrupt.** `irq_o` is a level output from a register: high while any bit of {st} "
                    f"({bits}) is set together with the same bit of {en}. Clear the cause by writing 1 to its {st} bit "
                    "(W1C); the line falls one clock after the clear takes effect. A clear never loses a new event (a "
                    "hardware set in the same clock wins), but events of the same cause between the handler's read and "
                    "its clear merge into one: count them elsewhere if each one matters. Clear the cause before "
                    "unmasking the line at the interrupt controller."))
    else:
        out.append(("interrupt", "**Interrupt.** None: this block has no interrupt output; software polls its status."))
    out.append(("clock", f"**Clock domain and timing.** Every field is in the `{c.clock}` domain; hardware inputs must "
                f"be synchronous to `{c.clock}` (the block has no synchronisers). A write takes effect on the hardware "
                "in the clock its write response (BVALID) is raised" + (", and a W1P pulse is high for exactly that "
                "clock" if pops else "") + ". A read returns the hardware's values as they were in the clock the read "
                "address was accepted."))
    return out


def _field_rows(m: RegMap, r: Register) -> list[str]:
    L = ["| Bits | Field | Access | Reset | Summary |", "|---|---|---|---|---|"]
    for f in sorted(r.fields, key=lambda x: -x.lsb):
        bits = f"{f.msb}" if f.width == 1 else f"{f.msb}:{f.lsb}"
        s = m.snapshot_of(r.name, f.name)
        rst = ("0" if s or f.access in ("W1P", "WO") and not f.reset else
               "hw" if f.hw_input and not f.hw_reset else f"0x{f.reset:x}")
        acc = "RO const" if f.const else f.access
        summ = f.summary + (f" (snapshot {s.name}: reads the copy taken by {'.'.join(s.trigger)})" if s else "")
        L.append(f"| {bits} | {f.name} | {acc} | {rst} | {summ.strip()} |")
    return L


def datasheet(m: RegMap, level: int = 2) -> list[str]:
    """Register table, access types, Behaviour, each register's fields and the snapshot groups: the generated
    register document's body, and the "Registers" section of an ip_lib README (flow/net/ipdoc.py)."""
    h = "#" * level
    L = [f"{h} Register map", "", "| Offset | Register | Reset | Summary |", "|---|---|---|---|"]
    for r in m.registers:
        L.append(f"| 0x{r.offset:03x} | {r.name} | 0x{r.reset:08x} | {r.summary} |")
    L += ["", "Reset is what a read returns after reset with every hardware input low.", "",
          f"{h} Access types", "", "| Access | Meaning |", "|---|---|"]
    used = {f.access for r in m.registers for f in r.fields}
    for a, t in {**ACCESS_TEXT, **DOC_ACCESS}.items():
        if a in used or (a in ACCESS and not m.doc_only):
            L.append(f"| {a} | {t} |")
    L += ["", f"{h} Behaviour", ""] + [f"- {s}" for _, s in behaviour(m)] + [""]
    done = set()
    for r in m.registers:
        if r.group:                                   # a count: register: one section for the whole run
            if r.group in done:
                continue
            done.add(r.group)
            run = [x for x in m.registers if x.group == r.group]
            L += [f"{h} {run[0].name} to {run[-1].name} (0x{run[0].offset:03x} to 0x{run[-1].offset:03x}, "
                  f"{len(run)} registers, the same fields)", ""]
        else:
            L += [f"{h} {r.name} (0x{r.offset:03x})", ""]
        if r.summary:
            L += [r.summary, ""]
        L += _field_rows(m, r) + [""]
    if m.snapshots:
        L += [f"{h} Snapshot groups", "", "| Group | Trigger | Fields, low part first | Bits | Summary |",
              "|---|---|---|---|---|"]
        for s in m.snapshots:
            L.append(f"| {s.name} | {'.'.join(s.trigger)} | {', '.join('.'.join(x) for x in s.fields)} | "
                     f"{m.snapshot_width(s)} | {s.summary} |")
        L.append("")
    return L


# ---- markdown ------------------------------------------------------------------------------------------------------
def emit_md(m: RegMap) -> str:
    L = [f"# {m.name} registers", "", f"<!-- {_banner(m, '').strip()} -->".replace("\n", " "), "",
         f"{m.summary} {convention_sentence(m)}".strip(), "",
         f"AXI4-Lite, 32-bit registers, a 0x{m.window_bytes:x}-byte window (address bits [{m.addr_width - 1}:2] "
         f"decoded). Unmapped addresses answer {_resp(m.unmapped)} and read 0. "
         f"Version {m.version}; model sha256 `{m.sha256[:16]}`.", ""]
    L += datasheet(m)
    L += ["## Hardware ports", "", "| Port | Direction | Width |", "|---|---|---|"]
    for d, n, w in ports(m):
        L.append(f"| `{n}` | {d} | {w} |")
    L.append("")
    return "\n".join(L)


EMIT = {"sv": emit_sv, "h": emit_c, "py": emit_py, "md": emit_md}


def generate(m: RegMap, out: str | Path) -> dict[str, Path]:
    # a RegMap built in code skips from_dict: check the text that goes into comments and docstrings again
    errs = text_problems("summary", m.summary) + ([] if VERSION_RE.match(m.version) else [f"version {m.version!r}"])
    for r in m.registers:
        errs += text_problems(f"register {r.name}.summary", r.summary)
        errs += [e for f in r.fields for e in text_problems(f"register {r.name} field {f.name}.summary", f.summary)]
    for s in m.snapshots:
        errs += text_problems(f"snapshot {s.name}.summary", s.summary)
    if m.doc_only:
        errs.append(f"{m.name} is a documentation-only map (a hand-written block): nothing to generate but the datasheet")
    if errs:
        raise RegmapError("cannot generate:\n  " + "\n  ".join(errs))
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
    for s in m.snapshots:
        S = f"{P}_SNAP_{s.name}"
        lines.append(f'  printf("S {s.name} %u %u %u\\n", (unsigned){S}_TRIGGER_OFFSET, (unsigned){S}_TRIGGER_MASK, '
                     f'(unsigned){S}_WIDTH);')
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
        elif t[0] == "S":
            got.setdefault("__snap__", {})[t[1]] = {"offset": int(t[2]), "mask": int(t[3]), "width": int(t[4])}
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
    got["__snap__"] = {n: {"trigger": ".".join(s["trigger"]), "fields": [".".join(x) for x in s["fields"]]}
                       for n, s in getattr(mod, "SNAPSHOTS", {}).items()}
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
        ms = re.match(r"^\| ([A-Z][A-Z0-9_]*) \| ([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*) \| ([A-Z0-9_., ]+) \| (\d+) \|", ln)
        if ms:
            got.setdefault("__snap__", {})[ms.group(1)] = {"trigger": ms.group(2), "fields": ms.group(3).split(", "),
                                                           "width": int(ms.group(4))}
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


def compile_sv(sv: Path) -> list[str]:
    """The block must compile: read_sv only reads its ports and constants. Icarus Verilog if it is on PATH (CI installs
    it); without it the step is skipped and says so."""
    iv = shutil.which("iverilog")
    if not iv:
        print(f"note: iverilog not on PATH: {sv.name} not compiled", file=sys.stderr)
        return []
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([iv, "-g2012", "-o", str(Path(td) / "a.vvp"), str(sv)], capture_output=True, text=True)
    if r.returncode:
        return [f"SystemVerilog: does not compile (iverilog -g2012): {(r.stderr or r.stdout).strip()[:400]}"]
    return []


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
        c = read_c(m, out / names["h"])
        cmp("C header", c)
        errs += snapshot_agreement(m, {"C header": c.get("__snap__", {})})
    except (RuntimeError, KeyError, ValueError, IndexError) as ex:
        errs.append(f"C header: cannot be read back: {ex}")
    try:
        g = read_py(m, out / names["py"])
        if "__sha__" in g:
            errs.append(f"Python driver: model hash {g['__sha__'][:16]} is not the YAML's {m.sha256[:16]}")
        cmp("Python driver", g)
        errs += snapshot_agreement(m, {"Python driver": g["__snap__"]})
    except Exception as ex:  # noqa: BLE001 (a broken generated module is a finding, not a crash)
        errs.append(f"Python driver: cannot be imported: {type(ex).__name__}: {ex}")
    md = read_md(out / names["md"])
    cmp("markdown", md)
    errs += snapshot_agreement(m, {"markdown": md.get("__snap__", {})})
    sv = read_sv(m, out / names["sv"])
    cmp("SystemVerilog", sv, fields=False)
    errs += compile_sv(out / names["sv"])
    if sv["__ports__"] != ports(m):
        want, have = set(ports(m)), set(sv["__ports__"])
        errs.append(f"SystemVerilog: ports differ: missing {sorted(want - have)}, unexpected {sorted(have - want)}")
    return errs


def snapshot_agreement(m: RegMap, got: dict[str, dict]) -> list[str]:
    """Each output's snapshot groups against the YAML: the trigger and the parts (or, for the C header, the trigger's
    offset and mask), and the width."""
    errs = []
    for kind, g in got.items():
        if set(g) != {s.name for s in m.snapshots}:
            errs.append(f"{kind}: snapshot groups {sorted(g)}, the YAML says {sorted(s.name for s in m.snapshots)}")
            continue
        for s in m.snapshots:
            x = g[s.name]
            if "offset" in x:
                tr = m.reg(s.trigger[0])
                want = {"offset": tr.offset, "mask": m.field(*s.trigger).mask, "width": m.snapshot_width(s)}
            else:
                want = {"trigger": ".".join(s.trigger), "fields": [".".join(f) for f in s.fields]}
                if "width" in x:
                    want["width"] = m.snapshot_width(s)
            if x != want:
                errs.append(f"{kind}: snapshot {s.name} is {x}, the YAML says {want}")
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
