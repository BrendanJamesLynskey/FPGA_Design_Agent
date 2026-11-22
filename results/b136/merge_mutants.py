#!/usr/bin/env python3
"""Merge the partial outputs of run_mutants_ppm.py (run as several processes in parallel, each with --out) into results/b136/mutants_ppm.json.
    python3 results/b136/merge_mutants.py part1.json part2.json ..."""
import json
import sys
from pathlib import Path

parts = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
order = ["unmutated", "mut_overflow", "mut_underflow", "mut_gray_step", "mut_unsynced_pointer", "mut_wrong_entry", "mut_insert_in_frame", "mut_delete_in_frame", "mut_delete_any", "mut_no_pop", "mut_no_delete", "mut_delete_late", "mut_no_stall"]
by = {m["name"]: m for p in parts for m in p["mutants"]}
out = dict(frames_per_point=parts[0]["frames_per_point"], points_ppm=parts[0]["points_ppm"], mutants=[by[n] for n in order if n in by])
Path(__file__).with_name("mutants_ppm.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["mutants"]), "mutants merged")
