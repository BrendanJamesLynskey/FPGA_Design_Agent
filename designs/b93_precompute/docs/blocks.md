# Blocks and parameters (datasheet)

Every behaviour a user could reasonably guess wrong is stated here. Generated blocks come from
`python3 -m designs.b93_precompute.model.gen_rtl` (`--check` fails when a committed file is out of date).

## `ml_feat_pre` (early feature unit)

Same function as the 87 `ml_feat`, computed early. Ports: `clk`, `rst` (synchronous, active high), `ml_inst` (tracked
instrument), `inst_v` (the parser's `msg_inst_v`), `msg_px_v`, `msg_type`, `msg_side` (valid with `msg_px_v`),
`msg_inst` (valid from the clock after `inst_v`), `bk_valid`, `bk_*` (the book entry for this message), outputs
`trk_v`, `feat_v`, `feat[37:0]` (the 87 packing: f0 bits 7:0 bid size, f1 15:8 ask size, f2 19:16 spread, f3 22:20
imbalance bucket, f4 27:23 trade sign sum, f5 35:28 order-flow imbalance, f6 37:36 mid direction).

- Clocks, with `c` the clock `inst_v` is high: the book entry is on `bk_*` at `c+1`; `trk_v` is high at `c+1` for a
  message of the tracked instrument; `feat_v`/`feat` follow at `c+2` and hold until the next tracked message's
  `c+2`; `msg_px_v` comes at `c+4` (four price bytes later).
- **State is committed at `msg_px_v`, not at `c+1`**, from values registered at `c+2`. A message whose price field never
  completes leaves every state element unchanged; its vector appears on `feat` and is never used again. (On the wire
  this cannot happen with the 58A parser, because the FCS bytes reach the parser as data and complete the price
  field; the unit is correct for it anyway, and `tb/tb_feat_pre.sv` tests it.)
- No vector and no `trk_v` for a message whose instrument is outside the book (`bk_valid` low), as `ml_feat` gives none.
- Features of an empty side: size 0 and spread 15 (the 87 convention). Reset clears the state to zero sizes and prices,
  last direction "flat".

## `ml_gate_pre` (gate for an early class)

Same agreement rule and counters as `ml_gate`: a buy order needs class 2 (up), a sell order class 0 (down); a
disagreeing order is kept out (`o_fire_order` low), the rule's other actions go on, `vetoes` counts it.

- Gate disabled (`en` low): every decision passes unchanged in the same clock.
- Enabled and the message is tracked (`trk_v` seen since the last `inst_v`, and the decision not yet taken): if the
  class has arrived (earlier, or `cls_v` in the same clock as the decision) the decision leaves in the same clock;
  if not, it is held and leaves in the clock `cls_v` arrives. A tracked decision is taken once; a second decision for
  the same message passes unchanged.
- The next `inst_v` forgets the previous message's class and tracking, so a class is never used for another message.
- `en` is read at the decision's clock. `last_cls` follows every `cls_v`.

## `gbt_pe`, `gbt_pe2`, `lgs_pe`, `lgs_pe2` (table blocks)

Partial evaluation of the 87 trees (`gbt_*`, 20 intervals) and of the 89 `lg_small` network (`lgs_*`, 8 intervals) on
the late feature f5 (the order-flow imbalance, 8 bits). Ports: `clk`, `rst` (clears the valid pipeline only),
`e_v`, `e_f[37:0]` (the early features; bits 35:28 are ignored), `l_v`, `l_x[7:0]` (the late value), `out_v`,
`out_cls[1:0]`. Parameters (localparams of the generated file): `FILL` 1 (`*_pe`) or 2 (`*_pe2`, the class scores
are registered before the argmax), `LATENCY_LATE` 1, `NI` intervals.

- **Timing contract.** The table for the early vector presented at clock `t` is valid from `t + FILL`. `l_v` may be
  high from `t + FILL` up to `t' + FILL - 1`, where `t'` is the clock of the next `e_v`. A late value presented
  earlier or later is answered with another message's table: nothing detects it. `out_v` is `l_v` delayed by exactly 1
  clock. One late value a clock is accepted (the table is read, not consumed), and an early vector a clock when
  `l_v` follows `FILL` clocks later (the tightest legal use, tested).
- The table holds the class of the whole model for each interval of f5; an interval is a maximal set of values with
  the same results for every comparison the model makes with f5. Ties between class scores go to the lower class, as in
  the 87 and 89 models.
- Reset does not clear the table or the datapath; `out_cls` is undefined until the first `out_v`.
- In `trigger_core` (`ML_PRE` 2 and 3) the late value is the feature unit's own f5, delayed by `FILL` clocks as a deeper
  feature pipeline would deliver it; nothing in this design has f5 later than the others.

## `trigger_core` parameters

`ML_ARM` 0 none (default), 1 87 trees, 2 87 LUT network, 3 87 MLP (refused: 13 clocks), 4 89 `lg_small_comb`.
`ML_PRE` 0 (default; 87 behaviour, features at the price field), 1 early features with the unchanged model block, 2 early
features and the table block with `FILL` 1, 3 as 2 with `FILL` 2. `ML_PRE` > 0 needs `ML_ARM` 1, 2 or 4 (2 and 3: 1 or 4).
Registers 0x02A-0x02C are unchanged (`docs/register_map.md`).
