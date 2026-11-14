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

An interface profile (house, amd_compatible or strict; brief 73) names a bundle of the settings below; a map or a design
chooses one and may override single settings. `--spec designs/<d>/spec.yaml` reads the design's choice
(`interfaces: {axi_lite_profile: ..., blocks: {<map name>: {...}}}`).

The format, the access types and the generated names are in docs/hwsw.md. Plain Python and PyYAML; `check` also needs
a C compiler (gcc or cc) for the header probe.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pprint
import re
import shutil
import subprocess
import sys
import tempfile
import types
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
    unmapped: str = "split"            # split | okay | slverr: the response to an unmapped address inside the window
    reserved: str = "zero"             # zero (read 0, writes ignored) | undefined (read undefined; write 0)
    strobes: str = "honoured"          # honoured | ignored (WSTRB)
    reset: str = "aresetn"             # the reset input's name
    reset_active: str = "low"          # low | high
    reset_style: str = "synchronous"   # synchronous | asynchronous
    clock: str = "aclk"                # the clock every field is in
    partial_write: str = "accept"      # accept | slverr: a write whose strobes cover part of a multi-byte field (brief 73)
    unaligned: str = "ignore"          # ignore (address bits [1:0] are not decoded) | slverr: an address that is not word-aligned
    reserved_write: str = "ignore"     # ignore | slverr: a write of 1 to a reserved bit
    wide_values: str = "optional"      # optional | snapshot: a value in two registers must be a snapshot group


HOUSE = Conventions()
UNMAPPED_CHOICES = ("split", "okay", "slverr")
CONV_CHOICES = {"unmapped": UNMAPPED_CHOICES, "reserved": ("zero", "undefined"), "strobes": ("honoured", "ignored"),
                "reset_active": ("low", "high"), "reset_style": ("synchronous", "asynchronous"),
                "partial_write": ("accept", "slverr"), "unaligned": ("ignore", "slverr"),
                "reserved_write": ("ignore", "slverr"), "wide_values": ("optional", "snapshot")}
# ---- interface profiles (brief 73): a named bundle of the settings above, chosen once per design -------------------
# error_capture is a mode here: off | on | on+irq (the capture's place in the window is not part of a profile).
PROFILES = {
    "house": {"unmapped": "split", "error_capture": "on", "partial_write": "accept", "unaligned": "ignore",
              "reserved_write": "ignore", "wide_values": "optional"},
    "amd_compatible": {"unmapped": "okay", "error_capture": "off", "partial_write": "accept", "unaligned": "ignore",
                       "reserved_write": "ignore", "wide_values": "optional"},
    "strict": {"unmapped": "slverr", "error_capture": "on+irq", "partial_write": "slverr", "unaligned": "slverr",
               "reserved_write": "slverr", "wide_values": "snapshot"},
}
NEW_SETTINGS = ("partial_write", "unaligned", "reserved_write", "wide_values")         # added by brief 73
PROFILE_SETTINGS = tuple(PROFILES["house"])                    # the settings a profile sets, in the order shown
SETTING_CHOICES = {**{k: CONV_CHOICES[k] for k in PROFILE_SETTINGS if k != "error_capture"},
                   "error_capture": ("off", "on", "on+irq")}
PROFILE_TEXT = {
    "house": "the default: a read of a hole answers SLVERR and a write OKAY, the error-capture registers are on, byte "
             "strobes are honoured, a write of 1 to a reserved bit is ignored",
    "amd_compatible": "driver-visible compatibility with the AMD AXI4-Lite peripherals measured in brief 69: a hole "
                      "answers OKAY and reads 0, and no error-capture registers take address space; it copies none of "
                      "their defects (aliasing, lost events, tearing reads, read side effects, a lost write response)",
    "strict": "for bring-up, safety or verification-heavy work: every access the block cannot take as asked answers "
              "SLVERR (a hole, an unaligned address, a partial write to a multi-byte field, a write of 1 to a reserved "
              "bit), the error-capture registers are on with their interrupt, and a value wider than the bus must be a "
              "snapshot group",
}
INTERFACE_KEYS = {"axi_lite_profile", "blocks", "amd_ip_acknowledged"}
WIDE_PAIRS = (("_LO", "_HI"), ("_LOW", "_HIGH"), ("_LSW", "_MSW"), ("_L", "_H"))
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
C_RESERVED = {"OFFSET", "RESET", "RW_MASK", "RO_MASK", "W1C_MASK", "W1S_MASK", "W1P_MASK"}   # register-level suffixes
PROFILE_KEYS = {"profile", "partial_write", "unaligned", "reserved_write", "wide_values"}   # generated blocks only
MODEL_KEYS = {"regmap", "name", "version", "summary", "data_width", "addr_width", "unmapped", "interrupt", "registers",
              "snapshot", "error_capture"} | PROFILE_KEYS
DOC_MODEL_KEYS = (MODEL_KEYS - PROFILE_KEYS) | {"conventions", "staging"}   # documentation-only maps (an ip.yaml register_map)
REG_KEYS = {"name", "offset", "summary", "fields"}
SNAP_KEYS = {"name", "trigger", "fields", "summary"}
GROUP_KEY = object()          # set only by the count: expansion of a documentation-only map; no YAML key can equal it
STAGING_KEYS = {"name", "registers", "commit", "summary"}
FIELD_KEYS = {"name", "lsb", "width", "access", "reset", "const", "summary"}
# Names the generated block uses for its own signals. A register's per-register signals (wr_<reg>, rd_<reg>) and a
# field's ports must not meet them: a register named HIT would declare wr_hit twice.
PORT_SUFFIXES = ("_o", "_i", "_set_i", "_clr_i", "_pulse_o")
SV_INTERNAL = {"aclk", "aresetn", "aw_got", "w_got", "aw_word", "w_data", "w_bits", "w_strb", "wr_commit", "wr_hit",
               "rd_value", "rd_hit", "irq_o", "unused_ok", "ecap_bad_wr", "ecap_bad_rd", "ecap_clr", "ecap_first",
               "ecap_n", "ecap_sum", "ecap_sticky", "ecap_count", "ecap_addr", "ecap_is_write", "ecap_irq_en"}
# The error-capture registers (docs/hwsw.md): generated by default, two words; the block itself drives their fields, so
# they have no hardware ports. Their names are reserved when the capture is on.
ECAP_REGS = ("ERR_ADDR", "ERR_STATUS")
ECAP_COUNT_BITS = 8                      # ERR_STATUS.COUNT saturates at 2**8 - 1
ECAP_SIGNAL = {("ERR_ADDR", "ADDR"): "ecap_addr", ("ERR_STATUS", "STICKY"): "ecap_sticky",
               ("ERR_STATUS", "IS_WRITE"): "ecap_is_write", ("ERR_STATUS", "IRQ_EN"): "ecap_irq_en",
               ("ERR_STATUS", "COUNT"): "ecap_count"}
