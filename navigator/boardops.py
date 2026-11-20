"""Locked, read-only board actions: list the JTAG targets, read the loaded design's identity, read the die sensors, read the link status.

What one action does, in order, and why it is safe:

1. It looks the board up in ``~/.config/fpga_design_agent/boards.yaml`` and refuses a board, serial or device that is not there or not shaped like one.
2. It takes ``_handoff/board.lock`` (exclusive create, text starting ``103S2:``); if the lock is held it refuses and says by whom. It then takes a heavy slot
   through ``_handoff/take_heavy_slot.sh``, because it starts ``hw_server`` and Vivado's hardware manager. If either is refused nothing starts.
3. It builds a Tcl script from the fixed templates below, and ``check_tcl`` refuses any script that uses a hardware command outside the read-only list,
   a ``set_property``, anything that programs, writes, boots, erases or sources another file, or a register scan whose command word is not a read of a
   whitelisted read-only register. The same check runs in the tests on every action and board.
4. It runs the script through the transport (real: ``hw_server`` and ``vivado -mode batch`` in their own process group, memory-capped; tests: a fake), parses
   the tagged lines and judges the sensor readings against the recommended operating conditions.
5. It releases the heavy slot, then the board lock, on every path (success, refusal, error, timeout); a lock whose text is not exactly the one written is left alone.

Never: program a device (SRAM or anything else), write a register (the scan's write bit is always 0), set a hardware property (so not even the cable
clock), touch the laser, the flash, the eFUSE or BBRAM. The register reads go through the design's USER4 bus the way ``b58a_rd`` does, with its own read-only
copy of the scan procedure, so the write procedures of ``jtag_regs.tcl`` are not even loaded.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from navigator import guards, redact

SEG = re.compile(r"[A-Za-z0-9_.-]{1,60}")
UID = re.compile(r"[A-Za-z]{2,20}/[A-Za-z0-9]{4,40}")
DEVICE = re.compile(r"[A-Za-z0-9_]{2,30}")
READ_BIT, WRITE_BIT = 45, 44
MARKER = 0x58A0
#: the registers a read may address (all read-only in designs/b96_kr260_10g/regmap.py: ID, BUILD, FEATURES, GT_STAT; reads have no side effects)
READ_REGS = {"ID": 0x000, "BUILD": 0x004, "FEATURES": 0x008, "GT_STAT": 0x014}
#: the Vivado hardware-manager commands a generated script may use; every one reads or opens/closes a connection
ALLOWED_HW = frozenset({"open_hw_manager", "connect_hw_server", "get_hw_targets", "open_hw_target", "close_hw_target", "get_hw_devices", "current_hw_target", "current_hw_device",
                        "get_hw_sysmons", "refresh_hw_sysmon", "disconnect_hw_server", "close_hw_manager", "scan_ir_hw_jtag", "scan_dr_hw_jtag"})
FORBIDDEN_TCL = re.compile(r"b58a_|b96_|jtag_regs|set_property|program|write|cfgmem|flash|efuse|bbram|laser|erase|boot|commit|run_hw|source|exec|eval|uplevel|\bfile\b|\bopen\b|\bcd\b|rename|\bsocket\b|\bputs\s+\[exec", re.I)
ACTIONS = {
    "jtag_targets": ("targets",),
    "design_id": ("id",),
    "sysmon": ("sysmon",),
    "link_status": ("link",),
    "all": ("targets", "sysmon", "id", "link"),
}
ACTION_TITLE = {"jtag_targets": "List JTAG targets", "design_id": "Read build ID and FEATURES", "sysmon": "Read SYSMON (temperature, supplies)", "link_status": "Read link status", "all": "All four reads in one session"}
#: Recommended operating conditions per profile (min, max; None = no bound): DS925 v1.30 table 2 for the KR260's xck26 -2LV (the same numbers as b96c_ppm.ROC, which a test compares); Tj at most the house rule's 85 C
KR260_ROC = {"TEMPERATURE": (0.0, 85.0), "VCCINT": (0.698, 0.742), "VCCAUX": (1.746, 1.854), "VCCBRAM": (0.825, 0.876)}
#: Artix-7 -1 (the Nexys A7): AMD DS181 table 2; the same numbers as flow/program.py's ROC, which a test compares (the navigator does not import the programming module)
ARTIX7_ROC = {"TEMPERATURE": (None, 85.0), "VCCINT": (0.95, 1.05), "VCCAUX": (1.71, 1.89), "VCCBRAM": (0.95, 1.05)}
PROFILES: dict[str, dict[str, Any]] = {
    "kr260": {"design": "b96_kr260_10g (brief 96)", "id": 0x96A00001, "device_prefix": "xck26", "roc": KR260_ROC,
              "roc_source": "AMD DS925 v1.30 table 2, Zynq UltraScale+ xck26 -2LV (as used by designs/b96_kr260_10g/host/b96c_ppm.py); Tj limit 85 C is the house rule"},
}
FEATURE_BITS = {0: "ALWAYS_1", 1: "NEAR_END", 2: "TRADE", 3: "RATE_MATCH", 4: "EYESCAN", 5: "RM_OWN", 6: "GT_BYPASS"}       # named in regmap.py's FEATURES row (a test checks)
GT_STAT_BITS = {"tx_done": 0, "rx_done": 1, "pgood": 2, "cdr_lock": 3, "txpma": 4, "rxpma": 5, "cdr_stable": 8, "pcs_lock": 9, "mod_abs": 10, "rx_los": 11, "tx_fault": 12}
CAVEAT = "The SYSMON samples at about 1 MSPS across channels, so this single reading cannot see a fast supply droop; it is one sample, not a soak."


class Transport(Protocol):
    def run_tcl(self, tcl: str, name: str) -> str: ...


class BoardRefused(Exception):
    pass


# --- the Tcl templates ----------------------------------------------------------------------------------------------------------

def read_cmd(reg: str) -> str:
    """The 64-bit scan word of a read of one whitelisted register: read bit set, write bit clear, address in bits 43:32, data 0 (as ``b58a_cmd 0 1 addr 0``)."""
    addr = READ_REGS[reg]
    v = (1 << READ_BIT) | (addr << 32)
    assert not (v >> WRITE_BIT) & 1
    return f"{v:016x}"


def tcl_header() -> str:
    return "set_param general.maxThreads 1\n"


def tcl_targets() -> str:
    return """
