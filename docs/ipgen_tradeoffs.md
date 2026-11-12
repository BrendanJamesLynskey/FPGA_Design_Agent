# ipgen trade-off view (design only, brief 19 section 8)

Status: **specification, not built.** Owner request (2026-11-10): "drop-down menus describe the performance options
available, and the consequent resource implications."

## What the user sees

One page per signal chain (the YAML of [docs/ipgen.md](ipgen.md)). The chain diagram of `results/19_ipgen_2026_1/chain/chain.svg` is
the canvas: each IP block carries one drop-down per option the adapter exposes, and every drop-down choice moves the
numbers on the diagram.

| Block | Drop-downs (the adapter's `options`) |
|---|---|
| FIR Compiler | coefficient width (12 .. 24), number of taps (from the design tool's minimum up to +50 %), data width, rounding mode, architecture (systolic / transpose), clock-to-sample ratio |
| CIC Compiler | stages (3 .. 6), rate, differential delay (1, 2), DSP or fabric adders, output width (full or truncated) |
| DDS Compiler | phase width, output width, SFDR mode (dither on or off) |
| CORDIC | iterations, data width, rounding |
| FFT | point size, scaling schedule (unscaled, scaled, block floating point), data width |
| Converter (external) | the part, from the board's inventory; its data-sheet numbers are read-only |

Beside each block: LUT, register, DSP, BRAM, Fmax and latency for the current choice, each with the change against the
current baseline (for example "DSP 4 -> 6, +2"). At the top of the page: the end-to-end SINAD and ENOB at the
last node, the passband ripple and the alias rejection, again with the change against the baseline. A node whose SINAD
falls by more than 1 dB against the previous node is marked: that is where the chain loses quality.

## Where the numbers come from

A **pre-computed sweep grid**, produced by the pipeline of this brief, never a live Vivado run.

1. **Grid.** For each block, the cross product of its options is bounded (a FIR: 4 coefficient widths x 4 tap
   counts x 2 data widths = 32 points; a CIC: 4 stages x 3 rates x 2 delays = 24). One pipeline run per point makes
   `grid/<block>/<hash>.json`: the spec, the design summary, the `create_ip` read-back (output width, latency,
   multiply-accumulates), the out-of-context synthesis numbers, and the bit-exact xsim result. The hash is of the
   block's spec, so a point is computed once.
2. **Chain numbers** (SINAD, ENOB, ripple, rejection) need no Vivado: they come from the integer chain model
   (`flow/ipgen/chain.py`) run for every combination of the blocks' choices that the page offers. The chain model is
   cheap (seconds), so these are a full grid, stored as `chain_grid.json`.
3. **Measured and predicted.** Every grid point carries both. *Measured* means the integer chain ran on the test
   tones; *predicted* means the noise budget only. A point is shown as measured when its IP stage was also matched
   bit for bit in xsim (`sim.match` true), otherwise as predicted and labelled so. Resources are always from a
   synthesis run (post-synthesis, out of context); a point without one shows "not synthesised".
4. **Interpolation rules.** Between grid points the page does **not** interpolate resources or Fmax (a DSP count is an
   integer that jumps). It interpolates nothing silently: a choice outside the grid is disabled in the drop-down.
   For SINAD along a continuous option (taps, coefficient width) the page may draw the trend line through the grid
   points, but the number printed is only ever a grid value. Fmax is shown as a range of the neighbouring points
   when the grid is sparse, never a single interpolated figure.

## How the agent uses the same table

The grid is the agent's lookup. Given a spec ("48 kS/s audio from the PDM microphone, SINAD at least 58 dB, at most 6 DSP"):

1. read `chain_grid.json` and keep the rows whose predicted-or-measured SINAD meets the spec;
2. of those, keep the rows within the resource budget (DSP, BRAM, LUT, and the board's Fmax);
3. choose the row with the least of the scarcest resource, preferring measured points over predicted ones;
4. emit that row's per-block specs to `flow/ipgen/run.py` (the build path the agent already uses), which regenerates
   the chosen IP and re-checks it in xsim. The grid chooses; the pipeline confirms. If the confirmed numbers differ
   from the grid's by more than a stated tolerance, the grid entry is marked stale.

No new registered tool is needed: the lookup is a file read plus the existing flow step. (A new tool changes the
model's tool list, which the eval-1 golden request test freezes; see brief 16.)

## What it would cost

About 24 to 32 synthesis runs per block at 2 to 5 minutes each, and xsim runs at 2 to 4 minutes, for the four blocks of the
PDM chain: a long overnight sweep under the heavy-slot rules, one implementation run at a time. The grid is rebuilt only when
a block's adapter or the Vivado version changes (the grid records both).

## Open questions for the owner

- Which chains does the page cover first (the PDM chain here; an XADC chain; a DDC from DDS + CIC + FIR)?
- Is a static page, built from the grid and shipped as JSON, enough, or does it need to run in the browser against the
  user's own spec (this needs the chain model ported to JavaScript)?