ECAP_KEYS = {"offset", "interrupt"}
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
    internal: bool = False    # an error-capture register: the block drives its fields itself (no hardware ports)

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
    error_capture: dict | None = None      # {offset, interrupt} of the generated error-capture registers, or None
    profile: str = ""                      # the interface profile (brief 73); "" for a documentation-only map

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
                           **({"internal": True} if r.internal else {}),
                           "fields": [{"name": f.name, "lsb": f.lsb, "width": f.width, "access": f.access,
                                       "reset": f.reset, "const": f.const} for f in r.fields]}
                          for r in self.registers],
            **({"error_capture": self.error_capture} if self.error_capture else {}),
            # only a map that leaves the house profile or its new settings changes its hash (older outputs stay current)
            **({"interface": {"profile": self.profile, **{k: getattr(self.conventions, k) for k in NEW_SETTINGS}}}
               if self.profile and (self.profile != "house" or any(getattr(self.conventions, k) != getattr(HOUSE, k)
                                                                   for k in NEW_SETTINGS)) else {}),
            **({"snapshot": [{"name": s.name, "trigger": ".".join(s.trigger), "fields": [".".join(x) for x in s.fields]}
                             for s in self.snapshots]} if self.snapshots else {}),
        }


# ---- reading and validating ----------------------------------------------------------------------------------------
def _int(v, what: str, errs: list[str]) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        errs.append(f"{what}: {v!r} is not an integer")
        return None
    return v


def load(path: str | Path, spec: str | Path | None = None) -> RegMap:
    """Read and validate a regmap YAML file. Raises RegmapError with every problem found. `spec`: the design's spec.yaml;
    a map that names no profile of its own takes the one the design chose for it (`interfaces:`, see inherit_for)."""
    p = Path(path)
    try:
        d = yaml.safe_load(p.read_text())
    except yaml.YAMLError as ex:
        raise RegmapError(f"{p}: not valid YAML: {ex}") from None
    inherit = None
    if spec is not None:
        try:
            sp = yaml.safe_load(Path(spec).read_text()) or {}
        except (OSError, yaml.YAMLError) as ex:
            raise RegmapError(f"{spec}: cannot be read: {ex}") from None
        ifs = sp.get("interfaces") if isinstance(sp, dict) else None
        errs = interfaces_errors(ifs)
        if errs:
            raise RegmapError(f"{spec}: interfaces:\n  " + "\n  ".join(errs))
        inherit = inherit_for(ifs, d.get("name") if isinstance(d, dict) else None)
    return from_dict(d, source=str(p), inherit=inherit)


def interfaces_errors(ifs) -> list[str]:
    """Why a spec.yaml `interfaces:` section is not valid ([] = fine, or absent)."""
    if ifs is None:
        return []
    if not isinstance(ifs, dict):
        return ["must be a mapping: {axi_lite_profile: house|amd_compatible|strict, blocks: {<map name>: {profile: ..., "
                "<setting>: ...}}, amd_ip_acknowledged: [<AMD IP name>, ...]}"]
    errs = []
    if set(ifs) - INTERFACE_KEYS:
        errs.append(f"unknown keys {sorted(set(ifs) - INTERFACE_KEYS)} (allowed: {', '.join(sorted(INTERFACE_KEYS))})")
    p = ifs.get("axi_lite_profile")
    if p is not None and not (isinstance(p, str) and p in PROFILES):
        errs.append(f"axi_lite_profile: {p!r} must be one of {', '.join(PROFILES)}")
    blocks = ifs.get("blocks", {})
    if not isinstance(blocks, dict):
        errs.append("blocks: must be a mapping from a register map's name to its profile and settings")
        blocks = {}
    for n, b in blocks.items():
        if not isinstance(b, dict):
            errs.append(f"blocks.{n}: must be a mapping (profile and/or settings)")
            continue
        for k, v in b.items():
            if k == "profile":
                if not (isinstance(v, str) and v in PROFILES):
                    errs.append(f"blocks.{n}.profile: {v!r} must be one of {', '.join(PROFILES)}")
            elif k in SETTING_CHOICES:
                if not (isinstance(v, str) and v in SETTING_CHOICES[k]):
                    errs.append(f"blocks.{n}.{k}: {v!r} must be one of {', '.join(SETTING_CHOICES[k])}")
            else:
                errs.append(f"blocks.{n}.{k}: unknown (a profile or one of {', '.join(SETTING_CHOICES)})")
    ack = ifs.get("amd_ip_acknowledged", [])
    if not isinstance(ack, list) or not all(isinstance(x, str) for x in ack):
        errs.append("amd_ip_acknowledged: must be a list of AMD IP names (for example axi_gpio)")
    return errs


def inherit_for(ifs: dict | None, name: str | None) -> dict:
    """What a map named `name` takes from the design's `interfaces:` when it names no profile itself: the profile (the
    block's own entry, else the design's, else None = house) and the block's single-setting overrides."""
    ifs = ifs or {}
    b = (ifs.get("blocks") or {}).get(name) or {}
    return {"profile": b.get("profile") or ifs.get("axi_lite_profile"),
            "settings": {k: v for k, v in b.items() if k != "profile"}}


