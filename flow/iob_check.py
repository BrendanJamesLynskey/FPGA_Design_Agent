#!/usr/bin/env python3
"""The I/O-block register packing check of the flow gates (brief 129): is every register that is meant to sit in the I/O block
(first input flip-flop, last output flip-flop of a source-synchronous or system-synchronous interface) really there, and when not,
why?

    python3 flow/iob_check.py <build dir> [--interfaces spec.yaml build.yaml ...]

Reads ``iob_route.txt`` (flow/iob_paths.tcl: each port's buffer, the register next to it, where it was placed, the IOB property
on the port and on the register, what else the nets drive) and ``vivado.log`` (the placer's own message when it could not honour
``IOB = TRUE``: UG903 "Physical Constraints" and UG904 "Placement": a Critical Warning, not an error, so ``drc_clean`` and the
timing gates never see it). Packing is not free: a register only goes into the I/O block when nothing but the pad sits between it
and the pin; otherwise Vivado leaves it in the fabric and the interface timing then depends on
where the placer put it. A register marked ``IOB TRUE`` that is not packed fails, with the cell name and the reason: Vivado's
message when the log has one, else what the netlist shows (the buffer drives a gate, the register's output is also read inside
the design, the pin has no register next to it).

    IOB-NOT-PACKED   a register marked IOB TRUE (on the register or its port) or in an interface declared ``iob: true`` that is
                     not in the I/O block                                                                     (blocking)
    IOB-MARK-ORPHAN  a register marked IOB TRUE that no port reaches through its buffer alone: the mark can never be honoured
                     (blocking)
    IOB-UNMARKED     a register next to a pin of a synchronous interface that is neither marked nor in the I/O block: its
                     input or output timing depends on placement. Advice, not a failure, unless the interface says
                     ``iob: true`` (then it is IOB-NOT-PACKED)                                                   (advisory)

Raw findings only. ``evaluate`` is pure (text in, dict out); flow/gates.py and flow/checks call it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --- the dump ---------------------------------------------------------------------------------------------------------------

PORT_KEYS = ("port", "dir", "port_iob", "buf_ref", "buf", "loads", "reg", "reg_ref", "reg_iob", "bel", "site", "reg_fanout", "d_driver")


def parse_iob_dump(text: str) -> dict[str, Any]:
    if "# end" not in text:
        raise ValueError("iob_paths dump truncated (no '# end')")
    out: dict[str, Any] = {"part": "", "family": "", "ports": {}, "marked": [], "errors": []}
    for line in text.splitlines():
        f = line.split("|")
        if f[0] == "PART" and len(f) >= 3:
            out["part"], out["family"] = f[1], f[2]
        elif f[0] == "PORT" and len(f) >= 14:
            rec = dict(zip(PORT_KEYS, f[1:14]))
            out["ports"][rec["port"]] = rec
        elif f[0] == "MARKED" and len(f) >= 7:
            out["marked"].append(dict(zip(("cell", "ref", "iob", "bel", "site", "prim"), f[1:7])))
        elif f[0] == "ERROR":
            out["errors"].append(line)
    return out


def family_class(arch: str, part: str = "") -> str:
    """``7series``, ``ultrascale_plus`` or ``other`` from Vivado's ARCHITECTURE (or the part name when the dump has none)."""
    a = (arch or "").lower()
    p = (part or "").lower()
    if a in ("artix7", "kintex7", "virtex7", "zynq", "spartan7", "artix7l", "kintex7l") or re.match(r"xc(7[azk]|7s|7v|7z)", p):
        return "7series"
    if "plus" in a or a in ("zynquplus", "kintexuplus", "virtexuplus", "artixuplus", "spartanuplus") or re.match(r"xc(zu|ku\d+p|vu\d+p|au\d+p|k26)|xck26", p):
        return "ultrascale_plus"
    if a in ("kintexu", "virtexu"):
        return "ultrascale"
    return "other"


def is_packed(rec: dict[str, str]) -> bool:
    """The register sits in an ILOGIC/OLOGIC (7-series) or I/O-bank register site: its BEL names the I/O logic, not a slice."""
    return bool(rec["reg"]) and bool(re.match(r"(I|O)LOGIC|IOB|IDDR|ODDR|BITSLICE|RIU", rec["bel"] + " " + rec["site"].split("_")[0]))


# --- Vivado's own messages ----------------------------------------------------------------------------------------------------

