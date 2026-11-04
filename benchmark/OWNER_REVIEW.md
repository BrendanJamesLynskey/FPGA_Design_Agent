# Benchmark v1: the owner's review (owner track)

One block per task. Tick each question after reading the files named, then sign. **Scoring of the held-out set waits until every held-out block is signed**; development tasks may be used for agent work once signed. Signed so far: none by the owner (2026-11-03). On 2026-11-04 the owner asked for the 16 development tasks to be reviewed by Claude Sonnet 5.5 instead (planner sub-agent, brief 06a3); the tasks were written by Claude Opus 5.5, so this is a second model's check, not a human one. Those blocks carry its signature and findings (3 blockers, 21 minor); the 8 held-out blocks are untouched.

## T1

### t1_bcd_updown (T1, dev): Decimal up/down counter with selectable step

Files: `t1_bcd_updown/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 6/6; book/demo twin: textbook button-press counter with a decimal 7-segment display; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **blocker**: `benchmark/lib/bench.py:104-121` (`scan_display`) with `hidden/acceptance.py:42-44`: the check demands that a dark digit never pulls its AN low. A design that blanks a digit by lighting its anode with every segment off (looks identical on the display, and the spec.md wording "stay dark" / "without leading zeros" allows it) is rejected. Checked: ref copy with that one change fails 4 of 9 tests (identity, decimal_display, leading_zero_blanking, random_sequence). Smallest fix: in `scan_display` treat an AN-low digit whose CA..CG and DP are all off as absent (or say in spec.md that a dark digit has its anode off). The trap test `test_leading_zero_blanking` is hit too, so it can fail a correct design for a non-spec reason.
  - **minor**: `hidden/acceptance.py:53`: CPU_RESETN is only checked at power-up; no test resets after COUNT/WRAPS are non-zero (spec.md says reset clears everything). Fix: one reset-after-activity check.

### t1_debounce_bank (T1, dev): Sixteen-switch debounce bank

Files: `t1_debounce_bank/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: textbook debouncer that samples each switch once per slow tick (10-20 ms enable); trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:119`: the settle latency window `n+1..n+5` assumes a two-flop synchroniser plus one output register; a 3-flop design (still correct) sits at n+4/n+5, a 4-flop one fails. Fix: widen to `n+1..n+8` or drop the absolute check (the relative `n//2` check already proves independence).

### t1_elevator_fsm (T1, dev): Four-floor lift controller

Files: `t1_elevator_fsm/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 9/9; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:41`: the watcher detects every departure from LED[14] rising, but spec.md never mentions LED[14] (only LED[3:0], [7:4], [15]); only spec.yaml:47 does. A design that follows spec.md without asking has no LED[14] and fails every motion test. Fix: add "LED[14] is lit while the lift is moving" to spec.md, or derive departures from LED[3:0]/STATE.
  - **minor**: `hidden/acceptance.py:75-79`: `dr == dm` makes arrive->open, arrive->next-floor and close->depart exactly 0 clocks. spec.yaml says so (motion), spec.md only says "fixed time" per floor. Fix: allow 0..2 clocks on those links or add the rule to spec.md.

### t1_gray_stepper (T1, dev): Gray-code stepper on the LEDs

Files: `t1_gray_stepper/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 8; mutants killed 8/8; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:167`: the comment says "a press still steps" in automatic mode, but the test writes CTRL=0 before pressing, so "Buttons still work in automatic mode" and the press/auto same-clock rule (spec.yaml counter) are never exercised. Fix: press once while AUTO=1 at a slow RATE.
  - **minor**: REQ-01/02 name formal proof ("I want that proved, not just tested"); `check_task` runs no formal tool, so that half is unscored (NOTES says so). Fix: none for the bench; say in the report that the score covers simulation only.

### t1_lfsr_dice (T1, dev): Electronic dice from an LFSR

Files: `t1_lfsr_dice/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 11; mutants killed 9/9; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **blocker**: `benchmark/lib/bench.py:104-121` (`scan_display`) with `hidden/acceptance.py:43`: the check demands that a dark digit never pulls its AN low. A design that blanks a digit by lighting its anode with every segment off (looks identical on the display, and the spec.md wording "stay dark" / "without leading zeros" allows it) is rejected. Checked: ref copy with that one change fails the same way as t1_bcd_updown (digit 0 before the first roll, digits 1-7). Smallest fix: in `scan_display` treat an AN-low digit whose CA..CG and DP are all off as absent (or say in spec.md that a dark digit has its anode off). Not run on this task; same `scan_display` call and the same `want` dict.
  - **minor**: `hidden/spec.yaml:53,52`: a burst steps once per clock and a press during a burst is lost; neither is in spec.md and neither is listed under assumptions. The bench needs both (`acceptance.py:193` waits n+10 clocks for n steps; `test_press_lost_during_burst`). Fix: add both to `assumptions`.
  - **minor**: NOTES.md Review: a STEP write during a burst ("replaces the steps left") is never tested. Fix: one directed test or drop the sentence from spec.yaml.

### t1_pattern_sequencer (T1, dev): LED pattern sequencer

Files: `t1_pattern_sequencer/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 11; mutants killed 9/9; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: spec.md says "CPU_RESETN resets everything"; spec.yaml:19 keeps the 16 entries across reset ("power up 0") and `behaviour.playback` (LENGTH read at each entry end) is not under assumptions. Nothing tests either. Fix: add both to `assumptions`, or reword spec.md.

