# What we found: deciding before the last byte

For an engineer picking this up. Every number is in a committed record under `results/b93/` (`summary.json` collects
them; `python3 results/b93/summary.py --check` says whether it is current). Synthetic data only; Vivado 2026.1,
out of context, one thread; simulation at the 125 MHz core clock (8 ns, one byte a clock). No board.

## Short answer

1. **In the 58A/87 path the model's inputs are all known three clocks before the price field completes** (section 1).
   The model needs none of the message's own price, size, type or side. So the cheap, real saving is to compute the
   features and the class early: the decision is no longer later than the rule's own decision. Trees and `lg_small`
   add **0 clocks** instead of 1 (tick to decision 4 -> 3 clocks from the last price byte; first byte out 9 -> 8 clocks
   speculative; safe mode stays 18 because the FCS wait hides it). That is 8 ns at 125 MHz and costs about 156
   flip-flops and no LUTs (section 3).
2. **The table (Shannon / partial evaluation) arm saves nothing in clocks in this design and costs 2.6 to 3.0 times the
   LUTs** (section 4). At the block level its late path is shorter (1.7 to 2.9 ns against 4.3 to 4.5), but the block's
   own clock is set by the table fill, which is as deep as the whole model unless it is registered in the middle;
   only `lgs_pe2` (2-clock fill) closes faster than its baseline, 2.95 ns against 4.45.
3. **The saving from the early arm is real but small in absolute terms** (one 8 ns clock) and it is not hidden behind
   anything slower in speculative mode; in safe mode it is hidden behind the FCS wait.
4. The table arm is the right tool for a model whose features include the message's own price. None of the 87, 89,
   91 or 92 models has one, and training one was out of scope (every arm must equal the 87 integer model).

## 1. Stage 0: the critical input

Clock 0 is the clock `msg_inst_v` is high (offset 3 of the message has just been registered by `feed_rx`); one byte a
clock at 1 Gb/s with the 8 ns core clock. Record: `results/b93/stage0.json`.

| Input | Bench Feed v1 offset | Known at clock | Used by the model? |
|---|---|---|---|
| type | 0 | -3 | no (sets the next message's trade sign) |
| side | 1 | -2 | no (as type) |
| instrument | 2-3 | 0 | yes: the book address and the tracked-instrument test |
| book entry (bid/ask price and size) | the book RAM | 1 | yes: the book before this message |
| price | 4-7 | 4 | no |
| size | 8-11 | 8 | no |
| previous snapshot, OFI window (16), trade window (8), last direction | state | before the frame | yes |

**Last-arriving input of the model: the book entry read for the message, at clock 1, three clocks before the price
field (clock 4).** Its width after the 87 quantisation is the whole packed feature vector, 38 bits: bid size 8, ask size
8, spread 4, imbalance bucket 3, trade-sign sum 5, order-flow imbalance 8, mid direction 2.

| Feature | Depends on | Class |
|---|---|---|
| f0 bid size, f1 ask size | book entry | early field (instrument), shallow |
| f2 spread | book entry (two prices) | early field, a subtract and a compare |
| f3 imbalance bucket | f0, f1 | early field, seven compares |
| f4 trade-sign sum | trade window, previous message's type and side | pure function of state known before the frame |
| f5 order-flow imbalance | book entry, previous snapshot, OFI window | early field, the deepest logic (four 32-bit compares, a 35-bit sum, a clip) |
| f6 mid direction | book entry, previous snapshot, last direction | early field, two 33-bit sums and a compare |

**No feature depends on the last field (the price).** Nothing in the model is a function of the message's own fields,
so there is no "last byte selects" case at all; the work the last byte used to wait for was the model's own start.

**Public feed format (prose, not built).** Nasdaq TotalView-ITCH 5.0, section 1.3.1, Add Order (no MPID attribution), 36
bytes: type 0, stock locate 1 (2 bytes), tracking number 3, timestamp 5 (6 bytes), order reference 11 (8 bytes),
buy/sell 19, shares 20 (4 bytes), stock 24 (8 bytes), price 32 (4 bytes). A model keyed on the book would address it
by the stock locate (offset 1) or the symbol (24-31): 4 to 31 bytes before the price completes. The conclusion does not
depend on our field order. A model with the order's own price or shares as an input would have the price (offset 32,
4 bytes) as its last input.