_MSG = re.compile(r"^(CRITICAL WARNING|WARNING|ERROR|INFO):\s*\[([A-Za-z]+ \d+-\d+)\]\s*(.*)$")


def parse_log_messages(log: str) -> list[dict[str, Any]]:
    """Every message of the Vivado log that mentions the IOB property or packing: {severity, id, text, line}. A message may run
    over several lines; the continuation (lines that are not a new message) is joined to it."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for n, line in enumerate(log.splitlines(), 1):
        m = _MSG.match(line)
        if m:
            if cur:
                out.append(cur)
            cur = {"severity": m.group(1), "id": m.group(2), "text": m.group(3).strip(), "line": n}
        elif cur and line.strip() and not line.startswith(("Phase", "Time", "Starting", "Ending", "---", "Checksum", "Command", "#")):
            if re.match(r"^\s", line) or line[:1].islower():
                cur["text"] += " " + line.strip()
            else:
                out.append(cur)
                cur = None
        else:
            if cur:
                out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    def about_iob(m: dict[str, Any]) -> bool:
        text = re.sub(r"\[[^\]]*\]", " ", m["text"])         # a file path in brackets is not the message
        return bool(re.search(r"\bIOB\b", text))
    return [m for m in out if about_iob(m) and m["severity"] in ("CRITICAL WARNING", "WARNING", "ERROR")]


def _cell_in(text: str, cell: str) -> bool:
    return bool(cell) and re.search(r"(?<![\w/\[])" + re.escape(cell) + r"(?![\w\]])", text) is not None


def message_for(cell: str, port: str, msgs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for m in msgs:
        if _cell_in(m["text"], cell) or _cell_in(m["text"], port):
            return m
    return None


# --- the reason a register is not packed --------------------------------------------------------------------------------------

def netlist_reason(rec: dict[str, str]) -> str:
    """What the dump shows about why the register did not pack (the placer's message is preferred when the log has one)."""
    d = rec["dir"]
    if not rec["buf"]:
        return f"no I/O buffer found on port {rec['port']} (the pin is not driven by or driving a buffer cell)"
    loads = [x for x in rec["loads"].split(",") if x and x != "-"]
    if d == "in":
        if not rec["reg"]:
            kinds = ",".join(sorted(set(loads))) or "nothing"
            if len(loads) > 1:
                return (f"the input buffer {rec['buf_ref']} drives {len(loads)} loads ({kinds}), not one register: only a single "
                        f"register can take the pad's data in the I/O logic")
            return f"the input buffer {rec['buf_ref']} drives {kinds}, not a register: logic sits between the pad and the first register"
        if rec["bel"] == "" or not is_packed(rec):
            return (f"the register ({rec['reg_ref']}) is the buffer's only load but was placed in {rec['site'] or 'no site'} "
                    f"({rec['bel'] or 'no BEL'}); its control pins or type did not fit the I/O logic and the placer gave no message")
    else:
        drv = (rec["loads"].split("(")[0] or "").strip()
        if not rec["reg"]:
            return f"the output buffer {rec['buf_ref']} is driven by {drv or 'nothing'}, not a register: logic sits between the last register and the pad"
        try:
            others = int(rec["reg_fanout"] or 0)
        except ValueError:
            others = 0
        if others > 0:
            return (f"the output register ({rec['reg_ref']}) also drives {others} other load(s) inside the design: the I/O logic's output "
                    f"goes to the pad only")
        return (f"the register ({rec['reg_ref']}) drives only the pad but was placed in {rec['site'] or 'no site'} "
                f"({rec['bel'] or 'no BEL'}); its control pins or type did not fit and the placer gave no message")
    return "not packed; no reason found in the netlist"


# --- the check ----------------------------------------------------------------------------------------------------------------

def _match(pattern: str, name: str) -> bool:
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, name) is not None


def declared_ports(interfaces: list[dict[str, Any]], ports: list[str]) -> dict[str, dict[str, Any]]:
    """Port name -> the declared interface that lists it (patterns as get_ports)."""
    out: dict[str, dict[str, Any]] = {}
    for i in interfaces:
        for pat in i.get("ports") or []:
            for p in ports:
                if _match(str(pat), p):
                    out.setdefault(p, i)
    return out