def from_dict(d, source: str = "<dict>", doc_only: bool = False, inherit: dict | None = None) -> RegMap:
    """Validate a regmap. doc_only: the map documents a hand-written block (an ip_lib entry's ip.yaml register_map),
    so it may also use WO registers, `count:` (DATA0..DATAn-1), RO fields with a known hardware reset, `conventions:`
    and `staging:`; nothing is generated from it but the datasheet."""
    errs: list[str] = []
    if not isinstance(d, dict):
        raise RegmapError(f"{source}: the top level must be a mapping")
    extra = set(d) - (DOC_MODEL_KEYS if doc_only else MODEL_KEYS)
    if extra:
        errs.append(f"unknown top-level keys {sorted(extra)}" +
                    (" (conventions and staging are for documentation-only maps; a generated block takes its conventions "
                     "from an interface profile, docs/hwsw.md)" if extra & {"conventions", "staging"} else "") +
                    (" (a profile and its settings are for generated blocks; a documentation-only map states the "
                     "hand-written block's own under conventions:)" if extra & PROFILE_KEYS else ""))
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
    if doc_only and "unmapped" not in d:
        errs.append("unmapped: a documentation-only map states the hand-written block's response (split, okay or "
                    "slverr): there is no default to assume")
    prof, prof_set, errs_p = _profile(d, inherit, doc_only)
    errs += errs_p
    unmapped = d.get("unmapped", prof_set["unmapped"] if prof else HOUSE.unmapped)
    if unmapped not in UNMAPPED_CHOICES:
        errs.append(f"unmapped: {unmapped!r} must be one of {', '.join(UNMAPPED_CHOICES)}")
    conv = {"unmapped": unmapped}
    if prof:
        for k in NEW_SETTINGS:
            conv[k] = d.get(k, prof_set[k])
            if conv[k] not in CONV_CHOICES[k]:
                errs.append(f"{k}: {conv[k]!r} must be one of {', '.join(CONV_CHOICES[k])}")
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
    cap = _error_capture(d, aw, doc_only, errs, prof_set["error_capture"] if prof else None)
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
                grown += [{**base, "name": f"{r.get('name')}{i}", "offset": off + 4 * i, GROUP_KEY: r.get("name"),
                               "summary": str(r.get("summary", "")).replace("{n}", str(i))} for i in range(n)]
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
        extra = set(r) - REG_KEYS - ({GROUP_KEY} if doc_only else set())
        if extra:
            errs.append(f"{where}: unknown keys {sorted(extra)}")
        if not isinstance(rn, str) or not REG_RE.match(rn):
            errs.append(f"{where}: name must be upper-case (letters, digits, _), starting with a letter")
            rn = f"R{i}"
        if cap and rn in ECAP_REGS:
            errs.append(f"{where}: the name is reserved for the error-capture registers (give the register another "
                        "name, or leave the capture out with error_capture: false)")
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
                                 str(r.get(GROUP_KEY, "")) if doc_only else ""))
    if cap and aw is not None:
        words = {cap["offset"] // 4, cap["offset"] // 4 + 1}
        for w in sorted(words & set(seen_off)):
            errs.append(f"error_capture: its registers ERR_ADDR (0x{cap['offset']:x}) and ERR_STATUS "
                        f"(0x{cap['offset'] + 4:x}) would overlap register {seen_off[w]} at 0x{4 * w:x}: move that "
                        "register, or place the capture elsewhere with error_capture: {offset: 0x...} (the offset of "
                        "ERR_ADDR; ERR_STATUS is the next word)")
        regs += _capture_registers(cap, aw)
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
    if prof and conv.get("wide_values") == "snapshot":
        errs += wide_value_problems(regs, snaps)
    if errs:
        raise RegmapError(f"{source}:\n  " + "\n  ".join(errs))
    m = RegMap(name, str(d.get("version", "0.0.0")), str(d.get("summary", "")), aw, unmapped,
               tuple(sorted(regs, key=lambda x: x.offset)), irq, snapshots=snaps, staging=stag, doc_only=doc_only,
               conventions=Conventions(**conv), error_capture=cap, profile=prof)
    h = hashlib.sha256(json.dumps(m.canonical(), sort_keys=True).encode()).hexdigest()
    return dataclasses.replace(m, sha256=h)


CAPTURE_RAW = {"off": False, "on": True, "on+irq": {"interrupt": True}}


def _profile(d: dict, inherit: dict | None, doc_only: bool) -> tuple[str, dict, list[str]]:
    """The map's interface profile and its settings (before the map's own single-setting keys): its `profile:` key, else
    what the design's spec.yaml chose for it (`inherit`, see inherit_for), else house. A documentation-only map has none."""
    if doc_only:
        return "", {}, []
    errs: list[str] = []
    own = d.get("profile")
    if own is not None and not (isinstance(own, str) and own in PROFILES):
        errs.append(f"profile: {own!r} must be one of {', '.join(PROFILES)} (docs/hwsw.md)")
        own = None
    inh = inherit or {}
    name = own or inh.get("profile") or "house"
    base = dict(PROFILES[name])
    if own is None:                      # a map that names its own profile is not changed by the design's block entry
        base.update(inh.get("settings") or {})
    return name, base, errs


def _capture_mode(cap: dict | None) -> str:
    return "off" if cap is None else "on+irq" if cap["interrupt"] else "on"


def wide_value_problems(regs, snaps) -> list[str]:
    """Wide values under wide_values: snapshot. A value wider than the bus is two or more registers; the generator cannot
    see which registers belong together, so it recognises the naming pairs NAME_LO/NAME_HI, _LOW/_HIGH, _LSW/_MSW and
    _L/_H: every hardware-input (RO) field in such a pair must be in a snapshot group. Any other wide value is the
    author's to put in a group; the datasheet says so."""
    names = {r.name: r for r in regs}
    in_snap = {x for sn in snaps for x in sn.fields}
    errs = []
    for lo, hi in WIDE_PAIRS:
        for n, r in names.items():
            if n.endswith(lo) and n[:-len(lo)] + hi in names:
                grp = {next((i for i, sn in enumerate(snaps) if (rr.name, f.name) in sn.fields), None)
                       for rr in (r, names[n[:-len(lo)] + hi]) for f in rr.fields if f.hw_input}
                if len(grp) > 1 and None not in grp:
                    errs.append(f"registers {r.name} and {n[:-len(lo)] + hi} look like the two halves of one value but are "
                                "in different snapshot groups: put both halves in one group")
                for reg in (r, names[n[:-len(lo)] + hi]):
                    bad = [f.name for f in reg.fields if f.hw_input and (reg.name, f.name) not in in_snap]
                    if bad:
                        errs.append(f"registers {r.name} and {n[:-len(lo)] + hi} look like the two halves of one value "
                                    f"and {reg.name} reads a hardware input ({', '.join(bad)}) outside a snapshot group: "
                                    "the profile requires one (a read of the halves can tear), or set wide_values: optional")
    return sorted(set(errs))


def _error_capture(d: dict, aw, doc_only: bool, errs: list[str], profile_mode: str | None = None) -> dict | None:
    """The `error_capture:` setting: absent or true = on at the top two words of the window, false = left out,
    {offset: 0x.., interrupt: true|false} = placed and/or with an interrupt. Returns {offset, interrupt} or None."""
    raw = d.get("error_capture", None if doc_only else CAPTURE_RAW[profile_mode or "on"])
    if doc_only:
        if "error_capture" in d:
            errs.append("error_capture: a documentation-only map describes a hand-written block; it has no generated "
                        "capture (a block that has one lists its registers in the map)")
        return None
    if raw is False:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - ECAP_KEYS:
        errs.append("error_capture: must be true, false or {offset: <ERR_ADDR byte offset>, interrupt: true|false}")
        return None
    irq = raw.get("interrupt", profile_mode == "on+irq")      # placing the capture does not drop its profile's interrupt
    if not isinstance(irq, bool):
        errs.append("error_capture.interrupt: must be true or false")
        irq = False
    if aw is None or not 4 <= aw <= 32:
        return None                              # addr_width is reported on its own
    off = raw.get("offset", (1 << aw) - 8)
    off = _int(off, "error_capture.offset", errs)
    if off is None:
        return None
    if off % 4 or not 0 <= off <= (1 << aw) - 8:
        errs.append(f"error_capture.offset: 0x{off:x} must be a multiple of 4 with room for two words inside the "
                    f"0x{1 << aw:x}-byte window")
        return None
    return {"offset": off, "interrupt": irq}


def _capture_registers(cap: dict, aw: int) -> list[Register]:
    """ERR_ADDR and ERR_STATUS: what the block records about an access to an unmapped address."""
    f = Field
    addr = Register("ERR_ADDR", cap["offset"], (
        f("ADDR", 0, aw, "RO", 0, False, "word-aligned address, inside the window, of the first unmapped access since "
          "the last clear; valid while STICKY is 1", True),), "Address of the first unmapped access since the last "
        "clear.", internal=True)
    fields = [f("STICKY", 0, 1, "W1C", 0, False, "an unmapped access happened since the last clear; write 1 to clear "
                "(also clears COUNT)"),
              f("IS_WRITE", 1, 1, "RO", 0, False, "the recorded access was a write; valid while STICKY is 1", True)]
    if cap["interrupt"]:
        fields.append(f("IRQ_EN", 2, 1, "RW", 0, False, "1 raises irq_o while STICKY is 1"))
    fields.append(f("COUNT", 8, ECAP_COUNT_BITS, "RO", 0, False, "unmapped accesses since the last clear, saturating at "
                    f"{(1 << ECAP_COUNT_BITS) - 1}", True))
    status = Register("ERR_STATUS", cap["offset"] + 4, tuple(fields), "Error-capture flags and count.", internal=True)
    return [addr, status]


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
    if r.internal:
        return ("", "", 0)
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
            if f.access in ("W1C", "W1S") and not r.internal:
                out.append(("output", f"{r.name}_{f.name}".lower() + "_o", f.width))
    if m.interrupt or capture_irq(m):
        out.append(("output", "irq_o", 1))
    return out


def capture_irq(m: RegMap) -> bool:
    return bool(m.error_capture and m.error_capture["interrupt"])


def settings(m: RegMap) -> dict[str, str]:
    """The profile's settings as this map has them (after the map's own overrides), in the profile's order."""
    c = m.conventions
    return {"unmapped": m.unmapped, "error_capture": _capture_mode(m.error_capture), "partial_write": c.partial_write,
            "unaligned": c.unaligned, "reserved_write": c.reserved_write, "wide_values": c.wide_values}


def settings_text(m: RegMap) -> str:
    return " ".join(f"{k}={v}" for k, v in settings(m).items())


def profile_overrides(m: RegMap) -> list[tuple[str, str, str]]:
    """(setting, this map's value, the profile's value) for every setting that differs from the map's profile."""
    return [(k, v, PROFILES[m.profile][k]) for k, v in settings(m).items() if v != PROFILES[m.profile][k]]


def rejects(m: RegMap) -> bool:
    """True when the block can answer SLVERR to an access to a mapped address (the strict settings)."""
    c = m.conventions
    return "slverr" in (c.partial_write, c.unaligned, c.reserved_write)


def lanes(f: Field) -> int:
    """The byte lanes a field occupies, as a 4-bit mask."""
    return sum(1 << b for b in range(4) if f.mask >> (8 * b) & 0xFF)


def multilane_fields(r: Register) -> list[Field]:
    """Writable fields that span more than one byte lane: a partial write could tear them."""
    return [f for f in r.fields if f.access != "RO" and bin(lanes(f)).count("1") > 1]


def reserved_mask(r: Register) -> int:
    used = 0
    for f in r.fields:
        used |= f.mask
    return ~used & 0xFFFFFFFF


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
    c = m.conventions
    unal, rej = c.unaligned == "slverr", rejects(m)
    resp_rd = "2'b10" if m.unmapped in ("slverr", "split") else "2'b00"    # split: a read of a hole is an error ...
    resp_wr = "2'b10" if m.unmapped == "slverr" else "2'b00"               # ... a write to a hole is not
    L = [_banner(m, "//").rstrip("\n"),
         f"// {m.name}_regs: AXI4-Lite register block. {m.summary}".rstrip(),
         "//",
         "// AXI4-Lite slave, 32-bit data, one outstanding read and one outstanding write. AW and W are captured",
         "// independently (either may come first); the write commits when both are held, then BVALID stays high until",
         "// BREADY. Byte strobes (WSTRB) are honoured bit by bit. Read data is registered at the AR handshake.",
         f"// Unmapped addresses: {_unmapped_comment(m.unmapped)}. Reads have",
         "// no side effects. A hardware set beats a same-clock W1C clear; a W1S set beats a same-clock hardware clear.",
         *(["// Every access to an unmapped address" + (", and every access this profile rejects," if rejects(m) else "") + " is recorded in ERR_ADDR and ERR_STATUS (error capture, docs/hwsw.md)."]
           if m.error_capture else []),
         f"// Only address bits [{aw - 1}:2] are decoded: the window repeats every 0x{m.window_bytes:x} bytes.",
         "// Writes to read-only bits are ignored with OKAY (strict: unless the write puts a 1 in a reserved bit). Reset: synchronous, active low (aresetn).",
         *_profile_comment(m),
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
          *(["    localparam logic [1:0] RESP_SLVERR = 2'b10;   // a mapped access this profile rejects"] if rej else []),
          f"    localparam logic [1:0] RESP_UNMAPPED_RD = {resp_rd};   // a read of an unmapped address",
          f"    localparam logic [1:0] RESP_UNMAPPED_WR = {resp_wr};   // a write to an unmapped address",
          "",
          "    // ---- write channel: capture AW and W independently, commit when both are held ----",
          "    logic            aw_got, w_got;",
          f"    logic [{aw - 3}:0]  aw_word;",
          *(["    logic [1:0]      aw_lo;           // address bits [1:0] of the write (strict: not 0 is an error)"] if unal else []),
          "    logic [31:0]     w_data, w_bits;",
          "    logic [3:0]      w_strb;",
          "    logic            wr_commit, wr_hit;",
          *(["    logic            wr_rej;          // a write to a mapped address that this profile rejects"] if rej else []),
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
          *(["            aw_lo <= '0;"] if unal else []),
          "            w_data <= '0;",
          "            w_strb <= '0;",
          "            s_axil_bvalid <= 1'b0;",
          "            s_axil_bresp <= RESP_OKAY;",
          "        end else begin",
          "            if (s_axil_awvalid && s_axil_awready) begin",
          "                aw_got <= 1'b1;",
          f"                aw_word <= s_axil_awaddr[{aw - 1}:2];",
          *(["                aw_lo <= s_axil_awaddr[1:0];"] if unal else []),
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
          ("                s_axil_bresp <= !wr_hit ? RESP_UNMAPPED_WR : wr_rej ? RESP_SLVERR : RESP_OKAY;" if rej else
           "                s_axil_bresp <= wr_hit ? RESP_OKAY : RESP_UNMAPPED_WR;"),
          "            end else if (s_axil_bvalid && s_axil_bready) begin",
          "                s_axil_bvalid <= 1'b0;",
          "            end",
          "        end",
          "    end",
          ""]
    # write decode
    L.append("    // write decode: one strobe per register" + ("; a write this profile rejects raises wr_rej and no strobe" if rej else ""))
    wregs = [r for r in m.registers if any(f.access != "RO" for f in r.fields)]
    for r in wregs:
        L.append(f"    logic wr_{r.name.lower()};")
    L.append("    always_comb begin")
    L.append("        wr_hit = 1'b0;")
    if rej:
        L.append("        wr_rej = 1'b0;")
    for r in wregs:
        L.append(f"        wr_{r.name.lower()} = 1'b0;")
    L.append("        if (wr_commit) begin")
    ind = "            "
    if unal:
        L.append("            if (aw_lo != 2'b00) begin   // unaligned address: rejected whatever it addresses")
        L.append("                wr_hit = 1'b1;")
        L.append("                wr_rej = 1'b1;")
        L.append("            end else begin")
        ind = "                "
    L.append(f"{ind}case (aw_word)")
    for r in m.registers:
        bad = _reject_terms(m, r)
        if not bad:
            if r in wregs:
                L.append(f"{ind}    ADDR_{r.name}: begin wr_hit = 1'b1; wr_{r.name.lower()} = 1'b1; end")
            else:
                L.append(f"{ind}    ADDR_{r.name}: wr_hit = 1'b1;   // read-only: the write is ignored")
        else:
            L.append(f"{ind}    ADDR_{r.name}: begin")
            L.append(f"{ind}        wr_hit = 1'b1;")
            L.append(f"{ind}        // rejected: " + ", or ".join(
                [f"strobes cover part of {f.name}" for f in multilane_fields(r)] * (c.partial_write == "slverr") +
                ["a 1 in a reserved bit"] * (c.reserved_write == "slverr" and bool(reserved_mask(r)))))
            L.append(f"{ind}        wr_rej = " + f"\n{ind}                 || ".join(bad) + ";")
            if r in wregs:
                L.append(f"{ind}        wr_{r.name.lower()} = !wr_rej;")
            L.append(f"{ind}    end")
    L.append(f"{ind}    default: wr_hit = 1'b0;")
    L.append(f"{ind}endcase")
    if unal:
        L.append("            end")
    L.append("        end")
    L.append("    end")
    L.append("")
    # field storage
    L.append("    // ---- field storage ----")
    for r in m.registers:
        if r.internal:
            continue
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
    if m.error_capture:
        L += _declare_capture(m)
    # read values
    L.append("    // ---- read path: the value of each register as software sees it ----")
    for r in m.registers:
        terms = []
        for f in r.fields:
            base = f"{r.name}_{f.name}".lower()
            if r.internal:
                src = ECAP_SIGNAL[(r.name, f.name)]
            elif f.access == "RO":
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
          *(["    logic        rd_unal;           // an unaligned read address (strict: SLVERR, data 0)",
             "    assign rd_unal = s_axil_araddr[1:0] != 2'b00;"] if unal else []),
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
          ("            s_axil_rdata <= rd_unal ? 32'h0 : rd_value;" if unal else "            s_axil_rdata <= rd_value;"),
          ("            s_axil_rresp <= rd_unal ? RESP_SLVERR : rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;" if unal else
           "            s_axil_rresp <= rd_hit ? RESP_OKAY : RESP_UNMAPPED_RD;"),
          "        end else if (s_axil_rvalid && s_axil_rready) begin",
          "            s_axil_rvalid <= 1'b0;",
          "        end",
          "    end"]
    if m.error_capture:
        L += _emit_capture(m)
    if m.interrupt or capture_irq(m):
        terms, what = [], []
        if m.interrupt:
            st, en = m.interrupt["status"], m.interrupt["enable"]
            terms.append(f"|(rd_{st.lower()} & rd_{en.lower()})")
            what.append(f"any {st} bit whose {en} bit is set")
        if capture_irq(m):
            terms.append("(ecap_sticky & ecap_irq_en)")
            what.append("ERR_STATUS.STICKY with ERR_STATUS.IRQ_EN")
        L += ["",
              f"    // ---- interrupt: level, registered: {', or '.join(what)} ----",
              "    always_ff @(posedge aclk) begin",
              "        if (!aresetn) irq_o <= 1'b0;",
              f"        else irq_o <= {' | '.join(terms)};",
              "    end"]
    L += ["",
          ("    // AxPROT is accepted and not used; address bits [1:0] are checked (strict), not decoded" if unal else
           "    // AxPROT is accepted and not used; the unused address bits [1:0] are word-aligned by the protocol"),
          "    logic unused_ok;",
          ("    assign unused_ok = ^{s_axil_awprot, s_axil_arprot};" if unal else
           "    assign unused_ok = ^{s_axil_awprot, s_axil_arprot, s_axil_awaddr[1:0], s_axil_araddr[1:0]};"),
          "endmodule", ""]
    return "\n".join(L)


