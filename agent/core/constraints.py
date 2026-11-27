"""A deterministic constraints checker for ``design.xdc`` against the board's files.

Rules (raw findings, rule id plus the offending line; no fix hints):

- ``FDA-CON-1`` a ``create_clock`` on a port that is not the board's dedicated clock input
  (``boards/<board>/board.yaml`` ``clock.port``). A button or switch used as a clock is the hazard the
  Packt/Bruno Ch. 4 demo shows on purpose (``create_clock`` on BTNC); see
  ``research/books_assessment_2026-10-31.md``.
- ``FDA-CON-2`` ``CLOCK_DEDICATED_ROUTE FALSE``: it turns off the check that a clock input sits on a
  clock-capable pin.
- ``FDA-CON-3`` a PACKAGE_PIN or IOSTANDARD that differs from the board's master XDC for the same port.
- ``FDA-CON-4`` two ports on one package pin, or a pin the master XDC does not use. (Ports may have the design's
  own names: the pin and I/O standard are checked against the master by PIN, 05c2.)
- ``FDA-CON-5`` a ``set_false_path`` or ``set_clock_groups -asynchronous`` with no comment in the eight lines above
  (waivers carry a reason, UG949 ch. 5/6). Brief 20 extends it to ``set_multicycle_path`` (the comment must name the
  enable that makes the path multi-cycle: a word such as enable, en, CE, "1 in N", "every N") and to
  ``set_max_delay -datapath_only`` (the comment must name the synchroniser or crossing structure: sync, synchroniser,
  ASYNC_REG, Gray, handshake, FIFO, XPM).
- ``FDA-CON-10`` (brief 20) a ``set_multicycle_path N -setup`` with no ``set_multicycle_path N-1 -hold`` on the same
  ``-from``/``-through``/``-to`` (any ``-start``/``-end`` choice): the hold check then moves N-1 cycles with the
  capture edge (UG903 ch. 5; brief 20 E2 measured it: Vivado raises only XDCH-1, a Warning, and hold fails by 4.7 ns at
  200 MHz). Allowed only
  when a comment above says the hold check stays at its default on purpose ("hold" with "default", "intentional" or
  "on purpose").
- ``FDA-CON-11`` (brief 20 part B, ``flow/io_check.py`` static rules) an input or output delay that is invented: a
  non-zero delay on a port the board lists as slow or asynchronous (``board.yaml`` ``slow_ports``: buttons, switches,
  LEDs, the USB-UART; these take a 0 ns placeholder and a commented false path), or a non-zero delay with no comment
  above naming the data-sheet terms it comes from (tCO, tSU, tH, trace, skew, data valid). Brief 20 part A's agent
  runs gave such ports made-up delays and, once, negative output delays to pass timing.
- ``FDA-CON-12`` (brief 20 part B) ``-min`` larger than ``-max`` on the same ports, clock and edge (Vivado says
  nothing: fixture I3), or a delay that a later line replaces because that line has no ``-add_delay`` (fixture I5b: a DDR
  input's falling-edge lines without it left the rising edge untimed).
- ``FDA-CON-13`` (brief 20 part B) a delay relative to a clock defined later in the file: Vivado drops the delay
  (CRITICAL WARNING 12-4739, fixture V4).
- ``FDA-CON-8`` (``check_top_ports``) a port that ``spec.yaml`` declares is not a port of the top module. The hidden
  bench of a task is written against the spec's ports, so a port the design "does not need" must still exist.
- ``FDA-CON-9`` (``check_top_ports``) the board's USB-UART is a pair (``board.yaml`` ``uart``): when the design uses the
  test shell, or uses either UART pin, the top has both, and design.xdc constrains both. Brief 08a: ``c14_nexys_tiny_cnn``
  run 1 left ``UART_TXD_IN`` out because the design only sends, and the bench, which drives it, scored 0 of 5.

Goal kind "block for a shell" (brief 235; ``Config.block_shell``, the ``.block_for_shell`` marker in the design): the design is a block inside
a supplied shell, not a board top, so the board-top rules above do not apply. ``check_block_xdc`` and ``check_block_ports`` replace them:

- ``FDA-BLK-1`` a pin, an I/O standard or any port reference in the XDC: a block has no board pins (the shell has them).
- ``FDA-BLK-2`` ``create_clock`` or ``create_generated_clock``: the shell owns the clock (the block gets it on its ``clk`` port).
- ``FDA-BLK-3`` any other timing command (delays, waivers, clock groups, max delay): the shell's constraints own every crossing.
- ``FDA-BLK-4`` a port of the shell interface (``boards/<board>/shell/shell.yaml``) missing on the top module.
- ``FDA-BLK-5`` a shell port with the wrong direction or width.
- ``FDA-BLK-6`` a top port the shell does not connect (it would float).
An empty or absent ``design.xdc`` passes.

The master-XDC parser is ``tools/inventory_check.py``'s.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from tools.inventory_check import parse_xdc

_CLOCK = re.compile(r"create_clock\b.*?get_ports\s*\{?\s*([^\s}\]]+)", re.I)
_DEDICATED = re.compile(r"CLOCK_DEDICATED_ROUTE\s+(FALSE|0)", re.I)
_WAIVER = re.compile(r"\b(set_false_path|set_clock_groups\b.*-asynchronous)", re.I)
_MULTICYCLE = re.compile(r"\bset_multicycle_path\b", re.I)
_DATAPATH_ONLY = re.compile(r"\bset_max_delay\b.*-datapath_only", re.I)
_ENABLE_WORDS = re.compile(r"\b(enable[sd]?|en|ce|clock[- ]enable|1[- ]in[- ]\d+|one (clock |cycle )?in \d+|every \d+|"
                           r"every (second|other|third|fourth|\w+th)( \w+)? (clock|cycle|edge)s?)\b|_en\b|\ben_", re.I)
_SYNC_WORDS = re.compile(r"(sync|synchroni[sz]|async_reg|gray|handshake|fifo|xpm|crossing)", re.I)
_HOLD_WAIVER = re.compile(r"hold\b.*\b(default|intentional|on purpose)|\b(default|intentional|on purpose)\b.*\bhold", re.I)


def _comments_above(lines: list[str], n: int) -> list[str]:
    """The comment lines among the eight lines above line ``n`` (1-based)."""
    return [l for l in lines[max(0, n - 9):n - 1] if l.lstrip().startswith("#")]


def _mcp_key(code: str) -> tuple[str, int | None, str, str]:
    """(kind, N, edge, path) of a set_multicycle_path line: kind setup/hold, edge start/end (the default for the kind
    when not given), path = the -from/-through/-to text with whitespace normalised."""
    kind = "hold" if re.search(r"-hold\b", code) else "setup"
    edge = "start" if re.search(r"-start\b", code) else "end" if re.search(r"-end\b", code) else (
        "end" if kind == "setup" else "start")
    m = re.search(r"set_multicycle_path\s+(?:-\w+\s+)*?(\d+)\b", code)
    n = int(m.group(1)) if m else None
    rest = re.sub(r"-(setup|hold|start|end)\b", " ", code.split("set_multicycle_path", 1)[1])
    rest = re.sub(r"(?<![\w\[])\d+(?![\w\]])", " ", rest, count=1)
    return kind, n, edge, " ".join(rest.replace(";", " ").split())


# Buses whose bits benchmark specs name as scalar ports (JA1, QSPI_DQ0, ACL_INT1): Pmod and connector pins.
# LED, SW, AN, VGA_* and the like are written as the bus (``LED[0]``), never ``LED0``.
SCALAR_BUS_FAMILIES = re.compile(r"^(J[A-D]|XA_[NP]|QSPI_DQ|ACL_INT|ETH_RXD|ETH_TXD|SD_DAT)$")
_PORT_BASE = re.compile(r"^([A-Za-z_]\w*?)(?:\[(\d+)\])?$")


def port_name_problem(port: str, master_ports: set[str]) -> str | None:
    """None if ``port`` (as written in a ``get_ports``) is a master-XDC name, a bit of a master bus, or a
    benchmark-convention scalar of a connector bus; else the message naming the master-XDC form."""
    if port in master_ports:
        return None
    m = _PORT_BASE.match(port)
    bases = {re.sub(r"\[\d+\]$", "", p) for p in master_ports}
    if m and m.group(1) in bases:
        return None                                            # a bus name, or a bit of one, in the master's own form
    g = re.fullmatch(r"(\w*?[A-Za-z_])(\d+)", port)
    if g and f"{g.group(1)}[{g.group(2)}]" in master_ports:
        if SCALAR_BUS_FAMILIES.match(g.group(1)):
            return None
        return (f"port {port} is not a master-XDC port name; the master XDC has {g.group(1)}[{g.group(2)}], bit "
                f"{g.group(2)} of bus {g.group(1)}. Declare the top-level port as the bus {g.group(1)} and use "
                f"{g.group(1)}[{g.group(2)}]")
    near = sorted(b for b in bases if b.lower() == (m.group(1).lower() if m else port.lower()))
    hint = f" (the master XDC has {near[0]})" if near else ""
    return (f"port {port} is neither a master-XDC port name nor a bus of one{hint}. Top-level ports use the master "
            f"XDC's names (e.g. CLK100MHZ, BTNC, LED[0] of bus LED, SW[0] of bus SW)")


def check_xdc(xdc_text: str, board_dir: Path) -> list[dict[str, Any]]:
    board = yaml.safe_load((board_dir / "board.yaml").read_text())
    master, _ = parse_xdc((board_dir / board["master_xdc"]).read_text())
    clock_port = board["clock"]["port"]
    by_pin: dict[str, str] = {pin: port for port, (pin, _s) in master.items()}
    mine, _ = parse_xdc(xdc_text)
    pin_std = {pin: std for pin, std in master.values()}
    clock_pin = board["clock"]["pin"]
    my_clock_ports = {p for p, (pin, _s) in mine.items() if pin == clock_pin}   # the design's name for the clock pin
    out: list[dict[str, Any]] = []
    lines = xdc_text.splitlines()

    def add(rule: str, n: int, msg: str) -> None:
        out.append({"rule": rule, "line": n, "text": lines[n - 1].strip(), "message": msg})

    for n, line in enumerate(lines, 1):
        code = line.split("#", 1)[0]
        if not code.strip():
            continue
        m = _CLOCK.search(code)
        if m and m.group(1) != clock_port and m.group(1) not in my_clock_ports:
            add("FDA-CON-1", n, f"create_clock on port {m.group(1)}, which is not the board's clock input {clock_port}")
        if _DEDICATED.search(code):
            add("FDA-CON-2", n, "CLOCK_DEDICATED_ROUTE FALSE disables the dedicated clock-route check")
        if _WAIVER.search(code) and not _comments_above(lines, n):
            add("FDA-CON-5", n, "timing waiver without a comment line above it")
        if _MULTICYCLE.search(code) and not any(_ENABLE_WORDS.search(c) for c in _comments_above(lines, n)):
            add("FDA-CON-5", n, "multicycle path without a comment above it that names the enable making the path "
                                "multi-cycle")
        if _DATAPATH_ONLY.search(code) and not any(_SYNC_WORDS.search(c) for c in _comments_above(lines, n)):
            add("FDA-CON-5", n, "set_max_delay -datapath_only without a comment above it that names the synchroniser or "
                                "crossing it bounds")
    out += _multicycle_pairs(lines)
    out += io_delay_findings(xdc_text, board)
    seen: dict[str, str] = {}
    master_ports = set(master)
    for port, (pin, std) in mine.items():
        n = next((i for i, l in enumerate(lines, 1) if f"{{ {port} }}" in l or f"{{{port}}}" in l), 1)
        problem = port_name_problem(port, master_ports)
        if problem:
            add("FDA-CON-7", n, problem)
        if port in master:                                     # the master's own name: pin and standard must match
            if pin != master[port][0]:
                add("FDA-CON-3", n, f"{port} on {pin}, the board's master XDC has {master[port][0]}")
            if std != master[port][1]:
                add("FDA-CON-3", n, f"{port} is {std}, the board's master XDC has {master[port][1]}")
        elif pin not in pin_std:                               # the design's own name: the pin must exist on the board
            add("FDA-CON-4", n, f"{port} on {pin}, which is not a pin the master XDC uses")
        elif std != pin_std[pin]:
            add("FDA-CON-3", n, f"{port} on {pin} is {std}, the board's master XDC has {pin_std[pin]} for that pin")
        if pin in seen and seen[pin] != port:
            add("FDA-CON-4", n, f"{port} on {pin}, which port {seen[pin]} already uses")
        seen.setdefault(pin, port)
    return out


_IO_RULE = {"IO-INVENTED": "FDA-CON-11", "IO-NO-FORMULA": "FDA-CON-11", "IO-MIN-GT-MAX": "FDA-CON-12", "IO-REPLACED": "FDA-CON-12",
            "IO-CLOCK-ORDER": "FDA-CON-13"}


def io_delay_findings(xdc_text: str, board: dict) -> list[dict[str, Any]]:
    """FDA-CON-11/-12/-13: flow/io_check.py's XDC-only rules, under this checker's rule ids."""
    from flow.io_check import static_findings
    out = []
    for f in static_findings([("design.xdc", xdc_text)], board.get("slow_ports")):
        rule = _IO_RULE.get(f["rule"])
        if rule:
            out.append({"rule": rule, "line": f["line"] or 1, "text": f["text"] or "",
                        "message": f"{f['rule']}: {f['message']}"})
    return out


def _multicycle_pairs(lines: list[str]) -> list[dict[str, Any]]:
    """FDA-CON-10: every ``-setup N`` multicycle has a ``-hold N-1`` on the same path (or a comment
    above saying the hold check stays at its default on purpose)."""
    setups, holds = [], set()
    for n, line in enumerate(lines, 1):
        code = line.split("#", 1)[0]
        if not _MULTICYCLE.search(code):
            continue
        kind, k, edge, path = _mcp_key(code)
        if kind == "hold":
            holds.add((k, path))
        else:
            setups.append((n, k, edge, path))
    out = []
    for n, k, edge, path in setups:
        if k is None or k < 2 or (k - 1, path) in holds:
            continue
        if any(_HOLD_WAIVER.search(c) for c in _comments_above(lines, n)):
            continue
        out.append({"rule": "FDA-CON-10", "line": n, "text": lines[n - 1].strip(),
                    "message": f"set_multicycle_path {k} -setup has no set_multicycle_path {k - 1} -hold on the same path: the "
                               f"hold check moves {k - 1} cycles later with the capture edge"})
    return out


def _base(name: str) -> str:
    return re.sub(r"\[[^\]]*\]$", "", str(name).strip())


#: Brief 239 (planner decision 2026-11-27): module names of AMD primitives and XPM macros. A file that defines one must not be a synthesis
#: source, or it replaces the library cell (the real primitive) in the build.
AMD_PRIMITIVE_NAME = re.compile(
    r"^(xpm_\w+|FD[CPRS]E?|LUT[1-6](_[DL])?|MMCM\w*|PLL\w*|BUFG\w*|BUFH\w*|BUFR|BUFIO|IBUF\w*|OBUF\w*|IOBUF\w*|IDDR\w*|ODDR\w*|IDELAY\w*|"
    r"ODELAY\w*|ISERDES\w*|OSERDES\w*|BSCANE2|USR_ACCESSE2|STARTUPE\d|ICAPE\d|DSP48E\d|RAMB\d+\w*|URAM\w*|CARRY\d|SRL\w*|GT[HXYP]E?\d?\w*|IBUFDS\w*|OBUFDS\w*)$")


def primitive_name_findings(modules: dict[str, list[str]]) -> list[dict[str, Any]]:
    """FDA-CON-11. ``modules`` maps a synthesis source file (name as shown) to the module names it defines. Each module with an AMD primitive
    or XPM name is a finding: such a stand-in belongs in the design's ``sim/`` folder, which the simulators read and synthesis never does."""
    out = []
    for f, names in modules.items():
        for n in names:
            if AMD_PRIMITIVE_NAME.match(n):
                out.append({"file": f, "rule": "FDA-CON-11", "line": 0, "text": f"module {n}",
                            "message": f"{f} defines module {n}, the name of an AMD primitive or XPM macro, in a synthesis source: it would replace the "
                                       f"library cell in the build. Move the stand-in to sim/ (read by lint and the simulators, never by synthesis) and "
                                       f"instantiate the real primitive in rtl/."})
    return out


