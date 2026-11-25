# Brief 201: published Fmax figures against the clock-buffer cap

Audit of every Fmax published in this repository against the clock-buffer minimum period of its part and speed grade, the cap applied where it binds, and the three extra parts measured for it. Vivado 2026.1, one routed out-of-context run per part, one thread. Method from [results/199_dsp_fmax](../199_dsp_fmax/README.md). Dated 2026-11-24.

## The limits

An out-of-context run has no clock buffer, so 1000 / (period - WNS) can exceed what a real design can clock: every fabric clock goes through a BUFG or BUFGCE, and `report_pulse_width` on a design with a BUFG in the clock path adds a Min Period check on the buffer's I pin. The probe is the brief-199 wrapper (`dsp_mul_pipe_ooc_bufg.sv`) at a clock faster than the buffer allows; the Min Period row is the cap.

| part | speed grade | buffer | Vivado Min Period | cap | data sheet | source of the run |
| --- | --- | --- | --- | --- | --- | --- |
| xc7a100tcsg324-1 | -1 | BUFG/I | 2.155 ns | 464.0 MHz | DS181 Table 32, FMAX_BUFG -1: 464 | [199](../199_dsp_fmax/pulse_width/a7_bufg/pulse_width.rpt) |
| xc7a35tcpg236-1 | -1 | BUFG/I | 2.155 ns | 464.0 MHz | DS181 (same) | [pulse_width/a35_bufg](pulse_width/a35_bufg/pulse_width.rpt) |
| xc7z020clg484-1 | -1 | BUFG/I | 2.155 ns | 464.0 MHz | DS187 Table 67, FMAX_BUFG -1: 464 | [pulse_width/z7020_bufg](pulse_width/z7020_bufg/pulse_width.rpt) |
| xczu3eg-sfvc784-2-e | -2 (0.85 V) | BUFGCE/I | 1.290 ns | 775.2 MHz | DS925 Table 84, BUFG FMAX -2 at 0.85 V: 775 | [pulse_width/zu3eg_bufg](pulse_width/zu3eg_bufg/pulse_width.rpt) |
| xck26-sfvc784-2LV-c | -2LV | BUFGCE/I | 1.379 ns | 725.2 MHz | DS925 Table 84, BUFG FMAX -2 at 0.72 V: 725 | [199](../199_dsp_fmax/pulse_width/k26_bufg/pulse_width.rpt) |

All five Vivado figures equal the data-sheet figure. The zu3eg row also settles brief 199's inference: the -2LV part is timed at the 0.72 V column (1.379 ns), the -2 part at the 0.85 V column (1.290 ns). Not measured, so no cap is applied: xcvu2p (refused by the Basic licence), -2 and -3 Artix-7 (data sheet 628 MHz), -1 UltraScale+ parts, -2L parts.

## Which published figures are above their cap

Searched: every JSON, Markdown, YAML and CSV under `results/`, `ip_lib/*/char/`, `designs/`, `site/data`, `docs`, `benchmark/` and the course repository, for any Fmax, MHz or closed-clock key or text; every Fmax producer in `flow/`, `designs/*/ooc`, `results/*/summary.py` and `hwsw/`. Artix-7 and Zynq-7000 figures: the highest is 367 MHz (137 xc7a35t), 307.5 MHz (ip_lib), 345 MHz (ipgen) against 464, so none is affected. K26 figures above 725.2 MHz:

| figure | file | raw | capped | binding limit |
| --- | --- | --- | --- | --- |
| 137 CORDIC P07, K26, post-synthesis Fmax | results/137_arith_pareto/k26/measured.json (`synth`), comparison.md | 832.64 | 725.2 | clock-buffer minimum period (BUFGCE) |
| b101 crc64_rx, K26, `viv_default`, closed 1.30 ns | results/b101/summary.json, summary.md, README.md | 769.2 | 725.2 (latency 2.6 to 2.758 ns) | clock-buffer minimum period |
| b101 crc64_rx, K26, `viv_perf`, closed 1.30 ns | same | 769.2 | 725.2 (2.758 ns) | same |
| b101 crc64_rx, K26, `viv_perf_retime`, closed 1.30 ns | same | 769.2 | 725.2 (2.758 ns) | same |
| b89 `lg_b87_layer`, K26, closed 1.3 ns | results/b89/summary.json (`rows[5].k26`) | 769.2 | 725.2 | same |
| b87 `imb_rule`, K26, closed 0.55 ns | results/b87/summary.json (`rows[0]`) | 1818.2 | 725.2 | same |
| 185 DSP study, 12 K26 points | results/185_dsp_slices/data/k26.json | up to 1126.1 | 725.2 | done in brief 199 |

Not affected, although the brief listed them: 137 K26 **post-route** figures (maximum 615.38), b91 (maximum 487.8), the other b101 K26 arms (maximum 606.1), b89 other rows, b87 `gbt_pipe` 645.2 and `lutnet` 512.8, b92, b93, the ip_lib characterisations (K26 maximum 308.5 MHz), b110 and b119 (161.1 MHz). The b87, b89, b91 and b92 latencies were already quoted at no faster than 2.0 ns, so they do not change. The 137 Pareto fronts use the post-route figure, so they do not change. K26 post-synthesis Fmax error of the cost model: RMS 64.0 % (max 68.2 %) as published, 62.8 % (64.9 %) with P07 at 725.2 (computed from `comparison.json`; the published tables keep the raw estimate).

