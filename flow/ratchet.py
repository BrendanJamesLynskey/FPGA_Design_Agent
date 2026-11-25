#!/usr/bin/env python3
"""Regression ratchet (brief 189 item 6; idea from Edwards 2026, ch 17). Advisory first: ``enforced: false``.

A creeping regression (a few LUTs, one more logic level, one more clock of latency per change) shows up weeks later as a failing timing
run. The ratchet keeps three numbers per module for every build, so growth is visible as a change in a number at the commit that caused it:

* ``lut`` and ``ff``: per module, from a block table such as ``at_required.blocks`` in an out-of-context result record
  (results/b110/ooc/*.json);
* ``logic_depth``: per module, the most logic levels on any reported path that ends in the module (flow/digest/timing.py parses the
  ``Logic Levels`` of a ``report_timing`` text; only the paths the report lists are seen, so it is a floor on the true depth);
* ``clocks``: named latencies in clocks (a flat or two-level JSON of simulated stage latencies), compared name by name.

Store: one JSON file per design (``history``: a list of snapshots, oldest first, each with a build id, a date and an ``accepted``
flag). ``check`` compares a current snapshot with the last accepted one (RATCHET-01: growth above ``--pct``, default 5 %) and with the
best (lowest) value ever accepted (RATCHET-02: creep above ``--creep-pct``, default 10 %). A growth must also reach the metric's absolute
floor (5 LUTs or FFs, 1 level, 1 clock) so that noise on tiny modules is not flagged. A waiver (module, metric, reason) or a
``--override REASON`` for the build accepts a growth and is written to the record; an empty reason is not honoured. ``record`` appends
a snapshot; it is accepted when the check passes or every finding is waived.

    python3 -m flow.ratchet snapshot --blocks OOC.json [--run at_required] [--timing RPT ...] [--clocks JSON --clocks-key K]
                                     --build ID --out SNAP.json
    python3 -m flow.ratchet check  --store STORE.json --snap SNAP.json [--pct 5] [--creep-pct 10] [--waivers W.json] [--override REASON]
    python3 -m flow.ratchet record --store STORE.json --snap SNAP.json [...same options as check]

Exit status is 0 unless ``--enforce`` is given (then 1 on an unwaived finding)."""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MIN_ABS = {"lut": 5, "ff": 5, "logic_depth": 1, "clocks": 1}


