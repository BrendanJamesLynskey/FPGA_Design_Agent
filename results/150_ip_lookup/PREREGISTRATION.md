# Brief 150: what the probe is expected to show, written before the test half was scored

Written 2026-11-21 22:07 GMT (from `date`), after the labelled set was committed and after the dev half was used to tune the ranker, and
**before the test half (`split: test`, 10 requests and 5 decoys) was run on any system.**

What had already been seen when this was written (so it is not a prediction): the existing `flow.ipvariants --search` finds
1 of the 20 positives (P07), because it needs every word of the request to be a whole word of an entry's text; the new
ranker, tuned on the dev half, gets 10/10 recall@3 and 5/5 clean decoys there. Dev numbers are therefore not evidence.

## Null result (what would mean the tool is not worth having)

- **N1.** On the test half, recall@3 of `flow.iplookup` is not at least 20 percentage points above the existing search's.
- **N2.** The ranker answers "nothing fits" for fewer than 4 of the 5 test decoys (it recommends a wrong entry).
- **N3.** With the abbreviation table switched off (ALIASES, written by the same executor after reading all the queries, so a
  possible leak into the test half), recall@3 on the test half falls below 70%. Then the headline figure rests on the table
  and is not a measure of the ranker.
- **N4.** A planner offered the tool does not call it, or calls it and still writes the block fresh (reused blocks do not
  rise above rewritten ones): then offering the tool changes nothing. This one is measured in the stage-1 run below.

## Expectation

N1 and N2 will not hold (test recall@3 about 90%, 4 of 5 decoys clean; the near-miss decoy D06, a clock-crossing FIFO, is the
one likely to fail because `pkt_queue_sched` mentions a descriptor FIFO). N3 is the open one. N4 is open.

## Deviations from the review's method (4.1)

1. The set was written by the brief-150 executor, not by a different brief; the dev/test split and this file are the guard.
2. Three recorded stage-1 visits are not replayed (the recorded runs' prompts and tapes are not available to this brief
   as a replay with a new tool; see the report). A stage-1 trial on a small set of written requests replaces them, and its
   counts are not comparable with the review's wording.

## Stage-1 trial (written 2026-11-21 22:24 GMT, while the first run was already finished and read, and the other seven were just started)

Method: `python -m agent run <spec> --interview off --stop-after 1 --harness claude_code --cc-model claude-haiku-5-5` (Haiku 5.5 on
the Max plan, the cheapest model the agent allows; plan-cost estimates are in each run's summary.json; nothing goes through
OpenRouter), once per request and arm, n = 1 each. Arm `with` is the stage as built (ip_lookup offered, the stage-1 bullet
added); arm `without` removes ip_lookup from the stage's tools (and with it the bullet) at start-up
(`results/150_ip_lookup/stage1_trial/run_arm.py`). Four requests written for the trial (`stage1_trial/specs/`), with the
library entries a reviewer would call a reuse fixed here, before the other runs are read:

| spec | library answer (reuse means the design names it as taken and does not rewrite its function) |
|---|---|
| ping | icmp_echo (primary); eth_mac_rmii (secondary: the MAC only) |
| crc | crc32_step (primary) |
| fir | fir |
| uart | none: a seven-segment counter; any library entry taken here is a false reuse |

Counts: tool calls (ok / error), entries searched, entries `taken` in ARCHITECTURE.md "Library entries considered" or named as a
library block in architecture.yaml, and reused versus rewritten for the primary entry. N4 holds if `with` reuses no more primary entries than `without`.
With one run per cell this can show that the tool is used and where it fails; it cannot show a rate. A stage-1 run with a
different model, or the same one twice, would differ. These runs are not scored evaluations (no pinned CLI preflight; the eval checklist does not apply).
