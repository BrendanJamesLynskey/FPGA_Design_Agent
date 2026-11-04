# Benchmark v1: frozen 2026-11-03

Written by brief 06a before any agent tuning on these tasks, by a session that did not read the agent's prompts or
run records. Nothing in `benchmark/tasks`, `benchmark/pool`, `benchmark/lib` or the scoring tools may change after
this point without a new version and a new freeze; a change found necessary is recorded in the scoring report.

| What | Value |
|---|---|
| Tasks | 24: T1 12, T2 12. Held out 8 (T1: breathe_rgb, combo_lock, reaction_timer, stopwatch_lap; T2: adxl362_fifo, ascii_console, uart_regs, vga_800x600), development 16 |
| Split | `split.yaml`, seed 20261103, `random.Random(seed).sample(sorted(ids), round(n/3))` per tier; SHA-256 `1cf56ebdef900f5397f132ec3c7f9ea173a146b0cda6b3b0cc0eb1af01f68bcc` |
| Manifest | `MANIFEST.json` (86 units: 24 tasks, 40 pool specs, 18 probe tasks, 4 shared bench units; per unit the SHA-256 of its sorted `sha256  path` lines; held-out and probe units by digest only) |
| Private manifest | `benchmark_private/MANIFEST_full.json` in the private repository (every file of every unit) |
| Tools | Python 3.12.3, cocotb 2.0.1, Icarus 12.0, Verilator 5.048, Vivado 2025.2, PyYAML 6.0.1 |

## How to verify

```bash
python3 benchmark/tools/freeze.py verify                              # public units, from a fresh clone
python3 benchmark/tools/freeze.py verify --private <private>/benchmark_private   # every unit
python3 benchmark/tools/split.py show benchmark/split.yaml
```

`benchmark/tests/test_bench_static.py` (CI) re-runs the draw from the recorded seed and verifies the manifest.

## Rules from here

- Held-out tasks are never used while tuning the agent; scoring of the held-out set waits for the owner's sign-off
  in [OWNER_REVIEW.md](OWNER_REVIEW.md) (none signed at freeze).
- A held-out `spec.md` is published here only after scoring.
- The knowledge bank must stay free of every spec's distinctive phrases (`tools/bank_grep.py`; 0 hits at freeze).

## v1.1 (2026-11-03, after the first board run)

Two units changed after the 22/24 bring-up of the references; nothing else did. Each change is a bench or self-check
fix, recorded here and in [OWNER_REVIEW.md](OWNER_REVIEW.md):

- `t2_vga_sprite`: the self-check's bounce rule brackets the frame count (the v1 window was too narrow, a board
  measurement error), and `hidden/acceptance.py` gains three directed tests for the four recorded survivors.
- One held-out task: its on-board self-check changed (the board flow's identify step; detail in the private repository). Public: digest only.

Also in v1.1: `flow/board_check.py` reads a self-check module's `NO_SHELL` flag. Re-frozen: `MANIFEST.json` (the two
unit digests and the shared-unit digests only).

## v1.1 re-freeze (2026-11-04): t2_vga_sprite mutants

The four recorded survivors of `t2_vga_sprite` were run as mutants against the v1.1 `acceptance.py` (Icarus) and all
were killed, so they moved from `known_survivors` into `mutants` (now 9/9 killed; `known_survivors: []`). Re-frozen:
that unit's digest only (`hidden/mutants.yaml`, `hidden/NOTES.md`); `results/reference/t2_vga_sprite__icarus.json` regenerated. No spec,
reference RTL, test or held-out file changed. `freeze.py verify`: 86 units, 0 mismatches.

## v1.2 (2026-11-04, brief 06a4): the second-model review's blockers and cheap minors

