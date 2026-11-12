"""The transaction program format of the brief 59A transactor: a YAML (or JSON, or Python) list of steps, assembled into
4-word instructions for the on-chip sequencer (axi_tx/rtl/axi_tx_core.sv). Loading a new program needs no rebuild.

    name: bram_random_rw
    target: bram                      # bram | periph   (axi_tx_sys target select)
    lite_bug: none                    # optional: a seeded bug of the peripheral (regs.LITE_BUGS)
    stream_bug: none                  # optional: a seeded bug of the stream FIFO (regs.STREAM_BUGS)
    steps:
      - set: {seed_data: 0x1234, seed_lite: 7, valid_p: 64, ready_p: 128, sb_base: 0x0}
      - loop: 200
        body:
          - write: {addr: 0x0, rand_addr: 0xFFC, rand_data: true, strb: 0xF, sb: true, order: aw_first, gap: 3}
          - read:  {addr: 0x0, rand_addr: 0xFFC, sb: true, resp: OKAY}
      - ssend: {len: 7, first: 0x100, keep_last: 0x3}
      - swait: {}

Steps (every key is optional unless marked):
  write: addr*, data, strb (0xF), rand_addr (mask of random address bits), rand_data, rand_strb, areg (address from
         AREG, then AREG += 4), order (together | aw_first | w_first), gap (cycles, 0-255), inject (none | valid_drop |
         data_change), sb (record in the scoreboard), resp (expected: OKAY | EXOKAY | SLVERR | DECERR, checked if given)
  read:  addr*, rand_addr, areg, sb (check against the scoreboard), expect ({data, bytes}: compare these bytes),
         resp, inject (none | valid_drop)
  wait: cycles      loop: count + body: [steps]      swait: {}      waitev: {mask, timeout}
  set: any of seed_data, seed_lite, seed_stream, valid_p, ready_p, s_valid_p, s_ready_p, areg, sb_base, watchdog
  ssend: len*, first, rand_first, keep_last (0xF), no_last, expect (true), block (false)
valid_p is the chance (of 256) that a VALID waits one more cycle; ready_p + 1 is the chance (of 256) that the
transactor's READY is high in a cycle (255: always).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from axi_tx.host import regs

OP = {"end": 0, "write": 1, "read": 2, "wait": 3, "loop": 4, "endloop": 5, "set": 6, "ssend": 7, "swait": 8, "waitev": 9}
OPNAME = {v: k for k, v in OP.items()}
SET_REGS = {"seed_data": 0, "seed_lite": 1, "seed_stream": 2, "valid_p": 3, "ready_p": 4, "s_valid_p": 5,
            "s_ready_p": 6, "areg": 7, "sb_base": 8, "watchdog": 9}
SET_NAMES = {v: k for k, v in SET_REGS.items()}
ORDER = {"together": 0, "aw_first": 1, "w_first": 2}
INJECT = {"none": 0, "valid_drop": 1, "data_change": 2}
RESP = {name: i for i, name in enumerate(regs.RESP)}
DEFAULTS = {"seed_data": 1, "seed_lite": 1, "seed_stream": 1, "valid_p": 0, "ready_p": 255, "s_valid_p": 0,
            "s_ready_p": 255, "areg": 0, "sb_base": 0, "watchdog": 1_000_000}
MAX_INSTR = 256
MAX_NEST = 4
M32 = 0xFFFF_FFFF


class ProgramError(ValueError):
    """The program does not fit the format; the message names the step."""


@dataclass
class Program:
    name: str
    target: str = "bram"
    lite_bug: str = "none"
    stream_bug: str = "none"
    steps: list[dict[str, Any]] = field(default_factory=list)
    words: list[int] = field(default_factory=list)     # 4 per instruction

    @property
    def n_instr(self) -> int:
        return len(self.words) // 4


def _int(v: Any, where: str, lo: int = 0, hi: int = M32) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ProgramError(f"{where}: expected an integer, got {v!r}")
    if not lo <= v <= hi:
        raise ProgramError(f"{where}: {v} is outside {lo}..{hi}")
    return v


def _keys(d: dict, allowed: set[str], where: str) -> None:
    extra = set(d) - allowed
    if extra:
        raise ProgramError(f"{where}: unknown key(s) {sorted(extra)}; allowed {sorted(allowed)}")


def _enc_lite(kind: str, a: dict, where: str) -> list[int]:
    if "addr" not in a and not a.get("areg"):
        raise ProgramError(f"{where}: {kind} needs addr (or areg: true)")
    w0 = OP[kind] << 28
    addr = _int(a.get("addr", 0), f"{where}.addr")
    if addr & 3:
        raise ProgramError(f"{where}.addr: 0x{addr:x} is not 4-byte aligned (AXI4-Lite 32-bit transfers here)")
    rmask = _int(a.get("rand_addr", 0), f"{where}.rand_addr")
    if rmask:
        w0 |= 1 << 8
    if a.get("areg"):
        w0 |= 1 << 9
    if "resp" in a:
        if a["resp"] not in RESP:
            raise ProgramError(f"{where}.resp: one of {list(RESP)}")
        w0 |= (RESP[a["resp"]] << 4) | (1 << 6)
    inj = a.get("inject", "none")
    if inj not in INJECT or (kind == "read" and inj == "data_change"):
        raise ProgramError(f"{where}.inject: {inj!r} not allowed for {kind}")
    w0 |= INJECT[inj] << 20
    if a.get("sb"):
        w0 |= 1 << 22
    data = 0
    if kind == "write":
        _keys(a, {"addr", "data", "strb", "rand_addr", "rand_data", "rand_strb", "areg", "order", "gap", "inject", "sb",
                  "resp"}, where)
        w0 |= _int(a.get("strb", 0xF), f"{where}.strb", 0, 0xF)
        if a.get("rand_data"):
            w0 |= 1 << 7
        if a.get("rand_strb"):
            w0 |= 1 << 23
        order = a.get("order", "together")
        if order not in ORDER:
            raise ProgramError(f"{where}.order: one of {list(ORDER)}")
        w0 |= ORDER[order] << 10
        w0 |= _int(a.get("gap", 0), f"{where}.gap", 0, 255) << 12
        data = _int(a.get("data", 0), f"{where}.data")
    else:
        _keys(a, {"addr", "rand_addr", "areg", "sb", "expect", "resp", "inject"}, where)
        if "expect" in a:
            e = a["expect"]
            if not isinstance(e, dict) or "data" not in e:
                raise ProgramError(f"{where}.expect: {{data: ..., bytes: 0xF}}")
            w0 |= (1 << 24) | _int(e.get("bytes", 0xF), f"{where}.expect.bytes", 1, 0xF)
            data = _int(e["data"], f"{where}.expect.data")
    return [w0, addr, data, rmask]


def _assemble(steps: list, out: list[int], depth: int, where: str) -> None:
    if not isinstance(steps, list):
        raise ProgramError(f"{where}: steps must be a list")
    for i, st in enumerate(steps):
        w = f"{where}[{i}]"
        if not isinstance(st, dict) or not st:
            raise ProgramError(f"{w}: a step is a mapping with one operation key")
        keys = [k for k in st if k != "body"]
        if len(keys) != 1 or keys[0] not in OP or keys[0] in ("end", "endloop"):
            raise ProgramError(f"{w}: one of {[k for k in OP if k not in ('end', 'endloop')]}, got {keys}")
        op = keys[0]
        a = st[op]
        if op in ("write", "read"):
            if not isinstance(a, dict):
                raise ProgramError(f"{w}: {op} takes a mapping")
            out += _enc_lite(op, a, f"{w}.{op}")
        elif op == "wait":
            out += [OP["wait"] << 28, _int(a, f"{w}.wait", 1), 0, 0]
        elif op == "loop":
            if depth >= MAX_NEST:
                raise ProgramError(f"{w}: loops nest at most {MAX_NEST} deep")
            if "body" not in st:
                raise ProgramError(f"{w}: loop needs body")
            out += [OP["loop"] << 28, _int(a, f"{w}.loop", 1), 0, 0]
            _assemble(st["body"], out, depth + 1, f"{w}.body")
            out += [OP["endloop"] << 28, 0, 0, 0]
        elif op == "set":
            if not isinstance(a, dict) or not a:
                raise ProgramError(f"{w}: set takes a mapping of {list(SET_REGS)}")
            _keys(a, set(SET_REGS), f"{w}.set")
            for k, v in a.items():
                hi = 255 if k.endswith("_p") else M32
                out += [(OP["set"] << 28) | SET_REGS[k], _int(v, f"{w}.set.{k}", 0, hi), 0, 0]
        elif op == "ssend":
            if not isinstance(a, dict):
                raise ProgramError(f"{w}: ssend takes a mapping")
            _keys(a, {"len", "first", "rand_first", "keep_last", "no_last", "expect", "block"}, f"{w}.ssend")
            if "len" not in a:
                raise ProgramError(f"{w}.ssend: len is required")
            w0 = (OP["ssend"] << 28) | _int(a.get("keep_last", 0xF), f"{w}.ssend.keep_last", 0, 0xF)
            w0 |= (bool(a.get("no_last")) << 4) | (bool(a.get("expect", True)) << 5) | (bool(a.get("rand_first")) << 6)
            w0 |= bool(a.get("block")) << 7
            out += [w0, _int(a["len"], f"{w}.ssend.len", 1, 0xFFFF), _int(a.get("first", 0), f"{w}.ssend.first"), 0]
        elif op == "swait":
            out += [OP["swait"] << 28, 0, 0, 0]
        elif op == "waitev":
            if not isinstance(a, dict) or "mask" not in a:
                raise ProgramError(f"{w}: waitev takes {{mask, timeout}}")
            out += [OP["waitev"] << 28, _int(a["mask"], f"{w}.waitev.mask", 1, 255),
                    _int(a.get("timeout", 0), f"{w}.waitev.timeout"), 0]


def assemble(spec: dict | str | Path) -> Program:
    """A program from a mapping, YAML/JSON text or a file path. Raises ProgramError naming the faulty step."""
    if isinstance(spec, Path) or (isinstance(spec, str) and "\n" not in spec and spec.endswith((".yaml", ".yml", ".json"))):
        spec = yaml.safe_load(Path(spec).read_text())
    elif isinstance(spec, str):
        spec = yaml.safe_load(spec)
    if not isinstance(spec, dict) or "steps" not in spec:
        raise ProgramError("a program is a mapping with name, target and steps")
    _keys(spec, {"name", "target", "lite_bug", "stream_bug", "steps", "description", "requirements", "stream_maxlen"},
          "program")
    p = Program(name=str(spec.get("name", "unnamed")), target=spec.get("target", "bram"),
                lite_bug=spec.get("lite_bug", "none"), stream_bug=spec.get("stream_bug", "none"), steps=spec["steps"])
    if p.target not in regs.TARGETS:
        raise ProgramError(f"program.target: one of {list(regs.TARGETS)}")
    if p.lite_bug not in regs.LITE_BUGS or p.stream_bug not in regs.STREAM_BUGS:
        raise ProgramError("program.lite_bug / stream_bug: see axi_tx.host.regs LITE_BUGS, STREAM_BUGS")
    words: list[int] = []
    _assemble(spec["steps"], words, 0, "steps")
    words += [0, 0, 0, 0]                                   # END
    if len(words) // 4 > MAX_INSTR:
        raise ProgramError(f"program: {len(words) // 4} instructions, the RAM holds {MAX_INSTR}")
    p.words = words
    return p


def disassemble(words: list[int]) -> list[str]:
    out = []
    for i in range(0, len(words), 4):
        w0, w1, w2, w3 = words[i:i + 4]
        op = OPNAME.get(w0 >> 28, f"op{w0 >> 28}")
        if op == "set":
            out.append(f"{i // 4:3d} set {SET_NAMES.get(w0 & 0xFF, w0 & 0xFF)} = 0x{w1:x}")
        else:
            out.append(f"{i // 4:3d} {op:7s} w0=0x{w0:08x} w1=0x{w1:08x} w2=0x{w2:08x} w3=0x{w3:08x}")
    return out


def load_file(path: str | Path) -> dict:
    p = Path(path)
    return json.loads(p.read_text()) if p.suffix == ".json" else yaml.safe_load(p.read_text())
