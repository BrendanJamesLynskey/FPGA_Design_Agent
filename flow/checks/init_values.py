"""The initial-value check (brief 206): where an initial value of 1 quietly costs a hard block's register on AMD parts.

Measured on Vivado 2026.1 (``results/206_power_up``, xc7a35t and xck26, out-of-context synthesis):

- an initial (power-up) value is free on every fabric flip-flop and IOB register: FDRE/FDSE/FDCE/FDPE take INIT 0 or 1
  whatever the sense of their reset, with no extra LUT, and the GSR loads it at the end of configuration;
- **but a register with INIT = 1 is never absorbed into a DSP48 pipeline register (A/B/M/P) or a block RAM's output
  register**: the DSP registers power up 0 and a block-RAM port holds one INIT value, so synthesis leaves the register in
  the fabric (X8: 108 flip-flops, AREG = BREG = MREG = PREG = 0) and prints no warning for the DSP case (only the "DSP
  Final Report" shows the empty register columns); for the block RAM it prints only the generic INFO Synth 8-7052;
- **UltraRAM with non-zero initial contents is not built as UltraRAM**: ``ram_style = "ultra"`` is ignored and the memory
  goes to block RAM, with WARNING Synth 8-12183 (X11: eight RAMB36E2 instead of one URAM288).

Findings (all advisory: the design is correct, it is only bigger or slower than it looks):

- INIT-HB-01: a flip-flop with INIT = 1 wired straight to a DSP, block RAM, UltraRAM or FIFO (``init_scan.tsv``, written by
  ``fda_init_scan`` in flow/checks/vivado_checks.tcl). One finding per hard block.
- INIT-URAM-01: Synth 8-12183 in the build's ``vivado.log`` (an UltraRAM request refused because of initial contents).

The setting ``rtl.initial_values`` (brief 205, owner decision 38) decides whether initial values are allowed at all; this
check only says where an allowed one costs a hard block. The house rule and the Altera side (where every core register
powers up 0 and a 1 costs inverters) are in the KB skill ``power-up-values-amd-and-altera``.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

CODES = ("INIT-HB-01", "INIT-URAM-01")
KIND = (("DSP", "DSP"), ("RAMB", "block RAM"), ("URAM", "UltraRAM"), ("FIFO", "FIFO"))
FIX = {
    "INIT-HB-01": "if the power-up value of these registers does not matter (data qualified by a valid bit, or flushed before "
                  "use), drop the initial value (or make it 0) so synthesis can pull them into the block; if it matters, keep "
                  "it and accept fabric registers, or give the block's own registers a synchronous reset instead (a reset, "
                  "unlike an INIT, is supported by the DSP and RAM registers)",
    "INIT-URAM-01": "UltraRAM cannot hold initial contents (UG573: it powers up 0): load the contents after configuration, "
                    "or accept block RAM and remove ram_style = \"ultra\"",
}
#: measured cost quoted in the messages (results/206_power_up/README.md, Vivado 2026.1, one run each)
MEASURED = {
    "DSP": "results/206_power_up X8: an 18 x 18 multiply with A, B, M and P registers all INIT 1 gave AREG = BREG = MREG = PREG = 0 "
           "and 108 fabric flip-flops (all INIT 0: every register absorbed, 0 flip-flops)",
    "block RAM": "results/206_power_up X9: a 1K x 32 RAM whose output register had INIT 1 kept that register in the fabric "
                 "(DOB_REG = 0, 32 flip-flops)",
    "UltraRAM": "results/206_power_up X11: a 4K x 72 ram_style ultra memory with initial contents became eight RAMB36E2",
    "FIFO": "not measured",
}


def _kind(ref: str) -> str:
    for pre, name in KIND:
        if ref.startswith(pre):
            return name
    return ref


def read_scan(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def scan_findings(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One INIT-HB-01 finding per hard block that has INIT = 1 registers wired to it."""
    by: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        if str(r.get("init", "")).strip() not in ("1", "1'b1"):
            continue
        by.setdefault(r["block"], []).append(r)
    out = []
    for block, rs in sorted(by.items()):
        kind = _kind(rs[0].get("block_ref", ""))
        n_in = len({r["cell"] for r in rs if r.get("dir") == "to"})
        n_out = len({r["cell"] for r in rs if r.get("dir") == "from"})
        sides = ", ".join(x for x in (f"{n_in} feeding it" if n_in else "", f"{n_out} fed by it" if n_out else "") if x)
        out.append({"tool": "init_values", "code": "INIT-HB-01", "severity": "advisory", "where": block,
                    "count": len({r["cell"] for r in rs}),
                    "message": f"{sides} register(s) with initial value 1 next to {kind} {block} ({rs[0].get('block_ref')}): "
                               f"left in the fabric, not absorbed into the {kind}'s own registers (they power up 0, or hold one "
                               f"INIT per port). Measured: {MEASURED.get(kind, 'not measured')}",
                    "fix": FIX["INIT-HB-01"]})
    return out


URAM_MSG = re.compile(r"WARNING: \[Synth 8-12183\] (.*)")


def log_findings(log_text: str) -> list[dict[str, Any]]:
    """INIT-URAM-01 from a Vivado log: each distinct Synth 8-12183 message once."""
    seen: dict[str, int] = {}
    for m in URAM_MSG.finditer(log_text):
        seen[m.group(1).strip()] = seen.get(m.group(1).strip(), 0) + 1
    out = []
    for msg, n in seen.items():
        ram = re.search(r'on RAM "([^"]+)"', msg)
        out.append({"tool": "init_values", "code": "INIT-URAM-01", "severity": "warning", "where": ram.group(1) if ram else "vivado.log",
                    "count": n, "message": f"Synth 8-12183: {msg[:300]}. Measured: {MEASURED['UltraRAM']}",
                    "fix": FIX["INIT-URAM-01"]})
    return out