The review of brief 06a3 (a second model, on the owner's instruction; see [OWNER_REVIEW.md](OWNER_REVIEW.md)) found five
blockers: three public, two held out. All five are fixed, each proven with the reviewer's alternative-but-correct design
(it failed on v1.1 and passes on v1.2), with the reference passing and every listed mutant and the trap checked again on
Icarus (Python 3.12.3, cocotb 2.0.1, Icarus 12.0). No held-out detail is published: the two held-out tasks are named in the
private repository only; here they appear as digests in `MANIFEST.json`.

| Blocker | Fix | Proof (v1.1 -> v1.2) |
|---|---|---|
| `scan_display` (`lib/bench.py`) rejected a dark digit whose anode is low; shared by `t1_bcd_updown`, `t1_lfsr_dice` and held-out tasks | a digit with every segment and DP off is dark, anode high or low; a digit that lights any segment still fails | tests passed, bcd_updown copy 5/9 -> 9/9 (the trap still fires); lfsr_dice copy 6/11 -> 11/11; the held-out users were checked privately |
| `t2_qspi_sfdp` required DQ0 = 0 in the dummy and read bytes, which spec.md never states | compare the opcode and address bytes and the byte count (4, 21); spec.yaml says DQ0 is a don't-care there (the flash ignores it, a MISO-echoing shift register is correct) | tests passed, MOSI-echo copy 3/5 -> 5/5; reference 5/5; mutants 9/9 |
| two held-out tasks (one display, one SPI transaction) | one through the shared helper plus a spec.yaml sentence; one by comparing fewer bytes | fixed, proven (detail in the private repository) |

Also in v1.2 (each recorded in its OWNER_REVIEW block):

- Tolerances widened: SCL high time 2Q to 2Q + 8 clocks (was + 4) in `t2_i2c_scanner`, `t2_i2c_cmd_master`, `t2_adt7420_alarm`
  (two-flop synchroniser plus 1-3 clocks of state and output latency); `t1_debounce_bank` settle latency n + 1 to n + 8
  (was n + 5).
- Wording and `assumptions` (what the task asks is unchanged): `t1_elevator_fsm` and `t1_press_classifier` and
  `t2_i2c_cmd_master` gain one sentence each in spec.md (LED[14] while moving; the status word; equal SCL halves);
  `t1_lfsr_dice`, `t1_pattern_sequencer`, `t2_sevenseg_marquee` gain `assumptions` entries; `t2_pdm_vu` NOTES corrected.
- Directed tests for stated-but-untested clauses: `t1_gray_stepper` `test_press_during_auto` (and mutant
  `press_restarts_prescaler`, killed); `t2_vga_sprite` `test_bounce_plain_step_and_bounce_off` (+1/-1 step, BOUNCE = 0
  holds still).
- Mutants re-written because the fix made them equivalent to the reference (a lit digit with a blank glyph is dark):
  `dark_digit_shows_zero` (`t1_lfsr_dice`), and two probe tasks' `upper_digits_lit` (private repository).
- Deferred to v2 (one line each in the OWNER_REVIEW blocks): reset after activity (bcd_updown); STEP write during a burst
  (lfsr_dice); zero-clock elevator transitions; SCL low-time duty (i2c_scanner); pdm_vu padding and CTRL race;
  spi_master_modes DIV wording and TXDATA width; vga_sprite (0,0)-after-reset bound; formal halves unscored.

Re-frozen: `lib/bench.py` and the shared-unit digests; the digests of the 14 public tasks listed above (all of
`t1_bcd_updown`, `t1_debounce_bank`, `t1_elevator_fsm`, `t1_gray_stepper`, `t1_lfsr_dice`, `t1_pattern_sequencer`,
`t1_press_classifier`, `t2_adt7420_alarm`, `t2_i2c_cmd_master`, `t2_i2c_scanner`, `t2_pdm_vu`, `t2_qspi_sfdp`,
`t2_sevenseg_marquee`, `t2_vga_sprite`), the two held-out tasks and two probe tasks; `benchmark/results/reference/<task>__icarus.json`
regenerated for the tasks whose tests changed. `freeze.py verify --private`: 86 units, 0 mismatches. Pool specs have no
reference RTL and are not run; their `scan_display` users (`p_bin2bcd`, `p_digital_clock`, `p_tennis_score`) are spec
units only.
