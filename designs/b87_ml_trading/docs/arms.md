# Decision arms and the model gate: datasheet

## Arm modules (`rtl/gen/*.sv`, `rtl/mlp_hls4ml_wrap.sv`)

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | the only clock |
| `rst` | in | 1 | synchronous, active high; clears the valid pipeline only (the datapath is not reset) |
| `in_v` | in | 1 | `in_f` is a sample this clock |
| `in_f` | in | 38 | packed features, f0 in the low bits: f0[7:0] bid size, f1[15:8] ask size, f2[19:16] spread, f3[22:20] imbalance bucket, f4[27:23] trade signs + 8, f5[35:28] OFI + 128, f6[37:36] last mid move (docs/data_model.md) |
| `out_v` | out | 1 | `out_cls` is the class of the sample given exactly `LATENCY` clocks earlier |
| `out_cls` | out | 2 | 0 down, 1 flat, 2 up; never 3 |

What a user could guess wrongly:

- **Inputs are not registered by the arm.** The producer must register `in_f` (the out-of-context wrapper and
  `ml_feat` do); a combinational path into an arm is timed only with its source register.
- **Latency is fixed** (the localparam `LATENCY`) for every input and every input spacing, and one sample may enter
  each clock. `out_cls` holds its last value when `out_v` is low and carries no meaning then.
- **Ties** between class scores go to the lower class index (down before flat before up).
- **Reset** clears `out_v` but not `out_cls`.
- **The hls4ml arm** runs its core every clock (`x_ap_vld` tied high); validity travels in the wrapper. Driving the
  core's `x_ap_vld` from `in_v` stalls the generated pipeline while no sample is valid (measured: latency 33 to 96
  clocks), so do not.

## Model control in `trigger_core` (only with `ML_ARM` > 0)

| Address | Name | Access | Bits |
|---|---|---|---|
| 0x02A | ML_CTRL | RW | [0] enable the gate; [31:16] tracked instrument; reset 0 |
| 0x02B | ML_LAST_CLASS | RO | [1:0] the class of the latest tracked message (reset 1); updates whether or not the gate is enabled |
| 0x02C | ML_VETOES | RO | orders dropped because the class disagreed; saturates at 2^32 - 1; cleared only by reset |

With `ML_ARM` = 0 the three addresses read 0, 1 and 0 and writes to 0x02A have no effect on the path.

Behaviour:

- **Features** come from the book entry read for each message of the tracked instrument (the book before that
  message) and from history registers that only that instrument's messages update. Other instruments do not change
  the features.
- **Gate off** (bit 0 = 0): the rule's decision goes on in the same clock, exactly as in 58A.
- **Gate on**: a decision for the tracked instrument waits `LATENCY` clocks for the class of the same message, then
  goes on. A buy order is kept only if the class is up, a sell only if it is down; otherwise the decision goes on with
  no order (the rule's pin and log actions still happen) and ML_VETOES counts it. A decision for another instrument
  goes on unchanged in the same clock.
- **Changing ML_CTRL while a decision is held**: the held decision is still released by its class.
- **Limit**: `LATENCY` at most 8 clocks (elaboration error otherwise), so a decision cannot drift past its frame's
  check-sequence verdict, which the 58A order slot binds it to.
