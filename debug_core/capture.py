"""The common capture format (``schemas/capture.schema.json``, "fda-capture/1") and its VCD export.

One timeline, typed channels: sample ``i`` of every channel is at cycle ``i - timebase.trigger_sample`` (cycle 0 is the
trigger). Digital channels hold one integer per sample. Every instrument driver (debug_core/instruments.py; later the bench
boxes of brief 52) writes this format and every view and query (debug_core/answer.py, the viewer) reads only it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from debug_core.plan import validate


def make_capture(*, plan: dict[str, Any], samples: dict[str, list[int]], trigger_sample: int, instrument: dict[str, Any],
                 build: dict[str, Any] | None = None, conditions: dict[str, Any] | None = None,
                 stimulus_log: list[dict[str, Any]] | None = None, readback: dict[str, Any] | None = None,
                 requirement: str | None = None) -> dict[str, Any]:
    """``samples``: {plan probe label: [value per sample]} (extra keys are ignored)."""
    n = max((len(v) for v in samples.values()), default=0)
    chans = []
    for p in plan["probes"]:
        if p["label"] not in samples:
            raise ValueError(f"the capture has no samples for probe {p['label']}")
        s = list(samples[p["label"]])
        if len(s) != n:
            raise ValueError(f"probe {p['label']} has {len(s)} samples, others {n}")
        chans.append({"name": p["label"], "path": p["path"], "kind": "digital", "width": p["width"], "samples": s})
    cap = {"schema": "fda-capture/1", "instrument": instrument, "design": plan["design"], "build": build or {},
           "request": plan.get("request"), "question": plan.get("question"), "plan_probeset": plan["probeset"],
           "timebase": {"unit": "cycle", "clock": plan["clock"].get("domain"), "mhz": plan["clock"].get("mhz"),
                        "samples": n, "trigger_sample": int(trigger_sample), "alignment_uncertainty_cycles": 0},
           "channels": chans, "trigger": dict(plan["trigger"]), "window": dict(plan["window"]),
           "conditions": conditions or {}, "stimulus_log": stimulus_log or [], "readback": readback or {},
           "requirement": requirement, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    bad = validate(cap, "capture") + check_samples(cap)
    if bad:
        raise ValueError("capture does not match its schema: " + "; ".join(bad))
    return cap


def check_samples(cap: dict[str, Any]) -> list[str]:
    """What the schema cannot say: every digital sample is an integer in 0 .. 2**width - 1, every channel has
    ``timebase.samples`` samples, and the trigger sample is inside the window."""
    errs = []
    n = cap["timebase"]["samples"]
    if not 0 <= cap["timebase"]["trigger_sample"] < n:
        errs.append(f"trigger sample {cap['timebase']['trigger_sample']} is outside the {n} samples")
    for c in cap["channels"]:
        if len(c["samples"]) != n:
            errs.append(f"channel {c['name']} has {len(c['samples'])} samples, the time base says {n}")
        if c["kind"] == "digital":
            top = 1 << c["width"]
            bad = next((v for v in c["samples"] if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < top), None)
            if bad is not None:
                errs.append(f"channel {c['name']}: sample {bad!r} is not a {c['width']}-bit unsigned value")
    return errs


def load(path: Path | str) -> dict[str, Any]:
    cap = json.loads(Path(path).read_text())
    bad = validate(cap, "capture")
    if not bad:
        bad = check_samples(cap)
    if bad:
        raise ValueError(f"{path}: not an fda-capture/1 file: " + "; ".join(bad))
    return cap


def save(cap: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # samples on one line per channel keep the file readable
    text = json.dumps(cap, indent=1)
    path.write_text(text + "\n")
    return path


def channel(cap: dict[str, Any], name: str) -> dict[str, Any]:
    for c in cap["channels"]:
        if c["name"] == name or c.get("path") == name:
            return c
    raise KeyError(f"no channel {name!r}; channels: {[c['name'] for c in cap['channels']]}")


def cycles(cap: dict[str, Any]) -> list[int]:
    t0 = cap["timebase"]["trigger_sample"]
    return [i - t0 for i in range(cap["timebase"]["samples"])]


def _vcd_id(i: int) -> str:
    chars = [chr(c) for c in range(33, 127)]
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, len(chars))
        out = chars[r] + out
    return out


def to_vcd(cap: dict[str, Any]) -> str:
    """A VCD of the capture (GTKWave): one time unit per clock period, time 0 at the first sample, a ``TRIGGER`` wire that
    is 1 on the trigger sample, signals under a scope named after their RTL path."""
    mhz = cap["timebase"].get("mhz") or 100.0
    ps = int(round(1e6 / mhz))
    L = [f"$date {cap.get('created', '')} $end", "$version FPGA_Design_Agent debug_core $end",
         f"$comment {cap.get('request') or ''} $end".replace("\n", " "), f"$timescale {ps} ps $end",
         "$scope module capture $end"]
    ids = {}
    for i, c in enumerate(cap["channels"]):
        ids[c["name"]] = _vcd_id(i)
        L.append(f"$var wire {c['width']} {ids[c['name']]} {c['name']} $end")
    trig = _vcd_id(len(cap["channels"]))
    L += [f"$var wire 1 {trig} TRIGGER $end", "$upscope $end", "$enddefinitions $end"]
    prev: dict[str, int | None] = {c["name"]: None for c in cap["channels"]}
    t0 = cap["timebase"]["trigger_sample"]
    for k in range(cap["timebase"]["samples"]):
        changes = []
        for c in cap["channels"]:
            v = c["samples"][k]
            if v != prev[c["name"]]:
                prev[c["name"]] = v
                changes.append(f"{v & 1}{ids[c['name']]}" if c["width"] == 1 else f"b{v:b} {ids[c['name']]}")
        if k in (0, t0, t0 + 1):
            changes.append(f"{1 if k == t0 else 0}{trig}")
        if changes:
            L.append(f"#{k}")
            L += changes
    L.append(f"#{cap['timebase']['samples']}")
    return "\n".join(L) + "\n"


def trim(cap: dict[str, Any], lo: int, hi: int) -> dict[str, Any]:
    """A copy holding only cycles lo..hi (relative to the trigger; clipped to the window)."""
    cyc = cycles(cap)
    lo, hi = max(lo, cyc[0]), min(hi, cyc[-1])
    a, b = lo - cyc[0], hi - cyc[0] + 1
    out = dict(cap)
    out["channels"] = [{**c, "samples": c["samples"][a:b]} for c in cap["channels"]]
    out["timebase"] = {**cap["timebase"], "samples": b - a, "trigger_sample": cap["timebase"]["trigger_sample"] - a}
    return out
