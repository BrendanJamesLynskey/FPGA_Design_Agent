"""Instrument drivers behind one contract (brief 50, "One interface for every instrument"); 50A has two of them.

Contract: ``describe()`` (channels, kinds, limits, safety limits), ``configure(plan)``, ``arm()``, ``capture()`` -> an
``fda-capture/1`` dict (debug_core/capture.py), ``close()``. Brief 52 moves the bench drivers (hil/instruments) onto it;
brief 50B adds our own capture core as a second logic-analyser driver behind the same front end.

- :class:`VendorIla`: the ILA IP of a debug build (brief 48) on the attached board, through hw_server and
  ``flow/ila_capture.tcl``; register set-up and stimulus over the UART shell; the XADC operating conditions through JTAG
  when armed and after upload. The caller holds ``board.lock``.
- :class:`MockIla`: the same output from recorded samples or a function, so the front end, tools and tests run without
  hardware (CI).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from debug_core.capture import make_capture
from debug_core.rtl_index import ROOT

BOARD_LIMITS = {"nexys_a7_100t": {"power_w_max": 2.0, "tj_c_max": 85.0, "program": "SRAM only (never flash)",
                                  "source": "house rules (wall power, 2026-10-31)"}}


class Instrument(ABC):
    kind = "instrument"

    @abstractmethod
    def describe(self) -> dict[str, Any]: ...

    @abstractmethod
    def configure(self, plan: dict[str, Any]) -> None: ...

    @abstractmethod
    def arm(self) -> None: ...

    @abstractmethod
    def capture(self) -> dict[str, Any]: ...

    def close(self) -> None:
        pass


def ila_limits() -> dict[str, Any]:
    from debug_core import plan as P
    return {"ila_instances": 1, "ports_max": P.ILA_MAX_PORTS, "clock_domains": 1, "depths": list(P.DEPTHS),
            "measured_port_bits": P.MEASURED_PORT_BITS, "measured_depth": P.MEASURED_DEPTH,
            "compare_chars": "0 1 X R F B (per bit)", "combine": ["AND", "OR (1-bit terms only)"],
            "source": "measured on Vivado 2026.1, Basic licence tier"}


class MockIla(Instrument):
    """A stand-in that produces the same capture format. ``source`` is ``{label: samples}`` (a whole window) or a
    function ``plan -> ({label: samples}, trigger_sample)``."""
    kind = "mock_ila"

    def __init__(self, source: dict[str, list[int]] | Callable[[dict[str, Any]], tuple[dict[str, list[int]], int]],
                 trigger_sample: int | None = None) -> None:
        self.source, self.t0, self.plan = source, trigger_sample, None

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "channels": "the plan's probes", "limits": ila_limits(), "safety": {}, "mock": True}

    def configure(self, plan: dict[str, Any]) -> None:
        self.plan = plan

    def arm(self) -> None:
        if self.plan is None:
            raise RuntimeError("configure first")

    def capture(self) -> dict[str, Any]:
        if callable(self.source):
            samples, t0 = self.source(self.plan)
        else:
            samples, t0 = self.source, self.t0 if self.t0 is not None else self.plan["window"]["position"]
        return make_capture(plan=self.plan, samples=samples, trigger_sample=t0,
                            instrument={"kind": self.kind, "driver": "debug_core.instruments.MockIla", "mock": True,
                                        "settings": {"position": self.plan["window"]["position"],
                                                     "depth": self.plan["window"]["depth"]}})


def conditions(cap_dir: Path, name: str) -> dict[str, Any]:
    """The XADC readings ila_capture.tcl wrote when armed and after upload, judged against ROC (flow/program.py)."""
    from flow.program import parse_conditions
    out: dict[str, Any] = {}
    outside: list[str] = []
    for when in ("armed", "done"):
        f = cap_dir / f"{name}.cond_{when}.txt"
        if f.is_file():
            c = parse_conditions(f.read_text())
            out[when] = c
            outside += [f"{when} {x}" for x in c.get("outside", [])]
            flags = c.get("flags")
            if flags:
                c["alarm_bits"] = alarm_bits(flags)
    if out:
        read = all(c.get("read") for c in out.values())
        alarms = sorted({a for c in out.values() for a in c.get("alarm_bits", [])})
        out["alarms"] = alarms
        out["verdict"] = ("inside ROC" if read and not outside and not alarms else
                          "outside ROC" if outside or alarms else "not read")
        out["outside"] = outside
        out["limits"] = next(iter(c.get("limits") for c in out.values() if isinstance(c, dict) and c.get("limits")), None)
    return out


def alarm_bits(flags: str) -> list[str]:
    """XADC flag register 0x3F (UG480): bit 0 ALM0 (temperature), 1 ALM1 (VCCINT), 2 ALM2 (VCCAUX), 3 OT, 8 ALM3 (VCCBRAM).
    The alarm thresholds are the XADC's defaults unless the design sets them; brief 50A reads, never writes, them."""
    try:
        v = int(flags, 16)
    except ValueError:
        return []
    names = {0: "ALM0 temperature", 1: "ALM1 VCCINT", 2: "ALM2 VCCAUX", 3: "OT over-temperature", 8: "ALM3 VCCBRAM"}
    return [n for b, n in names.items() if v >> b & 1]