if {[catch {
    open_hw_manager
    connect_hw_server -url localhost:3121
    foreach t [get_hw_targets -quiet] {
        puts "FDA-TARGET [get_property UID $t] $t"
        if {[catch {open_hw_target $t} msg]} {
            puts "FDA-TARGET-ERROR [get_property UID $t] $msg"
            continue
        }
        foreach d [get_hw_devices -quiet] {
            puts "FDA-DEVICE [get_property UID $t] $d [get_property PART $d] [get_property IDCODE_HEX $d]"
        }
        close_hw_target $t
    }
    puts "FDA-LIST-DONE"
    disconnect_hw_server
} msg]} { puts "FDA-ERR targets $msg" }
"""


def tcl_sysmon(uid: str, device: str) -> str:
    return f"""
if {{[catch {{
    open_hw_manager
    connect_hw_server -url localhost:3121
    set targets [get_hw_targets -quiet "*/{uid}"]
    if {{[llength $targets] != 1}} {{ error "expected exactly one target with the board's cable, found [llength $targets]" }}
    open_hw_target [lindex $targets 0]
    set dev [get_hw_devices -quiet {device}]
    if {{$dev eq ""}} {{ error "no device {device} on the chain" }}
    current_hw_device $dev
    foreach sm [get_hw_sysmons -quiet -of_objects $dev] {{
        refresh_hw_sysmon $sm
        puts "FDA-SYSMON $sm TEMPERATURE=[get_property TEMPERATURE $sm] VCCINT=[get_property VCCINT $sm] VCCAUX=[get_property VCCAUX $sm] VCCBRAM=[get_property VCCBRAM $sm]"
    }}
    close_hw_target
    disconnect_hw_server
}} msg]}} {{ puts "FDA-ERR sysmon $msg" }}
"""


def tcl_regs(uid: str, regs: list[str]) -> str:
    """Register reads over the design's USER4 bus. The read-only half of ``jtag_regs.tcl``: open, scan, read; the write procedure is not here."""
    reads = "\n".join(f'    puts "FDA-REG {r} [fda_read {read_cmd(r)}]"' for r in regs)
    return f"""
proc fda_scan {{bits64}} {{
    scan_ir_hw_jtag $::fda_ir -tdi $::fda_user4
    if {{$::fda_pad}} {{
        set w [scan $bits64 %llx]
        set r [scan_dr_hw_jtag 65 -tdi [format %017llx [expr {{$w << 1}}]]]
        set v [scan $r %llx]
        return [format %016llx [expr {{($v >> 1) & 0xFFFFFFFFFFFFFFFF}}]]
    }}
    return [scan_dr_hw_jtag 64 -tdi $bits64]
}}
proc fda_read {{cmd}} {{
    fda_scan $cmd
    fda_scan 0000000000000000
    set r [fda_scan 0000000000000000]
    set v [expr 0x$r]
    if {{(($v >> 48) & 0xFFFF) != 0x{MARKER:X}}} {{ error "no 0x{MARKER:X} marker in the captured data ($r): the loaded design has no such register bus" }}
    return [format %08x [expr {{$v & 0xFFFFFFFF}}]]
}}
if {{[catch {{
    open_hw_manager
    connect_hw_server -url localhost:3121 -allow_non_jtag
    set targets [get_hw_targets -quiet "*/{uid}"]
    if {{[llength $targets] != 1}} {{ error "expected exactly one target with the board's cable, found [llength $targets]" }}
    current_hw_target [lindex $targets 0]
    open_hw_target -jtag_mode on
    set dev [lindex [get_hw_devices -filter {{PART =~ xck26*}}] 0]
    if {{$dev eq ""}} {{ error "no xck26 device on the chain" }}
    if {{[llength [get_hw_devices]] != 2 || [llength [get_hw_devices -filter {{PART == arm_dap}}]] != 1}} {{ error "the chain is not the K26's two-device chain (PL and ARM DAP)" }}
    set ::fda_ir 16
    set ::fda_user4 923f
    set ::fda_pad 1
{reads}
    close_hw_target
    disconnect_hw_server
}} msg]}} {{ puts "FDA-ERR regs $msg" }}
"""


