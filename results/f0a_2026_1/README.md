# results/f0a_2026_1

T1 (`designs/t1_dimmer_counter`) built on **Vivado 2026.1** (Basic licence tier) by brief 48, collected with
`flow/summarise.py` by brief 49. Built with `flow/run_vivado.sh designs/t1_dimmer_counter base` and `... ila` on branch
`b48-vivado-2026-1` (commit `b9db73b`, clean tree), local build PC, 6 GB cap (base at 4 threads, the ILA build at 2). The
ILA build uses the IP route of brief 48 (one ILA IP, the 13 probes packed into 2 ports), because `create_debug_core` is refused on
the Basic tier. The post-route QoR-assessment gate is absent on Basic (`qor_unavailable_*.txt`), not passed.

## Records

| File | What |
|---|---|
| [t1_dimmer_counter.md](t1_dimmer_counter.md) | The summary table: gates, timing, utilisation, ILA cost, power, run time, memory |
| `t1_dimmer_counter_base.json`, `t1_dimmer_counter_ila.json` | Everything the table is made from: `gates` (flow/gates.py) and `run` (the runner's run.json) |
| `t1_dimmer_counter_ila_probe_map.txt` | Which signal is on which ILA probe port and bit offset |

These are the builds programmed in [results/f0b_2026_1](../f0b_2026_1/README.md). One build each; the WNS differences
from the earlier release's builds are single runs and not a trend.

## Reproduce

`flow/run_vivado.sh designs/t1_dimmer_counter base` and `... ila` (Vivado 2026.1, Basic licence tier, heavy slot, 6 GB cap), then
`flow/summarise.py designs/t1_dimmer_counter --out results/f0a_2026_1`. The board part is in [results/f0b_2026_1](../f0b_2026_1/README.md).

## Known gaps and limits

- One build of each variant, so a WNS difference from the earlier release's builds is a single-run difference and not a trend.
- The ILA build uses the IP route of brief 48 (13 probes in 2 ports), not `create_debug_core`, which the Basic tier refuses; its cost is not comparable with a debug-core build.
- The post-route QoR-assessment gate is absent on the Basic tier, not passed.
- Power is vectorless (no activity file).