def modules_from_blocks(blocks: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{instance: {lut, ff}} from a block table ({instance: {module, lut, ff, ...}}); the top ``u_dut`` row repeats its children and is kept."""
    return {k: {"lut": int(v["lut"]), "ff": int(v["ff"])} for k, v in blocks.items() if "lut" in v and "ff" in v}


def depth_by_module(report_text: str) -> dict[str, int]:
    """Most logic levels of any reported path, by the first hierarchy name of the destination register ('(top)' when it has none)."""
    from flow.digest import timing
    out: dict[str, int] = {}
    for p in timing.parse_paths(report_text):
        if p["kind"] != "setup" or p.get("logic_levels") is None:
            continue
        inst = ((p.get("dest_reg") or {}).get("instance") or "").strip("/")
        mod = inst.split("/")[0] if inst else "(top)"
        out[mod] = max(out.get(mod, 0), int(p["logic_levels"]))
    return out


def clocks_from_json(obj: Any, key: str | None = None) -> dict[str, int]:
    """Numeric leaves of a (possibly nested) dict, or of ``obj[key]``, as {name: clocks}; a name that repeats keeps the larger value."""
    if key is not None:
        for part in key.split("."):
            obj = obj[part]
    out: dict[str, int] = {}

    def walk(o: Any, trail: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{trail}.{k}" if trail else str(k))
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out[trail] = int(o)
    walk(obj, "")
    return out


def snapshot(design: str, build: str, modules: dict[str, dict[str, int]], depth: dict[str, int] | None = None,
             clocks: dict[str, int] | None = None, date: str | None = None) -> dict[str, Any]:
    mods = {k: dict(v) for k, v in modules.items()}
    for k, d in (depth or {}).items():
        mods.setdefault(k, {})["logic_depth"] = d
    return {"design": design, "build": build, "date": date or datetime.date.today().isoformat(), "modules": mods, "clocks": dict(clocks or {})}


def _flat(s: dict[str, Any]) -> dict[tuple[str, str], int]:
    out = {}
    for mod, m in (s.get("modules") or {}).items():
        for met, v in m.items():
            out[(mod, met)] = v
    for name, v in (s.get("clocks") or {}).items():
        out[(name, "clocks")] = v
    return out


def _waived(key: tuple[str, str], waivers: list[dict[str, Any]], override: str | None) -> str | None:
    if override and override.strip():
        return f"override: {override.strip()}"
    for w in waivers:
        if str(w.get("reason", "")).strip() and fnmatch.fnmatch(key[0], str(w.get("module", "*"))) and \
                fnmatch.fnmatch(key[1], str(w.get("metric", "*"))):
            return f"waiver: {w['reason'].strip()}"
    return None


def check(store: dict[str, Any], snap: dict[str, Any], pct: float = 5.0, creep_pct: float = 10.0,
          waivers: list[dict[str, Any]] | None = None, override: str | None = None) -> dict[str, Any]:
    """Findings of ``snap`` against the store's last accepted snapshot and its best values. Each finding has ``waived`` (the reason or None)."""
    waivers = waivers or []
    accepted = [h for h in store.get("history", []) if h.get("accepted")]
    rec: dict[str, Any] = {"enforced": False, "design": snap.get("design"), "build": snap.get("build"), "pct": pct, "creep_pct": creep_pct,
                           "baseline": accepted[-1]["build"] if accepted else None, "findings": [], "new": [], "gone": []}
    if not accepted:
        rec["note"] = "no accepted baseline: nothing to compare with (record this snapshot to start the ratchet)"
        rec["pass"] = True
        return rec
    base, cur = _flat(accepted[-1]), _flat(snap)
    best: dict[tuple[str, str], int] = {}
    for h in accepted:
        for k, v in _flat(h).items():
            best[k] = min(best.get(k, v), v)
    for key, v in sorted(cur.items()):
        met = key[1]
        floor = MIN_ABS.get(met, 1)
        if key not in base:
            rec["new"].append(f"{key[0]}.{met}")
            continue
        for code, ref, lim, what in (("RATCHET-01", base[key], pct, "the last accepted build"), ("RATCHET-02", best[key], creep_pct, "the best accepted value")):
            if ref > 0 and v - ref >= floor and (v - ref) * 100.0 / ref > lim:
                rec["findings"].append({"code": code, "module": key[0], "metric": met, "was": ref, "now": v,
                                        "growth_pct": round((v - ref) * 100.0 / ref, 1), "against": what,
                                        "waived": _waived(key, waivers, override)})
                break                                     # one finding per metric: the first (latest-build) reading
    rec["gone"] = [f"{k[0]}.{k[1]}" for k in sorted(base) if k not in cur]
    rec["pass"] = all(f["waived"] for f in rec["findings"])
    return rec


def record(store: dict[str, Any], snap: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    entry = {**snap, "accepted": bool(result["pass"]),
             "waived": [f for f in result["findings"] if f["waived"]]}
    store.setdefault("history", []).append(entry)
    return store


def _load(p: str | None, default: Any) -> Any:
    return json.loads(Path(p).read_text()) if p and Path(p).exists() else default


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--blocks", required=True)
    s.add_argument("--run", default="at_required", help="key of the run holding ``blocks`` in the OOC record, or runs[i] as runs.<i>")
    s.add_argument("--timing", nargs="*", default=[])
    s.add_argument("--clocks")
    s.add_argument("--clocks-key")
    s.add_argument("--build", required=True)
    s.add_argument("--design")
    s.add_argument("--out", required=True)
    for name in ("check", "record"):
        c = sub.add_parser(name)
        c.add_argument("--store", required=True)
        c.add_argument("--snap", required=True)
        c.add_argument("--pct", type=float, default=5.0)
        c.add_argument("--creep-pct", type=float, default=10.0)
        c.add_argument("--waivers")
        c.add_argument("--override")
        c.add_argument("--enforce", action="store_true")
        c.add_argument("--json")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        rec = json.loads(Path(a.blocks).read_text())
        run = rec
        for part in a.run.split("."):
            run = run[int(part)] if isinstance(run, list) else run[part]
        depth: dict[str, int] = {}
        for t in a.timing:
            for k, v in depth_by_module(Path(t).read_text(errors="replace")).items():
                depth[k] = max(depth.get(k, 0), v)
        clocks = clocks_from_json(json.loads(Path(a.clocks).read_text()), a.clocks_key) if a.clocks else None
        snap = snapshot(a.design or rec.get("design", "?"), a.build, modules_from_blocks(run["blocks"]), depth, clocks)
        Path(a.out).write_text(json.dumps(snap, indent=1) + "\n")
        print(f"snapshot {a.build}: {len(snap['modules'])} modules, {len(snap['clocks'])} clock figures")
        return 0
    store = _load(a.store, {"history": []})
    snap = json.loads(Path(a.snap).read_text())
    res = check(store, snap, a.pct, a.creep_pct, _load(a.waivers, []), a.override)
    for f in res["findings"]:
        print(f"{f['code']} {f['module']}.{f['metric']}: {f['was']} -> {f['now']} (+{f['growth_pct']} % against {f['against']})"
              + (f" [{f['waived']}]" if f["waived"] else ""))
    print(f"{'pass' if res['pass'] else 'ADVISORY: growth over the limit'} (baseline {res['baseline']}, {len(res['findings'])} finding(s))")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    if a.cmd == "record":
        Path(a.store).write_text(json.dumps(record(store, snap, res), indent=1) + "\n")
    return 1 if (a.enforce and not res["pass"]) else 0


if __name__ == "__main__":
    sys.exit(main())