def build_tcl(action: str, uid: str, device: str, profile: dict[str, Any] | None) -> str:
    secs = ACTIONS[action]
    out = [tcl_header()]
    if "targets" in secs:
        out.append(tcl_targets())
    if "sysmon" in secs:
        out.append(tcl_sysmon(uid, device))
    regs: list[str] = []
    if "id" in secs:
        regs += ["ID", "BUILD", "FEATURES"]
    if "link" in secs:
        regs += ["GT_STAT"]
    if regs:
        if profile is None:
            raise BoardRefused("this board has no register profile: the navigator reads only the design it knows (the KR260's)")
        out.append(tcl_regs(uid, list(dict.fromkeys(regs))))
    tcl = "".join(out)
    check_tcl(tcl)
    return tcl


def check_tcl(tcl: str) -> None:
    """Refuse a script that could do more than read. Raises BoardRefused; run on every script before it is executed."""
    for m in re.finditer(r"\b[a-z_]*hw[a-z_]*\b", tcl):
        w = m.group(0)
        if w not in ALLOWED_HW and not w.startswith("fda_") and w != "general":
            raise BoardRefused(f"the generated script uses {w}, which is not on the read-only list")
    # drop the allowed commands and the fixed text lines, then look for anything that programs, writes, boots, erases or reads another file
    body = re.sub(r"set_param general\.maxThreads 1", "", tcl)
    body = re.sub(r"\b(?:" + "|".join(sorted(ALLOWED_HW)) + r")\b", "", body)
    for m in FORBIDDEN_TCL.finditer(body):
        raise BoardRefused(f"the generated script contains {m.group(0)!r}: a board action never programs, writes, sets a hardware property or sources a file")
    for m in re.finditer(r"\bproc\s+(\w+)", tcl):
        if m.group(1) not in ("fda_scan", "fda_read"):
            raise BoardRefused(f"the generated script defines {m.group(1)}: only the two read-only scan procedures are allowed")
    for line in tcl.splitlines():
        if "set_param" in line and line.strip() != "set_param general.maxThreads 1":
            raise BoardRefused("the only parameter a script may set is general.maxThreads 1")
    # the scan procedures are pinned, not pattern-matched: exactly these call sites and no others
    if len(re.findall(r"scan_dr_hw_jtag", tcl)) != (2 if "proc fda_scan" in tcl else 0) or len(re.findall(r"scan_ir_hw_jtag", tcl)) != (1 if "proc fda_scan" in tcl else 0):
        raise BoardRefused("the generated script scans the JTAG chain outside the one read-only procedure")
    if "proc fda_scan" in tcl:
        for form in (r"scan_dr_hw_jtag 65 -tdi \[format %017llx \[expr \{\$w << 1\}\]\]", r"scan_dr_hw_jtag 64 -tdi \$bits64", r"scan_ir_hw_jtag \$::fda_ir -tdi \$::fda_user4"):
            if len(re.findall(form, tcl)) != 1:
                raise BoardRefused("a scan call differs from the read-only template")
    for m in re.finditer(r"(?<!proc )\bfda_scan\s+([^\s\]]+)", tcl):
        if m.group(1) not in ("$cmd", "0000000000000000"):
            raise BoardRefused(f"fda_scan is called with {m.group(1)!r}: only the command word of a read and zero fillers are allowed")
    for m in re.finditer(r"(?<!proc )\bfda_read\s+([^\s\]]+)", tcl):
        if m.group(1) == "{cmd}":
            continue
        if not re.fullmatch(r"[0-9a-f]{16}", m.group(1)) or m.group(1) not in {read_cmd(r) for r in READ_REGS}:
            raise BoardRefused(f"fda_read is called with {m.group(1)!r}: only the four whitelisted read words are allowed")
    if re.search(r"(^|;|\[)\s*\$", tcl, re.M) or re.search(r"\b(append|subst|interp|namespace|upvar|trace|after|vwait|lappend)\b", tcl):
        raise BoardRefused("the generated script runs a command through a variable or uses an indirection command")
    for m in re.finditer(r"fda_read ([0-9a-f]{16})\b", tcl):
        v = int(m.group(1), 16)
        addr = (v >> 32) & 0xFFF
        if not (v >> READ_BIT) & 1 or (v >> WRITE_BIT) & 1 or (v & 0xFFFFFFFF) or v >> 46 or addr not in READ_REGS.values():
            raise BoardRefused(f"scan word {m.group(1)} is not a read of a whitelisted read-only register")


