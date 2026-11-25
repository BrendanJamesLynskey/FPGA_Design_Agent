# Notional check: multiply against software price-band table (brief 188, item 14)

Question: can a table written by software replace the multiply, save a clock and not weaken the check? Out-of-context Vivado 2026.1 builds of `itch_ouch_top` for the K26 (xck26-sfvc784-2LV-c) at the 10G core clock, 6.2061 ns; records in `ooc/`. Clocks are RTL clocks from the last byte of the message (Icarus, `nt0/`, `nt1/`, `nt2/` `latency_sim.json`).

| Build | Where the check is computed | WNS at 6.2061 ns | LUT | FF | DSP | Closed |
|---|---|---|---|---|---|---|
| NOTIONAL_MODE 0 (no check) | - | +0.218 ns | 6669 | 6018 | 0 | yes |
| 1, multiply | in the verdict clock | -2.273 ns | 6969 | 6085 | 4 | no |
| 2, table | in the verdict clock | -0.634 ns | 7000 | 6530 | 0 | no |
| 1, multiply | pipelined over the book's three clocks | +0.080 ns | 6838 | 6178 | 4 | yes |
| 2, table | pipelined over the book's three clocks | +0.146 ns | 6848 | 6570 | 0 | yes |

Before brief 188 the same block (no notional check) read WNS +0.109 ns and 6621 LUTs (`results/b110/ooc/itch_ouch_top.json`).

## What this says
- Computed in the verdict clock, neither form closes: the multiply misses by 2.27 ns (four DSP blocks in a cascade) and the table by 0.63 ns (the shift, a 16 to 1 read and the compare). Closing either in that clock would cost at least one more clock between the book update and the order decision.
- Moving the work off the verdict clock removes the cost for both: the price is already known three clocks earlier (the ladder update, stage B3) and quantity and limits are static, so the check runs on an early copy of the price (`nt_px`) in three register stages that end in the verdict clock. Latency measured in simulation is the same in all three builds and the same as brief 110's record: book update 7 clocks, first order word 8 clocks, 3 when started speculatively (`nt0/` to `nt2/`).
- So the table does **not** save a clock against a pipelined multiply: both add none. What the table saves is the four DSP blocks, at about the same LUTs and 400 more flip-flops, and it closes with 0.066 ns more slack. What it costs is a software-written table and a check that can be stricter than the multiply.
- Not weaker: `tests/test_b110_model.py::test_notional_table_never_weaker_than_multiply` (20,000 random draws, shifts 0 to 19, limits to 2^40, prices to 2^32): the table never admits an order the multiply refuses; it refuses some that the multiply admits (a price below the top of its bucket). The bench compares both builds with the model on at-limit, one-over, zero-limit and last-bucket cases.
- The multiply is kept as `NOTIONAL_MODE` 1. The board build (`rm_gp_itch`) is NOTIONAL_MODE 0: its register window has no room for a 16-entry table.

## Cost of the other brief 188 logic (mode 0 against the earlier record)
WNS +0.218 ns now against +0.109 ns before, 6669 LUTs against 6621. A run at 5.0 ns is in `ooc/same_clock_nt0.json` (-0.096 ns; the earlier record closed it at +0.022 ns): the saturating level add, the software reference and the hold-off cost some margin at tighter clocks, none at the required one.
