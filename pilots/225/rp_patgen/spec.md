# P2: programmable pulse and pattern generator for the Red Pitaya (natural-language spec)

*Written as a user would write it, for my Red Pitaya STEMlab 125-14 on my desk. The block's ID register reads 0xFDA10201.*

I want the Red Pitaya to make a pulse train or a short repeating pattern on OUT1 (the DAC, +-1 V into 50 ohm, 8192 counts per volt). Pulse mode: a period and a
width in cycles of the 125 MHz clock, a high level and a low level, a number of periods or "until I stop it". Pattern mode: up to 16 samples, each held for a
number of cycles, repeated a number of times or until stopped. It is my first output design, so it must be safe: **every level and sample is cut to a ceiling
(LIMIT, default 0.5 V, never more than 0.9 V) in hardware**, whatever I write, and the output is 0 at reset, after STOP and when a sequence is done.

It goes into the vendor's Red Pitaya shell as a block (the shell keeps the ADC, DAC, scope and register window working; the shell adds the block's DAC term to the
factory generator's, which is idle); I only write the block, with the ports below.

## The block's ports (use exactly these)

```
module rp_patgen (
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
`sys_err` high with `sys_ack` means the access failed. Reads never have side effects. A write takes effect on the next clock. Only `dac_a` is driven (OUT1);
tie `dac_b` to 0. `adc_a` and `adc_b` are not used.

## Registers

| Offset | Name | Access | Reset | Meaning |
|---|---|---|---|---|
| 0x00 | ID | RO | 0xFDA10201 | block identifier |
| 0x04 | SCRATCH | RW | 0x00000000 | 32 bits, reads back what was written |
| 0x08 | CTRL | RW | 0x00000000 | bit 0 START (W1P: starts the sequence when not RUNNING; ignored while RUNNING); bit 1 STOP (W1P: ends the sequence at once and returns OUT1 to 0); bit 2 CONT (repeat until STOP) |
| 0x0C | MODE | RW | 0x00000000 | 0 pulse: LEVEL_HI for WIDTH cycles then LEVEL_LO for the rest of each PERIOD; 1 pattern: PAT_LEN samples, each held SAMPLE_DIV cycles, repeated; other values store as 0 |
| 0x10 | PERIOD | RW | 0x000004E2 | pulse period in adc_clk cycles, 2 to 2^32-1 (a write below 2 stores 2); default 1250 is 100 kHz |
| 0x14 | WIDTH | RW | 0x00000271 | cycles of LEVEL_HI in each period, 1 to PERIOD-1 (a write outside stores the nearest legal value at the next START) |
| 0x18 | LEVEL_HI | RW | 0x00000800 | signed 14 bit, counts: the low 14 bits of the write are the two's-complement value (write -4000 as 0x00003060, or any word whose low 14 bits are that), read back sign-extended to 32 bits; +-8192 is +-1 V into 50 ohm on OUT1; reset +2048 (+0.25 V) |
| 0x1C | LEVEL_LO | RW | 0x00000000 | signed 14 bit, counts, same write and read-back convention as LEVEL_HI; reset 0 |
| 0x20 | COUNT | RW | 0x00000001 | periods (pulse) or pattern passes (pattern) to emit when CONT is 0, 1 to 65535 (a write of 0 stores 1) |
| 0x24 | LIMIT | RW | 0x00001000 | ceiling on the magnitude of every level and sample sent to OUT1, in counts; a write above 7372 (0.9 V) stores 7372; reset 4096 (0.5 V) |
| 0x28 | STATUS | RO | 0x00000000 | bit 0 RUNNING; bit 1 DONE (cleared by START, set when COUNT periods have been emitted or STOP was written); bit 2 CLAMPED (a level or sample exceeded LIMIT since START and was cut to it) |
| 0x2C | PERIODS_DONE | RO | 0x00000000 | periods or passes completed since START |
| 0x30 | PAT_LEN | RW | 0x00000010 | pattern samples used, 1 to 16 (a write of 0 stores 1, above 16 stores 16) |
| 0x34 | SAMPLE_DIV | RW | 0x00000001 | adc_clk cycles each pattern sample is held, 1 to 65535 (a write of 0 stores 1) |
| 0x40 | PAT0 | RW | 0x00000000 | pattern sample 0, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x44 | PAT1 | RW | 0x00000000 | pattern sample 1, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x48 | PAT2 | RW | 0x00000000 | pattern sample 2, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x4C | PAT3 | RW | 0x00000000 | pattern sample 3, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x50 | PAT4 | RW | 0x00000000 | pattern sample 4, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x54 | PAT5 | RW | 0x00000000 | pattern sample 5, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x58 | PAT6 | RW | 0x00000000 | pattern sample 6, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x5C | PAT7 | RW | 0x00000000 | pattern sample 7, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x60 | PAT8 | RW | 0x00000000 | pattern sample 8, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x64 | PAT9 | RW | 0x00000000 | pattern sample 9, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x68 | PAT10 | RW | 0x00000000 | pattern sample 10, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x6C | PAT11 | RW | 0x00000000 | pattern sample 11, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x70 | PAT12 | RW | 0x00000000 | pattern sample 12, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x74 | PAT13 | RW | 0x00000000 | pattern sample 13, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x78 | PAT14 | RW | 0x00000000 | pattern sample 14, signed 14 bit counts, same write and read-back convention as LEVEL_HI |
| 0x7C | PAT15 | RW | 0x00000000 | pattern sample 15, signed 14 bit counts, same write and read-back convention as LEVEL_HI |

Behaviour a user could guess wrong:


- Registers are 32 bits on 4-byte steps from the base of the slot the block sits in: 0x40700000 for slot 7 and 0x40600000 for slot 6 (the shell build says which); the offsets below are from that base.
- An offset with no register, and any offset from the end of the map to 0xFFFFF, answers with a bus error (the shell's err line) and reads 0. Do not read them from Linux: what the PS does with the error is not documented. A write to a read-only register is ignored and answers with an error.
- Reset (the shell's adc_rstn, released some cycles after the PLL locks) returns every register to its reset value. A power cycle or a reload of the factory image ends the design.
- Reads have no side effects. A write takes effect on the next adc_clk cycle (125 MHz); the register bus runs on the same clock, so no read-back delay is needed.
- Every signed 14-bit register (thresholds, levels, pattern samples) takes the low 14 bits of the 32-bit write as a two's-complement number and reads back sign-extended to 32 bits; a write of the 32-bit word -4000 (0xFFFFF060) and of 0x00003060 are the same. Bits 31 to 14 of a write are ignored.
- OUT1 is the shell's DAC channel A; OUT2 (channel B) is not driven by this block (the factory ASG and PID are idle in this image), so it stays at 0.
- Every level and every pattern sample is cut to +-LIMIT on its way to the DAC, whatever the registers hold; the cut sets STATUS.CLAMPED. The output is 0 at reset, after STOP and when the sequence is done.
- Counts to volts: the DAC takes 14 bits for +-1 V into 50 ohm (8192 counts per volt). Into a high-impedance input the original generation's swing is not stated: start small and look.
- START with WIDTH, PERIOD or LEVEL values outside their limits does not fail: the nearest legal value is used and nothing is reported except through the registers' read-back.

## How I check it

A script writes the registers, starts a four-period pulse train at 0.25 V and 100 kHz and reads STATUS and PERIODS_DONE back; I look at OUT1 on a scope or loop
it into IN1 (LV) with a short lead. I also write levels above LIMIT and check CLAMPED sets and the output never exceeds LIMIT. The registers must behave exactly
as the notes say, including the cases a user could guess wrong. The waveform is checked cycle by cycle in simulation.

Requirements I care about most: no output sample ever exceeds LIMIT in magnitude (in either mode, for any register values, including during a change of
LIMIT); the output is 0 whenever the block is not running; START while RUNNING changes nothing; STOP ends the sequence at once; out-of-range writes store the
nearest legal value as the register table says.

## This is a block, not the board's top

The block has no pins of its own: the vendor's shell owns every pin and every clock and instantiates this block. So `design.xdc` holds **only comments**: no
PACKAGE_PIN, no IOSTANDARD, no `create_clock`, no `set_input_delay` or `set_output_delay` (the board-constraint check refuses a clock on any port that is not the
board's clock input, and this block's `clk` is not a board pin). Say in the comments that the block is built inside the Red Pitaya shell, whose ADC clock is 125 MHz
(8.000 ns). The port names are the ones above, not the board file's.
