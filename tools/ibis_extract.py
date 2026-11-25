#!/usr/bin/env python3
"""Derive a compact output-driver data set from the IBIS files AMD ships with Vivado (brief 155).

    python3 tools/ibis_extract.py [--root /opt/Xilinx/2025.2/data/parts/xilinx] [--out flow/offchip_data/driver_models.json]

The IBIS files (``artix7.ibs``, ``zynq.ibs``, ``zynquplus.ibs``, under ``<root>/<family>/public/ibis/``) are AMD's own
data and carry AMD's copyright and disclaimer, so the files themselves are never committed. This script reads them from
the local Vivado install and writes our own derived summary: for each LVCMOS (and SSTL DCI) output model and each of the
IBIS corners (typ, min, max) the pull-up and pull-down V-I curves sampled at fixed voltages (we keep 21 points of a curve
that has about 100), the die capacitance ``C_comp``, the receiver thresholds ``Vinl``/``Vinh``, the supply of the corner,
and the 20-80 % rise and fall time that the IBIS ``[Ramp]`` gives into its 50 ohm fixture. ``flow/offchip_model.py`` turns
the 20-80 % time into a switching ramp by calibration (so the committed file holds no waveform).

IBIS conventions used (IBIS 4.2 and 5.1, "Current directions: positive into the device"):

* ``[Pulldown]`` voltage is the pad voltage (-Vcc ... 2 Vcc); ``[Pullup]`` voltage is ``Vcc - Vpad``.
* the three data columns are typ, min and max: min is the weak corner (slow process, low supply, hot), max the strong one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path("/opt/Xilinx/2025.2/data/parts/xilinx")
FILES = {"artix7": "artix7/public/ibis/artix7.ibs", "zynq": "zynq/public/ibis/zynq.ibs",
         "zynquplus": "zynquplus/public/ibis/zynquplus.ibs"}
#: (file key, model-name regex) selecting the models kept; group 1 = standard, 2 = slew letter, 3 = drive or impedance
SELECT = [
    ("artix7", re.compile(r"^(LVCMOS(?:12|15|18|25|33))_([FS])_(\d+)_HR$")),
    ("zynq", re.compile(r"^(LVCMOS(?:12|15|18))_([FS])_(\d+)_HP$")),
    ("zynquplus", re.compile(r"^(HP_LVCMOS(?:12|15|18))_([FMS])_(\d+)$")),
    ("zynquplus", re.compile(r"^(HD_LVCMOS(?:18|33))_([FS])_(\d+)$")),
    ("zynquplus", re.compile(r"^(HP_SSTL(?:12|135|15|18)_DCI)_([FMS])_OUT(\d+)$")),
]
#: pad-side voltages at which a curve is kept (V); clipped to what the table covers
GRID = [-1.0, -0.6, -0.3, -0.15, 0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
_SCALE = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "G": 1e9}
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)$")


def num(tok: str) -> float:
    """An IBIS number with its optional scale letter and unit: ``28.67mA``, ``0.25nS``, ``1.84p``, ``-3.3V``, ``1.0M``."""
    m = _NUM.match(tok.strip())
    if not m:
        raise ValueError(f"not an IBIS number: {tok!r}")
    v, suffix = float(m.group(1)), m.group(2)
    if not suffix:
        return v
    if suffix[:3].lower() == "meg":
        return v * 1e6
    if suffix[0] in _SCALE and (len(suffix) > 1 or suffix[0] in "fpnumkM"):
        # a lone unit letter (V, A, S, F, s, ohm) is not a scale; 'm'/'M' differ by case as IBIS says
        if len(suffix) == 1 and suffix in "VAFSs":
            return v
        return v * _SCALE[suffix[0]]
    return v


def header(text_head: str) -> dict:
    out = {}
    for key in ("IBIS ver", "File Rev", "Date"):
        m = re.search(r"^\[" + re.escape(key) + r"\]\s*(\S.*)$", text_head, re.M)
        out[key] = m.group(1).strip() if m else ""
    return out


def split_models(text: str) -> dict[str, list[str]]:
    """model name -> its lines (up to the next [Model] or [End])."""
    models: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        if line.startswith("[Model]"):
            cur = line.split(None, 1)[1].strip().split()[0]
            models[cur] = []
        elif line.startswith("[Component]") or line.startswith("[End]") or line.startswith("[Package Model]"):
            cur = None
        elif cur is not None:
            models[cur].append(line)
    return models


def _rows(lines: list[str], start: int) -> list[list[float]]:
    rows = []
    for ln in lines[start + 1:]:
        if ln.startswith("["):
            break
        if not ln.strip() or ln.lstrip().startswith("|"):
            continue
        f = ln.split()
        if len(f) < 4:
            continue
        try:
            rows.append([num(t) for t in f[:4]])
        except ValueError:
            break
    return rows


def _section(lines: list[str], name: str) -> int:
    for i, ln in enumerate(lines):
        if ln.lower().startswith(name.lower()):
            return i
    return -1


def resample(rows: list[list[float]]) -> list[list[float]]:
    """Linear resampling of [v, typ, min, max] rows onto GRID (points outside the table dropped)."""
    rows = sorted(rows)
    lo, hi = rows[0][0], rows[-1][0]
    out = []
    for g in GRID:
        if g < lo - 1e-9 or g > hi + 1e-9:
            continue
        for a, b in zip(rows, rows[1:]):
            if a[0] - 1e-9 <= g <= b[0] + 1e-9:
                w = 0.0 if b[0] == a[0] else (g - a[0]) / (b[0] - a[0])
                out.append([g] + [round(a[k] + w * (b[k] - a[k]), 6) for k in (1, 2, 3)])
                break
    return out


def parse_model(lines: list[str]) -> dict:
    d: dict = {}
    for ln in lines:
        m = re.match(r"^(Vinl|Vinh)\s*=\s*(\S+)", ln, re.I)
        if m:
            d[m.group(1).lower()] = num(m.group(2))
        m = re.match(r"^C_comp\s+(\S+)\s+(\S+)\s+(\S+)", ln)
        if m:
            d["c_comp_f"] = [num(m.group(i)) for i in (1, 2, 3)]
        if ln.startswith("[Voltage Range]"):
            d["vcc"] = [num(t) for t in ln.replace("[Voltage Range]", "").split()[:3]]
    for key, name in (("pulldown", "[Pulldown]"), ("pullup", "[Pullup]")):
        i = _section(lines, name)
        d[key] = resample(_rows(lines, i)) if i >= 0 else []
    i = _section(lines, "[Ramp]")
    ramp = {}
    if i >= 0:
        for ln in lines[i + 1:]:
            if ln.startswith("["):
                break
            m = re.match(r"^dV/dt_([rf])\s+(.*)$", ln)
            if m:
                times = []
                for part in m.group(2).split():
                    a, _, b = part.partition("/")
                    times.append(num(b))
                ramp[m.group(1)] = times          # 20-80 % time (s) typ, min, max
            m = re.match(r"^R_load\s*=\s*(\S+)", ln)
            if m:
                ramp["r_load"] = num(m.group(1))
    d["t2080_s"] = ramp
    return d


def build(root: Path) -> dict:
    out: dict = {"_source": {}, "models": {}}
    for key, relpath in FILES.items():
        path = root / relpath
        if not path.is_file():
            raise SystemExit(f"missing {path}")
        text = path.read_text(errors="replace")
        out["_source"][key] = dict(file=relpath, **header(text[:4000]))
        models = split_models(text)
        for fkey, rx in SELECT:
            if fkey != key:
                continue
            for name, lines in models.items():
                m = rx.match(name)
                if not m:
                    continue
                d = parse_model(lines)
                if not d.get("pulldown") or not d.get("pullup") or "vcc" not in d or not d["t2080_s"].get("r"):
                    print(f"skip {name}: incomplete", file=sys.stderr)
                    continue
                d.update(file=key, std=m.group(1), slew=m.group(2), setting=int(m.group(3)))
                out["models"][f"{key}:{name}"] = d
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "flow/offchip_data/driver_models.json"))
    a = ap.parse_args(argv)
    data = build(Path(a.root))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=None, separators=(",", ":")) + "\n")
    print(f"{len(data['models'])} models -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