def samples_from_files(plan: dict[str, Any], csv: Path, probe_map: Path, hw_probes: Path,
                       labels: dict[str, str] | None = None) -> tuple[dict[str, list[int]], int, str]:
    """The ILA's CSV export -> ({plan label: samples}, trigger sample, where the trigger sample came from), through the
    build's probe_map.txt and the session's hw_probes.txt (flow/ila.py puts split and packed probes back together)."""
    from flow import ila
    labels = labels or {}
    raw = ila.load_capture(csv, probe_map, hw_probes)
    trig = raw.get("TRIGGER") or []
    t_idx = trig.index(1) if 1 in trig else int(plan["window"]["position"])
    samples = {p["label"]: raw[labels.get(p["label"], p["label"])] for p in plan["probes"]}
    return samples, t_idx, "TRIGGER column" if 1 in trig else "trigger position"


def plan_tcl(plan: dict[str, Any], slices: dict[str, tuple[int, int, int]], depth: int, labels: dict[str, str] | None = None,
             name: str = "cap") -> str:
    """The plan.tcl flow/ila_capture.tcl reads: one capture whose compares are [port 0 offset width pattern] per trigger
    probe (``slices``: build probe name -> (port, offset, width) from probe_map.txt)."""
    labels = labels or {}
    comps = []
    used_bits: set[tuple[int, int]] = set()
    used_ports: set[int] = set()
    for c in plan["trigger"]["conditions"]:
        bl = labels.get(c["probe"], c["probe"])
        if bl not in slices:
            raise ValueError(f"the build has no probe {bl} (has {sorted(slices)})")
        port, off, w = slices[bl]
        bits = {(port, off + i) for i in range(w)}
        if bits & used_bits:
            # ila_capture.tcl would keep only the last compare on these bits: the armed trigger would not be the plan's
            raise ValueError(f"two trigger compares on the same bits of port {port} ({bl}); refused")
        if plan["trigger"]["combine"] == "OR" and port in used_ports:
            # measured on the Basic tier: one comparator per port, OR compares cannot share it (Labtools 27-3239/27-3241)
            raise ValueError(f"two OR compares on port {port}; this build cannot arm them (one comparator per port)")
        used_bits |= bits
        used_ports.add(port)
        if len(c["pattern"]) != w or not set(c["pattern"]) <= set("01XRFB"):
            raise ValueError(f"trigger pattern {c['pattern']!r} for {bl} does not fit the {w}-bit probe")
        comps.append(f"[list {port} 0 {off} {w} {c['pattern']}]")
    pos = int(plan["window"]["position"])
    if not 0 <= pos < depth:
        raise ValueError(f"trigger position {pos} is not inside the build's depth {depth}")
    if plan["trigger"]["combine"] not in ("AND", "OR"):
        raise ValueError("combine must be AND or OR")
    return (f"set fda_depth {int(depth)}\nset fda_captures {{}}\n"
            f"lappend fda_captures [list {name} {plan['trigger']['combine']} {pos} [list {' '.join(comps)}]]\n")


