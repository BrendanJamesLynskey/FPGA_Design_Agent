# 92 Does order-flow history help, and is attention worth it in the fabric? Design note (written before code)

Date 2026-11-16. Decisions and the alternatives we rejected. Sections 1-3 are fixed before any code; sections 4-6 (stages 2-4)
are filled in before stage 2 code is written, and only if the stage 1 gate passes (this file's git history shows when).

## 1. The question and why the work is gated

Attention can help only if events before now carry information about the label that the current features do not.
The 87 features already summarise some history (the sum of the last 8 trade signs, the order-flow imbalance over 16
events). So the work goes in gated stages and stops at the first stage that says no:

0. a generator in which history can matter (otherwise a negative result would say nothing);
1. do lagged features help the 87 trees at all (CPU only; the gate);
2. the cheapest way to use history (decaying sums, learned fixed window, tiny attention, the 89 LUT network as a yardstick);
3. hardware for the arms on the accuracy-per-cost front;
4. where the winner belongs (per-tick path or the slow loop).

## 2. Stage 0: the self-exciting generator (`hist/hawkes_sim.py`)

The 87 generator (`designs/b87_ml_trading/model/lobsim.py`) is kept as it is. The variant `hawkes_sim.simulate` keeps
the same book mechanics, the same hidden value random walk and the same "informed" logistic tilt, and adds three
history mechanisms, each with stated parameters:

**A. Self-exciting arrivals (a discrete-event Hawkes-type process).** Each event is a market order with probability
`p_t = min(0.5, mu + A_t)`; after each market order `A <- rho A + alpha`, otherwise `A <- rho A`, with
`rho = 1 - 1/tau_e` (exponential kernel, tau_e = 16 events). The branching ratio (mean number of market orders one market order
causes) is `n = alpha tau_e` = 0.5, so the process is stationary and the long-run market share is `mu / (1 - n)` = 0.12, the
87 value. The remaining events are limit adds and cancels in the 87 proportion.
**B. Sign persistence.** A decayed sum of past trade signs `S <- rho_s S + sign` (tau_s = 24) adds `gamma S`
(gamma = 0.25) to the logit of a market order being a buy. This is the clustering of the sign of market orders that the
literature finds (Lillo and Farmer 2003).
**C. Informed bursts that move the hidden price.** A hidden state b in {-1, 0, +1} starts with probability 0.004 per
event (sign random), lasts a geometric number of events with mean 40, and while on (i) adds `beta_b b` (1.5) to the buy logit
of market orders, and (ii) moves the hidden value by `d_b b` (0.03 ticks) per event, i.e. the informed flow's information is
priced in gradually. Independent of the bursts, every market order moves the hidden value permanently by
`kappa * sign * size` (kappa = 0.01 ticks per lot): past flow moves the hidden mid.
Only the order flow shows b; a model has to infer it from past events. That is the only reason history should help.

These parameters were set once from the stated statistical targets below and were not tuned against any model's accuracy.
Splits by seed: train 5001-5020, validation 6001-6002, test 7001-7010 (87 sizes, 10,000 events a session, 50 dropped,
the last 40 unlabelled), so no label window crosses a session and the test sessions share no random stream with training.

**Checks of the variant (`results/b92/gen_stats.json`).** Autocorrelation of trade signs (market orders only) at lags 1, 2, 5,
10, 20 in trade time, and of the number of market orders in blocks of 20 events (event-time counts) at block lags 1-5;
for both generators. Qualitative comparison with the literature: real order-flow signs are strongly positively autocorrelated
with a slowly decaying (power-law) tail (Lillo and Farmer 2003, arXiv cond-mat/0311053; Bouchaud, Gefen, Potters and Wyart
2003, cond-mat/0307332), and event arrivals are clustered and well described by Hawkes processes with near-critical kernels
(Bacry, Mastromatteo and Muzy 2015, 1502.04592; Bacry and Muzy 2013, 1301.1135). Ours has an exponential (short-memory)
kernel plus a hidden burst state of mean length 40, so it reproduces positive clustering and sign persistence out to a few
tens of events, but **not** the power-law tail and not a near-critical branching ratio (n = 0.5); we say so in the report.
Optional public data (FI-2010): not used (no licence check was made); the data stay synthetic.

## 3. Stage 1: the gate (`hist/stage1.py`)

- Arms on both generators: (a) the 87 gradient-boosted trees (10 rounds x 3 classes, depth 3, learning rate 0.3,
  subsample 0.8) on the 7 current features; (b) the same trees on current features plus history, for N in {4, 8, 16}, in two
  feature families chosen before scoring: **lagged features** (the 7 features at lags 1..N) and **lagged primitives** (the
  per-event primitives of the last N events including the current one: trade sign, signed trade size, the event's
  order-flow term). The primitives are what the fabric sees on the message stream.
- Three training seeds each. The (family, N) used in the gate is the one with the best mean validation accuracy over the seeds
  (ties to the smaller N); validation is the only data used to choose.
- Gate: on the self-exciting generator's test split, the gate arm minus (a), paired over the 10 test sessions (mean over the
  three seeds per session), 95% t-interval; it passes only if the interval excludes zero on the positive side. If it does not,
  stage 2 is not run and the report says "history adds nothing here".
- A sensitivity check, not a gate: the same comparison with a higher-capacity booster (histogram gradient boosting, 100 rounds,
  depth 4), so a negative result cannot be blamed on 30 small trees.
- Leakage: every history column at event t is built from events <= t of the same session (`hist/prims.py`), the first
  retained event of a session has 50 events of history (more than the longest window, 16), and a test perturbs events after t
  and checks the columns do not move.

