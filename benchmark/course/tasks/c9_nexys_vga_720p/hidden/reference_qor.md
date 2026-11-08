# Reference QoR: p9_nexys_vga_720p

Not run (OOC or full-flow). The course recorded only the board result of the 720p lab design, in `results/p9_video_board.md` of the course repository (the video chain ran on the board; no timing numbers for this block).


## Whole-board reference build (course v1.3, brief 07a1c)

`tools/ref_build.py`, Vivado 2025.2, xc7a100tcsg324-1, 100 MHz, test shell included; gates all pass (the flow's standards check v1.0 still fails, as for every reference). Numbers from `results/c9_nexys_vga_720p__vivado.json`.

| WNS at 100 MHz | LUT | FF | RAMB36/18 tiles | DSP48 | Power |
|---|---|---|---|---|---|
| +3.678 ns | 507 | 318 | 0 | 0 | 0.229 W |

The `cdc_no_critical` gate failed on the first reference (BTNC and SW used directly in the pixel clock domain, MMCM LOCKED used directly in the system clock domain). Now two-flop `ASYNC_REG` synchronisers on all three; the CDC report lists only Info items.
