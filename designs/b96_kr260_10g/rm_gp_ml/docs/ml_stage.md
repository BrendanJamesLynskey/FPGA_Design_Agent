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

## 6. Measured (all from `results/b113/summary.json`)

**Tick-to-trade in context, simulation** (the whole core in xsim 2026.1 with AMD's real XPM macros and the GT stand-in; the synthetic feed injected on the receive words; 10 orders at each of four receive-clock phases;
clocks of 6.2058 ns; price word on the GT receive port to the order's start block on the GT transmit port; `results/b113/latency.json`):

| Configuration | Tick-to-trade (mean over 4 phases) | Change against the build without the stage |
|---|---|---|
| `rm_gp` (no stage, the control) | 12.93 clocks | |
| `rm_gp_ml`, shadow | 12.93 | **0.00** (at every phase) |
| `rm_gp_ml`, veto | 12.93 | **0.00** (at every phase) |
| counterfactual: class made after the message, release held 1 clock | 14.03 | +1.1 |
| counterfactual: held 2 clocks | 14.93 | +2.0 |

The receive-start path (what the board's E stamps) and D move only in the counterfactual rows. **The stage costs no clock** because its class is ready before the price word (section 4); the counterfactual
rows show that the measurement would see a clock if there were one (the 0.1 over 1.0 is the gearbox's one-in-33 pause meeting the held order). The simulated tick-to-trade of the control, 12.93, is the 96E figure (12.9).

**Bit-exactness** (`results/b113/twin/`): a 370-frame mixed synthetic feed (the brief 87 generator and a stress set; 305 good frames; bad FCS, a frame longer than its IPv4 length, other instruments, two-message frames, a wrong
port, a wrong header) is injected into the whole core. For each of the 350 frames the rule path accepts, the 38-bit feature vector, the class, the rule's hit, the decision and the veto equal the Python twin's (0 mismatches);
the order count (25 in veto mode, 78 in shadow mode) and every stage counter equal the twin's. Run at two receive-clock phases in veto mode and one in shadow mode. The unmodified `rm_gp` core on the same stream sends the same
78 orders as the stage in shadow mode. The board's own stream (50 generator frames through the near-end loop, instrument 1) gives the counters the board driver predicts (49 down, 1 up; veto mode sends 1 order, shadow mode 50).
`ml_stage` alone against the twin in Icarus (CI): the same equality plus three seeded faults that must fail (`tests/test_b113_stage_rtl.py`). Safety counters (poisoned, dropped, underrun, late, stale, frame errors, buffer
overflow) 0 in every run.

**Implementation for the KR260** (Vivado 2026.1, `xck26-sfvc784-2LV-c`, one thread, 6 GiB scope, 0 cap hits, 2,219 s; `results/b113/builds/rm_gp_ml/`):

| | `rm_gp_ml` | `rm_gp` (control, brief 96F1's rebuild) |
|---|---|---|
| gates | 29 of 29 | 29 of 29 |
| setup / hold slack at the 6.206 ns core clock | +0.220 / +0.010 ns | +0.055 / +0.011 ns |
| `report_cdc` | 0 critical (CDC-3 info 1,199; CDC-6 warning 6; CDC-9 info 4; CDC-15 warning 2,548), no waivers | 0 critical |
| DRC, methodology critical | 0, 0 (15 methodology warnings as before) | 0, 0 |
| LUT / FF / BRAM / DSP | 8,312 / 22,136 / 0 / 0 | 6,842 / 18,940 / 0 / 0 |
| vectorless power, Tj | 1.149 W, 48.5 C | 1.124 W |
| build stamp | 22c35e72 | 6fd8a2bf |

**In-context post-route timing of the stage at the core clock** (`results/b113/builds/rm_gp_ml/stage/stage_timing.json`, the worst setup path ending in each part; the clock is 6.206 ns): state to stage-1 registers
**+0.556 ns** (5.55 ns of data path, 13 logic levels: the order-flow term), features to class (the trees) **+0.757 ns** (5.34 ns, 15 levels), the book update at an apply +0.791 ns, the observation latch +2.96 ns, the rule's
decision registers (with the veto) +2.37 ns, the rest more. The brief 87/93 out-of-context figure for the trees was 4.3 ns; in context, with routing, 5.3 ns. Nothing in the stage limits the build's worst slack (+0.220 ns,
elsewhere in the design). The stage uses 1,367 LUTs (579 in the trees) and 884 FFs; the rest of the added area is the status readout (the 14-word handshake crossing is 1,756 FFs) and the pending message.

## 7. Known gaps

- **Not on a board.** The pre-registered board test and its script exist (`_handoff/fpga_agent/run_113_ml_stage3.sh`, `results/b113/preregistration.md`); the xsim stand-in for the transceiver is not the GT, so the latency
  statement is "no clock added in the fabric", which the board confirms or refutes.
- **One instrument, a top-of-book.** The real 58A book holds 256 instruments in a BRAM; a multi-instrument stage would need a read at the instrument field and a deeper model state (the windows are per instrument).
- **The model sees only the first message of a frame** and none of a frame longer than 60 bytes of IPv4 length, like the rule.
- **The generator is one planted-signal data set.** The classes the board stream produces (first frame up, then down) test the bit-exactness of the hardware, not the usefulness of the model; the model's accuracy is brief 87's.
- **Frames closer than 10 clocks are outside the contract**; `n_late`/`n_race` would show it (they cannot be provoked by the 10-clock minimum frame).
- **Control build rebuilt at an older main.** The resource and slack comparison uses brief 96F1's rebuild of `rm_gp`; `rm_gp` was not rebuilt in this brief.
- **Status readout area.** 1,756 FFs for 14 words crossed by the handshake; a narrower readout (a selector register, one word crossed) would save about 1,500 FFs and was not done.