class VendorIla(Instrument):
    """The ILA in a programmed debug build. ``build_dir`` is ``<overlay>/build/ila``; ``labels`` maps plan labels to the
    build's probe names when the build was made for a larger probe set (debug_core/build.find_build)."""
    kind = "vendor_ila"

    def __init__(self, build_dir: Path, board: str | None = None, work: Path | None = None,
                 labels: dict[str, str] | None = None, timeout_s: float = 60.0) -> None:
        from flow import hw
        self.hw = hw
        self.build_dir = Path(build_dir)
        self.board = hw.load_board(board or "nexys_a7_100t")
        self.work = work or ROOT / "build" / "debug" / time.strftime("%Y%m%d_%H%M%S")
        self.work.mkdir(parents=True, exist_ok=True)
        self.labels = labels or {}
        self.timeout_s = timeout_s
        self.proc: subprocess.Popen | None = None
        self.plan: dict[str, Any] | None = None
        self.shell = None
        self.log: list[dict[str, Any]] = []
        self.name = "cap"
        self.t_start = time.monotonic()

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "channels": "the debug build's probes (probe_map.txt)", "limits": ila_limits(),
                "safety": BOARD_LIMITS.get(self.board["name"], {}), "mock": False}

    def _slices(self) -> dict[str, tuple[int, int, int]]:
        from flow import ila
        return {n: (port, off, w) for n, port, off, w in ila.read_probe_slices(self.build_dir / "probe_map.txt")}

    def configure(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        pj = self.build_dir.parents[1] / "plan.json"
        self.depth = int(json.loads(pj.read_text())["window"]["depth"]) if pj.is_file() else plan["window"]["depth"]
        (self.work / "plan.tcl").write_text(plan_tcl(plan, self._slices(), self.depth, self.labels, self.name))

    def _ops(self, ops: list[dict[str, Any]], tag: str) -> dict[str, int]:
        reads = {}
        for o in ops or []:
            t = time.monotonic()
            if o["op"] == "write":
                self.shell.write(o["address"], int(o["value"]))
            elif o["op"] == "read":
                reads[o["register"]] = self.shell.read(o["address"])
            elif o["op"] == "wait_ms":
                time.sleep(float(o["ms"]) / 1000.0)
            self.log.append({"phase": tag, **{k: v for k, v in o.items()},
                             **({"read": reads[o["register"]]} if o["op"] == "read" else {}),
                             "t_s": round(t - self.t_start, 3)})
        return reads

    def arm(self) -> None:
        from shell.host.fpga_shell import FpgaShell
        if self.plan is None:
            raise RuntimeError("configure first")
        ltx = next(self.build_dir.glob("*.ltx"))
        man = self.build_dir / "manifest.json"
        expect = (json.loads(man.read_text()).get("build_id") or "") if man.is_file() else ""
        self.hw.preflight()
        self._out = open(self.work / "ila_capture.stdout.txt", "w")
        self.proc = subprocess.Popen(self.hw.vivado_cmd(ROOT / "flow" / "ila_capture.tcl",
                                                        [self.board["cable_serial"], str(ltx), str(self.work),
                                                         str(self.work / "plan.tcl"), expect], self.work / "ila_capture.log"),
                                     cwd=self.work, stdout=self._out, stderr=subprocess.STDOUT, start_new_session=True)
        self.shell = FpgaShell.open(self.board["uart"])
        self._ops(self.plan.get("setup", []), "setup")
        (self.work / f"{self.name}.go").write_text("go\n")
        if not self._wait(self.work / f"{self.name}.armed", 300):
            raise RuntimeError("the ILA was never armed: " + self._errors())
        time.sleep(0.2)

    def _wait(self, path: Path, timeout: float) -> bool:
        t0 = time.monotonic()
        while not path.exists():
            if (self.proc and self.proc.poll() is not None) or time.monotonic() - t0 > timeout:
                return False
            time.sleep(0.1)
        return True

    def _errors(self) -> str:
        f = self.work / "ila_capture.stdout.txt"
        lines = f.read_text(errors="replace").splitlines() if f.is_file() else []
        errs = [l.strip() for l in lines if l.startswith("ERROR")]
        errs += [l.strip() for l in lines if l.startswith("ila_capture.tcl:")]
        errs = list(dict.fromkeys(errs))
        return " | ".join(errs)[:1200] or "(no Vivado error line)"

    def capture(self) -> dict[str, Any]:
        assert self.plan is not None and self.shell is not None
        self._ops(self.plan.get("stimulus", []), "stimulus")
        t0 = time.monotonic()
        name = self.name
        while not (self.work / f"{name}.done").exists():
            if (self.work / f"{name}.timeout").exists():
                raise TimeoutError("the trigger never fired within the ILA wait (1 minute); conditions in "
                                   f"{self.work}/{name}.cond_armed.txt")
            if self.proc.poll() is not None or time.monotonic() - t0 > self.timeout_s + 120:
                raise RuntimeError("no capture: " + self._errors())
            time.sleep(0.1)
        readback = self._ops(self.plan.get("readback", []), "readback")
        samples, t_idx, t_from = samples_from_files(self.plan, self.work / f"{name}.csv", self.build_dir / "probe_map.txt",
                                                    self.work / "hw_probes.txt", self.labels)
        man = self.build_dir / "manifest.json"
        m = json.loads(man.read_text()) if man.is_file() else {}
        build = {"dir": str(self.build_dir.relative_to(ROOT)) if self.build_dir.is_relative_to(ROOT) else str(self.build_dir),
                 "build_id": m.get("build_id"), "build_stamp": (m.get("settings") or {}).get("build_stamp"),
                 "probeset": self.build_dir.parents[1].name, "vivado": self.vivado_version()}
        cap = make_capture(plan=self.plan, samples=samples, trigger_sample=t_idx,
                           instrument={"kind": self.kind, "driver": "debug_core.instruments.VendorIla", "mock": False,
                                       "settings": {"depth": self.depth, "position": int(self.plan["window"]["position"]),
                                                    "combine": self.plan["trigger"]["combine"],
                                                    "compares": {c["probe"]: c["pattern"] for c in self.plan["trigger"]["conditions"]},
                                                    "board": self.board["name"],
                                                    "cable_serial": self.hw.redact(self.board["cable_serial"])}},
                           build=build, conditions=conditions(self.work, name), stimulus_log=self.log,
                           readback=readback)
        cap["timebase"]["trigger_sample_from"] = t_from
        return cap

    def vivado_version(self) -> str | None:
        f = self.work / "ila_capture.stdout.txt"
        return self.hw.vivado_version(f.read_text(errors="replace")) if f.is_file() else None

    def close(self) -> None:
        if self.shell is not None:
            try:
                self.shell.__exit__(None, None, None)
            except Exception:
                pass
            self.shell = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)     # the vivado wrapper runs the real binary as a child
                self.proc.wait()
            self.proc = None
        if getattr(self, "_out", None):
            self._out.close()
            text = (self.work / "ila_capture.stdout.txt").read_text(errors="replace")
            ser = self.board.get("cable_serial") or ""
            if ser:
                (self.work / "ila_capture.stdout.txt").write_text(text.replace(ser, self.hw.redact(ser) or ""))
