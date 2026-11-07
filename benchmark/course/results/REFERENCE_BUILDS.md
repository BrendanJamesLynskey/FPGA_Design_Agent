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

## Second batch, 2026-11-07 (planner; the two-Vivado trial)

Same tool and settings, run two at a time for the small designs (each job capped at 5 GB) and one at a time at 12 GB for
the large ones. Agent results on the same tasks are in `results/course/<task>/run_*.json`.

| Task | Gates | WNS at 100 MHz | LUT | FF | DSP48 | Note |
|---|---|---|---|---|---|---|
| `c10_dds_sine` | pass | +3.26 ns | 1234 | 366 | 0 | |
| `c11_nco_mixer` | pass | +0.006 ns | 817 | 997 | 2 | closes with no margin |
| `c12_adsr_envelope` | pass | +3.24 ns | 523 | 357 | 0 | |
| `c12_nexys_pwm_audio` | pass | +3.06 ns | 368 | 317 | 1 | |
| `c14_systolic_matmul` | pass | +0.88 ns | 2195 | 2756 | 2 | |
| `c15_pq_search` | fail at post-route timing | -0.20 ns | 1854 | 1219 | 0 | close; a brownfield seed |
| `c14_nexys_tiny_cnn` | fail at post-route timing | -8.69 ns | 2872 | 1147 | 7 | brownfield seed |
| `c9_median3x3` | fail at post-route timing | -14.77 ns | 1199 | 1028 | 0 | the agent's batch-1 design met timing (+0.70 ns) |
| `c16_ntt_engine` | fail at post-route timing | -25.28 ns | 17856 | 3570 | 9 | 45 min, 5.8 GB at 12 GB cap; brownfield seed |
| `c9_nexys_vga_720p` | fail at post-synth CDC check | +3.92 ns | 495 | 310 | 0 | `cdc_no_critical` fails: a reference defect to fix |
| `c13_nexys_harris_vga` | **does not fit the device** | n/a | 155,527 needed | | | 63,400 LUTs available (also CARRY4, F7/F8): buffers inferred as logic; the task needs a fixed reference |
| `c13_nexys_blob_tracker` | not finished in 60 min at 12 GB | n/a | | | | still in timing optimisation |
| `c13_hough_lines` | not finished in 60 min at 12 GB | n/a | | | | still routing |

Memory (the monitor, `_handoff` of the planner): two small jobs together peaked at 7.9 GB; the large designs need 6 to
10 GB per job (NTT scope peak 10.4 GB), so they run alone.