def evaluate(dump_text: str, log_text: str = "", interfaces: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The verdict for one routed (or placed) design. ``interfaces`` are the design's ``io_interfaces`` entries (flow/io_check.py);
    ``kind`` asynchronous ones are skipped, ``iob: true`` makes every register of the interface required."""
    d = parse_iob_dump(dump_text)
    msgs = parse_log_messages(log_text)
    fam = family_class(d["family"], d["part"])
    decl = declared_ports(interfaces or [], list(d["ports"]))
    findings: list[dict[str, Any]] = []
    regs: list[dict[str, Any]] = []
    for name, rec in sorted(d["ports"].items()):
        iface = decl.get(name)
        marked = "TRUE" in (rec["port_iob"].upper(), rec["reg_iob"].upper()) and rec["reg_iob"].upper() != "FALSE"
        required_by_iface = bool(iface and iface.get("iob") is True)
        if not (marked or required_by_iface or (iface and iface.get("kind") != "asynchronous" and iface.get("iob") is not False)):
            continue
        packed = is_packed(rec)
        item = {"port": name, "dir": rec["dir"], "cell": rec["reg"] or None, "ref": rec["reg_ref"] or None, "bel": rec["bel"] or None,
                "site": rec["site"] or None, "marked": marked, "interface": iface.get("name") if iface else None, "packed": packed}
        regs.append(item)
        if packed:
            continue
        if marked or required_by_iface:
            m = message_for(rec["reg"], name, msgs)
            reason = ("Vivado: " + f"[{m['id']}] {m['text']}") if m else "netlist: " + netlist_reason(rec)
            why = ("marked IOB TRUE" if marked else "") + (" and " if marked and required_by_iface else "") + \
                  (f"in interface {iface['name']} (iob: true)" if required_by_iface else "")
            item["reason"] = reason
            findings.append({"code": "IOB-NOT-PACKED", "blocking": True, "port": name, "cell": rec["reg"] or None,
                             "where": rec["reg"] or name, "message":
                             (f"register {rec['reg']} of port {name}" if rec["reg"] else f"port {name} (no register next to its pad)")
                             + f" is {why} but is not in the I/O block: {reason}"})
        else:
            findings.append({"code": "IOB-UNMARKED", "blocking": False, "port": name, "cell": rec["reg"] or None,
                             "where": rec["reg"] or name, "message":
                             f"port {name} of {iface.get('kind')} interface {iface.get('name')} is not in the I/O block and not marked IOB: "
                             f"its {'setup/hold' if rec['dir'] == 'in' else 'clock-to-out'} depends on placement; "
                             f"{netlist_reason(rec)}; mark the register or the port IOB TRUE if the interface needs it"})
    for c in d["marked"]:
        m = message_for(c["cell"], "", msgs)
        findings.append({"code": "IOB-MARK-ORPHAN", "blocking": True, "port": None, "cell": c["cell"], "where": c["cell"],
                         "message": f"register {c['cell']} ({c['ref']}) is marked IOB TRUE but no port reaches it through its I/O buffer alone; "
                                    f"the mark cannot be honoured (placed in {c['site'] or 'no site'})"
                                    + (f"; Vivado: [{m['id']}] {m['text']}" if m else "")})
    out = {"pass": not any(f["blocking"] for f in findings), "part": d["part"], "family": d["family"], "family_class": fam,
           "registers": regs, "findings": findings, "log_messages": msgs, "dump_errors": d["errors"]}
    if d["errors"]:
        out["pass"] = False
    return out


def applies(dump_text: str, interfaces: list[dict[str, Any]] | None = None) -> bool:
    """Whether the design marks anything IOB TRUE or declares an interface ``iob: true`` (when neither, the gate is not added)."""
    d = parse_iob_dump(dump_text)
    if d["marked"] or any("TRUE" in (r["port_iob"].upper(), r["reg_iob"].upper()) for r in d["ports"].values()):
        return True
    return any(i.get("iob") is True for i in interfaces or [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--interfaces", type=Path, nargs="*", help="spec.yaml / build.yaml with io_interfaces")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import io_check
    ifs, _asy, _ = io_check.load_interfaces(*(a.interfaces or []))
    d = a.build_dir
    log = (d / "vivado.log").read_text(errors="replace") if (d / "vivado.log").is_file() else ""
    r = evaluate((d / "iob_route.txt").read_text(errors="replace"), log, ifs)
    print(json.dumps(r, indent=2))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
