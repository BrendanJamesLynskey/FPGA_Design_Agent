# c13_hough_lines reference, rebuilt after the 2026-11-12 amendment (Vivado 2026.1)

`c13_hough_lines__vivado.json`: `benchmark/tools/ref_build.py benchmark/course/tasks/c13_hough_lines`, Vivado 2026.1, xc7a100tcsg324-1, 100 MHz, test shell included, one build.
All gates pass except the flow's standards check v1.0 (fails for every reference).

| | before (`../49_vivado_2026_1/course_ref/`) | after |
|---|---|---|
| WNS at 100 MHz | -0.166 ns (setup gate fails) | +2.565 ns |
| LUT / FF / RAMB tiles / DSP48 | 3,069 / 1,919 / 2 / 0 | 3,055 / 1,992 / 2 / 0 |
| Power | 0.150 W | 0.148 W |

The change is described in [benchmark/AMENDMENTS.md](../../benchmark/AMENDMENTS.md) (2026-11-12). Placement moves of a few LUTs are run-to-run noise.
