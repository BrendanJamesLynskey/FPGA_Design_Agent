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

## 4-6. Stages 2-4

(To be filled in only if the gate passes.)

## 7. Literature (own words; every arXiv ID checked at export.arxiv.org on 2026-11-16)

- DeepLOB, Zhang, Zohren and Roberts 2019 (arXiv 1808.03668): a convolutional net over the last 100 snapshots of a 10-level book, then an
  inception module and an LSTM, predicts the mid-price move. It shows history of book snapshots is usable, and it is
  far too large for a nanosecond path.
- TransLOB, Wallbridge 2020 (2003.00130): replaces the recurrent part with self-attention over the window of snapshots.
- Prata, Masi, Berti and Arrigoni 2023 (2308.01915): a benchmark of order-book deep nets over the same data; its lesson we keep is that
  results depend on the data and horizon and that the gain from heavy models over simple ones is often small.
- Hawkes processes in order flow (1502.04592, 1301.1135), sign memory (cond-mat/0311053, cond-mat/0307332), and
  price impact of order-flow imbalance (Cont, Kukanov and Stoikov 2014, 1011.6402; our OFI feature is theirs).
- Linear attention (Katharopoulos, Vyas, Pappas and Fleuret 2020, 2006.16236): drop the softmax normalisation so attention is a
  sum of query-key products times values; with a window it needs no division. Base-2 softmax in hardware: Softermax
  (Stevens, Venkatesan, Dai and Khailany 2021, 2103.09301) replaces e^x by 2^x so exponentials become shifts.
