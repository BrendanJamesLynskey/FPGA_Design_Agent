# results/b136: six "what if a human had disagreed" decisions, measured (brief 136)

Records and scripts behind [docs/what_if_decisions.md](../../docs/what_if_decisions.md): for six delegated decisions of 2026-11-21 (owner decision 23), the human alternative is tried where that is cheap (simulation, Lean, the repository's own records) and the consequence recorded. Nothing here ran on a board and no Vivado run was made. The machine-readable summary is [what_if.json](what_if.json).

## Records

| File | What it is |
|---|---|
| `run_mutants_ppm.py`, `ratematch_whatif_cocotb.py`, `merge_mutants.py`, `mutants_ppm.json` | scenario 1: twelve seeded bugs of `rate_match_gp.sv` (nine of brief 115's mutants and three added here) against the cocotb rate-matcher bench at 0, +-100 and +-300 ppm; the merged record, per point |
| `inputs_b127/`, `cut_through.py`, `cut_through.json` | scenario 2: brief 127's three records (PR #253, commit 6f603bb3, not merged, copied) and the arithmetic on them |
| `lean/run_lean.sh`, `lean/run_lean.log`, `lean/Probe33.lean`, `lean/Stronger.lean` | scenarios 3 and 5: the checksum theorem at 32 words and the RTL equations at 33; the bit-wise gray statement; run in a scratch copy of `formal/lean` |
| `latency_targets.py`, `latency_targets.json` | scenario 4: every recorded board run against E <= 16 and tick-to-trade <= 20 clocks, with the simulated and pre-registered figures |
| `eye_target.py`, `eye_target.json` | scenario 6: the committed eye scans against 0.75 UI, with the grid resolution and a bathtub interpolation |
| `build_what_if.py`, `what_if.json` | the assembly of the machine-readable summary from the records above |

## Reproduce

Each script reads the committed records or runs a simulation from the repository root, and writes its JSON next to itself; run them in this order (the first is the long one).

```
python3 results/b136/run_mutants_ppm.py --frames 500 --out part.json      # about 100 s a point, 5 points a mutant, 13 builds; the run here used three processes at once
python3 results/b136/merge_mutants.py part1.json part2.json ...            # writes mutants_ppm.json
python3 results/b136/cut_through.py
bash results/b136/lean/run_lean.sh                                        # needs elan (Lean 4.36.0), as formal/lean/README.md says
python3 results/b136/latency_targets.py
python3 results/b136/eye_target.py
python3 results/b136/build_what_if.py
```

## Known gaps and limits

- Scenario 1 is one stimulus, one seed and 500 frames a point: at +-100 ppm that is two slips a point, and two of the twelve bugs (`mut_overflow`, `mut_delete_in_frame`) are not reached at any point. The twelve bugs are not a sample of all bugs.
- Scenario 2 rests on brief 127's records from an unmerged PR; the frame-error rate is an assumed grid, and the real feed's packet lengths are unknown.
- Scenario 3's 33-word result is about the Lean transcription of the RTL equations, not a simulation of the RTL (which has no length input).
- Scenario 4 uses medians of per-link minima with a one-clock counter; `lat_all3_bypass` has not run on a board.
- Scenario 6: one module, one fibre, one session; the interpolation is an estimate under an assumed bathtub shape.
- No finer eye grid, no TX variant at 1e-9, no board time.
