# Reference Vivado builds of the course-tier development tasks (brief 07a1)

`tools/ref_build.py` on the reference of each difficulty 1-2 development task: Vivado 2025.2, xc7a100tcsg324-1, 100 MHz constraint, the whole board top (test shell included).
Difficulty 3 tasks keep the course's out-of-context numbers only (`hidden/reference_qor.md` of each task). Numbers are from `<id>__vivado.json`.

| Task | Gates | WNS at 100 MHz | LUT | FF | DSP48 | Note |
|---|---|---|---|---|---|---|
| `c14_int8_dot_requant` | fail at post-route timing | -21.7 ns | 1367 | 521 | 2 | one combinational multiply-add stage, as the course wrote it |
| `c15_softmax_unit` | fail at post-route timing | -33.6 ns | 1925 | 541 | 16 | one combinational stage |
| `c15_rmsnorm_unit` | fail at post-route timing | -52.2 ns | 5859 | 848 | 73 | one combinational stage |
| `c16_montgomery_mult` | pass | +2.0 ns | 757 | 822 | 0 | bit-serial |
| `c13_hough_lines` | not finished | n/a | n/a | n/a | n/a | placed; the router did not converge in 25 minutes (the reference clears 1536 counters in one clock, which block RAM cannot do) and was stopped |

The three arithmetic references miss 100 MHz because the course wrote them as single combinational stages (these are the seeds of the brownfield "close timing" tasks, brief 07a3); a greenfield agent design is scored on timing against the task's 100 MHz requirement, the reference is not. The flow's standards check (v1.0) also fails for every reference (they are not written to it).
