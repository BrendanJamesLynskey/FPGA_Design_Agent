"""A deterministic constraints checker for ``design.xdc`` against the board's files.

Rules (raw findings, rule id plus the offending line; no fix hints):

- ``FDA-CON-1`` a ``create_clock`` on a port that is not the board's dedicated clock input
  (``boards/<board>/board.yaml`` ``clock.port``). A button or switch used as a clock is the hazard the
  Packt/Bruno Ch. 4 demo shows on purpose (``create_clock`` on BTNC); see
  ``research/books_assessment_2026-10-31.md``.
- ``FDA-CON-2`` ``CLOCK_DEDICATED_ROUTE FALSE``: it turns off the check that a clock input sits on a
  clock-capable pin.
- ``FDA-CON-3`` a PACKAGE_PIN or IOSTANDARD that differs from the board's master XDC for the same port.
- ``FDA-CON-4`` a port constrained to a package pin the master XDC gives to another port.
- ``FDA-CON-5`` a ``set_false_path`` or ``set_clock_groups -asynchronous`` with no comment in the eight lines above
  (waivers carry a reason, UG949 ch. 5/6).

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


def check_xdc(xdc_text: str, board_dir: Path) -> list[dict[str, Any]]:
    board = yaml.safe_load((board_dir / "board.yaml").read_text())
    master, _ = parse_xdc((board_dir / board["master_xdc"]).read_text())
    clock_port = board["clock"]["port"]
    by_pin: dict[str, str] = {pin: port for port, (pin, _s) in master.items()}
    mine, _ = parse_xdc(xdc_text)
    out: list[dict[str, Any]] = []
    lines = xdc_text.splitlines()

    def add(rule: str, n: int, msg: str) -> None:
        out.append({"rule": rule, "line": n, "text": lines[n - 1].strip(), "message": msg})

    for n, line in enumerate(lines, 1):
        code = line.split("#", 1)[0]
        if not code.strip():
            continue
        m = _CLOCK.search(code)
        if m and m.group(1) != clock_port:
            add("FDA-CON-1", n, f"create_clock on port {m.group(1)}, which is not the board's clock input {clock_port}")
        if _DEDICATED.search(code):
            add("FDA-CON-2", n, "CLOCK_DEDICATED_ROUTE FALSE disables the dedicated clock-route check")
        if _WAIVER.search(code) and not any(l.lstrip().startswith("#") for l in lines[max(0, n - 9):n - 1]):
            add("FDA-CON-5", n, "timing waiver without a comment line above it")
    for port, (pin, std) in mine.items():
        n = next((i for i, l in enumerate(lines, 1) if f"{{ {port} }}" in l or f"{{{port}}}" in l), 1)
        if port in master:
            if pin != master[port][0]:
                add("FDA-CON-3", n, f"{port} on {pin}, the board's master XDC has {master[port][0]}")
            if std != master[port][1]:
                add("FDA-CON-3", n, f"{port} is {std}, the board's master XDC has {master[port][1]}")
        elif pin in by_pin:
            add("FDA-CON-4", n, f"{port} on {pin}, which the master XDC gives to {by_pin[pin]}")
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
