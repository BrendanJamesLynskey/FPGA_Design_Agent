"""VHDL in the flow (brief 55): GHDL lint, GHDL synthesis to a Verilog netlist, and the language of a design.

The agent and the flow are SystemVerilog-first; a design may be written in VHDL-2008 instead (``language: vhdl`` in
spec.yaml, or ``--hdl vhdl``). The test shell stays SystemVerilog. What runs where:

- **Lint:** ``ghdl -a --std=08`` (analysis) and ``ghdl --synth --std=08`` (elaboration as synthesis sees it: an
  inferred latch, a multiply driven ``std_ulogic`` or a missing generic is an error here). Vivado's own reading of the
  VHDL is the ``rtl`` stage of the build (``synth_design -rtl`` after ``read_vhdl -vhdl2008``).
- **Simulation with the shell (mixed language):** no free simulator runs cocotb on VHDL and SystemVerilog together.
  :func:`to_verilog` turns the VHDL sources into a Verilog netlist with ``ghdl --synth --out=verilog`` (the shell's
  ``fpga_shell`` is an unbound component, so it stays a black-box instance with its generics), and Icarus or
  Verilator simulate that netlist beside the shell's SystemVerilog. The netlist is GHDL's synthesis of the VHDL: it
  checks the VHDL as hardware, not VHDL simulation semantics (a sensitivity-list omission, for example, is invisible
  in it). Top-level generics are fixed at synthesis, so the netlist's module header declares them again, unused, for
  the cocotb runner.
- **Simulation without the shell:** GHDL itself (``SIM=ghdl``), native VHDL semantics, cocotb through VPI.

GHDL is found as ``$FDA_GHDL``, on PATH, or at ``~/.local/bin/ghdl``. Version used for brief 55: GHDL 4.1.0 (Ubuntu
24.04 package ``ghdl`` 4.1.0+dfsg-0ubuntu2.1, mcode back end), the same package in CI.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
VHDL_SUFFIXES = (".vhd", ".vhdl")
STD = "08"
HDL_MARKER = ".hdl"           # a design directory's language marker (the harness writes "vhdl" for --hdl vhdl)

_COMMENT = re.compile(r"--[^\n]*")
_PKG_DEF = re.compile(r"^\s*package\s+(?!body\b)([A-Za-z]\w*)\s+is\b", re.M | re.I)
_PKG_BODY = re.compile(r"^\s*package\s+body\s+([A-Za-z]\w*)\s+is\b", re.M | re.I)
_ENT_DEF = re.compile(r"^\s*entity\s+([A-Za-z]\w*)\s+is\b", re.M | re.I)
_USE = re.compile(r"\bwork\s*\.\s*([A-Za-z]\w*)", re.I)


def is_vhdl(p: Path | str) -> bool:
    return Path(p).suffix.lower() in VHDL_SUFFIXES


def split(sources: Iterable[Path | str]) -> tuple[list[Path], list[Path]]:
    """(VHDL sources, the others), each in the order given."""
    vh, other = [], []
    for s in sources:
        (vh if is_vhdl(s) else other).append(Path(s))
    return vh, other


def ghdl_exe() -> str | None:
    env = os.environ.get("FDA_GHDL")
    if env and Path(env).is_file():
        return env
    found = shutil.which("ghdl")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "ghdl"
    return str(local) if local.is_file() else None


def ghdl_version() -> str | None:
    exe = ghdl_exe()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0].strip() if out else None


def _text(p: Path) -> str:
    try:
        return _COMMENT.sub(" ", p.read_text(errors="replace"))
    except OSError:
        return ""


def order_vhdl(files: Iterable[Path | str]) -> list[Path]:
    """VHDL sources in analysis order: a package before every file that uses it (``work.<pkg>``), a package body after
    its package, an entity before a file that instantiates it with ``entity work.<name>``. Stable: files with no
    dependency between them keep their order; a cycle keeps the input order."""
    paths = [Path(f) for f in files]
    texts = [_text(p) for p in paths]
    defs: dict[str, int] = {}
    for i, t in enumerate(texts):
        for n in _PKG_DEF.findall(t) + _ENT_DEF.findall(t):
            defs.setdefault(n.lower(), i)
    deps: list[list[int]] = []
    for i, t in enumerate(texts):
        need = {n.lower() for n in _USE.findall(t)} | {n.lower() for n in _PKG_BODY.findall(t)}
        deps.append(sorted({defs[n] for n in need if n in defs and defs[n] != i}))
    out: list[int] = []
    state: dict[int, int] = {}

    def visit(i: int) -> None:
        if state.get(i):
            return
        state[i] = 1
        for d in deps[i]:
            visit(d)
        state[i] = 2
        out.append(i)

    for i in range(len(paths)):
        visit(i)
    return [paths[i] for i in out]


def order_sources(files: Iterable[Path | str]) -> list[Path]:
    """A mixed source list: the non-VHDL files in their order (the caller orders SystemVerilog), then VHDL in analysis
    order. Vivado reads both; VHDL that instantiates a Verilog module by component needs nothing before it."""
    vh, other = split(files)
    return other + order_vhdl(vh)


# --- generics ------------------------------------------------------------------------------------------------------

_VLOG_LIT = re.compile(r"^\s*(\d+)\s*'\s*([hHbBdD])\s*([0-9a-fA-F_xXzZ]+)\s*$")


def generic_value(v: object) -> str:
    """A generic value for ``ghdl -g``: integers as they are; Verilog sized literals (``32'h1A2B``, the form the flow
    passes BUILD_STAMP in) as a VHDL bit-string of the same width; booleans as true/false; anything else as text."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    m = _VLOG_LIT.match(s)
    if m:
        width, base, digits = int(m.group(1)), m.group(2).lower(), m.group(3).replace("_", "")
        val = int(digits, {"h": 16, "b": 2, "d": 10}[base])
        return format(val, f"0{width}b")
    if re.fullmatch(r"-?\d+", s):
        return s
    return s


