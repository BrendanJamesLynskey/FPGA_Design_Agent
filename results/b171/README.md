# results/b171: Hardcaml scoping records

Recorded results for [docs/hardcaml_scoping.md](../../docs/hardcaml_scoping.md), brief 171: the `pipe_reg` and `credit_chan` library blocks written in Hardcaml (OCaml 5.3.0, Hardcaml v0.17.1), their generated Verilog run through the existing benches and formal wrappers, and compared with the hand-written SV in out-of-context Vivado 2026.1 synthesis on the Artix-7 and the Kria K26. Synthetic stimulus only; no board run.

## Records

| File | What | Made by |
|---|---|---|
| `ooc_compare.json` | 24 out-of-context synthesis builds (6 points of two blocks, SV and Hardcaml, a7 and k26): LUT, FF, WNS, WHS, Fmax estimate | `python3 tools/hardcaml/ooc_compare.py run` (heavy slot) |
| `pipe_reg_hc_sim.txt`, `credit_chan_hc_sim.txt` | pytest output of the existing benches on the generated Verilog | the blocks' `hardcaml/run_hc.sh` |
| `pipe_reg_hc_formal.txt`, `credit_chan_hc_formal.txt` | bounded model checks (depth 24) of the existing formal wrappers on the generated Verilog | same |
| `pipe_reg_lint.json` | lint of the generated Verilog | the flow's lint gate |
| `licences.txt`, `opam_list.txt` | package licences and the installed package versions | `tools/hardcaml/install_hardcaml.sh` |
| `probe/` | the agent fluency probe: Sonnet writing three small blocks in SV and Hardcaml | `python3 tools/hardcaml/probe/probe.py` (model calls; not free) |

## Reproduce

- Install the toolchain with `tools/hardcaml/install_hardcaml.sh` (about 25 minutes, needs `libgmp-dev` and `m4`).
- Generate the Verilog with each block's `ip_lib/<block>/hardcaml/run_hc.sh gen`, then run the comparison under a heavy slot (about 50 minutes for 24 builds, one thread, peak 3 GiB).
- The probe makes live model calls through the agent model table and cannot be replayed for free.

## Known gaps and limits

- Out-of-context synthesis only: no place and route, so the WNS and Fmax figures are synthesis estimates from single runs with no repeats.
- K26 Fmax above 725 MHz is not reachable: the BUFG minimum period on the xck26 -2LV is 1.379 ns (brief 199). The SV versus Hardcaml comparison there rests on WNS, LUT and FF.
- Formal evidence for the generated Verilog is bounded model checking only; the unbounded k-induction proofs do not close.
- Two blocks and six parameter points; the fluency probe has a ceiling effect (the tasks were too easy to separate the languages).
