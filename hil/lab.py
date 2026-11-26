"""The lab: which instruments exist, which a script may drive, and which measurement method fits a requirement (brief 221).

The agent knows the board (``boards/*/board.yaml``) but, before this module, not the bench. ``lab.yaml`` records one entry per instrument; the
interview reads it and asks only about gaps; stage 9 of a run picks, per requirement, the best available way to check it (``hil/lab_bringup.py``).

Two files, merged:

* the **owner's lab profile**, default ``$XDG_CONFIG_HOME/fpga-force/lab.yaml`` (``~/.config/fpga-force/lab.yaml``), or the file named by
  ``FDA_LAB_FILE`` (``none`` means no profile). It describes a private bench, so it never lives in the repository; ``hil/lab.example.yaml`` is a
  template;
* the **design's lab file**, ``lab.yaml`` in the design directory or its ``package/`` folder: for this design, which instruments are connected and
  what each channel probes (``connections``), and optional overrides of an instrument's fields (same ``id``).

Nothing here touches an instrument. A driver is opened by ``hil/lab_drivers.py`` only when a step runs, and the owner runs every instrument script.

What a lab file can get wrong, and what happens (see also docs/agent.md):

* an instrument with ``onboarded: false`` is never chosen as a method: it is offered as "available after onboarding";
* an output with no stated limit, or with ``never_by_script: true``, is never enabled by a script (:func:`check_drive` refuses);
* a probe recorded on the wrong pin is not detectable here: the plan prints the pin it assumed, and the bring-up asks the owner to confirm the wiring
  before the first reading;
* a ``connections`` entry for a channel the instrument does not have is a validation error;
* an instrument that is also a board (``is_board``, brief 225: the Red Pitaya) has a ``mode``: ``factory_instrument`` (its factory image runs, so its
  instruments work) or ``target_loaded`` with the ``build_id`` of the design loaded into it (the factory instruments are gone until a power cycle or the
  reload script restores them). It is never planned as the measurement of a design that runs on it (the design's ``target_board`` is its ``is_board``),
  unless the design is itself the instrument, and then only its own readout counts, never the factory oscilloscope. Every run row records the mode the
  measurement used (:func:`instrument_mode`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "fpga-force/lab/v1"
FILE = "lab.yaml"
ENV_FILE = "FDA_LAB_FILE"
KINDS = ("oscilloscope", "logic_analyser", "frequency_counter", "signal_generator", "bench_supply", "multimeter", "sfp_loopback",
         "ethernet_link_partner", "audio_capture", "video_capture", "sdr_transmitter", "sdr_receiver", "breakout", "on_chip")
#: what an instrument can do. ``measure`` entries answer a requirement; ``drive`` entries put a signal or power into the board.
MEASURES = ("frequency", "logic", "voltage", "audio", "video", "link")
CONTROL = ("scripted", "manual")
CONNECTIONS = ("usb", "lan", "none")
OUTPUT_KINDS = ("awg", "supply", "rf_tx", "pattern")
#: an instrument that is also a board (brief 225): which of its two roles the box is in now
MODE_STATES = ("factory_instrument", "target_loaded")
#: nothing may transmit RF into anything but a dummy load or at least this much attenuation (house rules, "RF")
MIN_TX_ATTENUATION_DB = 30.0


class LabError(ValueError):
    """A lab file that cannot be used (the message says which field)."""


class SafetyRefused(LabError):
    """A step that would drive an output beyond the lab file's limits, or an output a script may never enable."""


# ---- where the files are --------------------------------------------------------------------------------------------------------------
def profile_path() -> Path | None:
    """The owner's lab profile path: ``FDA_LAB_FILE`` (``none`` or empty: no profile), else the user's config folder. Not required to exist."""
    env = os.environ.get(ENV_FILE)
    if env is not None:
        return None if env.strip().lower() in ("", "none") else Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "fpga-force" / FILE


def design_path(design: Path | None) -> Path | None:
    if design is None:
        return None
    for f in (Path(design) / FILE, Path(design) / "package" / FILE):
        if f.is_file():
            return f
    return None


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise LabError(f"{path}: cannot be read: {e}") from e
    if not isinstance(doc, dict):
        raise LabError(f"{path}: a lab file is a mapping with an 'instruments' list")
    return doc


