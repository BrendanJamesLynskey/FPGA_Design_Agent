# results/ultrafast

Measured on 2025.2, superseded by `results/f0a_2026_1`.

Build results for brief 04e: T1 (`designs/t1_dimmer_counter`, **base** variant, the same sources as F0A, build
stamp `dfd4624e`) rebuilt with `flow/run_vivado.sh designs/t1_dimmer_counter base` through the staged flow
(`flow/build.tcl` with the UltraFast stage reports; `flow/gates.py` grouped by stage), then collected with
`flow/summarise.py designs/t1_dimmer_counter --out results/ultrafast`. Vivado 2025.2, local build PC, working tree
of branch `ultrafast-gates` on top of `20e0aeb`.

## Records

| File | What |
|---|---|
| [t1_dimmer_counter.md](t1_dimmer_counter.md) | The summary table: every stage and gate, timing, utilisation, power with its environment, run time per stage, memory |
| `t1_dimmer_counter_base.json` | Everything the table is made from: `gates` (flow/gates.py, with `stages`) and `run` (the runner's run.json) |

## Comparison with F0A: withdrawn

This README used to hold a table comparing this build with F0A (timings, utilisation, power, run time and memory per stage)
and an explanation of the change in the power figures. Every figure in it came from an earlier Vivado release and cannot be
re-measured: the flow now writes the Vivado 2026.1 records, which always include the UltraFast stage reports, so the paired
cost of those reports can no longer be separated. The comparison is withdrawn rather than relabelled. The current numbers for
the same T1 sources are in [results/f0a_2026_1](../f0a_2026_1/README.md). What stays here is the raw record the figures came
from (`t1_dimmer_counter_base.json`) and the generated table made from it (`t1_dimmer_counter.md`), both kept as made and not
to be quoted.

## Reproduce

`flow/run_vivado.sh designs/t1_dimmer_counter base`, then `flow/summarise.py designs/t1_dimmer_counter --out results/ultrafast`.
They need Vivado and a heavy slot; on the current install they write Vivado 2026.1 records, so these cannot be regenerated as they are.

## Known gaps and limits

- Superseded by [results/f0a_2026_1](../f0a_2026_1/README.md): the figures here came from an earlier Vivado release and the paired cost of the UltraFast reports was withdrawn, not re-measured.
- One build each of the compared builds; the usual run-to-run variation of a few seconds applies to the timings.
- The power comparison changes the thermal environment, not the design, as the section above explains.