Course lessons that quote an affected K26 figure (the course repository was not edited; each already says "setup-limited" and that the slice's own limit was not read, but none names the buffer cap): Part 18 lesson 1 (`01_the_k26_the_kr260_and_reading_an_ultrascale_plus_part.md`, table rows "32-bit registered adder 773 MHz" and "27 x 18 multiply 837 MHz"), Part 8 lesson 3 (`03_adders_and_the_carry_chain.md`, "about 773 MHz"), Part 8 lesson 9 (`09_arithmetic_timing_and_resources.md`, "about 837 MHz"). The Part 3 lesson 2 ratio (K26 2.5 to 2.9 times faster) rests on post-route figures below the cap and holds.

## Should the Fmax producers apply the cap? Yes

- A real design on these parts clocks through a BUFG or BUFGCE (or a BUFG_GT, whose limit is 512 MHz and is not modelled here); the data sheet and Vivado both forbid a faster clock, so an Fmax above the limit cannot be used. Nothing is lost by capping: the raw setup figure is kept beside it.
- The shared producer `flow/ipchar.py` is the one most likely to produce such a figure next, on any K26 block that closes fast. Today's ip_lib figures are all below the limit, so adding the cap changes no published number.
- Implemented as the brief-199 pattern: [flow/fmax_cap.py](../../flow/fmax_cap.py) holds the limits (one table, tested against `run_dsp.py`); `ipchar.parse(wd, clock_ns, part)` keeps `fmax_setup_mhz` (raw setup), sets `fmax_mhz` to the lowest of setup, the 2 x WPWS rule and the buffer limit, and adds `fmax_bound` (which limit binds) and `fmax_clock_buffer_mhz` for a part with a recorded limit. The result summaries (b87, b89, b91, b92, b101, 137) add `fmax_capped_mhz`, `fmax_bound` and `fmax_clock_buffer_mhz` beside the raw figure, which is not changed. Per-run records (`results/b101/k26/*.json`, `results/b87/ooc/*.json` and the like) are unchanged history. The `designs/*/ooc/ooc.py` search scripts still write the raw closed-clock figure; the summaries apply the cap.
- A cap is a ceiling, not a prediction: below it, setup, hold and primitive pulse width still decide, and the DSP data-sheet figure (644 MHz at 0.72 V) is lower than the buffer limit.

## Records

- `pw_probe.tcl`, `run_probe.sh`: the probe (three parts); `pulse_width/<run>/`: `pulse_width.rpt`, `pulse_width_violators.rpt`, `timing_summary.rpt`, `clock.xdc`, `info.txt` (part and speed grade, WNS) of the three runs (a35_bufg 1.8 ns, z7020_bufg 1.8 ns, zu3eg_bufg 1.0 ns). The a7 (xc7a100t) and k26 runs are in [results/199_dsp_fmax](../199_dsp_fmax/README.md).
- Code: [flow/fmax_cap.py](../../flow/fmax_cap.py), [flow/ipchar.py](../../flow/ipchar.py), [flow/arith_pareto.py](../../flow/arith_pareto.py) (`restate-cap`), [flow/oss_compare/run.py](../../flow/oss_compare/run.py) (`--table`), `results/b87|b89|b91|b92/summary.py`; tests: [flow/tests/test_201_fmax_cap.py](../../flow/tests/test_201_fmax_cap.py).
- Re-stated, with a dated change-log line in each README: [137](../137_arith_pareto/README.md), [b101](../b101/README.md), [b87](../b87/README.md), [b89](../b89/README.md), [b91](../b91/README.md), [b92](../b92/README.md); [docs/ip_variants.md](../../docs/ip_variants.md) describes the new row keys.

## Reproduce

Take a heavy slot (`_handoff/take_heavy_slot.sh "201: Vivado impl OOC 3 small BUFG pulse-width probe runs, <start>, expected end <hh:mm>, peak 3G"`), then `results/201_fmax_cap/run_probe.sh` (about 5 minutes; Vivado 2026.1, one thread, 4 GB cap), release your own lock. Without Vivado: `python3 flow/arith_pareto.py restate-cap` then `HW_DSE_SRC=<hw_dse src> python3 flow/arith_pareto.py report`; `python3 -m flow.oss_compare.run --table`; `python3 results/b87/summary.py` (likewise b89, b91, b92); `python3 flow/fmax_cap.py <part> <fmax_mhz>`.

## Known gaps and limits

- One run per part; the limit is a library constant of Vivado, so repeats would not change it. Parts and grades not probed (-2 and -3 Artix-7, -1 and -2L UltraScale+, xcvu2p) get no cap; `family()` returns None for them.
- BUFG_GT (transceiver clock, 512 MHz), MMCM and PLL output limits and the leaf-level BUFCE_LEAF are not modelled.
- The cap applies to a clock distributed by a global buffer; a design clocked from a transceiver or a regional buffer may have a different limit.
- The `ooc.py` search scripts of b87, b89, b91, b92, b93 and the generated ip_lib READMEs (`flow/net/ipdoc.py` text) are unchanged; their stored figures are all below their limits, except those restated above.
- b93 has no summary script; none of its figures is above a limit.