def _internal(entry: Any) -> bool:
    """Brief 239: a spec port entry whose direction is ``internal`` is a signal between two blocks (for example the register bus
    between the supplied ``jtag_bus`` and the core), not a pin of the top module, so FDA-CON-8 does not ask the top to have it."""
    return isinstance(entry, dict) and str(entry.get("direction", "")).strip().lower() == "internal"


def spec_port_names(spec: Any) -> list[str]:
    """Port names of a spec.yaml (``ports:`` as a list of mappings with ``name``, or a mapping name -> ...), without the entries
    declared ``direction: internal`` (brief 239: 20 of the 36 stage-2 runs of briefs 213 and 227 were held at lint by FDA-CON-8
    for the internal register bus of the supplied ``jtag_bus``; the Designer cannot, and should not, add those to the top)."""
    ports = (spec or {}).get("ports") if isinstance(spec, dict) else None
    if isinstance(ports, dict):
        return [_base(k) for k, v in ports.items() if not _internal(v)]
    return [_base(p["name"]) for p in ports or [] if isinstance(p, dict) and p.get("name") and not _internal(p)]


def check_top_ports(top: str, top_ports: set[str] | None, spec_ports: list[str], xdc_ports: set[str] | None,
                    board_dir: Path, shell: bool) -> list[dict[str, Any]]:
    """FDA-CON-8 and FDA-CON-9. ``top_ports`` is None when the top module's source does not exist yet (nothing to
    check); ``xdc_ports`` None when there is no design.xdc. Findings have ``file`` "rtl" and line 0."""
    if top_ports is None:
        return []
    have = {_base(p) for p in top_ports}
    out: list[dict[str, Any]] = []

    def add(rule: str, msg: str) -> None:
        out.append({"file": "rtl", "rule": rule, "line": 0, "text": f"module {top}", "message": msg})

    for name in dict.fromkeys(spec_ports):
        if name not in have:
            add("FDA-CON-8", f"spec.yaml declares port {name}, but the top module {top} has no port {name}. Every port "
                f"the spec declares must exist on the top, even when the design does not use it: declare it and mark an "
                f"unused input with `/* verilator lint_off UNUSEDSIGNAL */`; never delete the port.")
    board = yaml.safe_load((board_dir / "board.yaml").read_text())
    uart = [board["uart"][k]["port"] for k in ("fpga_rx", "fpga_tx") if k in (board.get("uart") or {})]
    if len(uart) == 2:
        used = shell or any(u in have for u in uart) or any(u in set(spec_ports) for u in uart)
        if used:
            for u in uart:
                other = next(x for x in uart if x != u)
                why = ("the design uses the test shell, which drives both UART pins" if shell else
                       f"the design uses the board's USB-UART ({other} is on the top)")
                if u not in have:
                    add("FDA-CON-9", f"{why}, so the top module {top} must declare the port {u} (the USB-UART is a pair; "
                        f"the bench drives {uart[0]} and reads {uart[1]}). Declare {u} even if the design never uses it, "
                        f"with `/* verilator lint_off UNUSEDSIGNAL */` for an unused input.")
                elif xdc_ports is not None and u not in {_base(p) for p in xdc_ports}:
                    add("FDA-CON-9", f"the top declares {u} but design.xdc does not constrain it: add board resource "
                        f"{'uart_rx' if u == uart[0] else 'uart_tx'} -> {u} to the board_constraints map.")
    return out