def _reject_terms(m: RegMap, r: Register) -> list[str]:
    """The SystemVerilog terms, ORed, that make a write to register r a rejected one (strict): a strobe pattern that
    covers part of a multi-lane field, a 1 written to a reserved bit."""
    c, t = m.conventions, []
    if c.partial_write == "slverr":
        for f in multilane_fields(r):
            ln = lanes(f)
            t.append(f"((w_strb & 4'b{ln:04b}) != 4'b0000 && (w_strb & 4'b{ln:04b}) != 4'b{ln:04b})")
    if c.reserved_write == "slverr" and reserved_mask(r):
        t.append(f"((w_data & w_bits & 32'h{reserved_mask(r):08x}) != 32'h0)")
    return t


def _profile_comment(m: RegMap) -> list[str]:
    """The profile and its settings, in a form the check tool reads back (flow/checks/axi_profile.py)."""
    if not m.profile:
        return []
    L = ["//", f"// PROFILE {m.profile}", f"// SETTINGS {settings_text(m)}"]
    c = m.conventions
    if c.unaligned == "slverr":
        L.append("// An access whose address bits [1:0] are not 0 answers SLVERR (a read returns 0; a write changes nothing).")
    if c.partial_write == "slverr":
        L.append("// A write whose strobes cover part of a field that spans several byte lanes answers SLVERR and changes nothing.")
    if c.reserved_write == "slverr":
        L.append("// A write of 1 to a reserved bit (in a strobed byte) answers SLVERR and changes nothing.")
    return L


