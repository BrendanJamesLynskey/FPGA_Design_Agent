# Brief 213 report: repair feedback (R1 first failing check, R2 failure ledger, R3 fresh-stimulus regrade)

Executor: Sonnet 5.5, 2026-11-26. PR #349 (branch b213-repair-feedback, not merged). Records: `results/213_repair_feedback/` (README, prereg.md, order.tsv, runs/, ab_runs.csv, paired_analysis.txt, sweep/, disagreement_classification.md).
Series ran 2026-11-26 04:26 to about 17:30 GMT (stamped from `date`).

## Done
1. **R1 first failing check** (`--harness-arm ...,R1`): a failed simulate on an assertion is re-run once with a snapshot hook (`flow/model_record.py`) that stops at the first failing cocotb test; the repair reason carries the assertion and bench line, RTL values over the last cycles beside the model's value, the model's recent calls (the transaction in flight) and the driver cone of the first wrong signal (textual RTL dataflow walk, not a netlist; says so). It replaces the raw log tail. It never assumes the model or bench is right.
2. **R2 failure ledger** (`R2`): per failed stage-2 visit: gates, finding, first failing check, files changed since the previous gate; shown to later visits (earlier entries only); a "check whether the check contradicts the request or a standard" hint after 3 identical consecutive failures (from the classification below). In run state, run record (`repair_feedback`), routing events and stop detail.
3. **R3 fresh-stimulus regrade** (`R3`): the simulate tool records the bench's calls to `Model`; after stage 2 would pass, `flow/regrade.py` replays the recorded stimulus in lock step (calibration), and only if that agrees drives new seeded sequences (pool values, random and neighbour values, bursts, back-pressure on ready-like inputs, mid-stream resets; seed recorded). Statuses not_applicable, not_calibrated, pass, fail, error.
4. All three are opt-in; no prompt text changed (no new golden or pin). Tests: 13 in `agent/tests/test_213_repair_feedback.py` on fixture designs (`agent/tests/data/b213_counter`: good; bad = corner case the design's own bench misses; bad_always = bug the bench catches).
5. Analysis tools: `tools/ab/` (`ablate.py`, `table.py` copied from CVDP_RTL_Agent b108d3c, MIT, with attribution; `adapter.py`; `paired_numeric.py` = paired bootstrap of any numeric column).

## Sample digest (live, seeded bug in the p2 pilot design, Icarus)
```
[first failing check] test test_reset_and_common_regs failed at 641 ns, clock cycle 16 ...: AssertionError: read 0x008: rtl 0x00000001 model 0x00000000
  bench line bench_p2_bram_rom.py:64 (rd): assert got == out["h_rdata"], (
  h_rdata: RTL 0 0 20920001 20920001 20920001 1 1 1 | model 0
  the model's recent calls, newest last: ... rd addr 0x0 val 0x20920001 @400ns; rd addr 0x8 val 0x0 @521ns
  drivers of h_rdata (RTL dataflow walk over the source text, not a netlist; depth 2):
    p2_core.sv:167  12'h008: h_rdata <= scratch ^ 32'h1;   [selected by the in-flight transaction's address]
```
The regrade digest on the fixture's corner case names cycle 136, `d=0xf0, en=1, load=1`, `q` expected 0xF0 and the statement `if (load && !(en && d == 8'hF0)) q <= d;`.

## A/B (pre-registered `prereg.md`, 2026-11-26 04:2x GMT; exploratory bundle; own-check verdicts, no independent check exists before the board visit)
18 runs, p1/p2/p3 x 3 replicates x 2 arms, Claude Code 2.1.321 pinned, Sonnet 5.5 medium, `--stop-after 2`, V2; order `order.tsv`; no run was a plan, rate or slot stop (all 18 have records). Paired on (design, replicate); stage-2 visits to pass scored as visits used, non-pass = 7.

| outcome | control (n=9) | treatment (n=9) | paired difference, 95% bootstrap | verdict |
|---|---|---|---|---|
| stage-2 visits to pass (primary) | 5.44 | 5.56 | +0.11 (-1.56 to +1.56; SD of differences 2.18); 1 better, 3 worse, 5 equal; sign test p = 0.62 | no detectable effect |
| own stage-2 pass | 4/9 | 3/9 | -0.11 (-0.44 to +0.22) | no detectable effect |
| plan cost USD | 3.12 | 2.67 | -0.45 (-1.26 to +0.33) | no detectable effect |
| wall time s | 1690 | 840 | -850 (-2266 to +46); the control mean includes one 9769 s run (run 8) | no detectable effect |

Power stated in advance: about 1.7 visits detectable; the interval half-width observed is about 1.6. So a gain of one visit or less cannot be excluded; a large one is excluded.

Run ids (results folder `runs/<n>_<design>_k<k>_<arm>`, agent run id in `RUN_ID.txt`):
- control: 1 p3 k3 stage-1 limit; 6 p3 k1 stage-1 limit; 9 p3 k2 stage-1 limit; 11 p2 k2 stage-1 limit; 8 p1 k2 stage-2 limit (other gates; 9769 s); done: 10 p2 k3, 12 p2 k1, 14 p1 k1, 18 p1 k3.
- treatment: 5 p2 k2, 7 p3 k2, 17 p3 k1 stage-1 limit; 2 p1 k3, 4 p1 k1, 15 p3 k3 stage-2 limit (lint); done: 3 p2 k3, 13 p1 k2, 16 p2 k1.

Nulls first: **no detectable effect on any outcome.** Not a gain. Mechanism counts (treatment arm, routing events): the ledger fired in all 9 runs (entries 1 to 6 per run); R1 produced a digest in 2 runs (4 firings): in run 3 three times, each ending "Simulator shut down prematurely" with no bench site (the snapshot caught the simulator's own shutdown, not the failing assertion; 787 characters of ring data, not an informative first failing check) and in run 4 once with no snapshot (failure did not reproduce); so **R1 delivered no useful first-divergence digest in this A/B**; regrade ran in 3 runs and was `not_applicable` in all 3 (benches use register calls or step() with no inputs).
- Most failures were not simulation mismatches: 7 of 18 runs ended on the **stage 1 visit limit** (stage-2 lint and design-standards failures route back to stage 1 and use up its 4 visits; visit counting is brief 234's), 4 on the stage-2 limit (lint or standards). The interventions, which act on simulate mismatches, had little to act on.
- Ledger case studies from this series: runs 2, 4 and 15 (p1, p3) show 5 to 6 consecutive identical lint failures at stage 2 despite the ledger; the repeat hint did not break the loop in these 3 runs (n=3, no control for it).

## Regrade BLOCKS decision
`flow/regrade.py BLOCKS` stays False at V1, V2 and V3 (report only). Evidence: the sweep over 16 recorded accepted designs (209 p1 to p3 x3, 224 p4 to p6 arm runs; `sweep/regrade_sweep.jsonl`, one design not reached: sweep still running when this report was written) gives 14 not_applicable, 1 error (p1 run3: its test entry never reaches a cocotb build), 1 not_calibrated (224 p5 run3), **0 pass, 0 fail**. So the regrade has never run on an agent design: applicability 0 of 16 against our own benches, no false alarms observed and no real catches either. It catches the seeded corner case and passes the good design only on the fixture. Blocking would gate on a mechanism with no field evidence. Revisit when benches drive the model through `step(inputs)`; that needs a Verifier prompt change (KB, pin, golden), a follow-up brief.

## Classification of the 26 CVDP disagreements (diagnosis only; hidden-test text kept out; `disagreement_classification.md`)
Own check passed, hidden failed (15): benchmark-limited 10, spec reading differs 3, RTL wrong 1, undecided 1. Own check rejected, hidden passed (11): RTL wrong 5, bench wrong 4, tool 1, undecided 1; reset values the cause in 6 of 11, and in 5 the prompt asks for an asynchronous reset while the house rule and the agent's gate want synchronous. Consequences built: the digest never assumes the model or bench is right; ledger repeat hint. Not built: contract-first stage 0 arm (not A/B'd; the classification says 10 of 15 own-pass failures are facts the prompt does not state, a stage-0 assumptions list is the candidate). Three verdicts are probable (hidden test source not read).

## How it was verified
- `agent/tests/test_213_repair_feedback.py` 13 passed; `test_99_prompts` 30 passed against the KB at the pin; doccheck and the full agent suite: see the hand-back message for the final run.
- Live: R1 digest on a seeded bug in a pilot design; lock-step bench on the fixtures and on the pilot recordings.

## What is illustrative
Fixture results prove the mechanism, not field value. The A/B is 3 designs x 3 replicates, exploratory, own verdicts only.

## Known gaps
- R1 snapshot fails to capture a true assertion when the simulator shuts down prematurely (run 3); not diagnosed.
- Regrade needs a step(inputs)-driven bench; register-API benches (all pilot designs) are not applicable. The harness does not know the jtag_bus register protocol.
- The 3-repeat ledger hint was added after the series launched; only treatment runs use it, all treatment runs used the same code (control unaffected).
- Usage stop: the pre-registered 75% was raised to 92% by the owner (planner message); the series finished at about 68% so it never bound.
- Contract-first arm not run; 224 p5/p6 loops not re-run with the ledger.
- No independent check column (pending the board visit).

## Gotchas
- cocotb's runner replaces PYTHONPATH with the parent's sys.path and lets os.environ override extra_env; helper entry scripts must put the repo root on sys.path themselves.
- Pytest collects `agent/tests/data/**/tests/test_*.py`: the fixture has a conftest ignoring them.

## Follow-ups for the planner
1. Brief 234: stage-2 lint/standards failures bounce to stage 1 and end on stage 1's limit (7 of 18 runs).
2. Why the R1 snapshot reported "Simulator shut down prematurely" (needs a look at the run 3 sim log).
3. Make benches step(inputs)-driven (Verifier prompt/KB change) or teach the regrade the jtag_bus protocol, before any further regrade work.
4. Decision for the owner: prompt-demanded asynchronous reset against the synchronous house rule (5 of 11 CVDP cases).

## Course impact
None.