## 4. Stage 2: the arms (decided after the stage 1 gate passed: `results/b92/stage1_test.json`)

What stage 1 showed that shapes the design: the trees gain from the lagged *features* (+0.0067 on the self-exciting generator,
interval [0.0032, 0.0101]) and not from the lagged raw primitives (+0.0010); the lagged-feature trees lean on the old order-flow sums
(lag 16 is the most-used lag) and on bid and ask sizes. So the window tokens carry the book state, not only the trades.

**Token** of one event (what the fabric already has on the message stream): trade sign (-1, 0, +1), signed traded size (-8..8), the
event's order-flow term (clipped to -31..31 here; the 87 clip of the sum stays), and the imbalance bucket (0..7). Window N = 16 events
(arm 2 also at N = 8 as a cheaper point). **Head.** All arms end in the same head so that only the history mechanism differs: the 91
`log4` network (power-of-two weights, hidden 16 then 8, 4-bit codes), trained as in brief 91 (quantisation in the loop, exact integer
twin, best validation epoch). The 89 LUT network on the arm-1 columns is arm 4. Reference arms with no history, all on the
self-exciting data: trivial rule, 87 trees (stage 1 numbers), 87 MLP, `log4` head on the current features, the 89 `lg_small` network.

1. **Decaying sums.** For each of four channels (trade sign, signed size, order-flow term, 2 x bucket - 7) and two rates k,
   `s <- s - (s >> k) + x` (arithmetic shift, floor), a shift and two adders per sum, no multiplier. The rate pair is chosen
   on validation from {(1,3), (2,4), (3,5), (4,6)} (time constants about 2, 4, 8, 16, 32, 64 events); the sums are cut to 8-bit
   unsigned columns by a fixed shift `sh` per column (the smallest with the training 99.9th percentile of |s >> sh| at most 127) plus 128,
   saturating, like the 87 order-flow feature. They enter the head as eight extra columns.
2. **Fixed window.** The last N tokens' codes (each token field coded to 2-4 bits by a threshold ROM shared across lags) go straight into the
   head's first layer: that layer *is* a learned fixed-weight linear filter per hidden unit over the window (power-of-two weights).
   Cost grows with 4 N inputs; that is the point of measuring it.
3. **Tiny attention** (key size d = 4, value size m = 4, N = 16; weights `log4`, queries from the 7 current features, keys and values
   from the token, both computed once when the event arrives and kept in the shift register; a learned integer position bias is added to
   each score). Two softmax-free forms, chosen because a softmax needs an exponential and a division, which neither shifts nor
   small adders give:
   - **top-1:** the output is the value of the highest-scoring position (ties to the most recent), a compare tree and a mux (the hard-attention
     limit; trained with the softmax gradient as a straight-through surrogate);
   - **ReLU-linear:** `a_i = clip((s_i) >> sa, 0, 7)`, output `clip((sum_i a_i v_i) >> so, -8, 7)` (linear attention without normalisation,
     Katharopoulos et al.; the shift `sa` is a power-of-two scale, standing in for a base-2 softmax's normaliser).
   The attention block is trained first with a small float head on top, frozen to integers, and its four output columns then go through the
   same 91 head training as every other arm. (End-to-end training of the quantised head would be better for attention; that is a known gap,
   it is stated in the report.)
4. **The 89 LUT network** (`lg_small` configuration) on the arm-1 columns, as the cheap-head yardstick.

Selection rule for every arm: three training seeds, the built seed is the best on validation, the test split is scored once
(`docs/preregistration_stage2.md`, committed before). Accuracy is reported with a paired 95% t-interval over the ten test sessions against
the trivial rule, the stage-1 trees and the history-free 91 head. "A margin whose interval excludes zero" for the attention decision is the
paired difference, tiny attention minus decaying sums, built seeds.

## 5. Stage 3: hardware (to be filled in after stage 2's results)

## 6. Stage 4: where it would sit (to be filled in with the stage 3 numbers)

## 7. Literature (own words; every arXiv ID checked at export.arxiv.org on 2026-11-16)

- DeepLOB, Zhang, Zohren and Roberts 2019 (arXiv 1808.03668): a convolutional net over the last 100 snapshots of a 10-level book, then an
  inception module and an LSTM, predicts the mid-price move. It shows history of book snapshots is usable, and it is
  far too large for a nanosecond path.
- TransLOB, Wallbridge 2020 (2003.00130): a causal convolution for features plus masked self-attention that updates each step's features
  from relevant earlier steps; reported as the best on the FI-2010 data at the time. It is the "attention helps" claim we test, at a
  size a fabric could hold.
- Prata, Masi, Berti and Arrigoni 2023 (2308.01915): a benchmark of fifteen order-book deep models; its finding that every model loses
  accuracy on new data is why we score on unseen sessions and report intervals, and why we do not read the published gains as ours.
- Hawkes processes in order flow (1502.04592, 1301.1135), sign memory (cond-mat/0311053, cond-mat/0307332), and
  price impact of order-flow imbalance (Cont, Kukanov and Stoikov 2014, 1011.6402; our OFI feature is theirs).
- Linear attention (Katharopoulos, Vyas, Pappas and Fleuret 2020, 2006.16236): drop the softmax normalisation so attention is a
  sum of query-key products times values; with a window it needs no division. Base-2 softmax in hardware: Softermax
  (Stevens, Venkatesan, Dai and Khailany 2021, 2103.09301) replaces e^x by 2^x so exponentials become shifts.