def _unmapped_comment(u: str) -> str:
    return {"okay": "OKAY on both channels, reads return 0",
            "slverr": "SLVERR on both channels, reads return 0",
            "split": "a read answers SLVERR with data 0, a write answers OKAY and changes nothing"}[u]


def _declare_capture(m: RegMap) -> list[str]:
    """The capture's signals, declared before the read path that reads them."""
    aw, cb = m.addr_width, ECAP_COUNT_BITS
    L = ["    // ---- error capture state (see below the read path) ----",
         "    logic ecap_bad_wr, ecap_bad_rd, ecap_clr, ecap_first;",
         "    logic ecap_sticky, ecap_is_write;",
         f"    logic [{aw - 1}:0] ecap_addr;",
         f"    logic [{cb - 1}:0] ecap_count;",
         f"    logic [{cb}:0] ecap_sum;"]
    if capture_irq(m):
        L.append("    logic ecap_irq_en;")
    return L + [""]


def _emit_capture(m: RegMap) -> list[str]:
    """Error capture: the first unmapped access since the last clear, a saturating count, a sticky flag. Whatever the
    unmapped response setting, every access to an unmapped address is recorded."""
    aw, irq = m.addr_width, capture_irq(m)
    cb = ECAP_COUNT_BITS
    L = ["",
         "    // ---- error capture: every access to an unmapped address is recorded (ERR_ADDR, ERR_STATUS) ----",
         "    // The first one since the last clear sets STICKY and is kept; later ones only add to COUNT (saturating).",
         "    // A write of 1 to STICKY clears the record; a bad access in the clock of that clear is not lost: it starts",
         "    // the new record. A bad read and a bad write in the same clock count 2 and the read is the one recorded.",
         ("    assign ecap_bad_wr = wr_commit && (!wr_hit || wr_rej);" if rejects(m) else
          "    assign ecap_bad_wr = wr_commit && !wr_hit;"),
         ("    assign ecap_bad_rd = s_axil_arvalid && s_axil_arready && (!rd_hit || rd_unal);" if m.conventions.unaligned == "slverr" else
          "    assign ecap_bad_rd = s_axil_arvalid && s_axil_arready && !rd_hit;"),
         "    assign ecap_clr    = wr_err_status && w_data[0] && w_bits[0];",
         "    assign ecap_first  = ecap_clr || !ecap_sticky;"]
    L += [f"    assign ecap_sum = {{1'b0, ecap_clr ? {cb}'h0 : ecap_count}} + {{{cb}'h0, ecap_bad_rd}} + {{{cb}'h0, ecap_bad_wr}};",
          "    always_ff @(posedge aclk) begin",
          "        if (!aresetn) begin",
          "            ecap_sticky <= 1'b0;",
          "            ecap_is_write <= 1'b0;",
          f"            ecap_addr <= {aw}'h0;",
          f"            ecap_count <= {cb}'h0;",
          "        end else if (ecap_bad_rd || ecap_bad_wr) begin",
          "            ecap_sticky <= 1'b1;",
          f"            ecap_count <= ecap_sum[{cb}] ? {{{cb}{{1'b1}}}} : ecap_sum[{cb - 1}:0];",
          "            if (ecap_first) begin",
          f"                ecap_addr <= ecap_bad_rd ? {{s_axil_araddr[{aw - 1}:2], 2'b00}} : {{aw_word, 2'b00}};",
          "                ecap_is_write <= !ecap_bad_rd;",
          "            end",
          "        end else if (ecap_clr) begin",
          "            ecap_sticky <= 1'b0;",
          f"            ecap_count <= {cb}'h0;",
          "        end",
          "    end"]
    if irq:
        L += ["    always_ff @(posedge aclk) begin",
              "        if (!aresetn) ecap_irq_en <= 1'b0;",
              "        else if (wr_err_status) ecap_irq_en <= (ecap_irq_en & ~w_bits[2]) | (w_data[2] & w_bits[2]);",
              "    end"]
    return L


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
         *([f"#define {P}_PROFILE \"{m.profile}\"", f"#define {P}_SETTINGS \"{settings_text(m)}\""] if m.profile else []),
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
PROFILE = {m.profile!r}
SETTINGS = {settings(m) if m.profile else {}!r}
ERROR_CAPTURE = {m.error_capture!r}
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


