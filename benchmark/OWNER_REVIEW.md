# Benchmark v1: the owner's review (owner track)

One block per task. Tick each question after reading the files named, then sign. **Scoring of the held-out set waits until every held-out block is signed**; development tasks may be used for agent work once signed. Signed so far: none (2026-11-03).

## T1

### t1_bcd_updown (T1, dev): Decimal up/down counter with selectable step

Files: `t1_bcd_updown/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 6/6; book/demo twin: textbook button-press counter with a decimal 7-segment display; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t1_debounce_bank (T1, dev): Sixteen-switch debounce bank

Files: `t1_debounce_bank/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: textbook debouncer that samples each switch once per slow tick (10-20 ms enable); trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t1_elevator_fsm (T1, dev): Four-floor lift controller

Files: `t1_elevator_fsm/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 9/9; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t1_gray_stepper (T1, dev): Gray-code stepper on the LEDs

Files: `t1_gray_stepper/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 8; mutants killed 8/8; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t1_lfsr_dice (T1, dev): Electronic dice from an LFSR

Files: `t1_lfsr_dice/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 11; mutants killed 9/9; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t1_pattern_sequencer (T1, dev): LED pattern sequencer

Files: `t1_pattern_sequencer/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 11; mutants killed 9/9; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t1_press_classifier (T1, dev): Short and long press classifier

Files: `t1_press_classifier/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: textbook button-press counter (debounced BTNC, every press counted); trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t1_sync_fifo_regs (T1, dev): Byte FIFO behind the test shell

Files: `t1_sync_fifo_regs/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 8/8; book/demo twin: FIFO Generator in standard (non-FWFT) read mode, as in the textbook temperature-sensor project; trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

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

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t2_i2c_cmd_master (T2, dev): Byte-command I2C master on the temperature-sensor bus

Files: `t2_i2c_cmd_master/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 9; mutants killed 9/9; book/demo twin: textbook fixed ADT7420 read sequence (STOP after the pointer write, then a fresh START); trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t2_i2c_scanner (T2, dev): I2C bus scanner on the temperature-sensor bus

Files: `t2_i2c_scanner/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6; mutants killed 9/9; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t2_pdm_vu (T2, dev): PDM microphone sound-level meter with peak hold

Files: `t2_pdm_vu/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6; mutants killed 8/8; book/demo twin: textbook PDM capture (M_LRSEL low, data taken at the M_CLK rising edge); trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t2_qspi_sfdp (T2, dev): Configuration flash JEDEC ID and SFDP header reader

Files: `t2_qspi_sfdp/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 5; mutants killed 9/9; book/demo twin: none; trap none.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

### t2_sevenseg_marquee (T2, dev): Scrolling raw-segment message on the eight 7-segment digits

Files: `t2_sevenseg_marquee/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 7; mutants killed 9/9; book/demo twin: textbook hex 7-segment display decoder; trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t2_spi_master_modes (T2, dev): General-purpose SPI master on Pmod JB, all four modes

Files: `t2_spi_master_modes/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 10; mutants killed 10/10; book/demo twin: textbook mode-0-only SPI master for the ADXL362; trap fires.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** the trap test fails on the textbook/demo behaviour and only on a real difference
- Signed: ________ (initials, date)   Notes:

### t2_vga_sprite (T2, dev): Bouncing 16 x 16 sprite on 640 x 480 VGA

Files: `t2_vga_sprite/spec.md`, `hidden/spec.yaml`, `hidden/model.py`, `hidden/acceptance.py`, `hidden/NOTES.md`, `ref/rtl/`. Tests 6 (9 in v1.1); mutants killed 5/5 in v1 (4 more recorded as survivors); **9/9 in v1.1** (the 4 survivors moved into `mutants` after the v1.1 tests killed them, 2026-11-04); book/demo twin: none; trap none.

**Changed in v1.1 (2026-11-03):** (1) `hidden/selfcheck.py`: the bounce check now brackets the frame count (FRAME read before and after the CTRL write and before and after the X/Y reads); v1 failed on the board with FRAME +60 and X/Y +62, a measurement-window error, not a design fault; the rule change and the board numbers are in its docstring. (2) `hidden/acceptance.py`: three directed tests added for the four recorded survivors (off-screen X and CTRL.EN = 0 checked on lines the sprite would cover; a bounce turn at X = 0 and Y = 464; blanking lines with a non-zero background). The v1 tests looked at lines past the sprite, or ran with a black background, where those faults cannot show. The reference passes all 9 tests (Icarus); the mutant run that confirms the survivors are now killed is queued.

- [ ] **Spec clear?** spec.md reads as a user would write it; what it leaves out is answerable from spec.yaml
- [ ] **Model right?** model.py does what spec.yaml says (and nothing the RTL happens to do)
- [ ] **Tests fair?** every acceptance test follows from spec.yaml; none depends on a reference-only choice
- [ ] **Trap valid?** n/a (no twin)
- Signed: ________ (initials, date)   Notes:

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

