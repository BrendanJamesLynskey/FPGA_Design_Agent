# Pre-registration: the options back-test (brief 104)

Written 2026-11-19 16:05 (local time) before any scored run. The prompts were developed on `designs/b102_managed_fcs` only (one live run, request "reach a
higher clock rate"); neither back-test design nor its truth file was used to tune anything. After this file is committed the prompts, the code that scores and
the case files are not changed before the runs are done.

## Question

Does the options generator, given only the analysis of a design (never the later result), offer the strategies that a measured earlier change turned out to
be, with a gain range that contains the measurement? Is the answer produced by the model, or by the hints the design's stage file hands it?

## Cases (fixtures in `backtest/`; truth in `backtest/truth/`, never read by the analysis)

1. `b96_10g_pre97`, request `lower latency`: the KR260 10G design at the start of brief 97 (11 clocks tick-to-trade). Truth: four measured variants
   (agent_cdc, hand_ref, agent_both, all3), each a set of latency stages and a measured cut in simulated clocks (`results/b97/postroute.json`). The brief names
   three (agent_cdc, agent_both, all3); hand_ref is scored too.
2. `c16_montgomery_200mhz`, request `the design misses timing at 200 MHz: improve its timing`: the course task c16 (bit-serial Montgomery multiplier) at
   200 MHz, WNS -0.615 ns. Truth: the closure loop's first iteration (carry-save compression in the multiplier core, WNS +0.679 ns, latency unchanged).

## Arms and runs

| case | arm | what the model sees | runs (k) |
|---|---|---|---|
| 1 | A: stage file as the 97 agents had it | stages with `technique` and `removable_clocks` | 3 |
| 1 | B: blind | the same without `technique`, `removable_clocks` and the `.removable` facts; the code's gain ceiling becomes the touched stages' own clocks | 3 |
| 2 | A | the digest of the failing build (no RTL source, no hierarchy report: totals only) | 3 |

Model: `claude-sonnet-5-5`, effort medium, endpoint `claude_code` (the Max plan), through the resolver purpose `options`; Claude Code 2.1.321 (accepted version,
auto-update off since before this brief; the version is checked before every run and a mismatch stops the driver). One call plus at most one repair call per run.
Sequential, one at a time. No Vivado, no board, no heavy slot. Prompts: private knowledge repository, branch `b104-options`, commit
`00acde95dd0c1410b7fa5e78d56fd2f7f64e8599`, prompt hashes `graph/options/system` 5776ae37..., `user` 30be8dfd..., `repair` bb56b4a4...; manifest hash
`b810a3eeed6b7152e0e9a8045690e2e08033db269501b0bc8553433f02ce789b`.

## Scoring (code, `flow/options/backtest.py`; no model scores anything)

- Case 1: `found(v)` = some option that passed every check touches exactly the stages of variant v. `in_range` = that option's gain range contains the measured cut.
  Per run and per arm: variants found (of 3 named, of 4), in range, and the options that match no variant (listed, judged by a human in the report).
- Case 2: `found` = an option scoped to exactly `montgomery_core` with metric `wns_ns`; in range = its range contains +0.679.
- A run that fails the checks on both attempts counts as `failed` (no options), not re-run. One re-run is allowed only for an infrastructure error (CLI timeout,
  authentication), recorded as such.

## Comparisons and reading

- Nulls and failures first. Counts per arm across the three runs; no significance claim at k = 3. Arm A versus arm B shows how much the technique hints carry:
  if B finds fewer of the variants, the A result is partly the hints. The stage file's `why` and `remove_risk` text still names mechanisms in both arms
  (it was in the file the 97 agents saw); this is a limit, stated in the report.
- Predictions are judged by whether the range contains the measurement and by how far its high end is above it (a very wide range is not a good prediction).
- Not claimed: that the generator would find an unknown improvement; only whether it re-finds measured ones from the analysis.

## Stopping

Nine live runs. No run is added or dropped after seeing a result, except the infrastructure re-run above. Cost: reported on the plan (no dollars); wall time per run is recorded.

## Addendum 2026-11-19 (after the nine runs; NOT pre-registered)

Result of the nine runs: on case 1 only `agent_cdc` was found (3 of 3 runs in each arm); `hand_ref`, `agent_both` and `all3`, the combinations that contain `cross_go`, were never offered:
the options were disjoint single changes plus one whole-design combination that left `cross_go` out. The generator offered no option that builds on another. As an exploratory step, the prompt
`graph/options/system` was revised with one rule (include a cumulative option that adds further changes to a narrower option) and case 1 was re-run, three runs per arm, as arms `A2`
and `B2`. These runs are labelled exploratory: the prompt was changed after seeing the truth, so they show whether the rule works, not how the first prompt performs. The pre-registered
results above stay the primary result.
