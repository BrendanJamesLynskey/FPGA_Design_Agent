# 230: constraints complete before synthesis

Records, replays, probes and the labelled arm for brief 230: every top port and every clock source is accounted for before synthesis, and the flow writes the constraints it already knows
([docs/constraints_complete.md](../../docs/constraints_complete.md), [flow/known_constraints.py](../../flow/known_constraints.py)). Vivado 2026.1, xck26. Numbers are in the files named below and in the
report the planner holds; nothing here is a significance claim.

## Records

| File | What it is |
|---|---|
| `records_scan.json`, `scan_records.py` | records first: stage visits and gates calls of recorded agent runs that failed `post_synth_no_unconstrained_endpoints`, and what the new tools write or flag for each endpoint |
| `replay_p5/`, `replay_p5_start/` | brief 224 arm p5 run 1's design inputs (the state where it stopped; the starting state of a constraints visit), built through `post_synth` with the new flow; `records/` has the gates, `check_timing`, the two known XDC files and the reports; `records_224_run1/` the original failing `check_timing` |
| `elab_probe/` | what Vivado reports on an elaborated design and a synthesised one: `elab_fixture.sv` (one of each clock source), `probe.tcl`, per-design `out/*/probe_rtl.txt`, `report_clocks_*.rpt`, `unclocked_pins_*.txt`; `run_summary.txt` is the trimmed driver log |
| `false_positive_scan.json`, `false_positive_scan.py` | the completeness check on every committed design with an XDC |
| `preregistration.md`, `control_224_arm2.json`, `arm_table.py` | the labelled arm's pre-registration (written before any run), the control's graded outcomes and the table script |
| `arm_runs.json` | the labelled arm's per-run graded outcomes (5 runs; see Reproduce); the run records, the ledger (`cost_ledger.tsv`) and the aborted attempts are in `pilots/230/` |

## Reproduce

- Records: `python3 results/230_constraints_complete/scan_records.py results/230_constraints_complete <224 worktree> <209 worktree>` (the recorded runs live in those worktrees' `runs/`).
- Replay: `FDA_STOP_AFTER=synth flow/run_vivado.sh results/230_constraints_complete/replay_p5/p5_async_fifo base` under a heavy slot (`_handoff/take_heavy_slot.sh`), then read `build/base/gates.json`.
- Probe: `vivado -mode batch -source elab_probe/probe.tcl -tclargs <outdir> <top> <part> <rtl|both> <xdc> <ip tcl or -> <sources>`; set `PROBE_STEPS` to run named steps only.
- Arm: `pilots/230/run_all.sh` (one agent run per slot, at most 50 USD), then `python3 results/230_constraints_complete/arm_table.py results/230_constraints_complete/arm_runs.json runs <run ids>`.

## Known gaps and limits

- The records scan classifies endpoints by instance and port name against each run's final design; it is not a re-run of each visit. Only p5 run 1 was replayed through Vivado.
- The replay's remaining failing gate (TIMING-6 and TIMING-7, clock groups) is not written by any tool.
- The elaborated-design check crashed Vivado on a PS design and is not part of the build.
- The arm has 5 runs, not 9: it stopped on the 50 USD cap (56.88 USD spent including two aborted attempts and one killed duplicate launch, 17.0 USD of the total). The control ran an older agent and without brief 234's changes: the comparison is illustrative, and what changed between the two is 230 plus 234.
