# results/225_redpitaya: the Red Pitaya STEMlab 125-14 as a target board, its shell build, and two custom instruments (brief 225)

What this folder holds: the records of brief 225 on the owner's Red Pitaya STEMlab 125-14 (original generation, v1.1): the Vivado 2026.1 builds of the vendor's shell with a trivial
block patched in and of the unpatched shell (to say whose timing result it is), the records of the real `--harness claude_code` agent runs that wrote two custom instruments (a
frequency and period meter, a pulse and pattern generator) as blocks for that shell, and what an independent cross-check found in the agent's RTL. **Nothing here was run on the board**:
no board, instrument or network address was touched; every hardware result is pending the owner's board visit. Dates: 2026-11-26 (GMT). Tool: Vivado 2026.1; the agent runs used Claude Code
2.1.321 on the subscription (no cost is reported for such runs).

## Files

- `shell_trivial/`: `build.json` (the build id, the pinned vendor commit, the hashes, timing, utilisation, power, all read from the build's reports), `red_pitaya_top_utilization_placed.rpt`,
  `user_to.rpt` and `user_from.rpt` (the worst setup path into and out of the user block, from the routed checkpoint).
- `shell_two_instruments/`, `owner_scripts/`, `dry_run/`: the build with both instruments, the two owner scripts and their dry runs (below).
- `shell_baseline/`: the same `build.json` and utilisation for the vendor's own top with no patch and no block (only the version lines changed).
- `runs/<design>_r<n>[_failed_stage1]/`: from each real agent run, `summary.json`, `config.json`, `permissions.jsonl`, `role_usage.jsonl`, and where it matters `verif_gates.json` and the `design.xdc` it wrote.
  The run directories themselves are not committed (house rule). The agent's RTL that was kept is in `pilots/225/<design>/agent_*_rtl/`, beside the executor's cross-check test bench.
- The specs the agent was given are `pilots/225/<design>/spec.md`, generated from the register maps by `pilots/225/make_specs.py`.

## Shell build results (numbers as printed in the build reports and build.json)

Shell build (Vivado 2026.1, `xc7z010clg400-1`, vendor RedPitaya-FPGA at commit 728a4f37e9, project v0.94 for the Z10; one pass, about 20 minutes, `MemoryMax=8G`, default threads, nice 15):

| Build | WNS (ns) | TNS (ns) | Failing endpoints | WHS (ns) | LUTs | Registers | Block RAM tiles | DSPs | Power (W) |
|---|---|---|---|---|---|---|---|---|---|
| Vendor shell, unpatched (`shell_baseline`) | -5.335 | -3444.713 | 2724 | 0.05 | 9799 | 12013 | 36 | 28 | 1.907 |
| Shell with the trivial block (`shell_trivial`) | -5.338 | -3791.770 | 2925 | 0.019 | 9866 | 12188 | 36 | 28 | 1.911 |
| Shell with the two agent-written instruments, `rp_freqcount` in slot 7 and `rp_patgen` in slot 6 (`shell_two_instruments`, build id 3a50020d) | -5.659 | -3636.577 | 2992 | 0.018 | 10768 | 13205 | 36 | 28 | 1.905 |

- **The two-instrument build** (`shell_two_instruments`, about 19 minutes) is the image the owner's scripts load: `rp_freqcount` (`rp_freqcount.sv` from `agent_r1_rtl`) in slot 7 at 0x40700000, `rp_patgen` (the four files of `agent_final_spec_rtl`) in slot 6 at
  0x40600000, so a self-test loop (OUT1 into IN1) needs one load. Its timing is not met either (above), again with the vendor's generator FIFO as the worst path; the user blocks' own slack was not measured for this build (no heavy slot was free for the checkpoint
  report). The load scripts for both blocks are in `owner_scripts/<block>/load_3a50020d.sh` (they need the package folder with `fpga.bit.bin`, `redpitaya_checks.py` and `redpitaya_regs.py` beside them: `python3 -m hil.redpitaya_load script <package> --block <name> --slot <6|7>`
  writes them); `dry_run/` holds their `DRY_RUN=1` output (every board command printed, none run) and the board-side checks run against the models (mock, not evidence). The bitstream itself (`fpga.bit.bin`, 997,572 bytes) is not committed: `tools/rp_shell.py` rebuilds it.
- **Timing is not met, in the vendor's own logic.** The worst paths are in the shell's arbitrary-generator AXI FIFO writer (`i_asg/chA`, `i_asg/chB`, clocks `pll_adc_clk` and the 250 MHz `pll_dac_clk_2x`), 17 to 21 logic levels
  of carry chains on a 32-bit address counter. The unpatched vendor shell on the same tool gives the same worst slack (-5.335 against -5.338 ns), so the failure is the vendor's design on Vivado 2026.1 (the vendor builds with 2025.1),
  not the patch. **The user block itself meets timing**: worst setup slack out of it +0.120 ns, into it +3.357 ns (`user_from.rpt`, `user_to.rpt`). The patch added 201 failing endpoints in the same vendor logic (a placement difference, not
  investigated). What this means on the board is not known: the failing paths belong to the deep-memory generator (the shell's DAC FIFO), which the instruments do not use, but a build with unmet timing is not claimed to work.
  The package's load script says so before it asks the owner to load.
- The vendor's block-design and IP scripts refuse any Vivado but 2025.1 with their own version check; `tools/rp_shell.py` changes that one line to accept the running version (recorded in `build.json`).
  Whether other 2025.1-to-2026.1 differences matter to the shell's behaviour on the board is not known.
- Smoke design for the board file (`results/95_boards/redpitaya_stemlab_125_14/smoke.json`): post-route timing met, DRC and methodology clean, bitstream written, 126.8 s.

## The agent runs (first-time results, with their interventions)

All runs: `python -m agent run pilots/225/<design>/spec.md --board redpitaya_stemlab_125_14 --no-shell --review off --interview off --verif-level V2 --harness claude_code --stop-after 2`
(stages 0 to 2: clarify, plan, RTL, tests and the stage-2 gates; the block is then built into the shell by `tools/rp_shell.py`). The default Claude Code model for the roles was `claude-haiku-5-5`.

| Run (folder under `runs/`) | Design | Spec version | Stage 1 constraints gate | Stage 2 | Wall | Tokens | Independent cross-check of its RTL |
|---|---|---|---|---|---|---|---|
| `rp_freqcount_r1` | frequency meter | first (no "not a top" paragraph) | passed (it left `design.xdc` empty) | **passed**, 2 visits | 1009 s | 2,829,349 | pass (`pilots/225/rp_freqcount/agent_r1_rtl`) |
| `rp_patgen_r1_failed_stage1` | pulse generator | first | **failed**: pinned `dac_a` to the DAC pins and `clk` to the board clock pin | not reached | 293 s | 941,759 | none |
| `rp_patgen_r2` | pulse generator | first "not a top" paragraph | passed | **passed**, 3 visits | 1269 s | 3,789,182 | **fail**: negative levels (14-bit field) read as large positive; bus latency 2 clocks (`agent_r2_rtl`) |
| `rp_freqcount_r2_failed_stage1` | frequency meter | first, plus register-convention and latency notes | **failed**: `create_clock` on `clk` | not reached | 266 s | not recorded | none |
| `rp_patgen_r3_failed_stage1` | pulse generator | first "not a top" paragraph, plus the convention and latency notes | **failed**: `create_clock` on `clk` | not reached | 261 s | not recorded | none |
| `rp_patgen_r4_final_spec` | pulse generator | final (strict paragraph, conventions, latency "exactly one clock") | passed | **not passed**: its synthesis gate was refused 100+ times because another session's Vivado held the one-job limit; V0 to V2 verification passed; I stopped it after about 2 h | not finished | about 3.28 M (model calls in the trace) | **pass** (`agent_final_spec_rtl`) |
| `rp_freqcount_r3_final_spec` | frequency meter | final | passed | **not passed**: same refusal; V0 to V2 passed; stopped by me | not finished | about 2.94 M | **fail** on the first read after reset (rdata 0, err X); the later checks pass; not root-caused (`agent_final_spec_rtl_fails_xcheck`) |

Runs r1 to r3 of the pulse generator and r1 to r2 of the frequency meter have `summary.json`; r4 and r3 were stopped before they finished, so their folders hold `config.json`, `permissions.jsonl`, `role_usage.jsonl`, `verif_gates.json` and `last_trace_line.json` only.
The RTL used in the shell build is the frequency meter's r1 (it passes the cross-check) and the pulse generator's final-spec RTL (it passes the cross-check); neither passed the stage-2 gate on the spec it was built from
(r1 did, on the first spec; the final-spec pulse generator did not reach the synthesis gate).

What this says:

- **The in-shell block does not fit the board-top constraints gate.** The agent treats the block's ports as a board top. Without a sentence in the spec saying the block has no pins, no clock and no timing constraints of its own, the gate
  `check_constraints` failed stage 1 in two of the three runs made without it (the third left `design.xdc` empty and passed). With a first version of the paragraph it passed once and failed once; with the strict version (no `create_clock` either) it
  passed twice. The spec was changed after failures, so these are interventions, not first-time results; the one clean first-time result is `rp_freqcount_r1` (stage 2 passed on the spec as first written).
- **The agent's own tests did not catch a spec gap.** The first pulse-generator RTL passed the agent's V2 verification, yet an independent cross-check (written by the executor from the spec and the reference model, not from the agent's tests)
  showed it reads a signed level written as a 14-bit two's-complement field (0x3060 for -4000) as a large positive 32-bit number and clamps it to +LIMIT: the spec did not say how a negative level is written (the frequency counter's spec did).
  The convention is now written once for every signed 14-bit register; the final-spec RTL passes the cross-check (see the table).
- **Latency.** The pulse generator's first RTL answered a bus access two cycles after it, where the spec said the next cycle; the frequency counter answered in one. The shell's bus is ack-based, so a slower slave is legal for the shell, but it was not what was asked.
  The spec now says "exactly one clock".

## Reproduce

```
python3 pilots/225/make_specs.py                       # the two specs from the register maps (no heavy slot)
python3 tools/rp_shell.py prepare <dir> [--block FILE.sv --slot7 MODULE --slot6 MODULE] ; python3 tools/rp_shell.py build <dir>   # heavy slot: Vivado impl, peak about 6G, about 20 minutes
python3 tools/rp_shell.py package <dir> <out>          # fpga.bit.bin and build.json
python3 -m hil.redpitaya_load script <out> --block rp_freqcount [--expect-hz F]     # the owner's load-and-check script (never run by the agent)
python3 -m hil.redpitaya_load dry-run --block rp_freqcount                          # the board-side checks against a model: marked mock, never evidence
cd pilots/225/<design> && iverilog -g2012 <crosscheck_tb.sv> <agent rtl>.sv && vvp a.out   # the independent cross-checks
```

The agent runs are paid subscription runs and are not regenerated by a command here; their records are in `runs/`. The vendor repository is fetched at the pinned commit by `prepare` (network needed, nothing of the vendor's is committed).

## Known gaps and limits

- **No hardware result.** The board was not touched. Whether the shell with the trivial block, the smoke design, or either instrument works on the board is not known; the load script (`hil/redpitaya_load.py`) is written for the owner and was only dry-run
  (`DRY_RUN=1`, a ssh that fails the test if called; the board-side checks against behavioural models, marked mock).
- **Timing of the shell is not met** (above), on the vendor's own paths. The first thing to try is Vivado 2025.1 for the shell build, or the vendor's constraints for the deep-memory path; neither was tried.
- **The instruments' RTL stops at stage 2.** The agent runs stopped after stage 2 by design; the bitstreams of the instruments (`rp_freqcount` in slot 7 and `rp_patgen` in slot 6 of one shell build) are built by `tools/rp_shell.py` from the agent's RTL, with the same unmet vendor timing.
  No agent run reached stage 9 or a board; no ILA or other debug core is in the shell build.
- **No repeated-run statistics.** The same spec gave a pass and a failure of the stage-1 gate within one hour, so the gate result is not a stable property of the spec. The two final-spec runs were stopped before the stage-2 synthesis gate could run (another session's Vivado job held the one-job limit), so no run of the final spec has a recorded stage-2 pass.
- **The frequency meter's final-spec RTL failed my cross-check on the first read after reset** (rdata 0, err X in simulation); the r1 RTL, used in the shell build, passes it. Not root-caused.
- The frequency counter's accuracy is the board's 125 MHz oscillator's, which the vendor does not state for this generation; the lab file gives no `accuracy_ppm` for it, so the plan treats a ppm claim as needing an independent instrument.
- DAC swing into a high-impedance input (IN1) on the original generation is not stated by the vendor; the self-test starts at 0.25 V.
- Model reference: `hil/redpitaya_models.py` models what the spec says in arithmetic; it is not the RTL and not evidence about it.