## 2. Arms and how they are verified

| Arm | What | Integration parameter |
|---|---|---|
| 1 baseline | the 87 integration: features at the price field, model after | `ML_PRE 0` |
| 2 early features | features at the book read, state committed at the price field | `ML_PRE 1` |
| 3 table | arm 2 plus a table of the model's classes per interval of the order-flow imbalance, filled in 1 (`*_pe`) or 2 (`*_pe2`) clocks | `ML_PRE 2`, `3` |
| 4 speculative send | not built; undo rate counted (section 5) | |

Each arm equals the 87 / 89 integer model on every test sample: the 99,100-sample test split, 20,000 random packed vectors
and every late value (0..255) against 40 random early vectors (`results/b93/block_equivalence.json`), and in the
integration on 400 generator messages, 300 edge-case messages (saturation, spread 15, OFI clip, empty sides, all
reached), bad-FCS frames and a stream with another instrument between tracked ones, for both models and every `ML_PRE`
(`results/b93/integration_*_twin*.json`). The early feature unit also runs in lockstep with the 87 unit on 20,000
messages, 25 % of which never reach their price field, and a mutant that commits early fails that test.

## 3. Clocks (simulation, 8 ns core clock; `results/b93/integration_*_latency.json`)

Same for trees and `lg_small`. "From the last price byte": the clock the last price byte enters `mac_rx`.

| Arm | Gate adds | Last price byte to decision | to first byte out (speculative) | (safe mode) | Class valid, clocks after the instrument field | Clocks before the rule's decision |
|---|---|---|---|---|---|---|
| model off (58A) | 0 | 3 | 8 | 18 | | |
| 1 baseline | 1 | **4** | 9 | 18 | 6 | -1 (after it) |
| 2 early features | 0 | **3** | 8 | 18 | 3 | 2 |
| 3 table, fill 1 | 0 | **3** | 8 | 18 | 4 | 1 |
| 3 table, fill 2 | 0 | **3** | 8 | 18 | 5 | 0 (same clock, bypass) |

The baseline reproduces the 87 figures (4 and 9 clocks, 18 in safe mode). The saving is the one clock the baseline
waited. It exists only because the rule's decision is 5 clocks after the instrument field; a model that took more than 4 clocks
(the 87 MLP: 13) would still add clocks. The table arms are later than arm 2 (4 and 5 against 3) because the late value is
delayed by the fill in `trigger_core`; they gain nothing here and the third and fourth rows only show they still fit.

## 4. Cost and clock of the blocks (post-route, out of context; `results/b93/ooc/`)

Latency = clocks x max(closed period, 2.0 ns) (the 87/89 convention; no clock buffer or jitter out of context).
Wrapper flip-flops are included (39 for the plain blocks, 48 for the table blocks, 210-211 for the feature units).
No DSP or BRAM anywhere.

**Decision blocks, K26 (xck26-sfvc784-2LV-c)**

| Block | Closed (ns) | LUT | FF | Early path (ns) | Late path (ns) | From the last input to the class |
|---|---|---|---|---|---|---|
| trees, baseline `gbt_comb` | 4.30 | 641 | 42 | | | 1 clock, 4.30 ns |
| trees, table fill 1 `gbt_pe` | 5.55 | 1,755 | 83 | 5.52 | 2.87 | 1 clock; 5.55 ns at the block's clock, 2.87 ns for the path alone |
| trees, table fill 2 `gbt_pe2` | 4.15 | 1,692 | 348 | 4.12 | 2.14 | 1 clock; 4.15 ns, 2.14 ns for the path alone |
| `lg_small` baseline `lg_small_comb` | 4.45 | 327 | 42 | | | 1 clock, 4.45 ns |
| `lg_small` table fill 1 `lgs_pe` | 4.60 | 986 | 59 | 4.53 | 1.73 | 1 clock; 4.60 ns, 2.0 ns (floor) for the path alone |
| `lg_small` table fill 2 `lgs_pe2` | 2.95 | 867 | 226 | 2.94 | 1.97 | 1 clock, 2.95 ns |

**Decision blocks, Artix-7 100T (xc7a100tcsg324-1)**

