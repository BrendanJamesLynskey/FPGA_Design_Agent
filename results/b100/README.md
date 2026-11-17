# results/b100: RapidWright in the agent, measured

Recorded results for [designs/b100_rapidwright](../../designs/b100_rapidwright/README.md): stage 0 (does RapidWright read and write Vivado 2026.1
checkpoints), three capabilities compared with Vivado alone on the K26 (`xck26-sfvc784-2LV-c`), and two agent runs, with and without the
RapidWright tools. Vivado 2026.1 is the referee for every number; RapidWright 2026.1.2 (JRE of Vivado 2026.1). No board was used.
Checkpoints (`*.dcp`), bitstreams and readable EDIF are not committed (git-ignored): they are vendor-format files that the scripts regenerate.

## Records

| Path | What | Made by |
|---|---|---|
| `summary.json` | the one record the README, handover.yaml and what_we_found.md quote; built only from the files below | `designs/b100_rapidwright/scripts/make_summary.py` |
| `summary_c23.json` | per arm and perturbation: Vivado's WNS (whole design, MAC to PCS, PCS to GT), hold slack, LUT, FF, achieved period, run times | `scripts/summarise_c23.py results/b100/c23 results/b100/summary_c23.json` |
| `s0/` | stage 0: the routed checkpoints' run records for both parts before and after a RapidWright round trip, route status, DRC, bitstream sizes, JVM memory peaks | `flow/rw/roundtrip.py`, `scripts/impl.tcl`, `flow/rw/referee.tcl` |
| `c1/` | capability 1: the out-of-context block, its relocations (`rw_mv_*.log`), the stamped and Vivado-alone four-copy runs (`stamp_*`, `alone_*`: run record, timing report, `*_blocks.csv` with every internal endpoint's delay), `summary.json` (endpoint comparison), the scans of valid relocation sites (`scans/`), and the failed attempts that changed the design (`failed_direct_ports/`, `first_pass_3_40/`) | `scripts/run_c1.sh` |
| `c23/` | capabilities 2 and 3 on the chain: for each arm (`base`, `place`, `placew`, `rwr`, `fixed`) and perturbation (`s0`, `s1`, `s2`): run record, `*_chain.json` (three path-class slacks), timing, hold, route status, DRC, utilisation, RapidWright logs; `crit_*_nets.txt` (the nets on Vivado's worst paths); `first_pass_bugs/` (runs from before a bug was fixed, kept as evidence) | `scripts/run_c23.sh` |
| `agent/a/`, `agent/b/` | stage 2: the task text, the Claude Code stream, the tool audit log, the agent's final message, the final design files, the baseline build record; `agent/a_attempt*` are runs stopped by a tool bug, kept | `agent_run/run_arm.py` |
| `dev/xck26_layout.txt` | the K26's clock regions and slice columns, read from Vivado | a one-off Vivado query, recorded for the site choices |

## Reproduce

- Install: `tools/rapidwright_env/setup.sh` (pinned in `flow/rapidwright_pin.py`). Run each script under a heavy slot (Vivado impl, peak 4G).
- Run times on the shared PC (Vivado one thread, other sessions running): an out-of-context block 6 to 8 minutes; a four-copy run 10 to 35 minutes; a chain run 6 to 13 minutes;
  a RapidWright step 15 to 75 seconds; an agent run 20 to 50 minutes (builds in the flow take 13 to 31 minutes).
- Wall times vary by a factor of three between runs of the same size because other sessions use the machine; compare them only within one run's own table.

## Known gaps and limits

- "Seeds" are 0.01 ns steps of the target period, because Vivado's placer has no seed parameter; two to three per capability.
- Stage 2 is one run per arm.
- No power report and no board result exist for any run.
