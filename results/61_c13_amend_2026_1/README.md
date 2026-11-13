# c13_hough_lines reference, rebuilt after the 2026-11-12 amendment (Vivado 2026.1)

`c13_hough_lines__vivado.json`: `benchmark/tools/ref_build.py benchmark/course/tasks/c13_hough_lines`, Vivado 2026.1, xc7a100tcsg324-1, 100 MHz, test shell included, one build.
All gates pass except the flow's standards check v1.0 (fails for every reference).

| | before (`../vivado_2026_1_remeasure/course_ref/`) | after |
|---|---|---|
| WNS at 100 MHz | -0.166 ns (setup gate fails) | +2.565 ns |
| LUT / FF / RAMB tiles / DSP48 | 3,069 / 1,919 / 2 / 0 | 3,055 / 1,992 / 2 / 0 |
| Power | 0.150 W | 0.148 W |

The change is described in [benchmark/AMENDMENTS.md](../../benchmark/AMENDMENTS.md) (2026-11-12). Placement moves of a few LUTs are run-to-run noise.

## Records

- `c13_hough_lines__vivado.json`: the single reference build (gates, timing, utilisation, power) the table above is read from.

## Reproduce

`python3 benchmark/tools/ref_build.py benchmark/course/tasks/c13_hough_lines` on Vivado 2026.1 (xc7a100tcsg324-1, 100 MHz, test shell included). It needs a heavy slot and writes a record like the one here; placement may move a few LUTs.

## Known gaps and limits

- One build before and one after the amendment; slack and LUT differences of this size include run-to-run placement noise.
- The standards check v1.0 fails here, as for every reference.
- Only `c13_hough_lines` was rebuilt; the other course references are in `../vivado_2026_1_remeasure/course_ref/`.
- No hidden-test or board result is recorded in this folder.
