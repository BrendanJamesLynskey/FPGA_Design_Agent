#!/usr/bin/env python3
"""Design security for a production build (brief 196): the request, the Vivado settings it becomes, and the check that proves them.

    python3 -m flow.security show   <build dir>                      the request and the evidence of one build (JSON)
    python3 -m flow.security check  <build dir>                      the gates; exit 1 if one fails
    python3 -m flow.security sysmon-init <board> [--write <file>]    the SYSMONE4 INIT values of the board's operating limits

**What is in scope** (owner, 2026-11-23): bitstream encryption and authentication settings, readback and JTAG-to-SYSMON settings,
production hygiene (no debug cores or debug ports), SYSMON alarm thresholds wired to a latched safe shutdown, and the build's proof of
each. **What is out** (human): key generation, storage and provisioning, **any eFUSE or BBRAM programming** (no code here writes or runs
one; no key file, key path or key value is read or recorded; the ``.nky`` Vivado writes beside an encrypted bitstream on a family that has that setting is git-ignored), the PS
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

#: Per family: the settings Vivado takes for write_bitstream, and the switches it cannot act on (``owner``: why). Measured on Vivado 2026.1 for xck26
#: (results/b196/probe_xck26_properties.txt): BITSTREAM.ENCRYPTION.* and BITSTREAM.AUTHENTICATION.* are read-only properties of a Zynq UltraScale+ MPSoC design
#: (settable on Kintex and Virtex UltraScale+ per UG908 table 40, not measured here); BITSTREAM.READBACK.SECURITY, GENERAL.JTAG_SYSMON and GENERAL.DISABLE_JTAG are
#: settable (UG908 table 43). On an MPSoC the PL bitstream is encrypted and authenticated in the boot image (UG1085 ch. 12): the PS secure-boot chain, the owner's.
FAMILY = {
    "zynq_ultrascale_plus": {
        "readback_off": [("BITSTREAM.READBACK.SECURITY", "LEVEL1"), ("BITSTREAM.GENERAL.JTAG_SYSMON", "DISABLE"), ("BITSTREAM.GENERAL.DISABLE_JTAG", "YES")],
        "owner": {"encrypt": "on a Zynq UltraScale+ MPSoC the PL bitstream is encrypted by the boot image (bootgen, UG1085 ch. 12): the PS secure-boot chain and the key are "
                             "the owner's; BITSTREAM.ENCRYPTION.* is read-only in Vivado 2026.1 for this part",
                  "authenticate": "likewise: RSA authentication of the PL partition belongs to the boot image; BITSTREAM.AUTHENTICATION.* is read-only in Vivado 2026.1 for this part"},
    },
}


def family_of(part: str) -> str:
    """The family name the flow uses for a part (the same split as agent/core/session.py PART_FAMILY); only Zynq UltraScale+ is measured."""
    return "zynq_ultrascale_plus" if re.match(r"^(xck2[46]|xczu)", part.strip().lower()) else "other"


def tcl_assignments(sw: dict[str, bool], family: str) -> list[tuple[str, str]]:
    """The design properties the switches set before ``write_bitstream`` (``flow/build.tcl`` applies them; the check reads them back). The key is
    never given: nothing here sets one."""
    if family not in FAMILY:
        raise SecurityError(f"production_secure has been measured on UltraScale+ (Zynq MPSoC) only, not {family}")
    return list(FAMILY[family]["readback_off"]) if sw["readback_off"] else []


def owner_items(sw: dict[str, bool], family: str) -> dict[str, str]:
    """Switches that are on but that Vivado cannot act on for this family: handed to the owner, listed in the record, never counted as met."""
    return {k: why for k, why in FAMILY[family]["owner"].items() if sw.get(k)}


# ---- the check ------------------------------------------------------------------------------------------------------------------------

DEBUG_PORT = re.compile(r"(?i)(^|[_\[./])(jtag|tck|tms|tdi|tdo|trst|swd|swclk|swdio|trace|dbg|debug|probe)([_\[\]./0-9]|$)")
APPLY_FILE, DUMP_FILE = "security_apply.txt", "security_design.txt"


def parse_dump(text: str) -> dict[str, Any]:
    """``security_design.txt`` (flow/security.tcl ``fda_security_dump``) as data."""
    d: dict[str, Any] = {"props": {}, "debug_cores": [], "debug_cells": [], "bscan": [], "mark_debug": [], "ports": [], "sysmon": {}, "sysmon_cells": []}
    cur = None
    for line in text.splitlines():
        k, _, rest = line.partition(" ")
        if k == "PART":
            d["part"] = rest.strip()
        elif k == "PROP":
            name, _, val = rest.partition(" ")
            d["props"][name] = val.strip()
        elif k == "DEBUG_CORES":
            n, _, names = rest.partition(" ")
            d["n_debug_cores"] = int(n)
            d["debug_cores"] = names.split()
        elif k == "DEBUG_CELL":
            d["debug_cells"].append(rest.strip())
        elif k == "DEBUG_CELL_COUNT":
            d["n_debug_cells"] = int(rest)
        elif k == "BSCAN_CELL":
            d["bscan"].append(rest.strip())
        elif k == "BSCAN_COUNT":
            d["n_bscan"] = int(rest)
        elif k == "MARK_DEBUG_NETS":
            d["n_mark_debug"] = int(rest)
        elif k == "MARK_DEBUG_NET":
            d["mark_debug"].append(rest.strip())
        elif k == "PORT":
            dr, _, name = rest.partition(" ")
            d["ports"].append((dr, name.strip()))
        elif k == "SYSMON_CELL":
            cur = rest.strip()
            d["sysmon_cells"].append(cur)
            d["sysmon"][cur] = {"attrs": {}, "pins": {}}
        elif k == "SYSMON_ATTR" and cur:
            name, _, val = rest.partition(" ")
            d["sysmon"][cur]["attrs"][name] = val.strip()
        elif k == "SYSMON_PIN" and cur:
            pn, _, r = rest.partition(" ")
            head, _, tail = r.partition(" :: ")
            toks = head.split()
            pin = {"loads": (int(toks[0]) if toks and toks[0].isdigit() else 0), "load_cells": tail.split(), "reg": None, "reg_qloads": 0}
            if len(toks) >= 4 and toks[1] == "reg" and toks[2] != "none":
                pin["reg"], pin["reg_qloads"] = toks[2], (int(toks[4]) if len(toks) > 4 and toks[3] == "qloads" and toks[4].isdigit() else 0)
            d["sysmon"][cur]["pins"][pn] = pin
    return d


def parse_apply(text: str) -> tuple[list[str], list[str]]:
    ok, bad = [], []
    for line in text.splitlines():
        if line.startswith("APPLY ok "):
            ok.append(line[len("APPLY ok "):].strip())
        elif line.startswith("APPLY ERROR "):
            bad.append(line[len("APPLY ERROR "):].strip())
    return ok, bad


def attr_value(s: str) -> int | None:
    """A SYSMONE4 INIT attribute as Vivado prints it (``16'hB740``, ``16'b1011..``, ``0xB740`` or plain hex) as an integer."""
    s = s.strip()
    m = re.match(r"^\d+'([hbdo])([0-9a-fA-F_xXzZ]+)$", s)
    try:
        if m:
            return int(m.group(2).replace("_", ""), {"h": 16, "b": 2, "d": 10, "o": 8}[m.group(1)])
        if s.lower().startswith("0x"):
            return int(s, 16)
        return int(s, 16)
    except ValueError:
        return None


def debug_findings(dump: dict[str, Any], waive: list[dict[str, str]], variant_files: list[str]) -> list[dict[str, str]]:
    """What a production build must not contain, from the dump of the implemented design. A finding is waived only by name, with a reason."""
    waived = {w["rule"] for w in waive}
    out: list[dict[str, str]] = []

    def add(rule: str, what: str) -> None:
        if rule not in waived:
            out.append({"rule": rule, "what": what})
    if dump.get("n_debug_cores", 0):
        add("debug_core", f"{dump['n_debug_cores']} debug core(s) in the design: {' '.join(dump['debug_cores'])}")
    if dump.get("n_debug_cells", 0):
        names = ", ".join(sorted({c.split()[0] for c in dump["debug_cells"]})[:6])
        add("debug_cell", f"{dump['n_debug_cells']} cell(s) of a debug core, hub or bridge (reference names: {names})")
    if dump.get("n_bscan", 0):
        add("bscan", f"{dump['n_bscan']} BSCAN primitive(s): a JTAG user-register path into the design")
    if dump.get("n_mark_debug", 0):
        add("mark_debug", f"{dump['n_mark_debug']} net(s) marked MARK_DEBUG")
    bad_ports = [n for _d, n in dump.get("ports", []) if DEBUG_PORT.search(n)]
    if bad_ports:
        add("debug_port", "top-level port(s) with a debug-class name: " + ", ".join(bad_ports[:6]))
    for f in variant_files:
        add("debug_file", f"the build wrote {f}, the probe file of a debug build")
    return out


def sysmon_findings(dump: dict[str, Any], expected: dict[str, int]) -> list[str]:
    cells = dump.get("sysmon_cells", [])
    if not cells:
        return ["no SYSMONE4 cell in the design"]
    out: list[str] = []
    for c in cells:
        got = dump["sysmon"][c]
        for reg, want in expected.items():
            v = attr_value(got["attrs"].get(reg, ""))
            if v != want:
                out.append(f"{c}: {reg} is {got['attrs'].get(reg, 'missing')}, the board's limits give 16'h{want:04X}")
        for pn in ("OT", "ALM[0]", "ALM[1]", "ALM[2]", "ALM[3]"):
            pin = got["pins"].get(pn)
            if not pin or pin["loads"] < 1:
                out.append(f"{c}: output {pn} drives nothing")
            elif not pin.get("reg"):
                out.append(f"{c}: output {pn} reaches no register within three cells ({' '.join(pin['load_cells'][:3])})")
            elif pin.get("reg_qloads", 0) < 1:
                out.append(f"{c}: output {pn} reaches register {pin['reg']}, whose output drives nothing")
    return out


def evaluate(build_dir: Path, board: str | None = None) -> dict[str, Any] | None:
    """The gates of one build, or None when the build has no security request. Reads only files Vivado or the flow wrote in the build directory."""
    d = Path(build_dir)
    rq = d / "security_request.json"
    if not rq.is_file():
        return None
    req = json.loads(rq.read_text())
    gates: dict[str, bool] = {}
    out: dict[str, Any] = {"source": req["source"], "request": req["request"], "switches": req["switches"], "policy_conflict": req["policy_conflict"],
                           "gates": gates, "findings": [], "evidence": {}}
    if req["policy_conflict"]:
        gates["security_policy_pin"] = False
        out["findings"] += [{"rule": "policy_conflict", "what": c} for c in req["policy_conflict"]]
    if not req["request"]["production_secure"]:
        return out
    sw = req["switches"]
    fam = family_of(req.get("part", ""))
    out["handed_to_owner"] = owner_items(sw, fam) if fam in FAMILY else {}
    prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").is_file() else {}
    top = prep.get("top") or next((p.stem for p in d.glob("*.bit")), "")
    ap, du = d / APPLY_FILE, d / DUMP_FILE
    ok, bad = parse_apply(ap.read_text()) if ap.is_file() else ([], ["security_apply.txt is missing"])
    gates["security_settings_applied"] = ap.is_file() and not bad and len(ok) >= len(req["properties"])
    if bad:
        out["findings"] += [{"rule": "apply", "what": b} for b in bad]
    if not du.is_file():
        out["findings"].append({"rule": "evidence", "what": "security_design.txt is missing: the build did not reach write_bitstream"})
        for k in SUBSWITCHES:
            if sw[k] and k not in out["handed_to_owner"]:
                gates[f"security_{k}"] = False
        gates["security_profile_met"] = False
        return out
    dump = parse_dump(du.read_text())
    out["evidence"]["properties"] = {k: v for k, v in dump["props"].items() if re.match(r"BITSTREAM\.(ENCRYPTION|AUTHENTICATION|READBACK\.SECURITY|GENERAL\.(JTAG|DISABLE_JTAG))", k)}
    pr = dump["props"]
    log = d / "vivado.log"
    wb = ""
    if log.is_file():
        txt = log.read_text(errors="replace")
        i = txt.find("Command: write_bitstream")
        wb = txt[i:] if i >= 0 else ""
    out["evidence"]["write_bitstream_log_lines"] = [ln.strip() for ln in wb.splitlines() if re.search(r"(?i)encrypt|authent|readback|security|jtag|key", ln)][:12]
    bit = d / f"{top}.bit"
    out["evidence"]["bit_bytes"] = bit.stat().st_size if bit.is_file() else 0
    out["evidence"]["key_file_present"] = (d / f"{top}.nky").is_file()          # existence only: the file is never read
    if sw["encrypt"] and "encrypt" not in out["handed_to_owner"]:
        gates["security_encrypt"] = (pr.get("BITSTREAM.ENCRYPTION.ENCRYPT") == "YES" and pr.get("BITSTREAM.ENCRYPTION.ENCRYPTKEYSELECT") in ("BBRAM", "EFUSE")
                                     and bit.is_file() and any(re.search(r"(?i)encrypt", ln) for ln in out["evidence"]["write_bitstream_log_lines"]))
    if sw["authenticate"] and "authenticate" not in out["handed_to_owner"]:
        gates["security_authenticate"] = pr.get("BITSTREAM.AUTHENTICATION.AUTHENTICATE") == "YES"
    if sw["readback_off"]:
        gates["security_readback_off"] = (str(pr.get("BITSTREAM.READBACK.SECURITY")).upper() in ("LEVEL1", "LEVEL2")
                                          and str(pr.get("BITSTREAM.GENERAL.JTAG_SYSMON")).upper() == "DISABLE"
                                          and str(pr.get("BITSTREAM.GENERAL.DISABLE_JTAG")).upper() == "YES")
    if sw["strip_debug"]:
        fl = debug_findings(dump, req["request"].get("waive", []), [p.name for p in d.glob("*.ltx")])
        gates["security_strip_debug"] = not fl
        out["findings"] += [{"rule": f["rule"], "what": f["what"]} for f in fl]
    if sw["sysmon_shutdown"]:
        b = board or prep.get("board")
        try:
            exp = sysmon_init(limits_of(b)) if b else None
        except SecurityError as e:
            exp, out["findings"] = None, out["findings"] + [{"rule": "sysmon_limits", "what": str(e)}]
        fl = sysmon_findings(dump, exp) if exp else ["no board operating_limits to compare the thresholds with"]
        gates["security_sysmon_shutdown"] = not fl
        out["findings"] += [{"rule": "sysmon_shutdown", "what": x} for x in fl]
    gates["security_profile_met"] = all(v for k, v in gates.items() if k != "security_profile_met")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sysmon-init")
    s.add_argument("board")
    s.add_argument("--write")
    for name in ("show", "check"):
        c = sub.add_parser(name)
        c.add_argument("build_dir")
    a = ap.parse_args(argv)
    if a.cmd == "sysmon-init":
        text = sysmon_header(a.board)
        if a.write:
            Path(a.write).write_text(text)
        else:
            sys.stdout.write(text)
        return 0
    r = evaluate(Path(a.build_dir))
    if r is None:
        print("no security request in this build")
        return 0
    print(json.dumps(r, indent=1, sort_keys=True))
    return 0 if a.cmd == "show" or all(r["gates"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
