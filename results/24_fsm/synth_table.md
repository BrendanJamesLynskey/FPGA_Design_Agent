# Reference controller measurements (Vivado 2025.2, out of context, xc7a100tcsg324-1)

Clock 2.5 ns, input and output delay 0.5 ns. Slack in ns; negative = the path is longer than the budget. Synthesis only (no placement, so wire delay is an estimate: use it for order, not for Fmax).

### Separation

Separated FSM (11 states + 4-bit counter, zero flag combinational or registered) against the monolithic FSM (23 states, no counter).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_z1 | 30 | 9 | 2 | 3 | -0.51 | 333 | 0.52 | -1.62 | -0.60 | 11 states, sequential | 5/3/1/0 |
| mono_base | 26 | 23 | 1 | 2 | -0.97 | 288 | 0.27 | -1.74 | -0.60 | 23 states, one-hot | 0/22/1/0 |

### Outputs

OUT 0 combinational Moore decode, 1 registered decode (one cycle later), 2 lookahead (decode of the next state, registered).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_out1 | 33 | 16 | 3 | 2 | -1.01 | 285 | 0.01 | -0.46 | - | 11 states, sequential | 4/10/2/0 |
| sep_out2 | 70 | 22 | 2 | 3 | -1.05 | 281 | 0.12 | -0.46 | - | 11 states, one-hot | 3/17/2/0 |
| mono_base | 26 | 23 | 1 | 2 | -0.97 | 288 | 0.27 | -1.74 | -0.60 | 23 states, one-hot | 0/22/1/0 |
| mono_out1 | 26 | 31 | 2 | 3 | -1.03 | 283 | -0.06 | -0.46 | - | 23 states, one-hot | 0/29/2/0 |
| mono_out2 | 26 | 13 | 1 | 2 | -0.19 | 371 | 0.97 | -0.50 | - | 23 states, sequential | 0/12/1/0 |

### Inputs

IN 0 raw, 1 one register, 2 two ASYNC_REG registers.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_in1 | 31 | 13 | 3 | 2 | -1.09 | 279 | 1.86 | -2.14 | - | 11 states, sequential | 9/3/1/0 |
| sep_in2 | 31 | 18 | 3 | 2 | -1.13 | 276 | 1.89 | -2.14 | - | 11 states, sequential | 14/3/1/0 |

### Encoding

`-fsm_extraction` mode (base = auto).

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_enc_gray | 30 | 8 | 2 | 3 | -1.04 | 283 | -0.05 | -2.12 | -0.60 | 11 states, gray | 4/2/2/0 |
| sep_enc_johnson | 43 | 10 | 2 | 3 | -1.36 | 259 | -0.06 | -2.15 | -0.60 | 11 states, johnson | 4/2/4/0 |
| sep_enc_off | 28 | 8 | 2 | 2 | -0.94 | 291 | 0.24 | -2.13 | -0.60 | not extracted | 4/4/0/0 |
| sep_enc_one_hot | 24 | 15 | 2 | 2 | -0.79 | 304 | 0.20 | -1.59 | -0.60 | 11 states, one-hot | 4/10/1/0 |
| sep_enc_sequential | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| mono_base | 26 | 23 | 1 | 2 | -0.97 | 288 | 0.27 | -1.74 | -0.60 | 23 states, one-hot | 0/22/1/0 |
| mono_enc_gray | 20 | 5 | 1 | 2 | -0.65 | 317 | 0.52 | -1.77 | -0.60 | 23 states, gray | 0/1/4/0 |
| mono_enc_johnson | 84 | 12 | 1 | 3 | -1.51 | 250 | -0.12 | -3.27 | -1.18 | 23 states, johnson | 0/2/10/0 |
| mono_enc_off | 21 | 5 | 1 | 2 | -0.65 | 317 | 0.52 | -1.77 | -0.60 | not extracted | 0/5/0/0 |
| mono_enc_one_hot | 26 | 23 | 1 | 2 | -0.97 | 288 | 0.27 | -1.74 | -0.60 | 23 states, one-hot | 0/22/1/0 |
| mono_enc_sequential | 22 | 5 | 1 | 2 | -0.54 | 329 | 0.52 | -1.77 | -0.60 | 23 states, sequential | 0/3/2/0 |