| Block | Closed (ns) | LUT | FF | Early path (ns) | Late path (ns) |
|---|---|---|---|---|---|
| `gbt_comb` | 11.60 | 576 | 42 | | |
| `gbt_pe` | 15.35 | 1,702 | 83 | 15.35 | 5.04 |
| `gbt_pe2` | 11.70 | 1,663 | 350 | 11.59 | 4.87 |
| `lg_small_comb` | 12.35 | 251 | 42 | | |
| `lgs_pe` | 13.10 | 733 | 59 | 13.07 | 5.10 |
| `lgs_pe2` | 9.70 | 713 | 226 | 9.45 | 4.77 |

**Feature units (arm 1 and arm 2 front ends)**

| Unit | K26 closed (ns) / LUT / FF | A7 closed (ns) / LUT / FF |
|---|---|---|
| `ml_feat` (87, at the price field) | 6.05 / 572 / 440 | 15.85 / 564 / 440 |
| `ml_feat_pre` (early) | 6.00 / 566 / 596 | 15.40 / 564 / 596 |

What these say:

- **Does the table arm lower Fmax? Yes, with a 1-clock fill, for trees.** The fill is the whole model, so its path is
  the baseline's or deeper (5.55 ns against 4.30 on the K26, 15.35 against 11.60 on the A7). A shorter path after
  the last byte is useless if the clock gets slower. A 2-clock fill (scores registered before the argmax) brings the
  trees back to the baseline (4.15, 11.70) and `lg_small` well below it on the K26 (2.95 against 4.45, 9.70 against
  12.35 on the A7), at 2.6 to 2.7 times the LUTs on the K26 (867 against 327; 1,692 against 641) and 226 to 348 FFs.
- **The late path alone is 1.7 to 2.9 ns on the K26** (4.8 to 5.1 ns on the A7), against 4.3 to 4.5 for the baseline.
  That is the most the table could save per decision (1.4 to 2.7 ns), and only in a design where the clock is faster than
  the baseline closes at and the late input really arrives last.
- **The early arm costs no LUTs and about 156 flip-flops** (the snapshot and the results registered for the commit);
  the feature unit closes at 6.0 ns on the K26 and 15.4 ns on the A7, so on the K26 it fits the 8 ns clock with margin and
  **on the Artix-7 -1 it would not close at 125 MHz**, either version. The 58A design runs on the KR260 only.
- The 87 baseline numbers (4.4 ns, 640 LUTs for trees) and 89 (4.5 ns, 325 for `lg_small`) are reproduced to within a
  closed-clock step (4.30 and 4.45 here; the search is a closed point, not a bound, and routing noise is about 0.1 ns).
- The `ML_PRE 3` bypass (the class register to the order bit in the same clock as the decision) is not in these
  block builds; the gate is a few LUTs and was not built in Vivado, as `ml_gate` was not in 87.

## 5. Speculative send (arm 4), counted not built

The class is ready before the rule's decision, so there is nothing to start early. As a count
(`results/b93/speculation.json`, test split, weights from the train split): choosing the table's most likely class
would be wrong for 3.3 % of trees samples and 8.7 % of `lg_small` samples; of the buys it would start, 2.4 % (trees) and
6.2 % (`lg_small`) would be undone, of the sells 2.0 % and 7.4 %. 37 to 38 % of samples have a table with a single class.

## 6. Dead ends and decisions that cost time

- **A table fill of 1 clock is a trap**: it moves the work, not removes it. The first result (trees 5.55 ns, worse than
  baseline) led to the 2-clock variant.
- Treating the order-flow imbalance as "the late feature" is an assumption of the experiment, not a property of the
  design: all features are registered together. The integration delays it by the fill so that the table's contract is
  exercised, which also makes the table arms' class later than arm 2's.
- An integration cut-off-frame test was planned and dropped: the FCS bytes pass through the parser as data and complete
  the price field, so a message with an instrument field and no price field cannot occur on the wire. The non-commit
  rule is tested at the unit level instead (`tb/tb_feat_pre.sv`).
- Icarus hangs compiling `wait (cyc > tl[n-1] + 8)` in the table test bench (array element in a `wait`); a `while`
  loop compiles in milliseconds.

## 7. Known gaps

See the report; the main ones: out of context only; no board or full-design build of `ML_PRE` 1-3; the late value is
not actually late in this design; the model has no price input; one synthetic data set; the SVG timing diagrams were
checked as generated text, not rendered.
