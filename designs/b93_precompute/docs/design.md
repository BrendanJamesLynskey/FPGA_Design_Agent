# Brief 93 design note: deciding before the last byte

Status: decisions and alternatives. Written once stage 0 (reading the 58A/87 RTL for what each input depends on) had
shown what the question reduces to; the measurements in `what_we_found.md` came after it and did not change the
choices below. (The brief asked for this note before any code; the generator and the test benches were started
first on the strength of the stage-0 reading, and this note was committed before the Vivado runs and the results.
That ordering is recorded in the report as a deviation.)

## The question

Trading data arrives serially. Can the decision model do most of its work while the message is still arriving, so that
the last byte only selects an answer? Measure the saving from the last relevant byte to the decision and to the first
byte out, and what it costs in LUTs, flip-flops, block RAM and Fmax.

## What stage 0 found, and what it does to the question

The 87 features are functions of the book entry read for the message (the book **before** the message), of the
previous snapshot, of two windows (order-flow imbalance over 16 events, trade sign over 8) and of the previous
message's trade sign. None is a function of the message's own price, size, type or side. So in the 58A/87 path the
model's inputs are all known before the price field completes (3 clocks of slack after the book read). The "last
byte" the rules wait for (the price) is not an input of the model at all. That changes what each of the brief's
arms means:

1. **Baseline:** the 87 integration: features are computed at the price field, so the model adds clocks it did not need
   to (1 for the trees and `lg_small`, 3 for the 87 LUT network).
2. **Early features:** compute the whole feature vector at the book read, and commit the state at the price field
   exactly where 87 does. This is the arm that matters at 125 MHz, and it needs no table.
3. **Partial evaluation on the last-arriving feature.** Inside the feature unit the order-flow imbalance has the deepest
   logic (four 32-bit compares, a 35-bit sum, a clip, a window update). Treating it as the late feature, the block
   evaluates the model for each interval of its value and keeps the answers in a table. In this design the late
   value is no later than the others (they are registered together), so the table is exercised with a one- or
   two-clock skew, which is what a deeper feature pipeline would give; it is a block-level experiment, and the
   integration shows it costs nothing and gains nothing in clocks.
4. **Speculative decision:** not built. The class is ready before the rule's decision, so there is nothing to start
   early. The undo rate that a table-driven speculation would have had is counted on the test split.

A model whose features include the message's own price (for example "this order is inside the touch") would have the
price as its last input, and then arm 3 is the right tool. No such model exists in 87/89/91/92, and none was
trained here (it would not be "the 87 integer model", which the brief requires every arm to equal).

## Decisions and alternatives

| Decision | Alternatives | Why |
|---|---|---|
| Commit state only at `msg_px_v`, from values registered at the early clock | Commit at the early clock | A message that never reaches its price field (cut-off frame) must leave the state alone, as 87 does; the early unit holds results and commits them where 87 commits. `tb/tb_feat_pre.sv` runs both units in lockstep on streams with such messages. |
| Late feature = the order-flow imbalance (8 bits) | The directional feature (2 bits, deep compare); any of the early ones | It is the deepest logic in the feature unit; trees use 20 intervals of it and `lg_small` 8 (its encoder has 7 thresholds), so the table is small. The generator takes the late index as a constant (`LATE`). |
| Table over **intervals** the model can tell apart, not over all 256 values | A 256-entry table; the top bits only | Every threshold the model compares the feature with is a boundary; two values with the same compare results give the same class. 20 and 8 entries of 2 bits; no split of the feature is needed. |
| Table fill of 1 clock (`*_pe`) or 2 clocks (`*_pe2`, class scores registered before the argmax) | One only | The fill path is as deep as the whole model, so a 1-clock fill cannot beat the model's own Fmax. The 2-clock variant shows what registering the scores costs. |
| Late path: interval hit (compares of the 8-bit value with constants) then AND-OR of the table | Binary search; a 256-entry ROM | Parallel compares and one AND-OR are the shallowest; a ROM would need 256 table registers. |
| Class valid is checked against the gate in the integration: the gate releases at once when the class is already there, holds otherwise | Always hold one clock (baseline gate) | Holding would add a clock the early class does not need. `ml_gate_pre` has a bypass for a class arriving in the same clock as the decision and the hold path of `ml_gate` for a later one. |
| New parameter `ML_PRE` (0 default) in `trigger_core`; `ML_ARM` 4 = `lg_small_comb` | A separate top | Defaults keep 58A/87 behaviour (the 87 integration test passes unchanged in its numbers: 4/9/18). |
| Synthetic data and the 87 integer model, unchanged | A retrained model | Required: each arm equals the 87 model on every test sample. |

