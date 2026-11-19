"""Agent tool ``eye_scan`` (brief 96D): read an on-chip eye-scan capture and return the link margin against stated thresholds, so a design step can cite a measured margin.

It reads a capture inside the design directory (``fda-capture-eye/1``, written by ``python -m flow.eyescan run``) and computes width, height and margin from the raw
counts (flow/eyescan/api.py). It never touches a board: a new measurement is the owner's (the board is owner-run through ``_handoff/board.lock``), so with ``measure: true``
the tool returns the plan to hand to the owner instead. The eye is measured AFTER the receiver's equaliser, at a stated BER depth; a synthetic (offline model) capture never passes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.core.registry import tool
from agent.core.session import Session
from flow.eyescan import api
from flow.eyescan import capture as C


@tool("eye_scan", "Read an on-chip RX eye-scan capture of a GTH link (a JSON file written by `python -m flow.eyescan run`, under the design directory) and return the eye width (UI) and "
      "height (mV) at a stated BER depth, and the margin against thresholds you state. The eye is the receiver's statistical eye AFTER its equaliser, from the transceiver's own "
      "error counters, not the eye at the pins; each point's depth is limited by the bits it examined (points that cannot vouch for the depth are counted as 'shallow', not open). "
      "A synthetic (offline model) capture never passes. This tool does not run the board: with measure=true it returns the plan for the owner to run.",
      {"capture": {"type": "string", "description": "path of the capture JSON, relative to the design directory"},
       "depth": {"type": "number", "description": "BER depth to read the eye at (default 1e-9)"},
       "min_width_ui": {"type": "number", "description": "required eye width in UI (default 0.3)"},
       "min_height_mv": {"type": "number", "description": "required eye height in mV (default 30)"},
       "measure": {"type": "boolean", "description": "return the plan for the owner to take a new scan instead of reading a capture"}})
def eye_scan(s: Session, capture: str = "", depth: float = 1e-9, min_width_ui: float = 0.3, min_height_mv: float = 30.0, measure: bool = False) -> dict:
    if measure:
        return {"ok": True, "output": ("The board is owner-run; this tool cannot take a scan. Hand the owner: build designs/b96_kr260_10g/eyescan with flow/run_vivado.sh, then "
                                       "`bash _handoff/fpga_agent/run_96d_stage3.sh <loop lead metres> YES` (it takes _handoff/board.lock, programs SRAM only, runs the scans "
                                       "and leaves the laser off). Then call eye_scan on a written capture under results/b96d/hw/."), "plan": True}
    if not 0 < depth < 1 or min_width_ui < 0 or min_height_mv < 0:
        return {"ok": False, "output": "eye_scan: depth must be in (0, 1) and the thresholds not negative"}
    if not capture:
        return {"ok": False, "output": "eye_scan: name a capture file, or pass measure=true for the owner's plan"}
    p: Path = s.jail.resolve(capture)
    if not p.is_file() or p.suffix != ".json":
        return {"ok": False, "output": f"eye_scan: {capture!r} is not a .json capture file in the design directory"}
    try:
        cap = C.load(p)
    except (C.CaptureError, json.JSONDecodeError) as e:
        return {"ok": False, "output": f"eye_scan: {e}"}
    m = api.margin(cap, depth, min_width_ui, min_height_mv)
    e = C.eye_at(cap, depth)
    lines = [f"eye at BER {depth:g} ({cap['settings']['equaliser']}, {cap['settings']['line_rate_gbps']} Gb/s, after the equaliser): width "
             + (f"{m['width_ui']:.3f} UI" if m["width_ui"] is not None else "none")
             + ", height " + (f"{m['height_mv']:.0f} mV" if m["height_mv"] is not None else "none")
             + f"; margin against {min_width_ui} UI / {min_height_mv} mV: "
             + ("width " + (f"{m['width_margin_ui']:+.3f} UI" if m["width_margin_ui"] is not None else "n/a") + ", height " + (f"{m['height_margin_mv']:+.0f} mV" if m["height_margin_mv"] is not None else "n/a"))
             + f"; verdict {'PASS' if m['pass'] else 'NOT PASSED'}"]
    lines += [f"  - {r}" for r in m["reasons"]]
    lines.append(f"  points: {e['counts']}; grid resolution {e['width_ui_hi'] - e['width_ui']:.3f} UI / {e['height_mv_hi'] - e['height_mv']:.0f} mV" if e.get("width_ui") is not None and e.get("height_mv") is not None else f"  points: {e['counts']}")
    lines.append("  " + m["note"])
    return {"ok": True, "output": "\n".join(lines), "eye_scan": {**m, "capture": capture, "synthetic": bool(cap.get("synthetic")), "conditions": cap.get("conditions")}}