# --- parsing and judging --------------------------------------------------------------------------------------------------------

def parse(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"targets": [], "devices": [], "sysmon": [], "regs": {}, "errors": [], "list_done": False}
    for ln in text.splitlines():
        f = ln.strip().split()
        if not f:
            continue
        if f[0] == "FDA-TARGET" and len(f) >= 2:
            out["targets"].append({"uid": f[1], "error": None})
        elif f[0] == "FDA-TARGET-ERROR" and len(f) >= 2:
            for t in out["targets"]:
                if t["uid"] == f[1]:
                    t["error"] = mask(redact.brief(" ".join(f[2:]), 100))
        elif f[0] == "FDA-DEVICE" and len(f) >= 5:
            out["devices"].append({"uid": f[1], "device": f[2], "part": f[3], "idcode": f[4]})
        elif f[0] == "FDA-LIST-DONE":
            out["list_done"] = True
        elif f[0] == "FDA-SYSMON" and len(f) >= 3:
            kv = dict(re.findall(r"(\w+)=([-\d.eE+]+)", ln))
            if kv:
                out["sysmon"].append({k: float(v) for k, v in kv.items()})
        elif f[0] == "FDA-REG" and len(f) == 3 and re.fullmatch(r"[0-9a-fA-F]{8}", f[2]):
            out["regs"][f[1]] = int(f[2], 16)
        elif f[0] == "FDA-ERR" and len(f) >= 2:
            out["errors"].append({"section": f[1][:20], "what": mask(redact.brief(" ".join(f[2:]), 200))})
    return out