### t1_press_classifier (T1, dev): Short and long press classifier

Files: `t1_press_classifier/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: textbook button-press counter (debounced BTNC, every press counted); trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:36`: every register check reads STATUS (offset 3: debounced level and the two LED toggles), which spec.md never mentions; only the oracle can supply it. Same hidden-register-map pattern as every task, but here an unrequested register is read on every test. Fix: add "a status word with the button level and the LED states" to spec.md.

### t1_sync_fifo_regs (T1, dev): Byte FIFO behind the test shell

Files: `t1_sync_fifo_regs/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: FIFO Generator in standard (non-FWFT) read mode, as in the textbook temperature-sensor project; trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes:

### t1_breathe_rgb (T1, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

### t1_combo_lock (T1, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

### t1_reaction_timer (T1, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

### t1_stopwatch_lap (T1, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

## T2

### t2_adt7420_alarm (T2, dev): ADT7420 16-bit temperature monitor with a comparator-mode alarm

Files: `t2_adt7420_alarm/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 8; mutants killed 9/9; book/demo twin: textbook ADT7420 reader (power-on 13-bit mode, Celsius display); trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:173`: SCL high time must be 2Q..2Q+4 clocks. At the bench's small Q that admits a two-flop synchroniser plus one registered output enable and no more; a design with a 3-flop synchroniser is still a correct I2C master but fails. Fix: allow 2Q..2Q+8 (still catches a missed stretch wait).

### t2_i2c_cmd_master (T2, dev): Byte-command I2C master on the temperature-sensor bus

Files: `t2_i2c_cmd_master/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 9/9; book/demo twin: textbook fixed ADT7420 read sequence (STOP after the pointer write, then a fresh START); trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:135, 145`: SCL high time must be 2Q..2Q+4 clocks. At the bench's small Q that admits a two-flop synchroniser plus one registered output enable and no more; a design with a 3-flop synchroniser is still a correct I2C master but fails. Fix: allow 2Q..2Q+8 (still catches a missed stretch wait).
  - **minor**: `hidden/acceptance.py:147`: SCL low time must be 2Q..2Q+2, i.e. a 50% duty cycle; spec.md gives only the period (4Q). The duty cycle is in spec.yaml waveforms only. Fix: add "50% duty" to spec.md or widen the check.

### t2_i2c_scanner (T2, dev): I2C bus scanner on the temperature-sensor bus

Files: `t2_i2c_scanner/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6; mutants killed 9/9; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:113`: SCL high time must be 2Q..2Q+4 clocks. At the bench's small Q that admits a two-flop synchroniser plus one registered output enable and no more; a design with a 3-flop synchroniser is still a correct I2C master but fails. Fix: allow 2Q..2Q+8 (still catches a missed stretch wait). The same file's low-time check (`lo <= t <= lo + 2`) repeats the duty-cycle point.

### t2_pdm_vu (T2, dev): PDM microphone sound-level meter with peak hold

Files: `t2_pdm_vu/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6; mutants killed 8/8; book/demo twin: textbook PDM capture (M_LRSEL low, data taken at the M_CLK rising edge); trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: NOTES.md:14 says a design whose blocks are offset by a sample or two still passes, but `hidden/acceptance.py:111` (`test_peak_hold_and_decay`, first part) gives the loud pattern no padding, so a one-sample offset changes the block levels and the exact PEAK values. Fix: pad the loud span by 8 samples as the second part does, or correct NOTES.
  - **minor**: `hidden/acceptance.py:143-146` (`test_random_stream`): the model pre-computes the block after the CTRL write with the old HOLD, while the design may already use the new one. With HOLD < ~4 (about 1.6% of seeds) and PEAK chosen the checked value can differ. Fix: write CTRL, wait two blocks, then call `advance_model`.

### t2_qspi_sfdp (T2, dev): Configuration flash JEDEC ID and SFDP header reader

