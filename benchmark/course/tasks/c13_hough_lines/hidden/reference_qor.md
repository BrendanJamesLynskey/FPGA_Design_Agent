# Reference QoR: P13-5

Memory estimate by the course's sizing exercise: 16 x 96 = 1536 cells, 16-bit counts = 2 RAMB18 or 1 RAMB36 (`hough_bram36` of 16 angles, 32 x 32 picture, 1024 votes = 1). The
reference clears all cells in one clock, which a block RAM cannot do (a sweep or a generation counter is the real design). Vivado QoR: **not run**.


## Whole-board reference build (course v1.3, brief 07a1c)

`tools/ref_build.py`, Vivado 2025.2, xc7a100tcsg324-1, 100 MHz, test shell included; gates all pass (the flow's standards check v1.0 still fails, as for every reference). Numbers from `results/c13_hough_lines__vivado.json`.

| WNS at 100 MHz | LUT | FF | RAMB36/18 tiles | DSP48 | Power |
|---|---|---|---|---|---|
| +0.013 ns | 3,062 | 1,915 | 2 | 0 | 0.149 W |

The first reference cleared 1,536 counters in one clock, which block RAM cannot do (placed, router did not converge). Now two block RAMs plus one valid bit per cell: `clear` still zeroes every cell in one clock; a vote takes 4 clocks after its angle clock and busy stays high for them.