# --- goal kind "block for a shell" (brief 235) -----------------------------------------------------------------

_BLK_CLOCK = re.compile(r"\bcreate_(generated_)?clock\b")
_BLK_PIN = re.compile(r"\b(PACKAGE_PIN|IOSTANDARD|IOB|DRIVE|SLEW|PULLTYPE)\b|\bget_ports\b", re.I)
_BLK_TIMING = re.compile(r"\b(set_input_delay|set_output_delay|set_false_path|set_clock_groups|set_max_delay|set_min_delay|set_multicycle_path|"
                         r"set_clock_latency|set_clock_uncertainty|set_input_jitter|set_system_jitter|set_data_check|set_bus_skew)\b")


def load_shell_interface(board_dir: Path, name: str = "shell.yaml") -> dict[str, Any]:
    """The shell-interface file of a board (``boards/<board>/shell/<name>``)."""
    f = board_dir / "shell" / Path(name).name
    if not f.is_file():
        raise FileNotFoundError(f"{f} does not exist: this board has no supplied shell to build a block for")
    return yaml.safe_load(f.read_text()) or {}


def check_block_xdc(xdc_text: str) -> list[dict[str, Any]]:
    """FDA-BLK-1 / -2 / -3 over a block's ``design.xdc`` (empty text: no findings)."""
    out: list[dict[str, Any]] = []
    lines = xdc_text.splitlines()
    for n, line in enumerate(lines, 1):
        code = line.split("#", 1)[0]
        if not code.strip():
            continue
        def add(rule: str, msg: str) -> None:
            out.append({"rule": rule, "line": n, "text": line.strip(), "message": msg})
        if _BLK_CLOCK.search(code):
            add("FDA-BLK-2", "create_clock in a block: the shell owns the clock; the block receives it on its clk port and has no clock of its own to define")
        elif _BLK_PIN.search(code):
            add("FDA-BLK-1", "a pin, I/O standard or port reference in a block's constraints: the block is not the board's top and has no pins; the shell "
                             "has them. Leave design.xdc empty")
        elif _BLK_TIMING.search(code):
            add("FDA-BLK-3", "a timing command in a block's constraints: the shell's constraints own the clock crossings and the I/O delays; "
                             "a block states none")
        if _DEDICATED.search(code):
            add("FDA-CON-2", "CLOCK_DEDICATED_ROUTE FALSE disables the dedicated clock-route check")
    return out


