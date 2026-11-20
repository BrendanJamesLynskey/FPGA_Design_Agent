# rm_gp_ml: the ML decision stage in the 10G trading path (brief 113)

Build `rm_gp_ml` of `designs/b96_kr260_10g` is build `rm_gp` (RATE_MATCH = 1, RM_OWN = 1: the own gray-pointer elastic buffer, board-measured in brief 96E) with a model behind the rule. Everything here is
**synthetic**: the stimulus is the seeded order-flow generator of brief 87 (`designs/b87_ml_trading/model/lobsim.py`) and a random stress set, the frames are our own Bench Feed v1 mock format, and no exchange, firm or
product is involved. Register map: [ml_registers.md](ml_registers.md). Results and records: `results/b113/`.

## 1. Which block, and why (by evidence)

The candidates are the decision blocks of briefs 87, 89, 91, 92 and 93, all trained and scored on the brief 87 splits (seed split, 10 test sessions, 99,100 samples; paired 95 % t-intervals). The path's clock
is the core clock, 161.1328 MHz = 6.2061 ns; the out-of-context numbers are on the xck26-sfvc784-2LV-c, Vivado 2026.1 (brief reports 87, 89, 91, 93).

| Block | Test accuracy | Clocks (II 1) | Closed at (K26, out of context) | LUT | Fits one 6.2061 ns clock | Source |
|---|---|---|---|---|---|---|
| trivial imbalance rule (baseline) | 0.4266 | 1 | 2.0 ns floor | 2 | yes | 87 |
| **87 boosted trees, `gbt_comb`** | **0.4914** (3-seed mean 0.4924) | 1 | 4.30 to 4.4 ns | 640 | yes | 87, 93 |
| 89 `lg_small_comb` (LUT network) | 0.4892 (3-seed mean 0.4856) | 1 | 4.45 to 4.5 ns | 325 | yes | 89, 93 |
| 89 `lg_add_comb` | 0.4913 | 1 | 4.95 ns | 882 | yes | 89 |
| 87 MLP int8, hand RTL | 0.4988 | 13 | 2.9 ns | 6,018 | no: 13 clocks (37.7 ns) | 87 |
| 91 best low-bit net (`log4_nz`, `int4`) | 0.4919, 0.4890 | 1 (comb) | 10.05 to 11.0 ns | 1,406 to 2,068 | no: does not close at 6.2 ns | 91 |
| 91 `log4p1` (h8) | 0.4803 | 1 | 6.85 ns | 624 | no | 91 |
| 92 history arms | 0.4997 (other data: self-exciting generator, not comparable) | stateful, 10 ns head | 10 ns | | no | 92 |