def judge_sysmon(readings: list[dict[str, float]], roc: dict[str, tuple[float | None, float | None]]) -> dict[str, Any]:
    r = next((x for x in readings if all(k in x for k in ("TEMPERATURE", "VCCINT", "VCCAUX", "VCCBRAM"))), None)
    if r is None:
        return {"verdict": "not read", "channels": []}
    if not roc:
        return {"verdict": "not judged", "channels": [{"name": k, "value": r[k], "min": None, "max": None, "inside": True} for k in ("TEMPERATURE", "VCCINT", "VCCAUX", "VCCBRAM")]}
    ch = []
    for k, (lo, hi) in roc.items():
        v = r[k]
        ch.append({"name": k, "value": v, "min": lo, "max": hi, "inside": (lo is None or v >= lo) and (hi is None or v <= hi)})
    return {"verdict": "inside ROC" if all(c["inside"] for c in ch) else "outside ROC", "channels": ch}


def decode_id(regs: dict[str, int], profile: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "ID" in regs:
        out["id"] = f"0x{regs['ID']:08X}"
        known = profile is not None and regs["ID"] == profile["id"]
        out["design"] = profile["design"] if known else "a design with the same register bus but another ID"
    if "BUILD" in regs:
        out["build_stamp"] = f"0x{regs['BUILD']:08X}"
    if "FEATURES" in regs:
        v = regs["FEATURES"]
        out["features"] = f"0x{v:08X}"
        out["features_set"] = [n for b, n in FEATURE_BITS.items() if (v >> b) & 1]
        out["features_clear"] = [n for b, n in FEATURE_BITS.items() if not (v >> b) & 1]
    return out


def decode_link(regs: dict[str, int]) -> dict[str, Any]:
    if "GT_STAT" not in regs:
        return {}
    v = regs["GT_STAT"]
    bits = {k: (v >> b) & 1 for k, b in GT_STAT_BITS.items()}
    return {"gt_stat": f"0x{v:08X}", "bits": bits, "link_up": bool(bits["tx_done"] and bits["rx_done"] and bits["pcs_lock"]),
            "note": "link_up = TX_DONE and RX_DONE and PCS BLOCK_LOCK (as the bench's link_ok); MOD_ABS 1 means no module only if the SFF polarity holds"}


# --- the real transport ---------------------------------------------------------------------------------------------------------

class VivadoTransport:
    """hw_server and ``vivado -mode batch`` through flow.hw's guarded starters, each in its own session so a timeout can stop the whole group."""

    def __init__(self, workdir: Path, timeout_s: float = 240):
        self.workdir, self.timeout_s = Path(workdir), timeout_s

    def run_tcl(self, tcl: str, name: str) -> str:
        from flow import hw
        self.workdir.mkdir(parents=True, exist_ok=True)
        script = self.workdir / f"{name}.tcl"
        script.write_text(tcl)
        try:
            hw.preflight()
            with hw.HwServer(self.workdir):
                p = subprocess.Popen(hw.vivado_cmd(script, [], self.workdir / f"{name}.log"), cwd=self.workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
                try:
                    out, _ = p.communicate(timeout=self.timeout_s)
                except BaseException as e:                 # a timeout, an interrupt, anything: the group is stopped before the locks are released
                    gone = False
                    for sig in (signal.SIGTERM, signal.SIGKILL):
                        try:
                            os.killpg(p.pid, sig)
                        except ProcessLookupError:
                            gone = True
                            break
                        try:
                            p.communicate(timeout=10)
                        except subprocess.TimeoutExpired:
                            continue
                        except BaseException:
                            pass
                        try:
                            os.killpg(p.pid, 0)
                        except ProcessLookupError:
                            gone = True
                            break
                    if not gone:
                        raise BoardRefused("Vivado could not be stopped: check for a vivado or hw_server process before the next action (the locks are still released)")
                    if isinstance(e, subprocess.TimeoutExpired):
                        raise BoardRefused(f"Vivado did not finish within {self.timeout_s:.0f} s and its process group was stopped")
                    raise
        except hw.HwError as e:
            raise BoardRefused(redact.brief(str(e), 200))
        return out


# --- the actions ----------------------------------------------------------------------------------------------------------------

def _last4(s: str | None) -> str | None:
    return "..." + str(s)[-4:] if s else None


_SERIAL = re.compile(r"((?:Xilinx|Digilent|Altera|Intel|Ftdi|FTDI)/)([A-Za-z0-9]{5,})")


def mask(text: str) -> str:
    """Cable serials in any text Vivado produced are cut to their last 4 characters (a target name carries the whole serial)."""
    return _SERIAL.sub(lambda m: m.group(1) + "..." + m.group(2)[-4:], text)


class BoardOps:
    def __init__(self, handoff: Path, runner: Any, config_dir: Path, transport: Transport, hours: float = 0.25):
        self.handoff, self.runner, self.config_dir, self._transport, self.hours = Path(handoff), runner, Path(config_dir), transport, hours
        self.last: dict[str, dict[str, Any]] = {}
        self._busy = threading.Lock()

    def _boards(self) -> dict[str, dict[str, Any]]:
        try:
            d = yaml.safe_load((self.config_dir / "boards.yaml").read_text()) or {}
        except (OSError, yaml.YAMLError):
            return {}
        b = d.get("boards") if isinstance(d, dict) else None
        return {k: v for k, v in (b or {}).items() if isinstance(k, str) and SEG.fullmatch(k) and isinstance(v, dict)}

    def profile_for(self, name: str, entry: dict[str, Any]) -> dict[str, Any] | None:
        pr = PROFILES.get(name)
        return pr if pr and str(entry.get("part", "")).startswith(pr["device_prefix"]) else None

    def listing(self) -> dict[str, Any]:
        lock = self.handoff / "board.lock"
        try:
            held = lock.read_text().strip()[:240] if lock.is_file() else None
        except OSError:
            held = None
        rows = []
        for name, b in self._boards().items():
            pr = self.profile_for(name, b)
            ok = isinstance(b.get("jtag_uid"), str) and bool(UID.fullmatch(b["jtag_uid"])) and isinstance(b.get("device"), str) and bool(DEVICE.fullmatch(b["device"]))
            acts = [a for a in ACTIONS if ok and (pr is not None or a in ("jtag_targets", "sysmon"))]
            rows.append({"board": name, "part": b.get("part"), "device": b.get("device"), "power": b.get("power_source"), "cable": _last4(str(b.get("cable_serial") or "")),
                         "profile": pr["design"] if pr else None, "actions": acts, "note": None if ok else "boards.yaml has no usable jtag_uid and device for this board",
                         "last": self.last.get(name)})
        return {"boards": rows, "titles": ACTION_TITLE, "lock": {"held": held is not None, "held_by": held},
                "rules": ["each action takes board.lock and a heavy slot, and releases both when it ends", "read-only: it never programs, writes a register, sets a hardware property, or touches the laser, the flash or the eFUSE",
                          "the owner's hardware rules are unchanged: this page does not start a soak or a run, it reads state"],
                "never": "program, write, laser, flash, eFUSE, BBRAM"}

    def run(self, board: str, action: str) -> dict[str, Any]:
        """One board action at a time in this process (a second request while one runs is refused without touching any lock); across sessions board.lock decides."""
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "refused": "a board action is already running from this navigator", "board": None}
        try:
            return self._run(board, action)
        finally:
            self._busy.release()

    def _run(self, board: str, action: str) -> dict[str, Any]:
        t0 = time.time()
        if not isinstance(board, str) or not isinstance(action, str) or action not in ACTIONS:
            return {"ok": False, "refused": "unknown board action", "board": None}
        entry = self._boards().get(board)
        if entry is None:
            return {"ok": False, "refused": "no such board in boards.yaml", "board": None}
        uid, dev = entry.get("jtag_uid"), entry.get("device")
        if not (isinstance(uid, str) and UID.fullmatch(uid) and isinstance(dev, str) and DEVICE.fullmatch(dev)):
            return {"ok": False, "refused": "boards.yaml has no usable jtag_uid and device for this board", "board": board}
        prof = self.profile_for(board, entry)
        try:
            tcl = build_tcl(action, uid, dev, prof)                     # also the safety check: before any lock is taken, so a refused script costs nothing
        except BoardRefused as e:
            return {"ok": False, "refused": str(e), "board": board, "action": action}
        bl = guards.OwnedLock(self.handoff / "board.lock", guards.lock_text(f"navigator read-only {action} on {board}", self.hours))
        slot = guards.HeavySlot(self.handoff, self.runner, guards.lock_text(f"navigator board read {action} {board} (hw_server and the Vivado hardware manager, not a build)", self.hours))
        res: dict[str, Any] = {"ok": False, "board": board, "action": action, "title": ACTION_TITLE[action], "locks": {"board_lock": bl.text, "slot_job": slot.text}}
        stdout = ""
        try:
            try:
                bl.take()
            except guards.LockBusy as e:
                return {**res, "refused": f"the board lock is held, so nothing was started ({e})", "locks": {**res["locks"], "board_lock_taken": False}}
            try:
                slot.take()
            except guards.LockBusy as e:
                return {**res, "refused": f"no heavy slot: {e}", "locks": {**res["locks"], "board_lock_taken": True, "slot_taken": False}}
            res["locks"].update(board_lock_taken=True, slot_taken=True)
            try:
                stdout = self._transport.run_tcl(tcl, f"{board}_{action}_{time.strftime('%Y%m%d_%H%M%S')}")
            except BoardRefused as e:
                res["error"] = mask(str(e))
            except Exception as e:                                         # the real transport raising anything: reported, locks still released below
                res["error"] = mask(redact.brief(f"{type(e).__name__}: {e}", 200))
        finally:
            released = guards.release_all(bl, slot)                         # reverse order: the slot, then the board lock
            res.setdefault("locks", {})["released"] = {"slot": released[0], "board_lock": released[1]}
        data = parse(stdout)
        res["seconds"] = round(time.time() - t0, 1)
        if data["errors"]:
            res["section_errors"] = data["errors"]
        secs = ACTIONS[action]
        if "targets" in secs:
            res["targets"] = [{"uid": t["uid"].split("/", 1)[0] + "/..." + t["uid"][-4:], "mine": t["uid"].endswith(uid.split("/", 1)[1]) if "/" in uid else False, "error": t["error"],
                               "devices": [{"device": d["device"], "part": d["part"], "idcode": d["idcode"]} for d in data["devices"] if d["uid"] == t["uid"]]} for t in data["targets"]]
            res["targets_complete"] = data["list_done"]
        if "sysmon" in secs:
            roc, src = (prof["roc"], prof["roc_source"]) if prof else self._roc(entry)
            res["sysmon"] = {**judge_sysmon(data["sysmon"], roc), "roc_source": src, "caveat": CAVEAT}
        if "id" in secs:
            res["design"] = decode_id(data["regs"], prof)
        if "link" in secs:
            res["link"] = decode_link(data["regs"])
        need = []
        if "targets" in secs:
            need.append(data["list_done"])
        if "sysmon" in secs:
            need.append(res["sysmon"]["verdict"] != "not read")
        if "id" in secs:
            need.append(all(k in data["regs"] for k in ("ID", "BUILD", "FEATURES")))
        if "link" in secs:
            need.append("GT_STAT" in data["regs"])
        res["ok"] = "error" not in res and not data["errors"] and all(need)                  # the action's own evidence, not just some output
        res["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last[board] = {k: res[k] for k in ("action", "ok", "checked_at") if k in res}
        return res

    @staticmethod
    def _roc(entry: dict[str, Any]) -> tuple[dict[str, tuple[float | None, float | None]], str]:
        if str(entry.get("part") or "").lower().startswith("xc7a"):
            return ARTIX7_ROC, "AMD DS181 table 2 (Artix-7 -1); Tj limit 85 C is the Nexys A7's house rule"
        return {}, "no recommended operating conditions are recorded for this part in the navigator: readings are shown, not judged"
