# P1: frequency and period meter for the Red Pitaya (natural-language spec)

*Written as a user would write it, for my Red Pitaya STEMlab 125-14 on my desk. The block's ID register reads 0xFDA10101.*

I want the Red Pitaya to be a frequency counter. The signal comes in on IN1 (the fast analogue input, on the LV jumper, so +-1 V full scale). Count its rising edges
over a gate that is a fixed number of cycles of the board's 125 MHz clock, and also time the span from the first to the last edge in the gate, so I can get the
frequency two ways: edges / gate time, and (edges - 1) x 125 MHz / span (better at low frequencies). A Schmitt trigger with two thresholds (in ADC counts, set
by registers) decides what an edge is, so noise on a slow signal does not count. Signals up to 30 MHz matter to me; a gate of 0.1 s or 1 s is typical.

I do not want the design to be the whole FPGA image. It goes into the vendor's Red Pitaya shell as a block (the shell keeps the ADC, DAC, scope and register
window working); I only write the block, with the ports below, and the shell's system bus is how I talk to it from Linux.

## The block's ports (use exactly these)

```
module rp_freqcount (
    input  logic               clk,        // 125 MHz, free running (the shell's ADC clock); every port below is synchronous to it
    input  logic               rstn,       // active low, synchronous
    input  logic        [31:0] sys_addr,   // byte address; only bits [19:0] matter (the block owns a 1 MiB window)
    input  logic        [31:0] sys_wdata,
    input  logic               sys_wen,    // one-cycle pulse
    input  logic               sys_ren,    // one-cycle pulse
    output logic        [31:0] sys_rdata,  // valid in the cycle sys_ack is high
    output logic               sys_err,    // high with sys_ack: the access failed
    output logic               sys_ack,    // one cycle, the cycle IMMEDIATELY after sys_wen or sys_ren (latency exactly one clock)
    input  logic signed [13:0] adc_a,      // IN1, two's complement, 125 MS/s (+-8192 is +-1 V on the LV jumper)
    input  logic signed [13:0] adc_b,      // IN2
    output logic signed [13:0] dac_a,      // added to OUT1's data (8192 counts per volt into 50 ohm)
    output logic signed [13:0] dac_b       // added to OUT2's data
);
```

The shell's register bus: one access per cycle; the block answers in the next cycle with `sys_ack` high for one cycle and `sys_rdata` valid in that cycle;
`sys_err` high with `sys_ack` means the access failed. Reads never have side effects. A write takes effect on the next clock. The block does not use `dac_a` or
`dac_b`: tie them to 0.

## Registers

| Offset | Name | Access | Reset | Meaning |
|---|---|---|---|---|
| 0x00 | ID | RO | 0xFDA10101 | block identifier |
| 0x04 | SCRATCH | RW | 0x00000000 | 32 bits, reads back what was written |
| 0x08 | CTRL | RW | 0x00000000 | bit 0 START (W1P: a write of 1 starts one gate when not BUSY, ignored while BUSY; reads 0); bit 1 CONT (a new gate starts as soon as one ends) |
| 0x0C | GATE_LEN | RW | 0x07735940 | gate length in adc_clk cycles; a write below 1000 stores 1000; the change applies to the next gate |
| 0x10 | THR_HIGH | RW | 0x00000100 | Schmitt trigger upper threshold, signed 14 bit (low 14 bits of the write, read back sign-extended): +-8192 is +-full scale |
| 0x14 | THR_LOW | RW | 0xFFFFFF00 | Schmitt trigger lower threshold, signed 14 bit; reset -256 |
| 0x18 | STATUS | RO | 0x00000000 | bit 0 BUSY; bit 1 DONE (cleared by START, set with the result registers); bit 2 FEW_EDGES (fewer than 2 edges in the last gate: SPAN is not valid); bit 3 BAD_THRESH (THR_HIGH <= THR_LOW: no edge is counted) |
| 0x1C | EDGES | RO | 0x00000000 | rising edges (a crossing of THR_HIGH after the signal was at or below THR_LOW) counted on IN1 in the last completed gate |
| 0x20 | GATE_ACTUAL | RO | 0x00000000 | adc_clk cycles in the last completed gate; equals the GATE_LEN in force when it started |
| 0x24 | SPAN | RO | 0x00000000 | adc_clk cycles from the first to the last counted rising edge of the last gate (valid when EDGES >= 2) |
| 0x28 | MEAS_DONE | RO | 0x00000000 | number of completed gates since reset (wraps) |

Behaviour a user could guess wrong:


- Registers are 32 bits on 4-byte steps from the slot base 0x40700000; the offsets below are from that base.
- An offset with no register, and any offset from the end of the map to 0xFFFFF, answers with a bus error (the shell's err line) and reads 0. Do not read them from Linux: what the PS does with the error is not documented. A write to a read-only register is ignored and answers with an error.
- Reset (the shell's adc_rstn, released some cycles after the PLL locks) returns every register to its reset value. A power cycle or a reload of the factory image ends the design.
- Reads have no side effects. A write takes effect on the next adc_clk cycle (125 MHz); the register bus runs on the same clock, so no read-back delay is needed.
- Every signed 14-bit register (thresholds, levels, pattern samples) takes the low 14 bits of the 32-bit write as a two's-complement number and reads back sign-extended to 32 bits; a write of the 32-bit word -4000 (0xFFFFF060) and of 0x00003060 are the same. Bits 31 to 14 of a write are ignored.
- The input is IN1 of the shell, 14-bit signed. On jumper LV full scale is +-1 V (one count is about 122 uV); on HV +-20 V. Thresholds are in counts, not volts.
- Gate counting: f = EDGES / (GATE_ACTUAL / 125 MHz). Reciprocal: f = (EDGES - 1) * 125 MHz / SPAN. Both are as accurate as the board's 125 MHz oscillator, whose error is not stated by the vendor.
- A START while BUSY is ignored; STATUS.DONE stays set from the end of one gate to the START of the next; with CONT set DONE stays set and the registers change at the end of each gate (read EDGES, GATE_ACTUAL and SPAN of one gate together by checking MEAS_DONE before and after: they must match).

## How I check it

On the board a script generates nothing: I feed IN1 from a known source (the Red Pitaya's own OUT1 through a short lead, a function generator, or the M2K) and run
three gates of 0.1 s, then compare both estimates with the known frequency. I expect agreement within 1000 ppm plus one edge of quantisation, and the two estimates
to agree with each other within the same quantisation. The registers must behave exactly as the notes say, including the cases a user could guess wrong.

Requirements I care about most: the count is exact for a clean periodic input (no edge lost or doubled at the gate boundaries); GATE_ACTUAL always equals the
gate that was asked for; a START while BUSY changes nothing; thresholds in the wrong order set BAD_THRESH and count nothing; an input that never crosses both
thresholds reports FEW_EDGES with EDGES 0 or 1 and does not hang.
