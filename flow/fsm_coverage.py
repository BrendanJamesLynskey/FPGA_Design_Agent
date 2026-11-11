#!/usr/bin/env python3
"""FSM state and transition coverage from a simulation trace (brief 24, V2 evidence).

None of the free simulators the flow uses gives FSM coverage out of the box (docs/fsm_coverage.md has the measured matrix:
Icarus 12 has no coverage at all, Verilator reports line/branch/toggle/user ``cover property`` but ignores covergroups, xsim has
covergroups and code coverage but no FSM coverage and cannot run in CI). This tool is the simulator-independent route: it
reads the **value changes of the state register** from a VCD file (any simulator can write one; ``cocotb_run`` does it with
``FDA_FSM_VCD=1``) and compares them with the machine's state table.

Input, per design: ``<design>/verif/fsm.yaml``::

    fsms:
      - name: ctl                       # a label for the report
        signal: tb_tmp.dut.st           # hierarchical name of the state register in the VCD; a leading '*.' matches any prefix
        file: rtl/i2c_ptr_read.sv       # the RTL file holding ``typedef enum ... {A, B, ...} st_t;`` (states and values come from it)
        enum: st_t
        reset_state: S_IDLE             # optional: a change into this state from any state is a reset or an abort, not listed
        transitions:                    # the LEGAL transitions of the spec's state table, [from, to]; self-loops are not listed
          - [S_IDLE, S_START]
        waive:                          # states or transitions the tests cannot reach, each with a reason (a waiver without one fails)
          - {item: "S_X->S_Y", reason: "needs a bus error the model cannot inject"}

Without ``transitions`` the check covers states only. ``--vivado-log`` reads the FSM Vivado extracted (the state table of
Synth 8-802/8-3354: state names and the encoding it chose) and cross-checks the names against the table.

Verdicts (all must hold for ``pass``): every state visited; every legal transition taken; no transition taken that the table does
not list (a change into ``reset_state`` is allowed); no waiver without a reason. Illegal transitions are for formal
(``artix7-fsm-bugs-and-formal-checks``), not for this check: a simulation cannot prove one impossible.

A trace that never asserts a reset still starts in the register's initial value: the first value seen is the initial state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


# ---- the RTL's enum ----------------------------------------------------------------------------------------------------
def parse_enum(sv: str, enum: str) -> dict[str, int]:
    """``typedef enum [logic [N:0]] {A, B = 3, C} <enum>;`` -> {name: value} (an unvalued name is the previous value + 1)."""
    sv = re.sub(r"//[^\n]*|/\*.*?\*/", "", sv, flags=re.S)
    m = re.search(r"typedef\s+enum\b[^{]*\{(.*?)\}\s*" + re.escape(enum) + r"\s*;", sv, re.S)
    if not m:
        raise ValueError(f"no `typedef enum ... {{...}} {enum};` in the file")
    out: dict[str, int] = {}
    nxt = 0
    for item in (x.strip() for x in m.group(1).split(",") if x.strip()):
        n, _, v = item.partition("=")
        n = n.strip()
        if v.strip():
            vv = v.strip().replace("_", "")
            mm = re.fullmatch(r"(?:\d+)?'([bBdDhH])([0-9a-fA-FxXzZ]+)", vv)
            if mm:
                nxt = int(mm.group(2), {"b": 2, "d": 10, "h": 16}[mm.group(1).lower()])
            else:
                nxt = int(vv, 0)
        out[n] = nxt
        nxt += 1
    return out


# ---- the trace a simulator run writes -----------------------------------------------------------------------------------
def trace_module(design: Path, out: Path) -> str | None:
    """SystemVerilog source of a module that writes ``<time> <value> <signal>`` to ``out`` for every value change of each state
    register in ``<design>/verif/fsm.yaml`` (and once at 1 ns for the initial value). Works in any simulator with $fopen
    and hierarchical references (Icarus and xsim); cocotb_run adds it to the build when FDA_FSM_TRACE names a directory.
    None when the design has no fsm.yaml. (Icarus under cocotb writes no VCD: the runner passes -none.)"""
    f = design / "verif" / "fsm.yaml"
    if not f.exists():
        return None
    sigs = [x["signal"] for x in (yaml.safe_load(f.read_text()) or {}).get("fsms", []) if not x["signal"].startswith("*.")]
    if not sigs:
        return None
    body = ["module fsm_trace_dump;", "  integer f;", f'  initial f = $fopen("{out.as_posix()}", "w");']
    for i, s in enumerate(sigs):
        body.append(f'  always @({s}) $fdisplay(f, "%0d %0d {s}", $time, {s});')
        body.append(f'  initial #1 $fdisplay(f, "%0d %0d {s}", $time, {s});')
    body.append("endmodule")
    return "\n".join(body) + "\n"


def read_trace(path: Path, wanted: list[str]) -> dict[str, list[tuple[int, int | None]]]:
    """The changes of ``wanted`` signals from a ``.fsmtrace`` file (as written by trace_module) or a VCD."""
    if path.suffix == ".vcd":
        return vcd_changes(path, wanted)
    out: dict[str, list[tuple[int, int | None]]] = {w: [] for w in wanted}
    for line in path.read_text(errors="replace").splitlines():
        t, v, sig = (line.split(None, 2) + ["", "", ""])[:3]
        if sig in out:
            out[sig].append((int(t), int(v) if v.isdigit() else None))
    return out


# ---- a VCD reader (value changes of the signals asked for) ---------------------------------------------------------------
def vcd_changes(path: Path, wanted: list[str]) -> dict[str, list[tuple[int, int | None]]]:
    """{wanted name: [(time, value | None for x/z), ...]} for each hierarchical name that matches ('*.tail' or the full name)."""
    ids: dict[str, list[str]] = {}            # VCD id -> the wanted names it carries
    scope: list[str] = []
    out: dict[str, list[tuple[int, int | None]]] = {w: [] for w in wanted}
    t = 0
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("$scope"):
                scope.append(line.split()[2])
            elif line.startswith("$upscope"):
                scope.pop()
            elif line.startswith("$var"):
                p = line.split()
                name = ".".join(scope + [p[4]])
                for w in wanted:
                    if (w.startswith("*.") and name.endswith(w[1:])) or name == w:
                        ids.setdefault(p[3], []).append(w)
            elif line.startswith("$enddefinitions"):
                break
        for line in f:
            line = line.strip()
            if not line or line[0] == "$":
                continue
            if line[0] == "#":
                t = int(line[1:])
            elif line[0] in "bB":
                val, _, ident = line[1:].partition(" ")
                for w in ids.get(ident.strip(), ()):
                    out[w].append((t, None if re.search(r"[xXzZ]", val) else int(val, 2)))
            elif line[0] in "01xXzZ" and len(line) > 1:
                for w in ids.get(line[1:], ()):
                    out[w].append((t, None if line[0] in "xXzZ" else int(line[0])))
    return out


def trace_to_sequence(changes: list[tuple[int, int | None]]) -> list[int]:
    """The distinct successive values of the register (x/z dropped), the first one being the initial state."""
    seq: list[int] = []
    for _, v in changes:
        if v is not None and (not seq or seq[-1] != v):
            seq.append(v)
    return seq


# ---- the check --------------------------------------------------------------------------------------------------------
def parse_vivado_log(path: Path) -> dict[str, dict]:
    """{state register: {'states': [...], 'encoding': 'sequential'}} from Synth 8-802 / 8-3354 and the state table between them."""
    out: dict[str, dict] = {}
    cur: list[str] = []
    in_tab = False
    for line in path.read_text(errors="replace").splitlines():
        if "State |" in line and "New Encoding" in line:
            in_tab, cur = True, []
            continue
        if in_tab:
            if line.startswith("---"):
                if cur:
                    in_tab = False
                continue
            p = [x.strip() for x in line.split("|")]
            if len(p) >= 3 and p[0]:
                cur.append(p[0])
        m = re.search(r"encoded FSM with state register '([^']+)' using encoding '([^']+)'", line)
        if m:
            out[m.group(1)] = {"states": cur, "encoding": m.group(2)}
            cur = []
    return out


def evaluate(design: Path, vcds: list[Path], vivado_log: Path | None = None) -> dict[str, Any]:
    cfgf = design / "verif" / "fsm.yaml"
    if not cfgf.exists():
        return {"design": design.name, "pass": False, "error": f"{cfgf}: write verif/fsm.yaml (states, transitions)"}
    cfg = yaml.safe_load(cfgf.read_text()) or {}
    fsms = cfg.get("fsms") or []
    viv = parse_vivado_log(vivado_log) if vivado_log else {}
    names = [f["signal"] for f in fsms]
    runs: dict[str, list[list[int]]] = {n: [] for n in names}
    for v in vcds:                                         # one run per file: no transition is read across two files
        ch = read_trace(v, names)
        for n in names:
            runs[n].append(trace_to_sequence(ch[n]))
    out_f = []
    for f in fsms:
        states = parse_enum((design / f["file"]).read_text(), f["enum"])
        by_val = {v: n for n, v in states.items()}
        seen, taken = set(), set()                         # covered if any run covered it
        for r in runs[f["signal"]]:
            seen |= {by_val[v] for v in r if v in by_val}
            taken |= {(by_val[a], by_val[b]) for a, b in zip(r, r[1:]) if a in by_val and b in by_val}
        out_f.append(_check_union(f, seen, taken, design, runs[f["signal"]], viv))
    ok = bool(out_f) and all(r["pass"] for r in out_f)
    return {"design": design.name, "traces": [str(v) for v in vcds], "fsms": out_f, "pass": ok}


def _check_union(cfg: dict, seen: set[str], taken: set[tuple[str, str]], design: Path, runs: list[list[int]],
                 viv: dict[str, dict]) -> dict[str, Any]:
    """check_fsm's verdicts for the union of several runs."""
    states = parse_enum((design / cfg["file"]).read_text(), cfg["enum"])
    by_val = {v: n for n, v in states.items()}
    legal = {(a, b) for a, b in (cfg.get("transitions") or [])}
    bad_names = sorted({n for pair in legal for n in pair if n not in states})
    waive = cfg.get("waive") or []
    no_reason = [w.get("item", "?") for w in waive if not str(w.get("reason", "")).strip()]
    waived = {str(w["item"]) for w in waive if str(w.get("reason", "")).strip()}
    reset = cfg.get("reset_state")
    unknown_vals = sorted({v for r in runs for v in r if v not in by_val})
    miss_states = [s for s in states if s not in seen and s not in waived]
    miss_trans = sorted(f"{a}->{b}" for a, b in legal if (a, b) not in taken and f"{a}->{b}" not in waived)
    unexpected = sorted(f"{a}->{b}" for a, b in taken
                        if legal and (a, b) not in legal and b != reset and f"{a}->{b}" not in waived)
    res: dict[str, Any] = {
        "name": cfg["name"], "signal": cfg["signal"], "n_states": len(states), "encoding": states,
        "states_hit": len(seen), "states_missed": miss_states,
        "transitions_listed": len(legal), "transitions_hit": len([1 for p in legal if p in taken]),
        "transitions_missed": miss_trans, "unexpected_transitions": unexpected, "values_outside_enum": unknown_vals,
        "waivers_without_reason": no_reason, "unknown_names_in_table": bad_names,
        "transitions_observed": len(taken), "runs": len(runs),
    }
    reg = next(iter(viv.values()), None) if viv else None
    if reg:
        res["vivado_extracted_states"] = len(reg["states"])
        res["vivado_encoding"] = reg["encoding"]
        res["vivado_states_match_enum"] = sorted(reg["states"]) == sorted(states)
    res["pass"] = not (miss_states or miss_trans or unexpected or no_reason or bad_names or unknown_vals)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design", help="design folder (has verif/fsm.yaml)")
    ap.add_argument("--trace", "--vcd", dest="vcd", action="append", required=True,
                    help="trace of one run: a .fsmtrace file (FDA_FSM_TRACE) or a VCD (repeat for several tests or seeds)")
    ap.add_argument("--vivado-log", help="synthesis log: cross-check the extracted FSM's state names")
    ap.add_argument("--json", help="write the evidence here")
    a = ap.parse_args(argv)
    rel = lambda p: Path(p) if Path(p).is_absolute() else ROOT / p
    rep = evaluate(rel(a.design), [rel(v) for v in a.vcd], rel(a.vivado_log) if a.vivado_log else None)
    if "error" in rep:
        print(f"FSM coverage: FAIL: {rep['error']}")
    for f in rep.get("fsms", []):
        print(f"FSM {f['name']} ({f['signal']}): states {f['states_hit']}/{f['n_states']}, "
              f"transitions {f['transitions_hit']}/{f['transitions_listed']}: {'PASS' if f['pass'] else 'FAIL'}")
        for k, label in (("states_missed", "state never visited"), ("transitions_missed", "legal transition never taken"),
                         ("unexpected_transitions", "transition taken that the table does not list"),
                         ("values_outside_enum", "state value outside the enum"),
                         ("waivers_without_reason", "waiver without a reason"),
                         ("unknown_names_in_table", "name in the table that is not in the enum")):
            for x in f[k]:
                print(f"    {label}: {x}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(rep, indent=2) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
