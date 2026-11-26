# 209: requirements and how each was verified (chosen runs)

From each run's `build/trace/trace.json` (flow/traceability.py). Result per method: pass, pending (hardware, until the board visit) or fail. Hardware rows stay pending.


## p1_clkmeter run 1

| Requirement | Text | Methods and results |
|---|---|---|
| REQ-01 | ID register at 0x000 reads 0x20910001. | simulation: pass, hardware: pending |
| REQ-02 | BUILD register at 0x004 reads the USR_ACCESSE2 word. | hardware: pending |
| REQ-03 | SCRATCH at 0x008 reads back the value written. | simulation: pass, hardware: pending |
| REQ-24 | SCRATCH resets to 0. | simulation: pass |
| REQ-04 | GATE_LEN resets to 156250000. | simulation: pass |
| REQ-05 | Writing START while not busy runs exactly one measurement. | simulation: pass, hardware: pending |
| REQ-06 | START written while BUSY is ignored. | simulation: pass, formal: pass |
| REQ-07 | GATE_ACTUAL equals GATE_LEN for every completed measurement. | simulation: pass, formal: pass, hardware: pending |
| REQ-08 | COUNT equals the number of clk_c3 rising edges inside the gate to within 1 edge. | simulation: pass |
| REQ-09 | DONE is cleared by an accepted START write. | simulation: pass, formal: pass |
| REQ-25 | DONE is set only after the COUNT register holds the final gate result. | simulation: pass, formal: pass |
| REQ-26 | DONE is set only after the GATE_ACTUAL register holds the final gate result. | simulation: pass, formal: pass |
| REQ-10 | MEAS_DONE increments by 1 per completed measurement. | simulation: pass, hardware: pending |
| REQ-11 | A gate length of 1000 cycles is the minimum accepted. | simulation: pass |
| REQ-12 | COUNT x 156.25 MHz / GATE_ACTUAL measures the C3 clock within 100 ppm of 25 MHz on the board. | hardware: pending |
| REQ-13 | Five consecutive one-second readings agree with each other within 10 ppm. | hardware: pending |
| REQ-14 | led[0] toggles every 12500000 clk_c3 cycles when LED_EN is 1. | simulation: pass, hardware: pending |
| REQ-15 | led[1] toggles every 78125000 clk_ref cycles when LED_EN is 1. | simulation: pass, hardware: pending |
| REQ-16 | Both LEDs are 0 after reset. | simulation: pass, formal: pass |
| REQ-27 | Both LEDs are 0 while LED_EN is 0. | simulation: pass, formal: pass |
| REQ-17 | sfp_tx_disable is 1 at all times. | formal: pass, analysis: pass |
| REQ-18 | No GT transceiver channel is instantiated. | analysis: pass |
| REQ-19 | h_rdata shows the addressed register within 2 clocks of h_re. | simulation: pass, formal: pass |
| REQ-28 | h_rdata holds the read value until the next h_re. | simulation: pass, formal: pass |
| REQ-20 | A write takes effect 1 clock after h_we. | simulation: pass |
| REQ-21 | Unmapped addresses read 0. | simulation: pass, formal: pass |
| REQ-29 | Writes to unmapped addresses change no register. | simulation: pass, formal: pass |
| REQ-22 | data/jtag_bus.sv is instantiated without modification. | analysis: pass |
| REQ-23 | The design meets timing with no unconstrained clock crossing. | analysis: pass |

## p2_bram_rom run 1