## Ideas, in our own words (checked citations)

- **Shannon expansion.** Any Boolean function can be written as `f = x . f(x=1) + not(x) . f(x=0)`: compute both
  cofactors, then let `x` choose. Hardware designers use it to move a late signal to the last multiplexer. Here the
  late feature is not one bit but a small integer, so the expansion has one cofactor per interval of its value
  (C. E. Shannon, "The synthesis of two-terminal switching circuits", Bell System Technical Journal 28(1), 1949,
  doi 10.1002/j.1538-7305.1949.tb03624.x; checked: the DOI record exists and matches title and year).
- **Carry-select addition** is the arithmetic analogue: compute the sum for carry-in 0 and carry-in 1, and let the
  late carry pick one (O. J. Bedrij, "Carry-select adder", IRE Transactions on Electronic Computers EC-11(3), 1962,
  pp. 340-346; checked against the dblp record and the IEEE DOI 10.1109/IRETELC.1962.5407919).
- **Partial evaluation** specialises a function on the part of its input that is already known. Fixing the early
  features and leaving the late one open gives a residual function of one variable, which is a table (Y. Futamura,
  "Partial evaluation of computation process: an approach to a compiler", Systems, Computers, Controls 2(5), 1971,
  pp. 45-50, reprinted in Higher-Order and Symbolic Computation 12(4), 1999, pp. 381-391; checked against the reprint
  record. N. D. Jones, C. K. Gomard and P. Sestoft, Partial Evaluation and Automatic Program Generation, Prentice
  Hall, 1993, is the textbook).
- **Speculative execution:** start the likely path and undo it if wrong. Here the undo is the 58A poison-or-cancel;
  see `docs/what_we_found.md` for why it was not needed.
- **Public feed format** (stage 0, prose only): Nasdaq TotalView-ITCH 5.0, section 1.3.1 "Add Order - No MPID
  Attribution": message type at offset 0, stock locate at 1 (2 bytes), tracking number at 3, timestamp at 5 (6 bytes),
  order reference at 11 (8 bytes), buy/sell at 19, shares at 20 (4 bytes), stock at 24 (8 bytes), price at 32 (4
  bytes), 36 bytes in all. The offsets were read from the published specification PDF text, not from memory.

No code was copied from any source.

## Verification plan (decided before the runs)

- Each block equals the 87 / 89 integer model on the whole 87 test split (99,100), on 20,000 random packed vectors
  and on every value of the late feature crossed with 40 random early vectors each; `out_v` follows `l_v` by exactly
  1 clock, with back-to-back samples (the tightest legal use) and with random gaps and delays.
- The integration (cocotb, Icarus): twin match on 400 generator messages and 300 edge-case messages (saturation, spread
  15, OFI clip, empty sides) for every `ML_ARM` x `ML_PRE`; bad-FCS frames; the 58A stage latencies with the model off
  and on, speculative and safe; the veto test.
- `ml_feat_pre` against `ml_feat` in lockstep, including messages that never reach their price field; a mutant that
  commits at the instrument field must fail.
- Verilator `-Wall` clean for the generated blocks and the new modules.
