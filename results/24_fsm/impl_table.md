# Reference controller measurements (Vivado 2025.2, out of context, xc7a100tcsg324-1)

Clock 2.5 ns, input and output delay 0.5 ns. Slack in ns; negative = the path is longer than the budget. After opt_design, place_design and route_design (routed timing).

### Separation

Separated FSM (11 states + 4-bit counter, zero flag combinational or registered) against the monolithic FSM (23 states, no counter).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 29 | 8 | 2 | 2 | -1.29 | 264 | 0.04 | -1.54 | -0.60 | 11 states, sequential | 4/3/1/0 |
| mono_base | 24 | 23 | 1 | 2 | -0.73 | 310 | 0.24 | -1.39 | -0.60 | 23 states, one-hot | 0/22/1/0 |

### Outputs

OUT 0 combinational Moore decode, 1 registered decode (one cycle later), 2 lookahead (decode of the next state, registered).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 29 | 8 | 2 | 2 | -1.29 | 264 | 0.04 | -1.54 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_out1 | 29 | 16 | 3 | 2 | -0.49 | 334 | 0.31 | -0.44 | - | 11 states, sequential | 4/10/2/0 |
| sep_out2 | 66 | 22 | 2 | 3 | -0.42 | 342 | 0.41 | -0.50 | - | 11 states, one-hot | 3/17/2/0 |
| mono_base | 24 | 23 | 1 | 2 | -0.73 | 310 | 0.24 | -1.39 | -0.60 | 23 states, one-hot | 0/22/1/0 |
| mono_out2 | 22 | 13 | 1 | 2 | 0.15 | 426 | 0.88 | -0.44 | - | 23 states, sequential | 0/12/1/0 |

### Inputs

IN 0 raw, 1 one register, 2 two ASYNC_REG registers.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 29 | 8 | 2 | 2 | -1.29 | 264 | 0.04 | -1.54 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_in1 | 29 | 13 | 3 | 2 | -0.82 | 301 | 1.85 | -1.49 | - | 11 states, sequential | 9/3/1/0 |

### Encoding

`-fsm_extraction` mode (base = auto).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 29 | 8 | 2 | 2 | -1.29 | 264 | 0.04 | -1.54 | -0.60 | 11 states, sequential | 4/3/1/0 |
| mono_base | 24 | 23 | 1 | 2 | -0.73 | 310 | 0.24 | -1.39 | -0.60 | 23 states, one-hot | 0/22/1/0 |

### Reset style

0 async (FDCE), 1 sync (FDRE), 2 none (initial value), 3 async assert + 2-flop release.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 29 | 8 | 2 | 2 | -1.29 | 264 | 0.04 | -1.54 | -0.60 | 11 states, sequential | 4/3/1/0 |

### Reset style with a clock enable

The FSM advances only on `ce`. rst 4 = a synchronous reset looked at only when `ce` is high.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|

### Enable ratio (slow-FSM pattern)

One-in-N enable from a free-running counter; `_mc` adds `set_multicycle_path N -setup` and `N-1 -hold` on the FSM's own registers (brief 20 pattern). WNS r2r is over every register pair, so it includes the enable counter; WNS FSM->FSM is the FSM's own registers only.

| variant | LUTs | FFs | levels r2r | WNS r2r | WNS FSM->FSM | Fmax r2r (MHz) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|
| ratio_n2_mc | 28 | 9 | 1 | -0.03 | 1.28 | 395 | 5/3/1/0 |
| ratio_n2_nomc | 28 | 9 | 3 | -0.58 | -0.58 | 324 | 5/3/1/0 |
| ratio_n4_mc | 30 | 11 | 1 | 0.27 | 6.27 | 448 | 7/3/1/0 |
| ratio_n4_nomc | 30 | 11 | 3 | -0.66 | -0.66 | 317 | 7/3/1/0 |
| ratio_n8_mc | 31 | 12 | 1 | 0.29 | 16.36 | 452 | 8/3/1/0 |
| ratio_n8_nomc | 31 | 12 | 3 | -0.66 | -0.66 | 316 | 8/3/1/0 |

### Input from another clock

IN 0 / 1 / 2 on an `ack` launched by an unrelated clock.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
