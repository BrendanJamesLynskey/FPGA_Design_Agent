"""Writes pilots/225/<block>/spec.md for the two Red Pitaya custom instruments (brief 225) from the register maps in hil/redpitaya_regs.py, so the spec's
register tables cannot differ from the maps the models and checks use. Run: python3 pilots/225/make_specs.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hil.redpitaya_regs import MAPS  # noqa: E402

PORTS = """```
module {name} (
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
```"""

TEXT = {
"rp_freqcount": """# P1: frequency and period meter for the Red Pitaya (natural-language spec)

*Written as a user would write it, for my Red Pitaya STEMlab 125-14 on my desk. The block's ID register reads 0xFDA10101.*

I want the Red Pitaya to be a frequency counter. The signal comes in on IN1 (the fast analogue input, on the LV jumper, so +-1 V full scale). Count its rising edges
over a gate that is a fixed number of cycles of the board's 125 MHz clock, and also time the span from the first to the last edge in the gate, so I can get the
frequency two ways: edges / gate time, and (edges - 1) x 125 MHz / span (better at low frequencies). A Schmitt trigger with two thresholds (in ADC counts, set
by registers) decides what an edge is, so noise on a slow signal does not count. Signals up to 30 MHz matter to me; a gate of 0.1 s or 1 s is typical.

I do not want the design to be the whole FPGA image. It goes into the vendor's Red Pitaya shell as a block (the shell keeps the ADC, DAC, scope and register
window working); I only write the block, with the ports below, and the shell's system bus is how I talk to it from Linux.

## The block's ports (use exactly these)

{ports}

The shell's register bus: one access per cycle; the block answers in the next cycle with `sys_ack` high for one cycle and `sys_rdata` valid in that cycle;
`sys_err` high with `sys_ack` means the access failed. Reads never have side effects. A write takes effect on the next clock. The block does not use `dac_a` or
`dac_b`: tie them to 0.

## Registers

{table}

## How I check it

On the board a script generates nothing: I feed IN1 from a known source (the Red Pitaya's own OUT1 through a short lead, a function generator, or the M2K) and run
three gates of 0.1 s, then compare both estimates with the known frequency. I expect agreement within 1000 ppm plus one edge of quantisation, and the two estimates
to agree with each other within the same quantisation. The registers must behave exactly as the notes say, including the cases a user could guess wrong.

Requirements I care about most: the count is exact for a clean periodic input (no edge lost or doubled at the gate boundaries); GATE_ACTUAL always equals the
gate that was asked for; a START while BUSY changes nothing; thresholds in the wrong order set BAD_THRESH and count nothing; an input that never crosses both
thresholds reports FEW_EDGES with EDGES 0 or 1 and does not hang.
""",
"rp_patgen": """# P2: programmable pulse and pattern generator for the Red Pitaya (natural-language spec)

*Written as a user would write it, for my Red Pitaya STEMlab 125-14 on my desk. The block's ID register reads 0xFDA10201.*

I want the Red Pitaya to make a pulse train or a short repeating pattern on OUT1 (the DAC, +-1 V into 50 ohm, 8192 counts per volt). Pulse mode: a period and a
width in cycles of the 125 MHz clock, a high level and a low level, a number of periods or "until I stop it". Pattern mode: up to 16 samples, each held for a
number of cycles, repeated a number of times or until stopped. It is my first output design, so it must be safe: **every level and sample is cut to a ceiling
(LIMIT, default 0.5 V, never more than 0.9 V) in hardware**, whatever I write, and the output is 0 at reset, after STOP and when a sequence is done.

It goes into the vendor's Red Pitaya shell as a block (the shell keeps the ADC, DAC, scope and register window working; the shell adds the block's DAC term to the
factory generator's, which is idle); I only write the block, with the ports below.

## The block's ports (use exactly these)

{ports}

The shell's register bus: one access per cycle; the block answers in the next cycle with `sys_ack` high for one cycle and `sys_rdata` valid in that cycle;
`sys_err` high with `sys_ack` means the access failed. Reads never have side effects. A write takes effect on the next clock. Only `dac_a` is driven (OUT1);
tie `dac_b` to 0. `adc_a` and `adc_b` are not used.

## Registers

{table}

## How I check it

A script writes the registers, starts a four-period pulse train at 0.25 V and 100 kHz and reads STATUS and PERIODS_DONE back; I look at OUT1 on a scope or loop
it into IN1 (LV) with a short lead. I also write levels above LIMIT and check CLAMPED sets and the output never exceeds LIMIT. The registers must behave exactly
as the notes say, including the cases a user could guess wrong. The waveform is checked cycle by cycle in simulation.

Requirements I care about most: no output sample ever exceeds LIMIT in magnitude (in either mode, for any register values, including during a change of
LIMIT); the output is 0 whenever the block is not running; START while RUNNING changes nothing; STOP ends the sequence at once; out-of-range writes store the
nearest legal value as the register table says.
""",
}
#: added to both specs after the agent runs on the spec without it: P2's first run failed stage 1 on the constraints gate (it pinned the block's dac_a to the DAC pins
#: and clk to the board clock pin, as if the block were the board's top); P1's first run passed (it left design.xdc empty), but P1's second run and P2's third failed the
#: same gate on a create_clock on clk. The agent runs are listed in results/225_redpitaya/README.md.
NOT_A_TOP = """
## This is a block, not the board's top

The block has no pins of its own: the vendor's shell owns every pin and every clock and instantiates this block. So `design.xdc` holds **only comments**: no
PACKAGE_PIN, no IOSTANDARD, no `create_clock`, no `set_input_delay` or `set_output_delay` (the board-constraint check refuses a clock on any port that is not the
board's clock input, and this block's `clk` is not a board pin). Say in the comments that the block is built inside the Red Pitaya shell, whose ADC clock is 125 MHz
(8.000 ns). The port names are the ones above, not the board file's.
"""
for name, m in MAPS.items():
    from hil.redpitaya_regs import datasheet
    ds = datasheet(m)
    table, notes = ds.split("Behaviour a user could guess wrong:")
    table = "\n".join(table.splitlines()[2:]).strip()
    body = (TEXT[name] + (NOT_A_TOP if name in ("rp_patgen", "rp_freqcount") else "")).format(ports=PORTS.format(name=name), table=table + "\n\nBehaviour a user could guess wrong:\n" + notes.rstrip())
    d = ROOT / "pilots" / "225" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body)
    print("wrote", d / "spec.md")