Files: `t2_qspi_sfdp/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 5; mutants killed 9/9; book/demo twin: none; trap none.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **blocker**: `hidden/model.py:22` (and `flash_model.py:62`, `acceptance.py:60,104`): `e.f.transactions == want` compares the MOSI bytes of the whole transaction, including the dummy and 16 read bytes, which the model says are 0 (spec.yaml:47 "DQ0 carries 0 during dummy and read bytes"). The flash ignores DQ0 there, spec.md says nothing about it, and a normal single shift register that clocks MISO in while shifting out echoes the received bits on MOSI. Checked: ref copy with `mosi <= sh_out[6] | sh_in[0]` during read bytes fails 2 of 5 tests (jedec_id_and_sfdp, random_contents). Smallest fix: compare only the opcode and the three address bytes (`rx[:1]` for RDID, `rx[:4]` for RSFDP) plus the byte count (4 and 21); drop the "carries 0" sentence from spec.yaml.

### t2_sevenseg_marquee (T2, dev): Scrolling raw-segment message on the eight 7-segment digits

Files: `t2_sevenseg_marquee/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 7; mutants killed 9/9; book/demo twin: textbook hex 7-segment display decoder; trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:166-171` tests that a write to POS restarts the scroll counter (spec.yaml:51 "Any write to CTRL or POS restarts the counter at 0"); it is in neither spec.md nor `assumptions`, and a counter that only restarts when SCROLL is set is just as reasonable and would fail. Fix: add it to `assumptions` so the oracle states it.

### t2_spi_master_modes (T2, dev): General-purpose SPI master on Pmod JB, all four modes

Files: `t2_spi_master_modes/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 10; mutants killed 10/10; book/demo twin: textbook mode-0-only SPI master for the ADXL362; trap fires.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [x] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/spec.yaml:41,44` says SCLK edges are at exactly k*DIV after CS_N falls and CS_N rises exactly DIV after the last edge; `acceptance.py:67-75` accepts DIV..2*DIV for both (NOTES agrees). Safe direction, but the two disagree. Fix: say "at least DIV, at most 2*DIV" in spec.yaml (and the assumption).
  - **minor**: `hidden/acceptance.py:155`: reads TXDATA back as 0x0180 after an 8-bit frame, so TXDATA must keep bits [15:8] (spec.yaml: "[15:0] the last accepted frame data"). A design that masks to the frame width is arguably also fine. Fix: mask the expected value to the frame width.

### t2_vga_sprite (T2, dev): Bouncing 16 x 16 sprite on 640 x 480 VGA

Files: `t2_vga_sprite/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6 (9 in v1.1); mutants killed 5/5 in v1 (4 more recorded as survivors); **9/9 in v1.1** (the 4 survivors moved into `mutants` after the v1.1 tests killed them, 2026-11-04); book/demo twin: none; trap none.

**Changed in v1.1 (2026-11-03):** (1) `hidden/selfcheck.py`: the bounce check now brackets the frame count (FRAME read before and after the CTRL write and before and after the X/Y reads); v1 failed on the board with FRAME +60 and X/Y +62, a measurement-window error, not a design fault; the rule change and the board numbers are in its docstring. (2) `hidden/acceptance.py`: three directed tests added for the four recorded survivors (off-screen X and CTRL.EN = 0 checked on lines the sprite would cover; a bounce turn at X = 0 and Y = 464; blanking lines with a non-zero background). The v1 tests looked at lines past the sprite, or ran with a black background, where those faults cannot show. The reference passes all 9 tests (Icarus); the mutant run that confirms the survivors are now killed is queued.

- [x] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [x] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [x] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: Reviewed: Claude Sonnet 5.5 (planner sub-agent, brief 06a3), 2026-11-04, on the owner's instruction; not reviewed by the owner   Notes (blocker/minor, file, line, what, why, smallest fix):
  - **minor**: `hidden/acceptance.py:82`: pixel (0,0) must start within 16 clocks of reset release; spec.yaml only says "after reset the first pixel shown is (0, 0)" (and all later checks anchor on HS, not on reset). Fix: drop the bound or state it in spec.yaml.
  - **minor**: NOTES.md:10 (acknowledged): the plain +-1 step away from the edges and BOUNCE = 0 holding still are never simulated (only turn cases at one frame wrap), so a design that ignores BOUNCE or steps 2 px passes. Coverage gap, not a wrong verdict on a tested path. Fix: one optional test over two frame wraps (about 5 minutes in Icarus).

### t2_adxl362_fifo (T2, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

### t2_ascii_console (T2, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

Changed in v1.1 (see the private review).

- Signed: ________

### t2_uart_regs (T2, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

### t2_vga_800x600 (T2, held out)

Reviewed in the private repository (`benchmark_private/OWNER_REVIEW_private.md`).

- Signed: ________

## Contamination probe

18 tasks, reviewed in the private repository.

