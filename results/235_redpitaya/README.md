# results/235_redpitaya: Red Pitaya follow-ups (brief 235): why the vendor shell misses timing, the goal kind "block for a shell", the two instruments re-run, the board-visit pack

> **Partly replaced: see [results/243_redpitaya](../243_redpitaya/README.md) (2026-11-27).** Build `170300fd` loaded but every read of its two blocks returned 0 at the board (the vendor's clock-crossing bridge reads the answer after the block has dropped it); the owner scripts and the owner pack here are replaced by those for build `d2f617ca`. The shell-timing study, the goal kind and the agent runs below stand.

What this folder holds: the records of brief 235, which follows brief 225 ([results/225_redpitaya](../225_redpitaya/README.md)). **Nothing here was run on the board**: no board, instrument or network address was touched; every hardware result is still pending the owner's board visit.
Dates: 2026-11-26 and 2026-11-27 (GMT). Tools: Vivado 2026.1 and 2025.2 (installed; the vendor's scripts name 2025.1, which is not installed), Claude Code 2.1.321 on the subscription (the agent runs report no dollars).
The vendor shell is RedPitaya-FPGA at the pinned commit 728a4f37e9 (project v0.94, Z10 build, `xc7z010clg400-1`).

## Files

- `shell_timing/<build>/`: for each shell build the `build.json` (id, hashes, timing, utilisation, power, from the build's own reports), the head of the routed timing summary and the utilisation report. Build `A` also holds the worst paths of both
  big clock domains (`path_1x.rpt`, `path_2x.rpt`), the clock-interaction report, the ignored-exceptions report, the failing endpoints grouped by block (`failing_endpoints_by_block.txt`) and the paths into and out of each block.
  `F_*` and `G_*` hold the same for the later builds (`G` is the image the owner pack is for).
- `runs/<design>_r<n>/`: from each real agent run `summary.json`, `config.json`, `permissions.jsonl`, `role_usage.jsonl`, `verif_gates.json` and the `design.xdc` it wrote. The run directories themselves are not committed (house rule). The agent's RTL is in
  `pilots/225/<design>/agent_235_r<n>_rtl/`, beside brief 225's independent cross-checks (`crosscheck_tb.sv`), which these four runs all pass.
- `owner_scripts/<block>/load_170300fd.sh` and `dry_run/`: the owner's load-and-check scripts for the final image and their `DRY_RUN=1` output (every board command printed, none run) and the board-side checks against the models (mock, not evidence).
  The scripts in `results/225_redpitaya/owner_scripts/` are for the older image `3a50020d` (its timing is the unmet one, the old RTL) and are superseded.
- [owner_pack.md](owner_pack.md): the one page for the board visit.

## 1. Shell timing: why the vendor shell misses, and what is left

Builds (two-instrument image: `rp_freqcount` in slot 7, `rp_patgen` in slot 6; same RTL in A, B and D, the final-spec runs' RTL in F and G; one pass each, `MemoryMax=8G`):

| Build | Vivado | Overlay | Directives | WNS (ns) | Failing endpoints | WHS (ns) | Build id |
|---|---|---|---|---|---|---|---|
| vendor shell, no patch (brief 225) | 2026.1 | no | default | -5.335 | 2724 | 0.05 | cfe374f0 |
| A: two instruments (brief 225's image, rebuilt: same build id) | 2026.1 | no | default | -5.659 | 2992 | 0.018 | 3a50020d |
| B: the same sources | 2025.2 | no | default | -5.655 | 2390 | 0.05 | e9756c33 |
| D: the same sources | 2026.1 | yes | default | -0.059 | 1 | 0.020 | bca65422 |
| E: the final-spec RTL (freqcount r1, patgen r1) | 2026.1 | yes | default | -0.101 | 8 | 0.059 | 501b7eb0 |
| F: as E | 2026.1 | yes | Explore | -0.049 | 4 | 0.037 | c330ca4c |
| **G: freqcount r2 + patgen r1, the final image** | 2026.1 | yes | Explore | **+0.016** | **0** | **+0.038** | **170300fd** |

**The cause is not a dropped clock-crossing constraint and not the tool version; it is real logic in the vendor's own instruments.** The evidence, from build A (every number is in `shell_timing/A_2026.1_no_overlay/`):

- *Clock interaction.* The failing paths are all same-clock paths, not crossings: `pll_dac_clk_2x` (250 MHz, the AXI clock of the deep-memory ports) to itself, WNS -5.659 ns, 2192 of 5000 endpoints; `pll_adc_clk` (125 MHz) to itself, -1.281 ns, 800 of 29821. Every crossing between clocks that the table lists
  is met (+0.426 ns and above), and the clock pairs the vendor waives show as ignored, not as timed.
- *Where.* Of 2992 failing endpoints: 1329 in the generator's AXI writer at 4 ns (worst -5.659; the path is a 32-bit address computation, 18 logic levels, 13 of them CARRY4: 9.49 ns of data path against 4 ns), 863 in the two AXI master bridges to the HP2 and HP3 ports
  (`ps/axi_master_2`, `ps/axi_master_3`), 698 in the generator's waveform logic and the reader at 8 ns (worst -1.281), 72 in the oscilloscope's decimator and calibration, 1 in the PDM, and 29 in our two blocks (worst -0.276 ns, patgen's sequencer; freqcount -0.093 ns).
  `failing_endpoints_by_block.txt` has the grouping.
- *Version.* The same sources on the installed 2025.2 give -5.655 ns (B), against -5.659 ns on 2026.1 (A): the same failure, so it is not a 2026.1 effect. 2025.1, the version the vendor names, is not installed and was not tried; whether it differs is not known.
  What the vendor's version check does: its block-design script and two IP scripts compare `set scripts_vivado_version 2025.1` with the running Vivado and, if they differ, print an error and stop before building anything. `tools/rp_shell.py` changes that one variable to the running version
  (recorded in `build.json`); the check guards the script's block-design commands, not the design's logic, and nothing else in the vendor's files is changed.
- *Constraints that match nothing.* The vendor's constraint file names `i_asg/ch*/inst_axi_dac/dac_rd_clr_r*/D`, a register that does not exist in its RTL (no source file contains `dac_rd_clr`), and others that belong to other models (`spi_done_csff`, `exp_p_io[8..10]`, `dac_clk_2x`); Vivado warns and skips them. None of them is on a failing path.
  So a missing exception is not what fails the shell. The vendor's shell on the Z10 simply does not close at 250 MHz on a speed-grade -1 part.

**The fix, in our own overlay, and what it claims.** [fda_overlay.xdc](../../boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc) (read after the vendor's files by `tools/rp_shell.py prepare --overlay`; nothing of the vendor's is edited) leaves the vendor's arbitrary-generator logic, its oscilloscope and the two AXI bridges
out of the timing analysis (two `set_false_path` over the leaf cells of `i_asg`, `i_scope`, `ps/axi_master_2`, `ps/axi_master_3`; the comments in the file give the reason and the limit). With it, on build A's routed design (checked without rebuilding, `overlay_applied_to_A_routing.rpt`) only 30 endpoints still fail, all in our two blocks.
The image is built for the board as a target: the owner's block is the instrument; the vendor's scope and generator are not used and nothing in the owner's scripts writes their registers (they read zero after the load). So, for build G:

- **Met, with those exclusions: WNS +0.016 ns, WHS +0.038 ns, 0 failing endpoints.** Power 1.906 W, 10632 LUTs, 13434 registers, 36 block RAM tiles, 28 DSPs (utilisation of the placed design). The two blocks' own paths are inside the same figure: no endpoint anywhere in the design is below +0.016 ns; their per-block slack was not reported separately for G (the report job was dropped for slot time).
- **What this does not say.** The vendor's generator (its waveform engine and its deep-memory AXI mode) and the oscilloscope are not claimed to work with this image loaded: their paths fail by up to 5.7 ns and are not analysed here. If either were started (the owner's scripts never do), no timing result stands behind it. The margin of the figure is 16 ps on the slow
  corner at 125 MHz; it is a result of this one place-and-route run (Vivado is deterministic for the same inputs and tool version: build A reproduced the earlier build id 3a50020d with the same -5.659 ns), not a statement about every run. The methodology report still has three critical warnings that belong to the vendor's shell (TIMING-6, -7, -17); the DRC report is in `G_*`.
- **Why Explore.** Without it the same constraints leave the blocks 0.05 to 0.1 ns short (D: patgen's sequencer, -0.059; E and F: freqcount's span register reset, -0.101 and -0.049; those paths are 12 to 15 logic levels of the agent's RTL at 8 ns). `tools/rp_shell.py prepare --explore` turns on the Explore directives for placement, physical optimisation and routing in our copy of the vendor's build script; the first
  Explore run (F) still missed by 0.049 ns, and G (the other freqcount RTL from the second run) met. So the met result depends on the RTL variant and the directive, and was found by trying; it is not a property of the design.

## 2. Goal kind "block for a shell"

Brief 225's constraints gate (`check_constraints`) treated a block as a board top: it failed stage 1 in 3 of 7 runs (pins on the block's ports, `create_clock` on `clk`). `python -m agent run <spec> --board redpitaya_stemlab_125_14 --block-for-shell` now says the design is a block for a supplied shell: the gate checks the block's ports, directions and widths against
[shell.yaml](../../boards/redpitaya_stemlab_125_14/shell/shell.yaml) (`FDA-BLK-4..6`), and `design.xdc` may be empty and may not carry a pin, a clock or a timing command (`FDA-BLK-1..3`). Tests: [agent/tests/test_235_block_for_shell.py](../../agent/tests/test_235_block_for_shell.py) (19). Docs: [docs/agent.md](../../docs/agent.md#the-red-pitaya-as-a-target-and-an-instrument-brief-225).
In the four runs below the gate passed 4 of 4 at stage 1 (each run's `design.xdc` is comments only). Four runs are a count, not a rate; the specs already carried brief 225's "block, not the board's top" paragraph, so these runs do not separate the new kind from the paragraph. It was not run on a spec without it.

## 3. The instruments re-run on their final specs (first-time results, no intervention)

`python -m agent run pilots/225/<design>/spec.md --board redpitaya_stemlab_125_14 --block-for-shell --review off --interview off --verif-level V2 --harness claude_code --stop-after 2`, default Claude Code model `claude-haiku-5-5` for every role, two runs per design, one run at a time, each under a heavy slot (`FDA_HEAVY_SLOT` exported, `FDA_PROMPTS_DIR` the pinned prompts).

| Run | Stage 1 constraints gate | Stage 2 | Visits to stage 2 | Wall (s) | Tokens | Independent cross-check of its RTL |
|---|---|---|---|---|---|---|
| `rp_freqcount_r1` | passed | **passed** | 1 | 799 | 2,590,268 | pass (`agent_235_r1_rtl`) |
| `rp_freqcount_r2` | passed | **passed** | 5 | 1696 | 3,942,646 | pass (`agent_235_r2_rtl`) |
| `rp_patgen_r1` | passed | **passed** | 2 | 1153 | 3,099,665 | pass (`agent_235_r1_rtl`) |
| `rp_patgen_r2` | passed | **passed** | 4 | 1479 | 4,519,551 | pass (`agent_235_r2_rtl`) |

All four passed stages 0 to 2 including the stage-2 synthesis gate, and the cross-check written in brief 225 from the spec (not from the agent's tests). The final-spec runs of brief 225 had not reached the synthesis gate (another session's Vivado held the one-job limit); these did.
**Alone was not possible:** other sessions' Vivado jobs (briefs 230, 213, 214, 239) held a slot continuously; I waited 90 minutes (18:58 to 20:32) for a window with no other Vivado, then ran with one alongside, and between my own runs waited for slots again. Wall times are therefore not clean timings.
Hardware results: none.

**The frequency meter's first read after reset, root-caused.** Brief 225's `agent_final_spec_rtl_fails_xcheck` read 0 with `err` X on its first access (the ID register). Cause: it decodes the bus address in a Verilog `always @(*)` block, which does not run at time 0; the cross-check's first read is at address 0, the address bus's initial value, so the decode never ran and its select signal stayed X until the address changed.
Two independent changes each remove it (`always_comb` in place of `always @(*)`, or a first read away from the initial address): both give `XCHECK PASS` ([hil/tests/test_235_redpitaya_followups.py](../../hil/tests/test_235_redpitaya_followups.py), iverilog). It is a simulation-only difference (a synthesised design has no time-zero gap), so the RTL would have worked on the board; it still matters for simulation and is what a
`always_comb` rule would have prevented. None of the four new RTL sets uses `always @(*)`.

## Reproduce

The shell builds need a heavy slot and the network; the agent runs are paid subscription runs. Each command below reproduces one family of results in this folder.

```
# shell builds (heavy slot each: Vivado impl, declared peak 4G, about 15 to 25 minutes, network needed for the vendor repository at the pin)
R=pilots/225
python3 tools/rp_shell.py prepare <dir> --block $R/rp_freqcount/agent_235_r2_rtl/rp_freqcount.sv --block $R/rp_freqcount/agent_235_r2_rtl/schmitt_edge.sv \
    $(for f in $R/rp_patgen/agent_235_r1_rtl/*.sv; do echo --block $f; done) --slot7 rp_freqcount --slot6 rp_patgen \
    --overlay boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc --explore        # build G; drop --overlay and --explore for A; add --vivado on build for 2025.2 (B)
python3 tools/rp_shell.py build <dir> [--vivado /opt/Xilinx/2025.2/Vivado/bin/vivado] ; python3 tools/rp_shell.py package <dir> <out>
python3 -m hil.redpitaya_load script <out> --block rp_freqcount --slot 7 -o <script>   # the owner's script (never run by the agent); dry-run: DRY_RUN=1 DRY_ANSWER=yes PKG=<out> bash <script>
python3 -m pytest agent/tests/test_235_block_for_shell.py hil/tests/test_235_redpitaya_followups.py     # the goal kind; the first-read root cause (iverilog); the overlay hooks
# the agent runs (paid subscription runs, not regenerated by a command here; their records are in runs/):
python -m agent run pilots/225/<design>/spec.md --board redpitaya_stemlab_125_14 --block-for-shell --review off --interview off --verif-level V2 --harness claude_code --stop-after 2
```

## Known gaps and limits

- No hardware result. Build G's timing is met only with the vendor's own generator, oscilloscope and AXI bridges excluded (above); with them included the same image misses by 5.7 ns, and nothing says whether the vendor's own image meets timing on the board.
- Vivado 2025.1 was not tried (not installed). The shell was built on 2026.1 and 2025.2 only.
- G is one place-and-route run; D, E and F show the blocks within 0.1 ns of the limit at default settings.
- Frequency accuracy needs an independent instrument (the board's 125 MHz oscillator has no stated ppm); OUT1 into IN1 only shows a pulse arrives (see the owner pack).
- Heavy-slot waiting dominated the elapsed time of this brief; the slot rule's memory test blocked a second Vivado impl run for hours. I declared `peak 4G` for the builds (`vivado_peak.py`'s figure for an unknown design; the builds ran under `MemoryMax=8G`); the actual peak was not measured.