def _unmapped_short(u: str) -> str:
    """The one-line statement of the response, for the top of the datasheet and the list of differences."""
    return {"okay": "OKAY and read 0", "slverr": "SLVERR and read 0",
            "split": "a read answers SLVERR with data 0 and a write answers OKAY and changes nothing"}[u]


def differences(m: RegMap) -> list[str]:
    """Where this block's behaviour differs from the house register conventions (docs/hwsw.md), in plain words."""
    c, h, out = m.conventions, HOUSE, []
    if c.unmapped != h.unmapped:
        out.append(f"unmapped addresses inside the block: {_unmapped_short(c.unmapped)} (house: "
                   f"{_unmapped_short(h.unmapped)})")
    if m.error_capture is None:
        out.append("it records no unmapped accesses (house: the ERR_ADDR and ERR_STATUS error-capture registers)")
    elif capture_irq(m):
        out.append("the error capture has an interrupt (house: none)")
    if c.partial_write != h.partial_write:
        out.append("a write whose strobes cover part of a multi-byte field answers SLVERR and changes nothing (house: "
                   "accepted, only the strobed bytes change)")
    if c.unaligned != h.unaligned:
        out.append("an access whose address bits [1:0] are not 0 answers SLVERR (house: the low bits are not decoded)")
    if c.reserved_write != h.reserved_write:
        out.append("a write of 1 to a reserved bit answers SLVERR and changes nothing (house: ignored)")
    if c.reserved != h.reserved:
        out.append("reserved bits read an undefined value (house: they read 0)")
    if c.strobes != h.strobes:
        out.append("byte strobes are ignored, so every write changes the whole word (house: strobes honoured)")
    if (c.reset, c.reset_active, c.reset_style) != (h.reset, h.reset_active, h.reset_style):
        out.append(f"the reset is `{c.reset}`, {c.reset_style}, active {c.reset_active} (house: `{h.reset}`, "
                   f"{h.reset_style}, active {h.reset_active})")
    return out


def profile_sentence(m: RegMap) -> str:
    """The profile the block follows, and every setting of the map that differs from it (generated blocks only)."""
    if not m.profile:
        return ""
    ov = profile_overrides(m)
    t = f"Interface profile: `{m.profile}` ({PROFILE_TEXT[m.profile]})."
    if ov:
        t += " Settings that differ from the profile: " + "; ".join(f"{k} = {v} (profile: {pv})" for k, v, pv in ov) + "."
    else:
        t += " No setting differs from the profile."
    return t


def convention_sentence(m: RegMap) -> str:
    d = differences(m)
    if not d:
        return "This block follows the house register conventions (docs/hwsw.md); the Behaviour section states each one."
    return ("This block differs from the house register conventions (docs/hwsw.md) in " + str(len(d)) + " way" +
            ("s" if len(d) > 1 else "") + ": " + "; ".join(d) + ".")