| Requirement | Text | Methods and results |
|---|---|---|
| REQ-01 | ID register at 0x000 reads 0x20920001. | simulation: pass, hardware: pending |
| REQ-02 | BUILD register at 0x004 reads the USR_ACCESSE2 word. | hardware: pending |
| REQ-03 | SCRATCH at 0x008 reads back the value written. | simulation: pass, hardware: pending |
| REQ-24 | SCRATCH at 0x008 reads 0 after reset. | simulation: pass, hardware: pending |
| REQ-04 | Reads of ROM words 0 to 1023 straight after configuration equal the lines of data/rom_init.hex. | simulation: pass, hardware: pending |
| REQ-05 | Reads of RAM word i straight after configuration, before any write, return 0xC0DE0000 + i for i in 0 to 1023. | simulation: pass, hardware: pending |
| REQ-06 | A RAM_DATA write stores h_wdata at the word addressed by MEM_ADDR. | simulation: pass, hardware: pending |
| REQ-25 | A RAM_DATA read after a write to the same address returns the written word. | simulation: pass, hardware: pending |
| REQ-07 | With AUTOINC set, each ROM_DATA read adds 1 to MEM_ADDR modulo 1024. | simulation: pass, formal: pass |
| REQ-08 | With AUTOINC set, each RAM_DATA read or write adds 1 to MEM_ADDR modulo 1024. | simulation: pass, formal: pass |
| REQ-09 | With AUTOINC clear, MEM_ADDR is unchanged by ROM_DATA and RAM_DATA accesses. | simulation: pass |
| REQ-10 | A register write takes effect 1 clock after h_we. | simulation: pass, formal: pass |
| REQ-11 | h_rdata shows the addressed register within 2 clocks after h_re. | simulation: pass, formal: pass |
| REQ-26 | h_rdata holds its value until the next h_re. | simulation: pass, formal: pass |
| REQ-12 | Reads of unmapped addresses return 0. | simulation: pass, formal: pass |
| REQ-27 | Writes to unmapped addresses change no register. | simulation: pass, formal: pass |
| REQ-13 | START clears MARCH_ERRS to 0. | simulation: pass |
| REQ-28 | START clears the passes-completed count to 0. | simulation: pass |
| REQ-29 | START sets MARCH_FIRST_ERR to 0xFFFFFFFF. | simulation: pass |
| REQ-14 | Each pass runs March C- over all 1024 RAM words with background 0x00000000. | simulation: pass |
| REQ-30 | Each pass runs March C- over all 1024 RAM words with background 0xFFFFFFFF. | simulation: pass |
| REQ-15 | A 200-pass run with no fault ends with MARCH_ERRS equal to 0. | simulation: pass, hardware: pending |
| REQ-32 | A 200-pass run with no fault ends with DONE set. | simulation: pass, hardware: pending |
| REQ-16 | A 3-pass run with INJECT_FAULT set ends with MARCH_ERRS greater than 0. | simulation: pass, hardware: pending |
| REQ-17 | MARCH_FIRST_ERR holds the address of the first wrong word. | simulation: pass, hardware: pending |
| REQ-31 | MARCH_FIRST_ERR reads 0xFFFFFFFF when no word read wrong. | simulation: pass, hardware: pending |
| REQ-18 | MARCH_STATUS bits 31:16 count completed passes. | simulation: pass |
| REQ-33 | MARCH_STATUS bits 31:16 equal MARCH_PASSES when DONE is set. | simulation: pass |
| REQ-19 | After a completed march run the RAM holds all zeros. | simulation: pass, hardware: pending |
| REQ-20 | sfp_tx_disable is 1 at all times. | simulation: pass, formal: pass, hardware: pending |
| REQ-21 | The design uses 0 GT transceiver channels. | analysis: pass |
| REQ-22 | data/jtag_bus.sv is instantiated unchanged. | analysis: pass |
| REQ-23 | The design meets timing at 25 MHz with WNS of 0 ns or more. | analysis: pass |

## p3_crc_engine run 2

| Requirement | Text | Methods and results |
|---|---|---|
| REQ-01 | ID register at 0x000 reads 0x20930001. | simulation: pass, hardware: pending |
| REQ-02 | BUILD register at 0x004 reads the USR_ACCESSE2 word. | hardware: pending |
| REQ-03 | SCRATCH at 0x008 reads back the last written 32-bit value. | simulation: pass, hardware: pending |
| REQ-20 | SCRATCH at 0x008 reads 0 after reset. | simulation: pass, hardware: pending |
| REQ-04 | CRC after any message pushed since INIT equals zlib.crc32 of those bytes. | simulation: pass, hardware: pending |
| REQ-05 | CRC of an empty message reads 0x00000000. | simulation: pass |
| REQ-06 | BYTE_COUNT equals the number of bytes pushed since INIT. | simulation: pass, hardware: pending |
| REQ-07 | A message of N full words gives BUSY_CYCLES equal to N. | simulation: pass, hardware: pending |
| REQ-08 | PUSH4 writes on consecutive clocks are each accepted. | simulation: pass, formal: pass |
| REQ-09 | PUSH_N pushes the low TAIL_LEN bytes, with TAIL_LEN 0 pushing nothing. | simulation: pass |
| REQ-10 | CTRL bit 0 written 1 sets CRC state to 0xFFFFFFFF. | simulation: pass, formal: pass |
| REQ-23 | CTRL bit 0 written 1 sets BYTE_COUNT to 0. | simulation: pass, formal: pass |
| REQ-24 | CTRL bit 0 written 1 sets BUSY_CYCLES to 0. | simulation: pass, formal: pass |
| REQ-11 | CTRL bit 0 reads 0 the clock after the INIT write. | simulation: pass |
| REQ-12 | Unmapped addresses read 0. | simulation: pass, formal: pass |
| REQ-21 | A write to an unmapped address changes no register. | simulation: pass, formal: pass |
| REQ-13 | h_rdata shows the addressed register within 2 clocks of h_re. | simulation: pass, formal: pass |
| REQ-22 | h_rdata holds its value until the next h_re. | simulation: pass, formal: pass |
| REQ-14 | A write takes effect the clock after h_we. | simulation: pass |
| REQ-15 | The clock clk runs at 100 MHz or more. | analysis: pass |
| REQ-16 | Timing closes with WNS of 0 ns or more at the chosen clock. | analysis: pass |
| REQ-17 | sfp_tx_disable is 1 at all times. | simulation: pass, formal: pass, hardware: pending |
| REQ-18 | No GT transceiver channel is used. | analysis: pass |
| REQ-19 | 1,000 random messages of lengths including 0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65 and a few hundred bytes give a CRC equal to zlib.crc32. | simulation: pass, hardware: pending |
| REQ-25 | The same 1,000 random messages give a BYTE_COUNT equal to the message length. | simulation: pass, hardware: pending |
