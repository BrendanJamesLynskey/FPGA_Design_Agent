"""Elaboration front end for the reset check (brief 71B): the sources are read by a real HDL front end, not by regular
expressions.

The source part of ``resets`` used to be a raw-text scanner, and three adversarial reviews each found new ways past it
(comments in included files, macros holding flops, ``always begin @(...)``, primitive variants, ...). A text scanner cannot be
made a sound HDL front end, so this module runs Yosys with the ``slang`` plugin (SystemVerilog, full preprocessing and
elaboration) or the ``ghdl`` plugin (VHDL), lowers the processes (``proc``), recovers synchronous resets (``opt_dff``) and
returns the storage cells with their asynchronous and synchronous reset pins, their source lines and the nets that drive
them, traced up through the hierarchy and through buffers and inverters to a top-level port or a register.

**Fail closed.** Anything the front end cannot read is an error here: ``run`` returns the tool's message and the caller
makes the source part PARTIAL. There is no fallback scanner.

Blackboxes. AMD primitives (FDCE, FDPE, LDCE, ...) and every other module the build does not define (XPM macros, IP cores,
unisims) are read as empty blackbox modules: the primitives that carry an asynchronous clear or preset are declared here with
their real ports, every other unknown module is declared from its instantiation sites (ports as inputs, widths of one bit),
which is enough because the source part only judges storage cells and the pins that reset them. The names of the
auto-declared ones are returned in ``Elab.stubbed``.

The tool is the OSS CAD Suite, version-pinned in ``flow/checks/oss_cad_suite.version`` (``tools.pin``); it is found through
``$FDA_OSS_CAD`` or ``~/.local/opt/oss-cad-suite``, then on ``$PATH``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: AMD primitives with an asynchronous clear and/or preset, by their asynchronous pins
ASYNC_PRIMS: dict[str, tuple[str, ...]] = {}
for _base, _pins in (("FDCP", ("CLR", "PRE")), ("LDCP", ("CLR", "PRE")), ("LDCPE", ("CLR", "PRE")), ("FDC", ("CLR",)), ("FDP", ("PRE",)), ("FDCE", ("CLR",)), ("FDPE", ("PRE",)), ("FDCPE", ("CLR", "PRE")),
                     ("LDC", ("CLR",)), ("LDP", ("PRE",)), ("LDCE", ("CLR",)), ("LDPE", ("PRE",))):
    ASYNC_PRIMS[_base] = ASYNC_PRIMS[_base + "_1"] = _pins

#: DDR registers: R/S (IDDR, ODDR; asynchronous unless SRTYPE is SYNC) and R/SR (IDDRE1, ODDRE1) are reset pins
DDR_PRIMS = {"IDDR": ("R", "S"), "ODDR": ("R", "S"), "IDDRE1": ("R",), "ODDRE1": ("SR",)}
_DDR_DECL = {"IDDR": "output Q1, output Q2, input C, input CE, input D, input R, input S",
             "ODDR": "output Q, input C, input CE, input D1, input D2, input R, input S",
             "IDDRE1": "output Q1, output Q2, input C, input CB, input D, input R",
             "ODDRE1": "output Q, input C, input D1, input D2, input SR"}
_FD_PORTS = {"FDCP": "C, CLR, D, PRE", "LDCP": "CLR, D, G, PRE", "LDCPE": "CLR, D, G, GE, PRE", "FDC": "C, CLR, D", "FDP": "C, PRE, D", "FDCE": "C, CE, CLR, D", "FDPE": "C, CE, PRE, D",
             "FDCPE": "C, CE, CLR, D, PRE", "FDRE": "C, CE, D, R", "FDSE": "C, CE, D, S", "FDR": "C, D, R", "FDS": "C, D, S",
             "LDC": "CLR, D, G", "LDP": "D, G, PRE", "LDCE": "CLR, D, G, GE", "LDPE": "D, G, GE, PRE", "LD": "D, G"}


def prim_stubs() -> dict[str, str]:
    """Empty (blackbox) declarations of the flip-flop and latch primitives, with their real ports (Q the only output)."""
    out = {}
    for base, ports in _FD_PORTS.items():
        for name in (base, base + "_1"):
            ins = ", ".join(f"input {p}" for p in ports.split(", "))
            out[name] = (f"module {name} #(parameter INIT = 1'b0, parameter IS_C_INVERTED = 1'b0, parameter IS_D_INVERTED = 1'b0,"
                         f" parameter IS_CLR_INVERTED = 1'b0, parameter IS_PRE_INVERTED = 1'b0, parameter IS_G_INVERTED = 1'b0,"
                         f" parameter IS_R_INVERTED = 1'b0, parameter IS_S_INVERTED = 1'b0)(output Q, {ins});\nendmodule\n")
    for name, decl in _DDR_DECL.items():
        out[name] = (f"module {name} #(parameter SRTYPE = \"ASYNC\", parameter DDR_CLK_EDGE = \"OPPOSITE_EDGE\", "
                     f"parameter INIT_Q1 = 0, parameter INIT_Q2 = 0, parameter INIT = 0, parameter IS_C_INVERTED = 0, "
                     f"parameter IS_D_INVERTED = 0, parameter IS_CB_INVERTED = 0, parameter IS_D1_INVERTED = 0, "
                     f"parameter IS_D2_INVERTED = 0, parameter SIM_DEVICE = \"\", parameter INIT_QZ = 0)({decl});\nendmodule\n")
    return out


#: modules that may be declared empty from their instantiation sites without making the source part PARTIAL: XPM macros,
#: AMD primitives of the families below, and the build's own IP cores. Any other module the build does not define is an error
#: (a missing file or a typo'd glob must not read as a clean pass).
UNISIM = re.compile(r"^(BUFG\w*|BUFH\w*|BUFR|BUFIO\w*|BUFMR\w*|IBUF\w*|OBUF\w*|IOBUF\w*|IDELAY\w*|ODELAY\w*|ISERDES\w*|OSERDES\w*|"
                    r"MMCM\w*|PLL\w*|DSP48\w*|RAMB\w*|FIFO18\w*|FIFO36\w*|SRL\w*|LUT\d|CARRY\w*|MUXF\d|GT[HPXY]\w*|STARTUP\w*|ICAPE\w*|"
                    r"XADC|SYSMON\w*|BSCAN\w*|DNA_PORT|EFUSE_USR|USR_ACCESS\w*|IDELAYCTRL|PS7|PS8|PULLUP|PULLDOWN|KEEPER|VCC|GND|"
                    r"RAM(32|64|128|256|512)\w*|CFGLUT5|IN_FIFO|OUT_FIFO|PHASER\w*|HARD_SYNC|BITSLICE\w*|RIU\w*|GTYE\w*|PCIE\w*|"
                    r"xpm_\w+)$")


def find_tool() -> tuple[str, dict[str, str]] | None:
    """(path of yosys, environment with the suite on the PATH), or None."""
    for base in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if base and (Path(base) / "bin" / "yosys").is_file():
            env = dict(os.environ)
            env["PATH"] = f"{base}/bin:{base}/lib:" + env.get("PATH", "")
            return str(Path(base) / "bin" / "yosys"), env
    y = shutil.which("yosys")
    return (y, dict(os.environ)) if y else None


def version() -> str:
    t = find_tool()
    if not t:
        return ""
    try:
        r = subprocess.run([t[0], "-V"], capture_output=True, text=True, timeout=60, env=t[1])
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class Elab:
    modules: dict[str, Any] = field(default_factory=dict)
    #: the same design after ``opt_dff`` (synchronous resets recovered as $sdff); the asynchronous pins are read from
    #: ``modules`` (before it), because opt_dff also deletes registers that cannot matter (an undriven D, a constant)
    sync_modules: dict[str, Any] = field(default_factory=dict)
    top: str = ""
    tops: list[str] = field(default_factory=list)       # every top-level module (slang elaborates all uninstantiated ones)
    errors: list[str] = field(default_factory=list)
    stubbed: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    languages: set[str] = field(default_factory=set)
    #: absolute path of the file each module was defined in, when the front end says (SystemVerilog)
    ok: bool = False


SV_EXT = {".sv", ".v", ".vlg", ".sverilog", ".verilog", ".vg"}
SV_HEADER = {".svh", ".vh", ".h", ".inc"}
VHDL_EXT = {".vhd", ".vhdl", ".vho", ".vht"}


def classify(files: list[Path]) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    """(SystemVerilog sources, VHDL sources, header files, files of another kind), by case-insensitive extension."""
    sv, vh, hdr, other = [], [], [], []
    for f in files:
        e = f.suffix.lower()
        (sv if e in SV_EXT else vh if e in VHDL_EXT else hdr if e in SV_HEADER else other).append(f)
    return sv, vh, hdr, other


def _balanced(text: str, k: int) -> tuple[str, int] | None:
    if k >= len(text) or text[k] != "(":
        return None
    depth = 0
    for i in range(k, len(text)):
        depth += text[i] == "("
        depth -= text[i] == ")"
        if depth == 0:
            return text[k + 1:i], i + 1
    return None


def _split_top(s: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def stub_from_instances(name: str, texts: list[str]) -> str | None:
    """An empty module declaration for ``name`` from its instantiation sites: the named parameters and ports it is used with
    (positional ones become p0, p1, ...). None if no instantiation site is found."""
    params: dict[str, str] = {}
    ports: dict[str, None] = {}
    found = False
    rx = re.compile(r"(?<![\w$`.])" + re.escape(name) + r"\s*(#\s*)?")
    for t in texts:
        for m in rx.finditer(t):
            k = m.end()
            if m.group(1):
                pp = _balanced(t, k)
                if pp is None:
                    continue
                for n, a in enumerate(_split_top(pp[0])):
                    mm = re.match(r"\s*\.\s*(\w+)\s*\((.*)\)\s*$", a, re.S)
                    val = mm.group(2).strip() if mm else ""
                    typ = "string" if val.startswith('"') else "real" if re.fullmatch(r"[-+]?\d+\.\d+(e[-+]?\d+)?", val, re.I) else ""
                    nm = mm.group(1) if mm else f"p{n}"
                    if params.get(nm) in (None, "", typ):
                        params[nm] = typ
                    else:
                        params[nm] = ""
                k = pp[1]
            im = re.match(r"\s*(\\\S+\s|\w+)\s*(\[[^\]]*\]\s*)*", t[k:])
            if not im:
                continue
            k += im.end()
            cp = _balanced(t, k)
            if cp is None:
                continue
            found = True
            for n, a in enumerate(_split_top(cp[0])):
                mm = re.match(r"\s*\.\s*(\w+)", a)
                if mm:
                    ports[mm.group(1)] = None
                elif a.strip() and not a.strip().startswith(".*"):
                    ports[f"p{n}"] = None
    if not found:
        return None
    pl = ", ".join((f"parameter string {p} = \"\"" if t == "string" else f"parameter real {p} = 0.0" if t == "real" else f"parameter {p} = 0")
                   for p, t in params.items())
    # a non-empty body (not an "empty blackbox"): yosys-slang cannot export real-valued parameters of a blackbox
    return f"module {name}" + (f" #({pl})" if pl else "") + f"({', '.join('input ' + p for p in ports)});\nwire fda_stub_unused = 1'b0;\nendmodule\n"


_UNKNOWN = re.compile(r"unknown module '([^']+)'")


def _yosys(argv: list[str], script: str, cwd: Path, timeout: int) -> tuple[int, str]:
    t = find_tool()
    assert t
    try:
        r = subprocess.run([t[0], "-q", "-p", script], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=t[1])
    except subprocess.TimeoutExpired:
        return 1, f"yosys timed out after {timeout} s"
    return r.returncode, (r.stdout + r.stderr)


def _errors(out: str) -> list[str]:
    msgs = [ln.strip() for ln in out.splitlines() if "ERROR" in ln or "error:" in ln.lower()]
    return msgs or [ln.strip() for ln in out.splitlines() if ln.strip()][-3:]


def run_sv(sv: list[Path], hdr: list[Path], top: str | None, defines: list[str], work: Path, timeout: int = 300,
           cwd: Path | None = None, ip_names: set[str] = frozenset()) -> Elab:
    """Elaborate the SystemVerilog sources with yosys-slang; module JSON in ``Elab.modules``."""
    el = Elab()
    sv, hdr = [f.resolve() for f in sv], [f.resolve() for f in hdr]
    incs = sorted({str(f.parent) for f in sv + hdr})
    texts: list[str] = []
    for f in sv + hdr:
        try:
            texts.append(_strip(f.read_text(errors="replace")))
        except OSError:
            pass
    stubs: dict[str, str] = {}
    prims = prim_stubs()
    out = work / "elab.json"
    out2 = work / "elab_sync.json"
    for attempt in range(4):
        stubfile = work / "stubs.sv"
        stubfile.write_text("\n".join(stubs.values()))
        args = ["read_slang", "--best-effort-hierarchy", "--empty-blackboxes", "--single-unit", "--allow-use-before-declare"]
        if top:
            args += ["--top", top]
        args += [f"-D {d}" for d in defines] + [f"-I {i}" for i in incs] + [f"--isystem {i}" for i in incs]
        files = [str(stubfile)] if stubs else []
        files += [str(f) for f in sv]
        script = (f"plugin -i slang; {' '.join(args)} {' '.join(files)}; proc; opt_expr; "
                  f"write_json {out}; setattr -set keep 1 t:* t:$* %d t:$*dff* t:$*latch* %u %u; opt_clean; opt_dff; "
                  f"write_json {out2}")
        out.unlink(missing_ok=True)
        out2.unlink(missing_ok=True)
        rc, log = _yosys([], script, cwd or work, timeout)
        if rc == 0 and out.is_file() and out2.is_file():
            break
        unknown = sorted(set(_UNKNOWN.findall(log)) - set(stubs))
        if not unknown:
            el.errors = _errors(log)
            return el
        for n in unknown:
            if n in prims:
                stubs[n] = prims[n]
                site = stub_from_instances(n, texts) if n in DDR_PRIMS else None
                if site:                    # extra parameters the design sets (SRVAL, SIM_DEVICE, ...)
                    extra = re.search(r"#\((.*?)\)\(", site, re.S)
                    have = set(re.findall(r"parameter (\w+)", stubs[n]))
                    add = [x for x in re.findall(r"parameter (?:string |real )?(\w+) = ", extra.group(1) if extra else "") if x not in have]
                    if add:
                        stubs[n] = stubs[n].replace(" #(", " #(" + ", ".join(f"parameter {a} = 0" for a in add) + ", ", 1)
                continue
            if not (UNISIM.match(n) or n in ip_names):
                el.errors = [f"module '{n}' is instantiated but not defined in the build's sources (and is not a recognised AMD "
                             "primitive, XPM macro or build IP): its body is not judged"]
                return el
            s = stub_from_instances(n, texts)
            if s is None:
                el.errors = [f"unknown module '{n}' and no instantiation site to declare it from"] + _errors(log)[:2]
                return el
            stubs[n] = s
            el.stubbed.add(n)
    else:
        el.errors = _errors(log)
        return el
    try:
        el.modules = json.loads(out.read_text()).get("modules", {})
        el.sync_modules = json.loads(out2.read_text()).get("modules", {})
    except (OSError, ValueError) as e:
        el.errors = [f"yosys wrote no usable netlist: {e}"]
        return el
    el.languages.add("sv")
    el.ok = True
    el.tops = [m for m, v in el.modules.items() if "top" in v.get("attributes", {})]
    el.top = el.tops[0] if el.tops else ""
    el.stubbed -= set(prims)
    bad = [m for m, v in el.modules.items() if "blackbox" in v.get("attributes", {}) and m not in stubs]
    if bad:
        el.ok = False
        el.errors = [f"module(s) {', '.join(sorted(bad)[:3])} carry a blackbox attribute in the source: their bodies are not judged"]
    return el


def _vhdl_entities(files: list[Path]) -> list[str]:
    ents = []
    for f in files:
        try:
            ents += re.findall(r"(?i)\bentity\s+(\w+)\s+is\b", f.read_text(errors="replace"))
        except OSError:
            pass
    return ents


def run_vhdl(vh: list[Path], top: str | None, work: Path, timeout: int = 300, cwd: Path | None = None) -> Elab:
    """Elaborate the VHDL sources with the ghdl plugin: the top entity, or each entity in turn when the top is not a VHDL one
    (a mixed design). Module JSON of all of them in ``Elab.modules``."""
    el = Elab()
    vh = [f.resolve() for f in vh]
    ents = _vhdl_entities(vh)
    txt = " ".join(f.read_text(errors="replace") for f in vh)
    for e in sorted(set(ents)):
        if len(re.findall(r"(?i)\barchitecture\s+\w+\s+of\s+" + re.escape(e) + r"\b", txt)) > 1:
            el.errors.append(f"entity {e} has several architectures: which one is built depends on the tool's binding rule")
    if re.search(r"(?i)\bconfiguration\s+\w+\s+of\b", txt):
        el.errors.append("a VHDL configuration is present: the architecture it binds is not judged")
    if el.errors:
        return el
    tops = [top] if top and top.lower() in {e.lower() for e in ents} else ents
    if not tops:
        el.errors = ["no VHDL entity found in the VHDL files"]
        return el
    files = " ".join(str(f) for f in vh)
    for n, t in enumerate(tops):
        out = work / f"elab_vhdl_{n}.json"
        out2 = work / f"elab_vhdl_sync_{n}.json"
        out.unlink(missing_ok=True)
        out2.unlink(missing_ok=True)
        script = (f"plugin -i ghdl; ghdl --std=08 -fsynopsys {files} -e {t}; proc; opt_expr; "
                  f"write_json {out}; setattr -set keep 1 t:* t:$* %d t:$*dff* t:$*latch* %u %u; opt_clean; opt_dff; "
                  f"write_json {out2}")
        rc, log = _yosys([], script, cwd or work, timeout)
        if rc != 0 or not out.is_file() or not out2.is_file():
            el.errors.append(f"entity {t}: " + "; ".join(_errors(log)[:2]))
            continue
        try:
            el.modules.update(json.loads(out.read_text()).get("modules", {}))
            el.sync_modules.update(json.loads(out2.read_text()).get("modules", {}))
        except (OSError, ValueError):
            el.errors.append(f"entity {t}: no usable netlist")
    el.languages.add("vhdl")
    el.ok = bool(el.modules) and not el.errors
    el.tops = [m for m, v in el.modules.items() if "top" in v.get("attributes", {})]
    el.top = el.tops[0] if el.tops else ""
    return el


def _strip(text: str) -> str:
    """Comments removed (only to find instantiation sites for blackbox declarations; an error here fails closed)."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="fda_elab_"))


#: the pinned tool: ``yosys -V`` of the OSS CAD Suite release the tests and the check were written against (2026-11-12,
#: build 20261112; CI installs this release). A different build is allowed to run, but the regression tests say so.
PIN_SUITE = "20261112"
PIN_YOSYS = "Yosys 0.70+385 (git sha1 098e46a36"