def behaviour(m: RegMap) -> list[tuple[str, str]]:
    """(topic, sentence) for every behaviour a user could reasonably guess wrong, each generated from a setting of the
    map (or of its conventions). hwsw/tests/test_64a_regmap.py checks that each sentence follows its setting."""
    c = m.conventions
    ref = lambda r, f: f"{r.name}.{f.name}"                                    # noqa: E731
    by_acc = lambda a: [ref(r, f) for r in m.registers for f in r.fields if f.access == a]   # noqa: E731
    out = []
    if m.profile:
        out.append(("profile", "**" + profile_sentence(m).replace("Interface profile: ", "Interface profile.** ", 1) +
                    " The profile is chosen once per design (spec.yaml `interfaces:`) and may be overridden per block "
                    "and per setting; the settings it bundles are listed in docs/hwsw.md."))
    win = f"0x{m.window_bytes:x}-byte window"
    outside = "Addresses outside the window belong to the interconnect (an AXI crossbar answers DECERR there)."
    exp = " What an Arm CPU does with these responses is expected, not yet measured on this project's platforms (docs/hwsw.md)."
    if c.unmapped == "okay":
        out.append(("unmapped", f"**Unmapped addresses.** An address inside this block's {win} that holds no register "
                    "answers OKAY and reads 0; a write there is ignored. " + outside))
    elif c.unmapped == "slverr":
        out.append(("unmapped", f"**Unmapped addresses.** An address inside this block's {win} that holds no register "
                    "answers SLVERR and reads 0, for a read and for a write (a write there is ignored). A SLVERR on a "
                    "load is expected to be a synchronous external abort on an Arm CPU, so a stray access stops the "
                    "program; a SLVERR on a posted write is expected to arrive late and imprecisely." + exp + " " + outside))
    else:
        out.append(("unmapped", f"**Unmapped addresses.** An address inside this block's {win} that holds no register: "
                    "a read answers SLVERR with data 0, and a write answers OKAY and changes nothing (split response). "
                    "The read is made visible because it reports at the load on an Arm CPU (expected: a synchronous "
                    "external abort); the write is quiet because a SLVERR on a posted write is expected to reach the "
                    "CPU late and imprecisely, where it is hard to attribute." + exp + " " + outside))
    if m.error_capture:
        a, s = m.reg("ERR_ADDR"), m.reg("ERR_STATUS")
        cnt = m.field("ERR_STATUS", "COUNT")
        irq = ("ERR_STATUS.IRQ_EN (reset 0) enables the interrupt: `irq_o` is high while STICKY is 1 and IRQ_EN is 1 "
               "(registered, one clock after the cause)." if capture_irq(m) else
               "The capture raises no interrupt.")
        also = (" An access this profile answers with SLVERR (an unaligned address, a rejected write: see Partial writes, "
                "Access width and alignment, Reserved bits) is recorded in the same way, so the registers do not say "
                "which cause it was." if rejects(m) else "")
        out.append(("error_capture", f"**Error capture.** Every access to an unmapped address is recorded, whatever "
                    f"the response above.{also} ERR_STATUS.STICKY (0x{s.offset:03x}) is set by the first one since the last "
                    f"clear; ERR_ADDR (0x{a.offset:03x}) then holds its word-aligned address inside the window (the "
                    "address bits the block decodes) and ERR_STATUS.IS_WRITE says whether it was a write. Later bad "
                    f"accesses do not replace them: ERR_STATUS.COUNT counts every one, saturating at "
                    f"{(1 << cnt.width) - 1}. Write 1 to STICKY to clear the record (STICKY and COUNT go to 0; ERR_ADDR "
                    "and IS_WRITE keep their last values and are meaningful only while STICKY is 1). A bad access in "
                    "the same clock as that clear is not lost: it starts the new record (STICKY 1, COUNT 1). A bad "
                    "read and a bad write in the same clock count 2 and the read is the one recorded. Reads of the "
                    "capture registers have no side effects. " + irq))
    else:
        out.append(("error_capture", "**Error capture.** None: this block records nothing about accesses to unmapped "
                    "addresses."))
    if c.reserved == "zero" and c.reserved_write == "slverr":
        out.append(("reserved", "**Reserved bits.** Bits that belong to no field read 0. A write that has 1 in a "
                    "reserved bit (in a byte lane whose strobe is 1) answers SLVERR and changes nothing at all, not even "
                    "the other fields of the register: write reserved bits as 0, or write back only what you read "
                    "(reserved bits read 0). A 0 in a reserved bit is accepted."))
    elif c.reserved == "zero":
        out.append(("reserved", "**Reserved bits.** Bits that belong to no field read 0 and ignore writes. Write them "
                    "as 0, so that a later version can give them a meaning."))
    else:
        out.append(("reserved", "**Reserved bits.** Bits that belong to no field read an undefined value: mask them "
                    "off after a read, and write them as 0."))
    staged = {x for g in m.staging for x in g.registers}
    pops = by_acc("W1P")
    trig = {".".join(s.trigger) for s in m.snapshots}
    cmds = [x for x in pops if x not in trig]
    bells = by_acc("W1S")
    wo = [r.name for r in m.registers if any(f.access == "WO" for f in r.fields) and r.name not in staged]
    acts = []
    if cmds:
        acts.append(f"To start, pop or acknowledge something, write 1 to its W1P bit: {_names(cmds)}.")
    if trig:
        acts.append(f"A snapshot is taken by writing 1 to its trigger: {_names(sorted(trig))}.")
    if bells:
        acts.append(f"Doorbells are W1S bits: {_names(bells)}.")
    if wo:
        acts.append(f"Writes act on the hardware only through {_names(wo)}.")
    act = " ".join(acts) or "This block has no command, doorbell or snapshot bits."
    rmw = by_acc("W1C") + bells + pops
    safe = ("so a debugger or a retried read is safe. A read-modify-write must write the W1C, W1S and W1P bits as 0 "
            f"(here {_names(rmw)}), or it clears, sets or pulses them: write back only the RW bits of what was read. "
            if rmw else "so a debugger, a retried read or a read-modify-write is safe. ")
    out.append(("side_effects", "**Reads have no side effects.** Reading any register changes nothing, " + safe + act +
                " A write to a read-only register is answered OKAY and ignored" +
                (", unless it puts a 1 in a reserved bit of that register (see Reserved bits)." if c.reserved_write == "slverr" else ".")))
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
    if c.strobes == "honoured" and c.partial_write == "slverr":
        ml = [f"{r.name}.{f.name}" for r in m.registers for f in multilane_fields(r)]
        out.append(("strobes", "**Partial writes.** Byte strobes (WSTRB) are honoured: a byte whose strobe is 0 keeps "
                    "its value, and in it W1C, W1S and W1P bits count as 0 (nothing is cleared, set or pulsed). A write "
                    "whose strobes cover only part of a writable field that spans several byte lanes answers SLVERR and "
                    "changes nothing (the whole write is rejected), because the field would be written torn; such "
                    "fields: " + (_names(ml) if ml else "none in this block") + ". A write that covers every lane of "
                    "such a field, or none of its lanes, is accepted, and so is any strobe pattern on a field inside "
                    "one byte lane. A write with all strobes 0 changes nothing and answers OKAY."))
    elif c.strobes == "honoured":
        out.append(("strobes", "**Partial writes.** Byte strobes (WSTRB) are honoured on every register: a byte whose "
                    "strobe is 0 keeps its value, and in it W1C, W1S and W1P bits count as 0 (nothing is cleared, set "
                    "or pulsed)."))
    else:
        out.append(("strobes", "**Partial writes.** Byte strobes (WSTRB) are ignored on every register: every write "
                    "changes the whole 32-bit word, so a CPU's byte or halfword store overwrites the other bytes. Use "
                    "32-bit stores only."))
    al = ("An address whose bits [1:0] are not 0 answers SLVERR: a read returns 0 and a write changes nothing, "
          "whatever it would address, even an unmapped word; " if c.unaligned == "slverr" else
          "Address bits [1:0] are not decoded, so an unaligned address reaches the word that holds it; ")
    out.append(("access", f"**Access width and alignment.** 32-bit registers on a {m.data_width}-bit AXI4-Lite bus. "
                "AXI4-Lite has no transfer size: a CPU's byte or halfword load reads the whole word, and its store "
                "arrives as a word write with fewer strobes (see Partial writes). " + al +
                f"only bits [{m.addr_width - 1}:2] are decoded, so the window repeats every 0x{m.window_bytes:x} bytes. "
                "Use aligned 32-bit accesses."))
    mw = []
    for s in m.snapshots:
        parts = ", then ".join(".".join(x) for x in s.fields)
        mw.append(f"Snapshot group {s.name} ({m.snapshot_width(s)} bits: {parts}, low part first): write 1 to "
                  f"{'.'.join(s.trigger)} to copy the whole value into shadow registers in one clock (the hardware's "
                  "values as they are in the clock the write takes effect; see Clock domain and timing), then read the "
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
    if c.wide_values == "snapshot":
        mw.append("This profile requires a snapshot group for a hardware value wider than the bus; the generator "
                  "recognises the register pairs NAME_LO/NAME_HI, _LOW/_HIGH, _LSW/_MSW and _L/_H, so name the halves "
                  "that way or put the value in a group yourself.")
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
    if any(f.const for r in m.registers for f in r.fields):
        L.append("| RO const | read-only constant, fixed when the block is built |")
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
         *([profile_sentence(m), "", f"Settings: `{settings_text(m)}`.", ""] if m.profile else []),
         f"AXI4-Lite, 32-bit registers, a 0x{m.window_bytes:x}-byte window (address bits [{m.addr_width - 1}:2] "
         f"decoded). Unmapped addresses: {_unmapped_short(m.unmapped)}. "
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
    lines = ["#include <stdio.h>"]
    if m.snapshots:                       # a fake bus, so the snapshot helpers can be run and their result checked
        lines += ["#include <stdint.h>",
                  "static uint32_t probe_rd(uintptr_t a) { return (uint32_t)(a * 2654435761u) ^ 0xA5A5A5A5u; }",
                  "static uintptr_t probe_wa; static uint32_t probe_wv;",
                  "static void probe_wr(uintptr_t a, uint32_t v) { probe_wa = a; probe_wv = v; }",
                  f"#define {P}_IO_READ32(addr) probe_rd((uintptr_t)(addr))",
                  f"#define {P}_IO_WRITE32(addr, v) probe_wr((uintptr_t)(addr), (uint32_t)(v))"]
    lines += [f'#include "{header.name}"', "int main(void) {"]
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
        lines.append(f'  {{ unsigned long long v = {m.name}_snapshot_{s.name.lower()}(0); printf("V {s.name} %llx %lu %u\\n", '
                     'v, (unsigned long)probe_wa, (unsigned)probe_wv); }')
    if m.profile:
        lines += [f'  printf("P %s\\n", {P}_PROFILE);', f'  printf("T %s\\n", {P}_SETTINGS);']
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
        elif t[0] == "P":
            got["__profile__"] = t[1]
        elif t[0] == "T":
            got["__settings__"] = " ".join(t[1:])
        elif t[0] == "V":
            got.setdefault("__snapcall__", {})[t[1]] = (int(t[2], 16), int(t[3]), int(t[4]))
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
    mod = types.ModuleType(f"_regmap_probe_{m.name}")          # from the source text, never a cached .pyc of an older edit
    exec(compile(Path(module).read_text(), str(module), "exec"), mod.__dict__)   # noqa: S102 (our own generated driver)
    got = {n: {"offset": r["offset"], "reset": r["reset"],
               "fields": {fn: {k: f[k] for k in ("lsb", "width", "access", "reset")} for fn, f in r["fields"].items()}}
           for n, r in mod.REGISTERS.items()}
    got["__window__"] = mod.WINDOW_BYTES
    if mod.PROFILE:
        got["__profile__"] = mod.PROFILE
        got["__settings__"] = " ".join(f"{k}={v}" for k, v in mod.SETTINGS.items())
    got["__snap__"] = {n: {"trigger": ".".join(s["trigger"]), "fields": [".".join(x) for x in s["fields"]]}
                       for n, s in getattr(mod, "SNAPSHOTS", {}).items()}
    if mod.REGMAP_SHA256 != m.sha256:
        got["__sha__"] = mod.REGMAP_SHA256
    return got


def read_md(md: Path) -> dict:
    got: dict = {}
    cur = None
    for ln in md.read_text().splitlines():
        mp = re.match(r"^Interface profile: `([a-z_]+)`", ln)
        if mp:
            got["__profile__"] = mp.group(1)
        mp = re.match(r"^Settings: `([^`]*)`\.$", ln)
        if mp:
            got["__settings__"] = mp.group(1)
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
    mp, ms = re.search(r"^// PROFILE (\w+)$", t, re.M), re.search(r"^// SETTINGS (.*)$", t, re.M)
    if mp:
        got["__profile__"] = mp.group(1)
    if ms:
        got["__settings__"] = ms.group(1).strip()
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
        if m.profile and (got.get("__profile__"), got.get("__settings__")) != (m.profile, settings_text(m)):
            errs.append(f"{kind}: profile and settings are {got.get('__profile__')!r} {got.get('__settings__')!r}, the "
                        f"YAML resolves to {m.profile!r} {settings_text(m)!r}")

    try:
        c = read_c(m, out / names["h"])
        cmp("C header", c)
        errs += snapshot_agreement(m, {"C header": c.get("__snap__", {}), "C helper": c.get("__snapcall__", {})})
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
        if kind == "C helper":                   # the helper run on a fake bus: trigger write and assembled value
            for s in m.snapshots:
                rd = lambda a: ((a * 2654435761) & 0xFFFFFFFF) ^ 0xA5A5A5A5      # noqa: E731 (the probe's bus)
                tr = m.reg(s.trigger[0])
                wv = (rd(tr.offset) & tr.mask("RW") if tr.mask("RW") else 0) | m.field(*s.trigger).mask
                v, sh = 0, 0
                for rn, fn in s.fields:
                    f = m.field(rn, fn)
                    v |= ((rd(m.reg(rn).offset) >> f.lsb) & ((1 << f.width) - 1)) << sh
                    sh += f.width
                if g.get(s.name) != (v, tr.offset, wv):
                    errs.append(f"C header: {m.name}_snapshot_{s.name.lower()}() on a test bus gives {g.get(s.name)}, "
                                f"the YAML says (value, trigger offset, trigger write) {(v, tr.offset, wv)}")
            continue
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


def check(path: str | Path, out: str | Path, spec: str | Path | None = None) -> list[str]:
    m = load(path, spec=spec)
    return drift(m, Path(out)) + agreement(m, Path(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hwsw.regmap", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["validate", "gen", "check"])
    ap.add_argument("yaml", nargs="+")
    ap.add_argument("--out", default=None, help="output folder (default: generated/ next to the YAML)")
    ap.add_argument("--spec", default=None, help="the design's spec.yaml: a map that names no profile takes the one its "
                    "`interfaces:` section chose for it")
    a = ap.parse_args(argv)
    rc = 0
    for y in a.yaml:
        out = Path(a.out) if a.out else Path(y).parent / "generated"
        try:
            m = load(y, spec=a.spec)
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
