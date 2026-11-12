# Reference QoR: P13-5

Memory estimate by the course's sizing exercise: 16 x 96 = 1536 cells, 16-bit counts = 2 RAMB18 or 1 RAMB36 (`hough_bram36` of 16 angles, 32 x 32 picture, 1024 votes = 1). The
reference clears all cells in one clock, which a block RAM cannot do (a sweep or a generation counter is the real design). Vivado QoR: **not run**.


## Whole-board reference build (course v1.3, brief 07a1c)

`tools/ref_build.py`, Vivado 2026.1, xc7a100tcsg324-1, 100 MHz, test shell included; gates all pass (the flow's standards check v1.0 still fails, as for every reference). Numbers from `results/61_c13_amend_2026_1/c13_hough_lines__vivado.json` (the 2026-11-12 amendment; before it the reference missed 100 MHz on 2026.1 by 0.166 ns).

| WNS at 100 MHz | LUT | FF | RAMB36/18 tiles | DSP48 | Power |
|---|---|---|---|---|---|
| +2.565 ns | 3,055 | 1,992 | 2 | 0 | 0.148 W |

The first reference cleared 1,536 counters in one clock, which block RAM cannot do (placed, router did not converge). Now two block RAMs plus one valid bit per cell: `clear` still zeroes every cell in one clock; a vote takes 6 clocks after its angle clock (table entry, products, distance, index, read, write) and busy stays high for them.