### Reset style

0 async (FDCE), 1 sync (FDRE), 2 none (initial value), 3 async assert + 2-flop release.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_base | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_rst1 | 31 | 8 | 2 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 7/0/0/1 |
| sep_rst2 | 28 | 8 | 2 | 2 | -0.97 | 289 | 0.00 | -2.14 | -0.60 | 11 states, sequential | 8/0/0/0 |
| sep_rst3 | 30 | 10 | 3 | 2 | -1.01 | 285 | 0.01 | -2.14 | -0.60 | 11 states, sequential | 4/5/1/0 |

### Reset style with a clock enable

The FSM advances only on `ce`. rst 4 = a synchronous reset looked at only when `ce` is high.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sep_ce_rst0 | 29 | 8 | 2 | 3 | -1.00 | 286 | 0.49 | -2.12 | -0.60 | 11 states, sequential | 4/3/1/0 |
| sep_ce_rst1 | 29 | 8 | 2 | 3 | -1.00 | 286 | 0.49 | -2.12 | -0.60 | 11 states, sequential | 7/0/0/1 |
| sep_ce_rst2 | 27 | 8 | 2 | 2 | -0.88 | 296 | 0.19 | -2.15 | -0.60 | 11 states, sequential | 8/0/0/0 |
| sep_ce_rst3 | 28 | 10 | 3 | 3 | -1.00 | 286 | 0.49 | -2.12 | -0.60 | 11 states, sequential | 4/5/1/0 |
| sep_ce_rst4 | 29 | 8 | 2 | 3 | -1.00 | 286 | 0.49 | -2.12 | -0.60 | 11 states, sequential | 7/0/0/1 |

### Enable ratio (slow-FSM pattern)

One-in-N enable from a free-running counter; `_mc` adds `set_multicycle_path N -setup` and `N-1 -hold` on the FSM's own registers (brief 20 pattern). WNS r2r is over every register pair, so it includes the enable counter; WNS FSM->FSM is the FSM's own registers only.

| variant | LUTs | FFs | levels r2r | WNS r2r | WNS FSM->FSM | Fmax r2r (MHz) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|
| ratio_n1 | 29 | 9 | 3 | -1.00 | -1.00 | 286 | 5/3/1/0 |
| ratio_n2_mc | 30 | 9 | 1 | -0.04 | 1.50 | 394 | 5/3/1/0 |
| ratio_n2_nomc | 30 | 9 | 3 | -1.00 | -1.00 | 286 | 5/3/1/0 |
| ratio_n4_mc | 32 | 11 | 1 | -0.03 | 6.50 | 395 | 7/3/1/0 |
| ratio_n4_nomc | 32 | 11 | 3 | -1.00 | -1.00 | 286 | 7/3/1/0 |
| ratio_n8_mc | 33 | 12 | 1 | -0.03 | 16.50 | 395 | 8/3/1/0 |
| ratio_n8_nomc | 33 | 12 | 3 | -1.00 | -1.00 | 286 | 8/3/1/0 |

### Input from another clock

IN 0 / 1 / 2 on an `ack` launched by an unrelated clock.

| variant | LUTs | FFs | control sets | levels r2r | WNS r2r | Fmax r2r (MHz) | WNS in->reg | WNS reg->out | WNS in->out | FSM (extracted) | flops (RE/CE/PE/SE) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cdc_in0 | 31 | 9 | 3 | 2 | -2.93 | 184 | -0.39 | -2.14 | -0.63 | 11 states, sequential | 5/3/1/0 |
| cdc_in1 | 31 | 14 | 4 | 2 | -1.09 | 279 | -0.39 | -2.14 | - | 11 states, sequential | 10/3/1/0 |
| cdc_in2 | 31 | 19 | 4 | 2 | -1.13 | 276 | -0.39 | -2.14 | - | 11 states, sequential | 15/3/1/0 |