def generic_args(generics: dict[str, object] | None) -> list[str]:
    return [f"-g{k}={generic_value(v)}" for k, v in (generics or {}).items()]


# --- lint ------------------------------------------------------------------------------------------------------------

def _run(argv: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout)


def lint_argv(files: list[Path], top: str | None, generics: dict | None = None, workdir: Path | None = None) -> list[list[str]]:
    """The GHDL commands of a lint: analysis of every file (warnings on), then synthesis-elaboration of the top."""
    exe = ghdl_exe() or "ghdl"
    wd = [f"--workdir={workdir}"] if workdir else []
    cmds = [[exe, "-a", f"--std={STD}", *wd, "-Wall", "-Wno-default-binding", *[str(f) for f in order_vhdl(files)]]]
    if top:
        cmds.append([exe, "--synth", f"--std={STD}", *wd, *generic_args(generics), top])
    return cmds


def lint(files: list[Path], top: str | None, generics: dict | None = None, workdir: Path | None = None,
         cwd: Path = ROOT) -> dict:
    """``{"ok", "output", "returncode"}``: GHDL analysis then synthesis-elaboration of ``top``. A black box (an unbound
    component, such as the test shell) is reported by GHDL as a warning and is allowed."""
    if not ghdl_exe():
        return {"ok": False, "output": "GHDL not found (FDA_GHDL, PATH or ~/.local/bin/ghdl)", "returncode": 127}
    clash = shell_name_clashes(files)
    if clash:
        return {"ok": False, "returncode": 1, "output": "[vhdl boundary] " + "; ".join(clash)}
    wd = workdir or (ROOT / "build" / "vhdl_lint" / hashlib.sha1("".join(map(str, files)).encode()).hexdigest()[:10])
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True, exist_ok=True)
    out, rc = [], 0
    for argv in lint_argv(files, top, generics, wd):
        r = _run(argv, cwd)
        if argv[1] == "--synth":          # stdout is the synthesised netlist: only the messages count
            lines = r.stderr.strip().splitlines()
            keep, skip = [], 0
            for l in lines:                 # an unbound component (the shell) is a warning plus its two context lines
                if "is not bound" in l:
                    skip = 2
                    continue
                if skip and (l.startswith(" ") or "(in default configuration of" in l):
                    skip -= 1
                    continue
                skip = 0
                if "(in default configuration of" not in l:
                    keep.append(l)
            text = "\n".join(keep).strip()
        else:
            text = (r.stdout + r.stderr).strip()
        if text:
            out.append(f"[ghdl {argv[1]}] " + text[:4000])   # the first errors are the cause; the rest cascade
        if r.returncode != 0:
            rc = r.returncode
            break
    return {"ok": rc == 0, "output": "\n".join(out), "returncode": rc}


