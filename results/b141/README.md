# results/b141: phase 0 of the application-optimised DDR2 scheduler (brief 141)

Recorded runs of `designs/m141_ddr2_sched` made for brief 141: the simulation measurements of the scheduler's two policies against a behavioural DDR2 timing model written from the Micron MT47H64M16 data sheet, and the SymbiYosys proof and mutant runs.
Everything here is simulation or formal; nothing is a board or a Vivado result, and the plan that explains them is [docs/memory_controller_plan.md](../../docs/memory_controller_plan.md).

## Records

| File | What | Made by |
|---|---|---|
| `sim_summary.json` | one entry per run (policy, address map, traffic pattern, timing profile): read latency distribution in clocks and nanoseconds, data-bus utilisation, bandwidth, row-hit rate, longest wait, refresh count and gap, and the model's violation counts | `designs/m141_ddr2_sched/tests/m141_measure.py` |
| `formal_full.json` | every formal job of the full set: the proofs, the covers and the mutants, with the engine, depth, seconds and the assertions that failed for each mutant | `designs/m141_ddr2_sched/verif/formal/run_formal.py --set full` |

The readable tables made from them are in [designs/m141_ddr2_sched/docs/results.md](../../designs/m141_ddr2_sched/docs/results.md) (generated, not typed).

## Reproduce

```
python3 designs/m141_ddr2_sched/tests/m141_measure.py --json results/b141/sim_summary.json
python3 designs/m141_ddr2_sched/verif/formal/run_formal.py --set full --json results/b141/formal_full.json
python3 designs/m141_ddr2_sched/tests/make_results_md.py
```

Needs Icarus Verilog 12 and, for the proofs, the pinned OSS CAD Suite (the release CI uses). No heavy slot: single-process simulation and solver runs, about three quarters of an hour for the measurements and about half an hour for the proofs on a loaded machine.

## Known gaps and limits

- No board, no PHY, no MIG and no Vivado: the latencies are clocks of the command bus in simulation, from the request handshake to the first data beat, without the PHY's own pipeline.
- The model is written from the data sheet by the same author as the scheduler and its constants come from one reading of the data sheet; the data sheet values and their rounding are in `tests/m141_timing.py`. JEDEC's refresh postponement allowance was not checked against the standard's text.
- One seed per run; the traffic is synthetic (random, sequential, copy, bursts, hazard stress), not a recorded application.
- The proof of bounded response is a bounded model check at small parameters; the response bound at real parameters is measured, not proved.
