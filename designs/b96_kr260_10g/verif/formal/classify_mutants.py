#!/usr/bin/env python3
"""classify_mutants.py (brief 143c): sort the survivors of a flow/formal_mutation.py run on rm_gp.sby into the reasons a survivor is expected, so the mutation score is read for what it is.

    python3 designs/b96_kr260_10g/verif/formal/classify_mutants.py results/143c/mutation/rm_gp_safety_bmc.json     # prints the table, writes `survivor_classes` into the file

A survivor is a mutant the task did not fail on. Reasons, by the wires of the mutated cell (a rule, not a proof: a cell is classed by the first rule that matches):
  free_input     the cell drives or is a free input of the harness (reset, valid, data, lock): inverting or sticking a free input only chooses other inputs the solver already tries, or
                 removes some, so the set of behaviours is unchanged or smaller: an equivalent mutant for a safety check
  entry_data     the 74-bit entry's storage or its synchronised copies (g_ent[i], ent, u_data_*, head): the proof follows ONE bit of the entry (KB = 0; the other bit classes are
                 proved by run_formal.py with a different KB), so a mutation of another bit is outside the slice
  liveness       the pace counter, the slot, the lock chain: only the progress properties (progress_bmc) can see them, not the safety task
  other          none of the above: a gap in the properties, or a mutant that needs more depth than the task has, to be read one by one
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FREE = ("wrst", "rrst", "clr_w", "clr_r", "w_v", "w_os", "w_lock", "w_d", "w_c", "wclk", "rclk")
ENTRY = ("g_ent[", "dut.ent", "u_data_s", "u_data_h", "dut.head", "dut.w_ent", "ent_r")
LIVE = ("dut.pace", "dut.slot", "dut.u_lk", "lock_s", "dut.lock", "r_lock")


def classify(m: dict) -> str:
    names = list(m.get("wires") or []) + ([m["wire"]] if m.get("wire") else [])
    if m["src"].startswith("rm_gp_fv_top.sv") or (names and all(n in FREE or n.split(".")[-1] in FREE for n in names)):
        return "free_input"
    if any(k in n for n in names for k in ENTRY) or any(k in m.get("rtl", "") for k in ("w_ent", "ent_r", "ent[")):
        return "entry_data"
    if any(k in n for n in names for k in LIVE) or "pace" in m.get("rtl", ""):
        return "liveness"
    return "other"


def main(argv: list[str]) -> int:
    p = Path(argv[1])
    r = json.loads(p.read_text())
    counts: dict[str, int] = {}
    for m in r["mutants"]:
        if m["result"] != "survived":
            continue
        c = classify(m)
        m["class"] = c
        counts[c] = counts.get(c, 0) + 1
        print(f"{m['n']:>3} {c:<11} {m['mode']:<7} {(m.get('wires') or [''])[0][:32]:<32} {m['src'][:34]:<34} {m['rtl'][:50]}")
    r["survivor_classes"] = counts
    p.write_text(json.dumps(r, indent=1) + "\n")
    print(r["summary"], counts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