# --- netlist for mixed-language simulation ---------------------------------------------------------------------------

_MOD_HEAD = re.compile(r"^module\s+(\w+)\s*\n?\s*\(", re.M)


def declare_params(netlist: str, top: str, params: dict[str, object] | None) -> str:
    """Give the netlist's top module a ``#(parameter ...)`` header for each name in ``params`` (values already fixed in
    the logic; declared so a runner's ``-P``/``-G`` finds them)."""
    if not params:
        return netlist
    decl = ", ".join(f"parameter {k} = {_vlog_value(v)}" for k, v in params.items())
    pat = re.compile(rf"^module\s+{re.escape(top)}\s*\n?\s*\(", re.M | re.I)
    m = pat.search(netlist)
    if not m:
        return netlist
    return netlist[:m.start()] + f"module {m.group(0).split()[1].rstrip('(')} #({decl})\n  (" + netlist[m.end():]


def _vlog_value(v: object) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    return s if (_VLOG_LIT.match(s) or re.fullmatch(r"-?\d+", s)) else f'"{s}"'


def netlist_key(files: list[Path], top: str, generics: dict | None) -> str:
    h = hashlib.sha256()
    h.update((ghdl_version() or "").encode())
    h.update(top.encode())
    h.update(repr(sorted((generics or {}).items(), key=lambda kv: kv[0])).encode())
    for f in order_vhdl(files):
        h.update(str(f.name).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def to_verilog(files: list[Path], top: str, generics: dict | None, out_dir: Path, cwd: Path = ROOT) -> Path:
    """Synthesise the VHDL ``files`` (top ``top``, ``generics`` fixed) to ``<out_dir>/<top>_ghdl.v`` with GHDL. Raises
    RuntimeError with GHDL's message when it fails. Cached by content: the same sources and generics reuse the file."""
    exe = ghdl_exe()
    if not exe:
        raise RuntimeError("GHDL not found (FDA_GHDL, PATH or ~/.local/bin/ghdl): VHDL sources cannot be simulated here")
    out_dir.mkdir(parents=True, exist_ok=True)
    key = netlist_key(files, top, generics)
    out = out_dir / f"{top}_ghdl_{key}.v"
    if out.is_file():
        return out
    wd = out_dir / f"work_{key}"
    wd.mkdir(parents=True, exist_ok=True)
    a = _run([exe, "-a", f"--std={STD}", f"--workdir={wd}", *[str(f) for f in order_vhdl(files)]], cwd)
    if a.returncode != 0:
        raise RuntimeError("GHDL analysis failed:\n" + (a.stdout + a.stderr)[-4000:])
    s = _run([exe, "--synth", f"--std={STD}", f"--workdir={wd}", "--out=verilog", *generic_args(generics), top], cwd)
    if s.returncode != 0:
        raise RuntimeError("GHDL synthesis failed:\n" + s.stderr[-4000:])
    text = f"// GHDL netlist of the VHDL top {top} ({ghdl_version()}); generated by flow/vhdl.py, do not edit\n" + s.stdout
    out.write_text(declare_params(text, top, generics))
    shutil.rmtree(wd, ignore_errors=True)
    return out


def design_language(design: Path) -> str:
    """``vhdl`` or ``sv`` for a design directory: spec.yaml ``language``, else build.yaml ``hdl``, else VHDL when
    rtl/ holds VHDL files and no SystemVerilog."""
    import yaml
    for name, key in (("spec.yaml", "language"), ("build.yaml", "hdl")):
        f = design / name
        if f.is_file():
            try:
                v = (yaml.safe_load(f.read_text()) or {}).get(key)
            except Exception:              # noqa: BLE001 - a malformed file is reported by its own checker
                v = None
            if isinstance(v, str) and v.strip().lower() in ("vhdl", "vhdl-2008", "vhdl2008"):
                return "vhdl"
            if isinstance(v, str) and v.strip():
                return "sv"
    m = design / HDL_MARKER
    if m.is_file():
        return "vhdl" if m.read_text().strip().lower() == "vhdl" else "sv"
    rtl = design / "rtl"
    if rtl.is_dir():
        has_v = any(is_vhdl(p) for p in rtl.iterdir())
        has_sv = any(p.suffix in (".sv", ".v") for p in rtl.iterdir())
        if has_v and not has_sv:
            return "vhdl"
    return "sv"


def rtl_files(design: Path) -> list[Path]:
    """The design's own HDL sources in rtl/: SystemVerilog/Verilog and VHDL."""
    rtl = design / "rtl"
    if not rtl.is_dir():
        return []
    return sorted(p for p in rtl.iterdir() if p.suffix in (".sv", ".v") or is_vhdl(p))


_INST_ENT = re.compile(r"\bentity\s+work\s*\.\s*([A-Za-z]\w*)", re.I)
_INST_COMP = re.compile(r"^\s*\w+\s*:\s*(?:component\s+)?([A-Za-z]\w*)\s+(?:generic|port)\s+map\b", re.M | re.I)


def top_entity(files: list[Path], preferred: str) -> str:
    """The VHDL entity to synthesise: ``preferred`` when an entity of that name exists (VHDL names ignore case),
    else the one entity no other VHDL file instantiates. Raises RuntimeError when that is not unique."""
    ents: dict[str, str] = {}
    used: set[str] = set()
    for f in files:
        t = _text(Path(f))
        for e in _ENT_DEF.findall(t):
            ents[e.lower()] = e
        used |= {n.lower() for n in _INST_ENT.findall(t)} | {n.lower() for n in _INST_COMP.findall(t)}
    if preferred.lower() in ents:
        return ents[preferred.lower()]
    roots = [ents[k] for k in ents if k not in used]
    if len(roots) == 1:
        return roots[0]
    raise RuntimeError(f"no VHDL entity named {preferred} and {len(roots)} top-level candidates ({', '.join(roots)})")


#: The test shell seen from VHDL (brief 55): a component declaration matching shell/rtl/fpga_shell.sv. Vivado binds a
#: VHDL component to a Verilog module of the same name; GHDL leaves it unbound (a black box in the netlist).
SHELL_COMPONENT = """  component fpga_shell is
    generic (
      CLKS_PER_BIT   : integer := 868;
      TIMEOUT_CYCLES : integer := 100000;
      DESIGN_ID      : std_logic_vector(31 downto 0) := x"00000000";
      BUILD_STAMP    : std_logic_vector(31 downto 0) := x"00000000");
    port (
      clk       : in  std_logic;
      rst       : in  std_logic;                      -- synchronous, active high
      uart_rx   : in  std_logic;
      uart_tx   : out std_logic;
      win_addr  : out std_logic_vector(6 downto 0);
      win_wr    : out std_logic;
      win_rd    : out std_logic;
      win_wdata : out std_logic_vector(31 downto 0);
      win_rdata : in  std_logic_vector(31 downto 0)); -- due one cycle after win_rd
  end component;"""

#: The language boundary, for the agent's conventions and the translation tool.
BOUNDARY_NOTES = """VHDL designs (language: vhdl; brief 55):
- Write VHDL-2008 in rtl/*.vhd: library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all. Never
  std_logic_arith, std_logic_unsigned or std_logic_signed. Ports are std_logic and std_logic_vector(N-1 downto 0)
  (always downto); arithmetic on unsigned/signed signals, converted at the ports.
- One entity per file, the file named after the entity. The board top's entity name is the spec's top name, and its
  port names are spelled exactly as the master XDC spells them (CLK100MHZ, CPU_RESETN, LED, SW, BTNU, UART_TXD_IN,
  UART_RXD_OUT ...): VHDL ignores case, but the constraints, the netlist and the test bench do not.
- The test shell stays SystemVerilog (shell/rtl/fpga_shell.sv). Instantiate it from VHDL through a COMPONENT
  declaration (never `entity work.fpga_shell`, which does not exist as a VHDL entity):
{shell}
  The board top declares the generic `BUILD_STAMP : std_logic_vector(31 downto 0) := x"00000000"` and passes it on
  (BUILD_STAMP => BUILD_STAMP); the flow sets it per build. Other top-level parameters the spec names (CLKS_PER_BIT,
  TIMEOUT_CYCLES, ...) are integer generics of the top with the spec's board defaults.
- Your own sub-blocks are VHDL entities, instantiated with `entity work.<name>`. The shell's SystemVerilog modules
  (fpga_shell, shell_core, uart_rx, uart_tx, sync2, reset_sync) are compiled into every build: a VHDL entity may not
  take one of those names. To use the shell's `sync2` (2-flop synchroniser: clk, rst, d, q) or `reset_sync` (clk,
  rst_n_async, rst), declare it as a component like fpga_shell; or write your own under another name.
- A register that a bench may read before the first clock edge needs a defined start value (a reset, or an initial
  value `:= '0'`): VHDL's rising_edge() does not fire on the 'U' -> '1' step at time zero that Verilog counts as a
  posedge, so a register with neither stays 'U' until the first real edge.
- Lint is GHDL (`ghdl -a --std=08`, then `ghdl --synth`, which refuses a latch); Vivado reads the files with
  read_vhdl -vhdl2008. With the test shell, simulations run the GHDL netlist of your VHDL beside the shell's
  SystemVerilog under Icarus or Verilator (no free simulator runs cocotb on both languages at once); a design without
  the shell may also run natively under GHDL (SIM=ghdl).""".format(shell=SHELL_COMPONENT)


def shell_modules(shell_dir: Path | None = None) -> set[str]:
    """The module names of the SystemVerilog test shell (fpga_shell, shell_core, uart_rx, uart_tx, sync2, reset_sync)."""
    d = shell_dir or ROOT / "shell" / "rtl"
    names: set[str] = set()
    for f in sorted(d.glob("*.sv")):
        names |= {m.lower() for m in re.findall(r"^\s*module\s+(\w+)", f.read_text(errors="replace"), re.M)}
    return names


def shell_name_clashes(files: Iterable[Path | str], shell_dir: Path | None = None) -> list[str]:
    """A VHDL entity named like a test-shell module: Vivado and the simulators would see two designs of one name
    (brief 55, mistake M1: every first translation re-wrote the shell's sync2/reset_sync as VHDL entities)."""
    sh = shell_modules(shell_dir)
    out = []
    for f in files:
        for e in _ENT_DEF.findall(_text(Path(f))):
            if e.lower() in sh:
                out.append(f"{Path(f).name}: entity {e} has the name of the test shell's SystemVerilog module {e.lower()}; "
                           f"either use the shell's module through a component declaration, or rename your entity")
    return out


_PORT_DECL = re.compile(r"([A-Za-z]\w*(?:\s*,\s*[A-Za-z]\w*)*)\s*:\s*(in|out|inout|buffer)\b", re.I)


def entity_ports(text: str, name: str) -> dict[str, str] | None:
    """The ports of entity ``name`` (case-insensitive match of the entity name) as {port name as spelled: direction};
    None when the text has no such entity. Comments are ignored."""
    t = _COMMENT.sub(" ", text)
    m = re.search(rf"\bentity\s+{re.escape(name)}\s+is\b(.*?)\bend\b", t, re.I | re.S)
    if not m:
        return None
    body = m.group(1)
    pm = re.search(r"\bport\s*\((.*)\)\s*;\s*$", body, re.I | re.S)
    if not pm:
        return {}
    ports: dict[str, str] = {}
    for decl in _PORT_DECL.finditer(pm.group(1)):
        for n in decl.group(1).split(","):
            ports[n.strip()] = decl.group(2).lower()
    return ports
