# Stage 2 (plan only): where FP4 hardware would matter, for the larger phase-2 student

Status: **plan only.** Nothing here has been built or measured. Phase 1 (this brief) used weights that are constants in
the fabric; the numbers it measured are in `what_we_found.md`.

## Why phase 1 says little about the larger student

The phase-2 student (brief 87, `designs/b87_ml_trading/docs/jepa_student_plan.md`: a JEPA-distilled model, trained by
self-supervised prediction on unlabelled order flow, then distilled into a fabric-sized network) is larger than the
networks here (264 weights at most), and its weights live in block RAM, because with tens of thousands of weights
constants-in-LUTs stop being cheap and because the weights can then be reloaded without a new bitstream. Three things
change:

1. **A weight is data, not wiring.** In phase 1 a power-of-two weight is a shift (free) and an INT4 weight a constant of
   at most two terms. With weights read from memory, a "multiply by a power of two" is a barrel shifter and an INT4
   multiply is a real 4 x 4 multiplier, so the log4 advantage (a shift needs no multiplier) becomes a smaller one: a
   3-bit-exponent shifter in LUTs against a DSP slice. Phase 1's measurement of that advantage does not transfer; it
   would have to be re-measured with the weight in a register.
2. **The multiply moves to the DSP48E2 or stays in LUTs.** The K26 (`xck26-sfvc784-2LV-c`, measured in this repo's
   utilisation reports) has 1,248 DSP slices, 144 block RAM tiles, 64 UltraScale RAM blocks and 117,120 CLB LUTs.
3. **Bandwidth, not arithmetic, tends to bound the size.** A block RAM tile read returns one word per port per clock;
   feeding a wide MAC array needs many ports (below).

## DSP48E2 packing of 4-bit operands

- AMD's white paper WP521, "Convolutional Neural Network with INT4 Optimization on Xilinx Devices" (24 June 2020, rev
  1.0.1), reports up to 77% more performance than INT8 on real hardware. Only its abstract page was read for this
  plan; the PDF body, where the packing is described, was not retrievable here and must be read before any design
  work.
- The packing scheme itself, as described in arXiv 2203.11028 (DSP-Packing: Squeezing Low-precision Arithmetic into FPGA
  DSP Blocks; abstract read): four 4-bit multiplications can be packed into one DSP in one clock, the earlier scheme
  gives errors (mean absolute error 0.37) that can be corrected, and an approximate "overpacking" fits six 4-bit
  multiplications per DSP at a mean absolute error of 0.47. Our plan: use the corrected, exact packing for INT4, and
  treat the approximate one as an accuracy experiment, never as the default, because a fixed-latency decision stage
  needs a result equal to its integer twin.
- What each format needs at the multiplier: INT4 weights times unsigned 4-bit activations are the case the packing was
  made for. **MXFP4 elements in integer units (x2) are 5-bit signed values (up to +-12), so they do not fit INT4
  operands:** either a DSP is used with wider operand slots (fewer products per DSP), or the element is decoded to a
  shift-add in LUTs (phase 1's `mxfp4` cost, 0 to 2 terms per element). The per-block E8M0 scale is applied once per
  block after the accumulation, as the OCP MX dot product defines, so it is a shift of a sum, not a per-product cost.
- MXFP4 against INT4 at this size: storage is 4.25 bits per weight against 4 (the shared scale: 8 bits per block of 32;
  our neurons' rows are shorter than a block, so the block would be a row padded or a smaller block), and the compute
  is equal-or-worse on a DSP (5-bit elements). Where MXFP4 can help is accuracy on weight distributions with outliers.
  Phase 1's accuracy measurements (in `what_we_found.md`) are the only evidence we have, on one 264-weight network; they
  say nothing about a wide model.

## Expected bottleneck (estimate, to be measured)

For a student of N weights per inference and a target of an answer in about 8 clocks, the MAC array must do N / 8
products a clock. With four INT4 products per DSP and all 1,248 DSPs that is at most about 5,000 products a clock, i.e.
N up to about 40,000 in 8 clocks, if the weights could be fed. One RAMB36 port carries 72 bits, which is 18 INT4
weights a clock, so about 280 ports (140 tiles, nearly all 144 on the K26) would be needed to feed 5,000 products a
clock: **weight bandwidth saturates the block RAM before the DSPs run out.** So a student of up to about 10,000 weights
is bounded by the DSP count and the adder-tree depth (about 2 clocks of accumulation for a 16-input sum at 125 MHz),
and above that by block RAM ports; keeping the weights in LUT RAM or registers (as phase 1 does for hundreds) removes
the port limit but costs LUTs (the 87 hand MLP: 6,018 LUTs, `results/b87/summary.json`). The brief 87
latency budget (8 clocks at 125 MHz) leaves about 2 clocks for the memory read and accumulation overhead.

## Plan

1. Read WP521 and arXiv 2203.11028 in full; write the exact packing for the DSP48E2 in our own words.
2. Build a one-layer test bench: 16 x 16 INT4 layer with weights in a RAMB18, once with DSP packing and once in LUTs;
   measure LUTs, DSPs, clock and latency on the K26 and the Artix-7 (7-series DSP48E1 is 25 x 18, so the packing does
   not carry over; record that in the family matrix).
3. Repeat with MXFP4 elements decoded in LUTs and with log4 as a shifter; compare at the same accuracy.
4. Only then choose the format of the distilled student, with accuracy decided on validation, as in this brief.