def _width_of(w: str) -> int | None:
    w = (w or "").strip()
    if not w:
        return 1
    m = re.fullmatch(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", w)
    return abs(int(m.group(1)) - int(m.group(2))) + 1 if m else None


def check_block_ports(top: str, top_ports: dict[str, dict[str, Any]] | None, shell: dict[str, Any]) -> list[dict[str, Any]]:
    """FDA-BLK-4 / -5 / -6: the top module against the shell interface. ``top_ports`` is name -> {dir, width} (None while the top's source does not
    exist yet: nothing to check). Findings have ``file`` "rtl" and line 0."""
    if top_ports is None:
        return []
    out: list[dict[str, Any]] = []

    def add(rule: str, msg: str) -> None:
        out.append({"file": "rtl", "rule": rule, "line": 0, "text": f"module {top}", "message": msg})

    want = {p["name"]: p for p in shell.get("ports") or []}
    have = {_base(k): v for k, v in top_ports.items()}
    sname = shell.get("shell", "the shell")
    for name, p in want.items():
        if name not in have:
            add("FDA-BLK-4", f"the top module {top} has no port {name} ({p['dir']}, {p['width']} bit): the shell {sname} connects it by name. Declare it "
                f"(mark an unused input with `/* verilator lint_off UNUSEDSIGNAL */`); never delete it.")
            continue
        h = have[name]
        if h.get("dir") and h["dir"] != p["dir"]:
            add("FDA-BLK-5", f"port {name} of {top} is an {h['dir']}, the shell {sname} drives it as an {p['dir']}")
        hw = _width_of(h.get("width", ""))
        if hw is not None and hw != int(p["width"]):
            add("FDA-BLK-5", f"port {name} of {top} is {hw} bit wide, the shell {sname} connects {p['width']} bit")
    for name in have:
        if name not in want:
            add("FDA-BLK-6", f"port {name} of {top} is not in the shell interface of {sname}: the shell does not connect it, so it would float. "
                f"The block's ports are exactly: {', '.join(want)}")
    return out


# --- the XDC command allow-list (the agent never sends free-form Tcl) -------------------------------------------

XDC_COMMANDS = {
    "set_property", "create_clock", "create_generated_clock", "set_input_delay", "set_output_delay", "set_false_path",
    "set_clock_groups", "set_multicycle_path", "set_max_delay", "set_min_delay", "set_clock_latency",
    "set_clock_uncertainty", "set_input_jitter", "set_system_jitter", "set_case_analysis", "set_disable_timing",
    "set_bus_skew", "set_max_time_borrow", "group_path", "set_clock_sense", "set_data_check", "set_load",
    "set_switching_activity", "set_operating_conditions", "current_design", "create_pblock", "add_cells_to_pblock",
    "resize_pblock", "set_input_transition", "set_propagated_clock", "set",
}
XDC_SUBSTITUTIONS = {"get_ports", "get_pins", "get_cells", "get_clocks", "get_nets", "all_inputs", "all_outputs",
                     "all_clocks", "all_registers", "get_pblocks", "get_property", "current_design"}


def check_xdc_safety(text: str) -> list[dict[str, Any]]:
    """``FDA-CON-6``: a command, or a ``[...]`` substitution, outside the allow-list. Vivado evaluates an XDC as
    Tcl, so ``exec``, ``source``, ``file`` and friends in it are code, not constraints."""
    out: list[dict[str, Any]] = []
    lines = text.splitlines()
    var_names: set[str] = set()                     # `set NAME [get_ports ...]`: the only variables allowed
    for n, raw in enumerate(lines, 1):
        code = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
        if not code.strip():
            continue
        mset = re.match(r"\s*set\s+(\w+)\s+\[\s*(get_\w+|all_\w+)\b", code)
        if mset:
            var_names.add(mset.group(1))
        elif re.match(r"\s*set\s", code) and not re.match(r"\s*set_\w", code):
            out.append({"rule": "FDA-CON-6", "line": n, "text": raw.strip(),
                        "message": "'set' is only allowed as: set NAME [get_ports|get_pins|... ...]"})
        if code.rstrip().endswith("\\"):
            out.append({"rule": "FDA-CON-6", "line": n, "text": raw.strip(),
                        "message": "line continuation is not allowed (one command per line)"})
        for stmt in [x for x in code.split(";") if x.strip()]:
            first = stmt.split()[0]
            if first not in XDC_COMMANDS:
                out.append({"rule": "FDA-CON-6", "line": n, "text": raw.strip(),
                            "message": f"command {first!r} is not in the XDC allow-list"})
        for sub in re.findall(r"\[\s*([A-Za-z_][\w:]*)", code):
            if sub not in XDC_SUBSTITUTIONS:
                out.append({"rule": "FDA-CON-6", "line": n, "text": raw.strip(),
                            "message": f"substitution [{sub} ...] is not in the XDC allow-list"})
        unbraced = re.sub(r"\{[^}]*\}", "", code)
        used = re.findall(r"\$(\w+)", unbraced)
        if any(u not in var_names for u in used) or re.search(r"\$[{(]|\bexec\b|\bsource\b|\beval\b", unbraced):
            out.append({"rule": "FDA-CON-6", "line": n, "text": raw.strip(),
                        "message": "variable use or exec/source/eval outside braces is not allowed"})
    return out


# --- constraints from board resource names (05c2, fix 2) --------------------------------------------------------
#
# Principle: pin numbers are a fact about the board, not something a model should recall. The model says which board
# RESOURCE each of its ports uses (``clk100``, ``led[0:15]``, ``sw[0:15]``, ``seg``, ``an``); the tool writes the
# constraint lines from the board's master XDC, so a pin or I/O standard can never be misremembered. The model still
# chooses its own port names. ``check_constraints`` remains the gate over whatever ends up in design.xdc.

_RES_REF = re.compile(r"^([a-z][a-z0-9_]*)(?:\[(\d+)(?::(\d+))?\])?$")
_PORT_REF = re.compile(r"^([A-Za-z_][A-Za-z0-9_]{0,63})(?:\[(\d+)\])?$")


def resource_catalogue(board_dir: Path) -> dict[str, dict[int, str]]:
    """``{resource: {index: master-XDC port}}``. Every master port is a resource (a bus ``SW[0..15]`` is ``sw``, a
    scalar ``BTNC`` is ``btnc`` with index 0); ``board.yaml``'s ``resources:`` adds named aliases and ordered buses."""
    board = yaml.safe_load((board_dir / "board.yaml").read_text())
    master, _ = parse_xdc((board_dir / board["master_xdc"]).read_text())
    cat: dict[str, dict[int, str]] = {}
    for port in master:
        m = re.match(r"^([A-Za-z0-9_]+)(?:\[(\d+)\])?$", port)
        cat.setdefault(m.group(1).lower(), {})[int(m.group(2) or 0)] = port
    for name, target in (board.get("resources") or {}).items():
        ports = target if isinstance(target, list) else [target]
        cat[name] = {i: p for i, p in enumerate(ports) if p in master}
    return cat


def describe_catalogue(cat: dict[str, dict[int, str]]) -> str:
    out = []
    for n in sorted(cat):
        idx = sorted(cat[n])
        out.append(n if idx == [0] and len(idx) == 1 else
                   f"{n}[{idx[0]}:{idx[-1]}]" + ("" if idx == list(range(idx[0], idx[-1] + 1)) else " (gaps)"))
    return ", ".join(out)


def generate_xdc(board_dir: Path, mapping: list[dict[str, str]]) -> dict[str, Any]:
    """The constraint file for ``mapping`` = ``[{resource, port}]``: ``resource`` is ``name``, ``name[i]`` or
    ``name[a:b]``; ``port`` is the design's port name (a bus for a range, scalar for one element), or ``name[i]`` to
    put one resource element on bit ``i`` of a bus. Returns ``{ok, xdc, ports: {port: width}, errors}``."""
    board = yaml.safe_load((board_dir / "board.yaml").read_text())
    master, _ = parse_xdc((board_dir / board["master_xdc"]).read_text())
    cat = resource_catalogue(board_dir)
    errors: list[str] = []
    bits: dict[tuple[str, int | None], str] = {}              # (design port, bit or None) -> master port
    used: dict[str, str] = {}                                 # master port -> design port
    for e in mapping:
        res, port = str(e.get("resource", "")), str(e.get("port", ""))
        m, pm = _RES_REF.match(res.strip().lower()), _PORT_REF.match(port.strip())
        if not m:
            errors.append(f"resource {res!r}: write it as name, name[i] or name[a:b] (lower case)")
            continue
        if not pm:
            errors.append(f"port {port!r}: not a plain port name (letters, digits, underscore; optional [bit])")
            continue
        name, a, b = m.group(1), m.group(2), m.group(3)
        if name not in cat:
            errors.append(f"unknown resource {name!r}; this board's resources: {describe_catalogue(cat)}")
            continue
        have = cat[name]
        if a is None:
            want = sorted(have)
        else:
            lo, hi = sorted((int(a), int(b if b is not None else a)))
            want = list(range(lo, hi + 1))
        missing = [i for i in want if i not in have]
        if missing:
            errors.append(f"resource {res}: {name} has no element {missing[0]} (it has {sorted(have)})")
            continue
        pname, pbit = pm.group(1), (int(pm.group(2)) if pm.group(2) is not None else None)
        if len(want) > 1 and pbit is not None:
            errors.append(f"port {port!r}: a {len(want)}-element resource {res} maps to a whole bus, give the bus name")
            continue
        for k, i in enumerate(want):
            key = (pname, pbit if len(want) == 1 and pbit is not None else (k if len(want) > 1 or (b is not None) else None))
            if key in bits:
                errors.append(f"port {pname}{'' if key[1] is None else f'[{key[1]}]'} is mapped twice")
                continue
            mp = have[i]
            if mp in used:
                errors.append(f"resource element {mp} is used by both port {used[mp]} and port {pname}")
                continue
            bits[key], used[mp] = mp, f"{pname}{'' if key[1] is None else f'[{key[1]}]'}"
    # a port is either scalar or a bus 0..n-1 with no gaps
    widths: dict[str, int] = {}
    for pname in sorted({p for p, _ in bits}):
        idx = sorted(i for p, i in bits if p == pname)
        if idx == [None]:
            widths[pname] = 1
        elif None in idx:
            errors.append(f"port {pname} is used both as a scalar and as a bus")
        elif idx != list(range(len(idx))):
            errors.append(f"port {pname}: bus bits {idx} are not 0..{len(idx) - 1} without gaps")
        else:
            widths[pname] = len(idx)
    if errors:
        return {"ok": False, "errors": errors, "xdc": "", "ports": {}}
    lines = ["## design.xdc: generated by the core's board_constraints tool from the board's master XDC",
             f"## ({board['master_xdc']}). Pins and I/O standards are the board's; do not edit pin numbers.", ""]
    clock_port = board["clock"]["port"]
    period = 1000.0 / float(board["clock"]["freq_mhz"])
    for (pname, bit), mp in sorted(bits.items(), key=lambda kv: (kv[0][0], -1 if kv[0][1] is None else kv[0][1])):
        pin, std = master[mp]
        ref = pname if bit is None else f"{pname}[{bit}]"
        lines.append(f"set_property -dict {{ PACKAGE_PIN {pin:<4} IOSTANDARD {std} }} [get_ports {{ {ref} }}];"
                     f"  # {mp}")
        if mp == clock_port:
            lines.append(f"create_clock -add -name sys_clk_pin -period {period:.2f} -waveform {{0 {period / 2:g}}} "
                         f"[get_ports {{ {ref} }}];")
    return {"ok": True, "xdc": "\n".join(lines) + "\n", "ports": widths, "errors": []}
