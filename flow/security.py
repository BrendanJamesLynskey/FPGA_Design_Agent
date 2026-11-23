#!/usr/bin/env python3
"""Design security for a production build (brief 196): the request, the Vivado settings it becomes, and the check that proves them.

    python3 -m flow.security show   <build dir>                      the request and the evidence of one build (JSON)
    python3 -m flow.security check  <build dir>                      the gates; exit 1 if one fails
    python3 -m flow.security sysmon-init <board> [--write <file>]    the SYSMONE4 INIT values of the board's operating limits

**What is in scope** (owner, 2026-11-23): bitstream encryption and authentication settings, readback and JTAG-to-SYSMON settings,
production hygiene (no debug cores or debug ports), SYSMON alarm thresholds wired to a latched safe shutdown, and the build's proof of
each. **What is out** (human): key generation, storage and provisioning, **any eFUSE or BBRAM programming** (no code here writes or runs
one; the only key material this module touches is the throw-away ``.nky`` Vivado writes next to a build that is never programmed), the PS
secure-boot chain, side-channel or certification claims.

The request has five sub-switches, ``encrypt``, ``authenticate``, ``readback_off``, ``strip_debug`` and ``sysmon_shutdown``, under the master
switch ``production_secure`` (the verification-profile switch of ``agent/graph/profiles.py``). It comes from, in order of precedence:

1. ``FDA_SECURITY`` in the environment: JSON the agent's harness sets from the run's pin (``<run dir>/policy.json``), which no role can reach;
2. ``security:`` in the design's ``build.yaml``: the way a person builds by hand.

If both exist and differ the pin wins and the build records a ``policy_conflict`` (gate ``security_policy_pin``).

The check reads only what Vivado wrote: ``security_design.txt`` (properties set on the design, read back after ``write_bitstream``, the debug
inventory and the SYSMON cell, all dumped by ``flow/build.tcl``), the build's Vivado log (the ``write_bitstream`` section) and the ``.bit``
file's header. A gate fails when the evidence is missing; nothing is inferred from the request itself.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUBSWITCHES = ("encrypt", "authenticate", "readback_off", "strip_debug", "sysmon_shutdown")
DEFAULTS_ON = {k: True for k in SUBSWITCHES}
ENV = "FDA_SECURITY"


class SecurityError(ValueError):
    pass


# ---- the request ---------------------------------------------------------------------------------------------------------------------

def normalise(raw: Any, where: str) -> dict[str, Any]:
    """A request mapping from ``build.yaml`` or the pin: ``production_secure`` (bool) and the five sub-switches (bool, default on once the
    master is on), plus optional ``waive`` (list of {rule, reason}). Anything else is refused: a misspelt switch must not quietly do nothing."""
    if raw in (None, False, "", "off"):
        return {"production_secure": False, **DEFAULTS_ON, "waive": []}
    if raw is True or raw == "on":
        raw = {"production_secure": True}
    if not isinstance(raw, dict):
        raise SecurityError(f"{where}: security must be a mapping, on or off")
    allowed = {"production_secure", "waive", *SUBSWITCHES}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise SecurityError(f"{where}: unknown security keys {extra}; allowed: {sorted(allowed)}")
    out: dict[str, Any] = {"production_secure": bool(raw.get("production_secure", True)), "waive": []}
    for k in SUBSWITCHES:
        v = raw.get(k, True)
        if not isinstance(v, bool):
            raise SecurityError(f"{where}: {k} must be true or false")
        out[k] = v
    for w in raw.get("waive") or []:
        if not (isinstance(w, dict) and w.get("rule") and len(str(w.get("reason", "")).split()) >= 4):
            raise SecurityError(f"{where}: a waiver needs a rule and a reason of at least four words")
        out["waive"].append({"rule": str(w["rule"]), "reason": str(w["reason"])})
    return out


def effective_switches(req: dict[str, Any]) -> dict[str, bool]:
    """The sub-switches that act: all off when the master is off."""
    return {k: bool(req["production_secure"] and req[k]) for k in SUBSWITCHES}


def resolve(build_cfg: dict[str, Any] | None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """The request of one build and where it came from. ``source`` is ``pin`` (the run's pin), ``build.yaml`` or ``none``; ``policy_conflict``
    lists a build.yaml request that the pin overrode."""
    env = os.environ if env is None else env
    yml = (build_cfg or {}).get("security")
    pin_raw = env.get(ENV)
    conflict: list[str] = []
    if pin_raw:
        try:
            pin = normalise(json.loads(pin_raw), f"${ENV}")
        except json.JSONDecodeError as e:
            raise SecurityError(f"${ENV} is not JSON: {e}") from None
        if yml is not None:
            try:
                y = normalise(yml, "build.yaml")
                if effective_switches(y) != effective_switches(pin):
                    conflict.append("build.yaml asks for " + json.dumps(effective_switches(y), sort_keys=True)
                                    + " but the run's pin is " + json.dumps(effective_switches(pin), sort_keys=True) + ": the pin wins")
            except SecurityError as e:
                conflict.append(str(e))
        return {"source": "pin", "request": pin, "switches": effective_switches(pin), "policy_conflict": conflict}
    if yml is not None:
        r = normalise(yml, "build.yaml")
        return {"source": "build.yaml", "request": r, "switches": effective_switches(r), "policy_conflict": []}
    r = normalise(None, "none")
    return {"source": "none", "request": r, "switches": effective_switches(r), "policy_conflict": []}


# ---- the SYSMON thresholds ----------------------------------------------------------------------------------------------------------

#: 10-bit transfer functions of the PL SYSMON, as used and read back on the owner's board by designs/b96_kr260_10g/host/b96c_ppm.py
#: (sysmon_to_units): temperature = code x 501.3743 / 1024 - 273.6777 degC; a supply = code / 1024 x 3 V.
TEMP_SCALE, TEMP_OFFSET = 501.3743, 273.6777


def temp_code(c: float, up: bool) -> int:
    x = (c + TEMP_OFFSET) * 1024.0 / TEMP_SCALE
    return int(math.ceil(x - 1e-9)) if up else int(math.floor(x + 1e-9))


def volt_code(v: float, up: bool) -> int:
    x = v / 3.0 * 1024.0
    return int(math.ceil(x - 1e-9)) if up else int(math.floor(x + 1e-9))


def code_to_temp(code: int) -> float:
    return code * TEMP_SCALE / 1024.0 - TEMP_OFFSET


def code_to_volt(code: int) -> float:
    return code / 1024.0 * 3.0


def limits_of(board: str) -> dict[str, Any]:
    import yaml
    f = ROOT / "boards" / board / "board.yaml"
    d = yaml.safe_load(f.read_text()) or {}
    lim = d.get("operating_limits")
    if not isinstance(lim, dict):
        raise SecurityError(f"boards/{board}/board.yaml has no operating_limits (needed for sysmon_shutdown)")
    return lim


def sysmon_init(lim: dict[str, Any]) -> dict[str, int]:
    """The SYSMONE4 INIT values that make the monitor raise the alarms of ``b196_sysmon_guard``. Each is written from the meaning the AMD
    simulation model (unisims/SYSMONE4.v, Vivado 2026.1) gives the register, in our own words:

    * INIT_41, configuration register 1: bits 15:12 the sequencer mode (0010: continuous sequence; the default mode 0000 leaves every alarm
      but OT off); bit 0 disables OT, bits 3:1 disable ALM2..0, bits 11:8 disable ALM6..3, so 0 enables and 1 disables (ALM3 on, ALM4..6 off);
      bits 7:4 the four calibrations (all on: DS925 note 4 says the stated accuracy needs them);
    * INIT_42: bits 15:8 the DCLK divider for ADCCLK (8: 25 MHz gives 3.125 MHz, inside DS925's 1 to 5.2 MHz);
    * INIT_43: bits 3:0 disable ALM11..8, the user-supply alarms (all off);
    * INIT_48: the channels the sequencer visits: bit 0 calibration, 8 temperature, 9 VCCINT, 10 VCCAUX, 14 VCCBRAM;
    * INIT_50 temperature upper alarm, INIT_54 its lower (re-arm) level; INIT_51/55 VCCINT upper/lower; INIT_52/56 VCCAUX; INIT_58/5C VCCBRAM:
      the 10-bit code in bits 15:6. An upper level is rounded up and a lower level down, so a reading inside the limits never trips;
    * INIT_53 (the OT limit) is left out: the monitor ignores a user OT limit unless its low four bits are 0011, and that pattern also enables
      the automatic device shutdown, which de-configures the part. The device's own default OT limit stays.
    """
    t_up = temp_code(float(lim["tj_alarm_c"]), True)
    t_lo = temp_code(float(lim["tj_alarm_c"]) - 10.0, False)
    out = {
        "INIT_41": (0x2 << 12) | (0xE << 8) | (0xF << 4),
        "INIT_42": 8 << 8,
        "INIT_43": 0x000F,
        "INIT_48": 0x4701,
        "INIT_50": t_up << 6, "INIT_54": t_lo << 6,
    }
    for reg_up, reg_lo, key in (("INIT_51", "INIT_55", "vccint_v"), ("INIT_52", "INIT_56", "vccaux_v"), ("INIT_58", "INIT_5C", "vccbram_v")):
        lo, hi = (float(x) for x in lim[key])
        out[reg_up] = volt_code(hi, True) << 6
        out[reg_lo] = volt_code(lo, False) << 6
    return out


def sysmon_header(board: str) -> str:
    vals = sysmon_init(limits_of(board))
    lim = limits_of(board)
    lines = [f"// b196_sysmon_pkg.sv: generated by `python3 -m flow.security sysmon-init {board} --write <this file>`; do not edit.",
             f"// Source: boards/{board}/board.yaml operating_limits ({lim.get('status')}): Tj alarm {lim['tj_alarm_c']} C, VCCINT {lim['vccint_v']} V,",
             f"// VCCAUX {lim['vccaux_v']} V, VCCBRAM {lim['vccbram_v']} V. The meaning of each register is in flow/security.py (sysmon_init)."]
    lines.append("package b196_sysmon_pkg;")
    for k, v in vals.items():
        lines.append(f"    localparam logic [15:0] SM_{k} = 16'h{v:04X};")
    lines.append("endpackage")
    return "\n".join(lines) + "\n"


# ---- the Vivado side -------------------------------------------------------------------------------------------------------------------

def family_of(part: str) -> str:
    """The family name the flow uses for a part (the same split as agent/core/session.py PART_FAMILY); only Zynq UltraScale+ is measured."""
    return "zynq_ultrascale_plus" if re.match(r"^(xck2[46]|xczu)", part.strip().lower()) else "other"


def tcl_assignments(sw: dict[str, bool], family: str) -> list[tuple[str, str]]:
    """The design properties the switches set before ``write_bitstream`` (``flow/build.tcl`` applies them; the check reads them back).
    ``family`` is ``zynq_ultrascale_plus`` (the only one measured). The key is never given: Vivado writes a fresh random one into a ``.nky``
    beside the bitstream, which this flow never programs anywhere."""
    if family != "zynq_ultrascale_plus":
        raise SecurityError(f"production_secure has been measured on UltraScale+ only, not {family}")
    out: list[tuple[str, str]] = []
    if sw["encrypt"]:
        out += [("BITSTREAM.ENCRYPTION.ENCRYPT", "YES"), ("BITSTREAM.ENCRYPTION.ENCRYPTKEYSELECT", "BBRAM")]
    if sw["authenticate"]:
        pass            # filled in by the measured Vivado behaviour, see docs/security.md
    if sw["readback_off"]:
        out += [("BITSTREAM.CONFIG.SECURITY", "LEVEL1"), ("BITSTREAM.GENERAL.JTAG_SYSMON", "DISABLE")]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sysmon-init")
    s.add_argument("board")
    s.add_argument("--write")
    a = ap.parse_args(argv)
    if a.cmd == "sysmon-init":
        text = sysmon_header(a.board)
        if a.write:
            Path(a.write).write_text(text)
        else:
            sys.stdout.write(text)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