Two blocks are statistically level on accuracy per clock: the trees and `lg_small` (paired difference -0.0022 [-0.0096, 0.0051] on the built seeds), both one clock, both closing inside one core clock with 1.7 ns of
margin before routing. **The trees are chosen**: the higher accuracy by seed mean (+0.0068 over `lg_small`'s 0.4856), the same 1 clock, the shortest closed period (4.30 ns), and the only block whose feature unit
and gate were already integrated and verified end to end (brief 87, `ML_ARM = 1`; brief 93 measured its early-feature variant). The cost is LUTs (640 against 325), which is 0.5 % of the part. Not chosen, and why:
the MLP (best accuracy, 13 clocks), the low-bit nets (do not close at 6.2 ns, 4 to 6 times the LUTs for the same accuracy: brief 91's verdict), history and attention (a different data set and a stateful front end:
brief 92's gate passed, but its heads close at 10 ns or more).

## 2. Which build: `rm_gp`, not the default

The default build (`RATE_MATCH = 0`, the 97C path) has the lowest latency (10.6 clocks in simulation) but runs the MAC and the decision in the recovered receive clock and crosses the decision to the transmit clock by
pulses and a quasi-static bus; it has no rate matching, so it is only safe against a partner within a few ppm of our clock. `rm_gp` (RATE_MATCH = 1, RM_OWN = 1) puts the whole decision in the core (transmit) clock behind
an elastic buffer that tolerates +-100 ppm, and it is the build with a board measurement (96E: E 21.0, L 54.0, D 12.0 clocks, 0 ppm), so an in-context change can be measured against that reference. The ML stage
needs a decision in one clock domain with the order logic; build `rm_gp_ml` therefore exists only with RATE_MATCH = 1 (the core refuses to elaborate otherwise). The bypass variant (`rm_gp_bypass`, brief 96F1b) is not
touched.

## 3. What the stage adds to the path, and what it had to add

The path has no book. The model's inputs are the order-flow features of brief 87: both best sizes, the spread, a 3-bit imbalance bucket, the trade-sign sum of 8, the order-flow imbalance over 16 events and the last
mid move. They need the top of the book of the tracked instrument and two short windows of past messages. **The minimum added** (all in `rtl/ml_stage.sv`, 14 status words, three registers):

- a one-instrument top-of-book (best bid and ask, price and size, 4 x 32 flops) with the semantics of `b58a_trigger/rtl/book.sv` (ADD and MODIFY set a side, CANCEL empties it, TRADE reduces it at its best price);
- the previous snapshot, a 16 x 8-bit order-flow window, an 8 x 2-bit trade window, the last mid direction (the state of `ml_feat.sv`, same arithmetic);
- the 30-tree classifier `gbt_comb` (unchanged generated RTL of brief 87), between registers.

One instrument only (the tracked one, ML_INST): a book for 256 instruments would be a BRAM and is not needed for the measurement.

## 4. How it is arranged: the class is ready before the message arrives

Brief 93 showed that no input of the model depends on the message's own price, size, type or side: every feature is a function of the book and windows BEFORE the message under decision. So the model is
a feed-forward pipeline running continuously behind registers that move only when a good frame ends:

| Clock | What happens |
|---|---|
| T0 to T5 | the frame arrives (`m_v` words 0 to 5): addresses, IPv4, UDP, header checked |
| T6 | word 6: type, side, instrument, price high half known |
| T7 | word 7: the price word. The rule's `hit` is computed; the stage **observes** the message (latches type, side, price, size) and `ml_agree` (registered class = up) is read for the veto |
| T8 | the rule's order decision `fire` is registered (**no clock added** by the stage) |
| about T11 | the frame ends: `m_end` with the FCS verdict. A good frame **applies** the message to the state (book, windows, previous snapshot); a bad one discards it |
| +1, +2, +3 after an apply | stage-1 registers (order-flow term, direction, sizes, spread, imbalance bucket, trade term), features registered (`feat_r`), class registered; `settle` counts these 3 clocks, `cls_ok` rises at +4 |

With frames at least 10 clocks apart (the minimum for a 66-byte frame: 10 words) the next price word comes at least 6 clocks after the apply, and the class is settled 4 clocks after it. A decision that ever
came earlier is counted (`n_late`) and, in veto mode, fails closed. The class is therefore of the state before the message, exactly as in brief 87 and 58A; the message moves the state after the decision.

Costs of this arrangement: 3 pipeline registers of 38 + 31 bits, the pending message (3 x 32 + 10 bits), and the state flops; no clock on the order path. What it cannot do: use the message's own fields as a model input
(none of the brief 87 features does).

**Counterfactual measured in simulation** (`ML_HOLD`, never in a real build): had the class had to be made after the message arrived, the order would leave 1 or 2 clocks later (features at the price word, class a
clock later, then the release), shown by holding the release N clocks; the measurement method resolves the clock (`results/b113/latency.json`).

## 5. Fail-closed rules

- A frame whose FCS fails, whose length differs from its IPv4 length plus 18, or that was cut by an error character is **observed but never applied**: the corrupted message cannot move the model.
- A message for another instrument is not classified and not applied; the rule's decision for it passes unchanged.
- In veto mode a rule decision is kept only if the class is "up" (the base design sends only buys); a vetoed decision sends nothing and takes no order number (the order-count and order-content checks of 97C stay valid).
- A decision before the class has settled is vetoed (and counted). With ML_CTRL bit 0 = 0 (shadow, the reset state) the rule decides exactly as in rm_gp and nothing is ever vetoed.