# ---- validation -----------------------------------------------------------------------------------------------------------------------
def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_instrument(i: Any, where: str = "instrument") -> list[str]:
    """Problems with one instrument entry; empty list when it is usable."""
    if not isinstance(i, dict):
        return [f"{where}: not a mapping"]
    w = f"{where} {i.get('id', '?')!r}"
    errs: list[str] = []
    if not isinstance(i.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", i.get("id") or ""):
        errs.append(f"{w}: id must be lower-case letters, digits and underscores")
    if i.get("kind") not in KINDS:
        errs.append(f"{w}: kind {i.get('kind')!r} is not one of {', '.join(KINDS)}")
    if "mock" in i and not isinstance(i["mock"], bool):
        errs.append(f"{w}: mock must be true or false (a mock instrument is for dry runs and CI; its readings are never evidence)")
    if not isinstance(i.get("onboarded"), bool):
        errs.append(f"{w}: onboarded must be true or false (a never-onboarded instrument is offered only as 'available after onboarding')")
    con = i.get("connection") or {}
    if con.get("type") not in CONNECTIONS:
        errs.append(f"{w}: connection.type must be one of {', '.join(CONNECTIONS)}")
    elif con["type"] == "lan" and not con.get("address"):
        errs.append(f"{w}: a LAN instrument needs connection.address (ask the owner; never guess one)")
    ctl = i.get("control") or {}
    if ctl.get("mode") not in CONTROL:
        errs.append(f"{w}: control.mode must be 'scripted' or 'manual'")
    elif ctl["mode"] == "scripted" and not ctl.get("driver"):
        errs.append(f"{w}: a scripted instrument names its driver (control.driver)")
    if "is_board" in i and not (isinstance(i["is_board"], str) and re.fullmatch(r"[a-z][a-z0-9_]*", i["is_board"])):
        errs.append(f"{w}: is_board names the board this instrument is (a board directory name such as redpitaya_stemlab_125_14)")
    if "mode" in i:
        m = i["mode"]
        if not isinstance(m, dict) or m.get("state") not in MODE_STATES:
            errs.append(f"{w}: mode.state must be one of {', '.join(MODE_STATES)}")
        elif m["state"] == "target_loaded" and not (isinstance(m.get("build_id"), str) and m["build_id"].strip()):
            errs.append(f"{w}: mode target_loaded needs the build_id of the design loaded into the board")
        elif m["state"] == "factory_instrument" and m.get("build_id"):
            errs.append(f"{w}: mode factory_instrument has no build_id (the factory image is running)")
        if not i.get("is_board"):
            errs.append(f"{w}: only an instrument that is also a board (is_board) has a mode")
    names = {c.get("name") for c in i.get("channels") or [] if isinstance(c, dict)}
    for c in i.get("channels") or []:
        if not isinstance(c, dict) or not c.get("name"):
            errs.append(f"{w}: every channel has a name")
    for k, cap in enumerate(i.get("capabilities") or []):
        if not isinstance(cap, dict) or cap.get("measure") not in MEASURES:
            errs.append(f"{w}: capability {k}: measure must be one of {', '.join(MEASURES)}")
            continue
        for ch in cap.get("channels") or []:
            if names and ch not in names:
                errs.append(f"{w}: capability {k} names channel {ch!r}, which the instrument does not list")
        for f in ("max_hz", "min_hz", "accuracy_ppm"):
            if f in cap and not _num(cap[f]):
                errs.append(f"{w}: capability {k}: {f} must be a number")
    for o in i.get("outputs") or []:
        if not isinstance(o, dict) or not o.get("name") or o.get("kind") not in OUTPUT_KINDS:
            errs.append(f"{w}: every output has a name and a kind ({', '.join(OUTPUT_KINDS)})")
            continue
        for f in ("max_v", "max_a", "max_dbm", "max_hz"):
            if f in o and not _num(o[f]):
                errs.append(f"{w}: output {o['name']}: {f} must be a number")
        if not o.get("never_by_script") and not any(f in o for f in ("max_v", "max_dbm")):
            errs.append(f"{w}: output {o['name']} has no limit and is not marked never_by_script: state max_v (or max_dbm) or forbid it")
    return errs


def validate(doc: Any, where: str = "lab", *, instruments: bool = True) -> list[str]:
    """Problems with a lab file. ``instruments=False`` checks only the shape (a design's file may hold partial overrides of profile instruments; the
    merged result is validated after the merge)."""
    if not isinstance(doc, dict):
        return [f"{where}: not a mapping"]
    errs: list[str] = []
    if doc.get("schema") not in (None, SCHEMA):
        errs.append(f"{where}: schema {doc.get('schema')!r} is not {SCHEMA}")
    seen: set[str] = set()
    for i in doc.get("instruments") or []:
        errs += validate_instrument(i, f"{where} instrument") if instruments else ([] if isinstance(i, dict) and "id" in i else [f"{where}: an instrument entry needs an id"])
        iid = i.get("id") if isinstance(i, dict) else None
        if iid in seen:
            errs.append(f"{where}: instrument id {iid!r} appears twice")
        seen.add(iid)
    for k, c in enumerate(doc.get("connections") or []):
        if not isinstance(c, dict) or not all(c.get(f) for f in ("instrument", "channel", "probes")):
            errs.append(f"{where}: connection {k} needs instrument, channel and probes (the pin or point the channel is wired to)")
    return errs


# ---- the merged lab -------------------------------------------------------------------------------------------------------------------
@dataclass
class Lab:
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    connections: list[dict[str, Any]] = field(default_factory=list)       # this design's wiring (from the design's lab file)
    profile: Path | None = None
    design_file: Path | None = None
    problems: list[str] = field(default_factory=list)
    declined: bool = False                                                # the design's lab file says: no instruments for this design
    target_board: str | None = None                                       # the board the design runs on (the design's lab file, else its build.yaml)
    design_is_instrument: bool = False                                    # the design's lab file says: the design itself is the instrument (brief 225)

    @property
    def present(self) -> bool:
        return bool(self.instruments)

    def get(self, iid: str) -> dict[str, Any]:
        if iid not in self.instruments:
            raise LabError(f"no instrument {iid!r} in the lab (known: {', '.join(sorted(self.instruments)) or 'none'})")
        return self.instruments[iid]

    def connected(self, iid: str) -> list[dict[str, Any]]:
        return [c for c in self.connections if c.get("instrument") == iid]

    def provenance(self) -> dict[str, Any]:
        return {"profile": str(self.profile) if self.profile else None, "design_file": str(self.design_file) if self.design_file else None,
                "instruments": sorted(self.instruments)}


def merge(profile: dict[str, Any] | None, design: dict[str, Any] | None) -> Lab:
    """The profile's instruments, with each design entry of the same ``id`` replacing the fields it states, and new ids added."""
    lab = Lab()
    for doc in (profile, design):
        for i in (doc or {}).get("instruments") or []:
            if not isinstance(i, dict) or "id" not in i:
                continue
            old = lab.instruments.get(i["id"], {})
            lab.instruments[i["id"]] = {**old, **{k: v for k, v in i.items() if v is not None}}
    lab.connections = [c for c in (design or {}).get("connections") or [] if isinstance(c, dict)]
    lab.declined = bool((design or {}).get("no_instruments"))
    lab.target_board = (design or {}).get("target_board") or None
    lab.design_is_instrument = bool((design or {}).get("design_is_instrument"))
    return lab


def load(design: Path | None = None, profile: Path | None = None, *, strict: bool = False) -> Lab:
    """The lab for a design. A missing file is an empty lab. A file that cannot be read or validated is recorded in ``Lab.problems`` (and the
    instruments of a file with problems are not used), or raised with ``strict=True``."""
    prof = profile if profile is not None else profile_path()
    dfile = design_path(design)
    docs: list[dict[str, Any] | None] = []
    problems: list[str] = []
    for f in (prof if prof and Path(prof).is_file() else None, dfile):
        if f is None:
            docs.append(None)
            continue
        try:
            d = _read(Path(f))
            bad = validate(d, str(f), instruments=f is not dfile)
        except LabError as e:
            d, bad = None, [str(e)]
        if bad:
            problems += bad
            d = None
        docs.append(d)
    if problems and strict:
        raise LabError("; ".join(problems))
    lab = merge(*docs)
    if dfile is not None and docs[1] is not None:                         # the design's partial overrides, checked as merged
        for iid in {i.get("id") for i in docs[1].get("instruments") or [] if isinstance(i, dict)}:
            bad = validate_instrument(lab.instruments[iid], f"{dfile} merged instrument")
            if bad:
                problems += bad
                lab.instruments.pop(iid, None)
    lab.profile, lab.design_file, lab.problems = (Path(prof) if prof and Path(prof).is_file() else None), dfile, problems
    if lab.target_board is None and design is not None and (Path(design) / "build.yaml").is_file():      # the design's own build.yaml names its board
        try:
            lab.target_board = (yaml.safe_load((Path(design) / "build.yaml").read_text()) or {}).get("board") or None
        except (OSError, yaml.YAMLError):
            pass
    good = []
    for c in lab.connections:                                              # a connection must name a real instrument and channel
        inst = lab.instruments.get(c.get("instrument"))
        chans = {x.get("name") for x in (inst or {}).get("channels") or []}
        if inst is None:
            lab.problems.append(f"connection to {c.get('instrument')!r}: no such instrument in the lab")
        elif chans and c.get("channel") not in chans:
            lab.problems.append(f"connection {c.get('instrument')}.{c.get('channel')}: the instrument has no such channel (channels: {', '.join(sorted(chans))})")
        else:
            good.append(c)
    lab.connections = good
    if strict and lab.problems:
        raise LabError("; ".join(lab.problems))
    return lab


# ---- needs and methods ----------------------------------------------------------------------------------------------------------------
@dataclass
class Need:
    """A requirement an instrument could check besides the design's own on-chip evidence."""
    requirement: str
    text: str
    quantity: str                         # one of MEASURES
    target: str                           # the signal in words ("the C3 clock", "led[0]")
    value: float | None = None            # the expected value in the unit of the quantity (Hz for frequency, V for voltage), when the text gives it
    tolerance_ppm: float | None = None
    onchip: str = ""                      # what the design itself measures it with, in words


_FREQ = re.compile(r"(\d+(?:\.\d+)?)\s*(GHz|MHz|kHz|Hz)\b", re.I)
_UNIT = {"ghz": 1e9, "mhz": 1e6, "khz": 1e3, "hz": 1.0}
_PPM = re.compile(r"(\d+(?:\.\d+)?)\s*ppm", re.I)
_VOLT = re.compile(r"(\d+(?:\.\d+)?)\s*(mV|V)\b")
_PIN = re.compile(r"\b(?:pin|net|port)\s+([A-Za-z]\w*)|\b(?:on|from)\s+(?:the\s+)?([A-Z]{1,2}\d{1,2})\b|\b([A-Z]{1,2}\d{1,2})\s+(?:clock|pin)\b")


def needs_from_spec(spec: dict[str, Any]) -> list[Need]:
    """The requirements whose proof includes hardware and whose text states a frequency, a voltage or a logic level that an instrument can see.
    Rules, not a model: a frequency with a unit (Hz, kHz, MHz, GHz) is a ``frequency`` need; a voltage is a ``voltage`` need; "toggles" or
    "blinks" with a period is a ``frequency`` need on the output."""
    out: list[Need] = []
    for r in spec.get("requirements") or []:
        if not isinstance(r, dict) or "hardware" not in (r.get("proof") or r.get("methods") or []):
            continue
        t = str(r.get("text", ""))
        rid = str(r.get("id", ""))
        pin = next((g for m in [_PIN.search(t)] if m for g in m.groups() if g), "")
        ppm = _PPM.search(t)
        after = _FREQ.search(t, ppm.end()) if ppm else None          # "within 100 ppm of 25 MHz": the frequency after the tolerance is the one asked for,
        f = after if after and re.match(r"\s*(?:of|to|from)\b", t[ppm.end():ppm.end() + 8]) else _FREQ.search(t)   # not the reference ("156.25 MHz") the design counts with
        if f and re.search(r"\bmeasur\w*|\bwithin\b|\bppm\b|\bclock\b|\bruns? at\b|\bfrequency\b", t, re.I):
            hz = float(f.group(1)) * _UNIT[f.group(2).lower()]
            out.append(Need(rid, t, "frequency", f"the {pin} signal" if pin else "the clock the requirement names", hz,
                            float(ppm.group(1)) if ppm else None, "the design's own count against its reference"))
            continue
        v = _VOLT.search(t)
        if v and re.search(r"\blevel\b|\bvolt\w*|\boutput\b|\bswing\b", t, re.I):
            volts = float(v.group(1)) * (1e-3 if v.group(2) == "mV" else 1.0)
            out.append(Need(rid, t, "voltage", f"the {pin} signal" if pin else "the output the requirement names", volts, None, "no on-chip equivalent"))
    return out


def _covers(cap: dict[str, Any], need: Need) -> str | None:
    """None when the capability can check the need, else the reason it cannot."""
    if cap.get("measure") != need.quantity:
        return f"it does not measure {need.quantity}"
    if need.value is not None and need.quantity == "frequency":
        if "max_hz" in cap and need.value > float(cap["max_hz"]):
            return f"{need.value:g} Hz is above its limit of {float(cap['max_hz']):g} Hz"
        if "min_hz" in cap and need.value < float(cap["min_hz"]):
            return f"{need.value:g} Hz is below its limit of {float(cap['min_hz']):g} Hz"
        if need.tolerance_ppm is not None and cap.get("accuracy_ppm") is not None and float(cap["accuracy_ppm"]) * 3 > need.tolerance_ppm:
            return f"its accuracy ({float(cap['accuracy_ppm']):g} ppm) is not at least three times better than the {need.tolerance_ppm:g} ppm asked for"
    if need.value is not None and need.quantity == "voltage" and "range_v" in cap:
        lo, hi = (float(x) for x in cap["range_v"])
        if not lo <= need.value <= hi:
            return f"{need.value:g} V is outside its range {lo:g} to {hi:g} V"
    return None


def instrument_mode(lab: Lab, iid: str) -> dict[str, Any] | None:
    """The mode a board-and-instrument is in (brief 225), for a run record: ``{"state", "build_id", "is_board", "design_runs_on_it"}``, or None for an
    instrument that is not also a board. An ``is_board`` instrument with no ``mode`` is in ``factory_instrument``, unless the design runs on it (then it
    is a target, whatever the file says: the factory image is not what is measuring)."""
    inst = lab.instruments.get(iid) or {}
    if not inst.get("is_board"):
        return None
    m = inst.get("mode") or {}
    on_it = bool(lab.target_board) and inst["is_board"] == lab.target_board
    state = m.get("state") or ("target_loaded" if on_it else "factory_instrument")
    return {"state": state, "build_id": m.get("build_id"), "is_board": inst["is_board"], "design_runs_on_it": on_it}


def factory_unavailable(lab: Lab, iid: str) -> str | None:
    """Why the factory instruments of ``iid`` cannot be used for this design, or None. The same box cannot be the instrument and the target at once:
    a power cycle or the reload script returns it to its factory image, which ends the design's run."""
    m = instrument_mode(lab, iid)
    if m is None:
        return None
    if m["design_runs_on_it"] and lab.design_is_instrument:
        return (f"the design runs on {iid} and is itself the instrument: only its own readout counts; the factory instruments of {iid} are not running "
                "(check it against another instrument)")
    if m["design_runs_on_it"]:
        return (f"the design runs on {iid}, so its factory instruments are not available (the board is the target; a power cycle or the reload script "
                "returns it to the factory image and ends the run)")
    if m["state"] == "target_loaded":
        return f"{iid} is loaded with build {m['build_id']}: its factory instruments are not running until a power cycle or the reload script restores them"
    return None


def plan_need(lab: Lab, need: Need) -> dict[str, Any]:
    """The methods for one need, best first, and what was left out and why.

    Order: a scripted, onboarded instrument connected for this design; a manual, onboarded one connected for this design (the owner types the
    reading); then the on-chip method, which is always available. An instrument the design has no connection for is "not connected for this
    design"; one that is not onboarded is "available after onboarding" and is never chosen. Where an instrument could do it but is not connected,
    the interview asks; the plan only records the state it found."""
    methods: list[dict[str, Any]] = []
    left_out: list[dict[str, str]] = []
    for iid, inst in sorted(lab.instruments.items()):
        if inst.get("kind") == "on_chip":                      # the design's own debug cores are the on-chip method, not an independent one
            continue
        caps = [c for c in inst.get("capabilities") or [] if isinstance(c, dict)]
        why = [_covers(c, need) for c in caps if c.get("measure") == need.quantity]
        if not why:
            continue
        ok = [c for c, w in zip([c for c in caps if c.get("measure") == need.quantity], why) if w is None]
        if not ok:
            left_out.append({"instrument": iid, "reason": why[0] or "cannot"})
            continue
        busy = factory_unavailable(lab, iid)
        if busy:                                              # brief 225: the same box cannot be the instrument and the target
            left_out.append({"instrument": iid, "reason": busy})
            continue
        if not inst.get("onboarded"):
            left_out.append({"instrument": iid, "reason": "available after onboarding"})
            continue
        wired = [c for c in lab.connected(iid) if not ok[0].get("channels") or c.get("channel") in ok[0]["channels"]]
        if not wired:
            left_out.append({"instrument": iid, "reason": "not connected for this design"})
            continue
        mode = (inst.get("control") or {}).get("mode", "manual")
        methods.append({"method": mode, "instrument": iid, "channel": wired[0]["channel"], "probes": wired[0]["probes"],
                        "accuracy_ppm": ok[0].get("accuracy_ppm"), "independent": True, "mock": bool(inst.get("mock"))})
    methods.sort(key=lambda m: 0 if m["method"] == "scripted" else 1)
    methods.append({"method": "on_chip", "instrument": None, "what": need.onchip or "the design's own measurement", "independent": False})
    return {"requirement": need.requirement, "text": need.text, "quantity": need.quantity, "target": need.target,
            "expected": need.value, "tolerance_ppm": need.tolerance_ppm, "methods": methods, "chosen": methods[0], "left_out": left_out,
            "independent": methods[0]["method"] != "on_chip"}


def plan(lab: Lab, needs: list[Need]) -> dict[str, Any]:
    rows = [plan_need(lab, n) for n in needs]
    return {"schema": "fpga-force/lab-plan/v1", "lab": lab.provenance(), "lab_problems": list(lab.problems), "requirements": rows,
            "summary": {"needs": len(rows), "independent_check": sum(r["independent"] for r in rows), "on_chip_only": sum(not r["independent"] for r in rows)}}


# ---- safety ---------------------------------------------------------------------------------------------------------------------------
def check_drive(lab: Lab, iid: str, output: str, *, volts: float | None = None, amps: float | None = None, dbm: float | None = None,
                hz: float | None = None, attenuator_db: float | None = None, board_vcco_v: float | None = None) -> dict[str, Any]:
    """Refuse (raise :class:`SafetyRefused`) any step that would put a signal or power into the board beyond the lab file's limits. Returns the
    output's entry when the step is within them. This is what brief 222's ``lab_limits`` never-rule stands for: no permission mode reaches it.

    Refused: an unknown instrument or output; an output marked ``never_by_script``; an instrument that is not onboarded; a requested value
    above the output's ``max_v``, ``max_a``, ``max_dbm`` or ``max_hz``; a request with no value where the output has a limit that needs one
    (volts for a supply or generator, dbm for RF); RF without at least 30 dB of attenuation or a declared dummy load; and a voltage above the
    VCCO of the pin it is wired to (``board_vcco_v``, from the design's connection)."""
    inst = lab.get(iid)
    out = next((o for o in inst.get("outputs") or [] if isinstance(o, dict) and o.get("name") == output), None)
    if out is None:
        raise SafetyRefused(f"{iid}.{output}: the lab file lists no such output, so a script may not enable it")
    if out.get("never_by_script"):
        raise SafetyRefused(f"{iid}.{output}: the lab file says this output is never enabled by a script")
    if not inst.get("onboarded"):
        raise SafetyRefused(f"{iid}: not onboarded; it cannot be driven")
    lim = {"max_v": volts, "max_a": amps, "max_dbm": dbm, "max_hz": hz}
    for k, want in lim.items():
        if k in out and want is None and k in ("max_v", "max_dbm"):
            raise SafetyRefused(f"{iid}.{output}: the step does not state its {k[4:]} and the output has a limit of {out[k]:g}: state it")
        if k in out and want is not None and float(want) > float(out[k]) + 1e-12:
            raise SafetyRefused(f"{iid}.{output}: {k[4:]} {want:g} is above the lab file's limit {float(out[k]):g}")
    if out.get("kind") == "rf_tx":
        need_db = max(MIN_TX_ATTENUATION_DB, float(out.get("requires_attenuator_db", 0)))
        if out.get("dummy_load"):
            pass
        elif attenuator_db is None or float(attenuator_db) < need_db:
            raise SafetyRefused(f"{iid}.{output}: RF is transmitted only into a dummy load or at least {need_db:g} dB of attenuation (house rule); "
                                f"the step declares {attenuator_db!r} dB")
    if volts is not None and board_vcco_v is not None and float(volts) > float(board_vcco_v) + 1e-12:
        raise SafetyRefused(f"{iid}.{output}: {volts:g} V is above the {board_vcco_v:g} V of the board pin it is wired to")
    return out


# ---- onboarding evidence: a listing only ----------------------------------------------------------------------------------------------
#: USB vendor:product ids of lab instruments, to tell "plugged in now" from a lab file's claim. A listing only: nothing is opened.
USB_IDS = {"0456:b672": "m2k", "0456:b673": "pluto", "0bda:2838": "rtl_sdr", "0bda:2832": "rtl_sdr", "2b89:5854": "ugreen_capture",
           "08bb:2902": "audio_interface"}


def usb_seen(lsusb_text: str) -> list[str]:
    """The lab instruments that a ``lsusb`` listing shows, by short name. Parsing only (the CLI runs ``lsusb``, which opens no device)."""
    return sorted({USB_IDS[m.group(1).lower()] for m in re.finditer(r"ID\s+([0-9a-fA-F]{4}:[0-9a-fA-F]{4})", lsusb_text) if m.group(1).lower() in USB_IDS})


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import subprocess
    import sys
    ap = argparse.ArgumentParser(description="Show the lab a design would see, or check a lab file. Touches no instrument.")
    ap.add_argument("--design", type=Path)
    ap.add_argument("--profile", type=Path, help="a lab profile to use instead of the default")
    ap.add_argument("--usb", action="store_true", help="also run lsusb (a listing only) and say which instruments are plugged in")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    lab = load(a.design, a.profile)
    seen = usb_seen(subprocess.run(["lsusb"], capture_output=True, text=True).stdout) if a.usb else None
    doc = {**lab.provenance(), "problems": lab.problems, "usb_seen": seen,
           "table": [{"id": i, "kind": v.get("kind"), "onboarded": v.get("onboarded"), "control": (v.get("control") or {}).get("mode"),
                      "connected_for_design": [c["channel"] for c in lab.connected(i)]} for i, v in sorted(lab.instruments.items())]}
    if a.json:
        print(json.dumps(doc, indent=1))
    else:
        print(f"profile: {doc['profile'] or 'none'}; design file: {doc['design_file'] or 'none'}")
        for r in doc["table"]:
            print(f"  {r['id']:14} {r['kind']:20} onboarded={r['onboarded']!s:5} {r['control']:9} wired: {', '.join(r['connected_for_design']) or '-'}")
        for p in lab.problems:
            print("  PROBLEM:", p)
        if seen is not None:
            print("plugged in now (lsusb):", ", ".join(seen) or "none of the known instruments")
    return 1 if lab.problems else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
