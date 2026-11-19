# Pre-registration: the combiner back-test (brief 104A)

Written 2026-11-19 (local time) before any scored run and before the combiner was applied to any recorded option. After this file is committed, `flow/options/combine.py`,
the prompts, the scoring code (`flow/options/backtest.py`, unchanged from brief 104; its SHA-256 is pinned by a test) and the case files are not changed before the runs are done.

## Question

Brief 104 found one of the three measured 10G latency variants (`agent_cdc`) and never the cumulative ones (`agent_both`, `all3`; also `hand_ref`), because the model offers
disjoint single changes. Does a deterministic combiner (code builds cumulative options from the valid single options) make `agent_both` and `all3` appear, with a gain range that
contains the measurement, **without** the analysis seeing the measured results?

## The combiner (fixed here)

- Input: the options that passed every check (`origin: model`): at most four from one request (the checker caps a reply at four), at most six after `--more`. Output: at most `MAX_COMBINED` = 4 combined options (`origin: combiner`, ids `C1`...).
- Two options combine only if they touch no stage in common and declare no interface change to the same port of the same component.
- `latency_clocks`: the cuts of disjoint stages add; low and high are the sums, capped by the checker's ceiling for the union of stages. Any labelled guess among the parts makes the whole a
  guess. Where the analysis holds a `prior_run` fact for exactly that set of stages, the measured cut replaces the sum (basis `measurement`). Not applicable to either back-test fixture
  (they have no `prior_runs.yaml`; a test checks this).
- `wns_ns`: not composable (the worst path sets the clock). `lut`/`ff`: added only across different components. Each rejected combination is recorded with its reason.
- Every combined option is built as a raw option and passed through the same per-option checks as a model option (`schema.check_single`): contract flags, owner approval, cost, not-touched.
- Ranking (`combine.rank_key`): measured-earlier first, then higher composed mid-gain, then fewer components touched, then no owner approval needed, then the model's order of the parts.
  The best combination of each size (2, 3, ...) is kept, the smallest sizes and the largest if there are more sizes than the cap, then the cap is filled with the next best.
- Contract flags: a combination across components is flagged by code and needs the owner's approval; this is reported, not a reason to drop an option.

## Back-test arms (same tasks and arms as brief 104; the only change is the combiner)

| case | arm | what the model sees | runs (k) |
|---|---|---|---|
| `b96_10g_pre97`, "lower latency" | A, with the combiner | stages with `technique` and `removable_clocks` | 3 |
| `b96_10g_pre97` | B, with the combiner | blind: no technique or removable hints | 3 |
| `c16_montgomery_200mhz`, "the design misses timing at 200 MHz: improve its timing" | A, with the combiner | the digest of the failing build | 3 |

Two prompt sets, both fixed now, both reported:

- **P1 (primary, as deployed):** the prompts pinned in `agent/core/prompts_pin.json` on main (private KB commit `38708ce6`, which includes the 104 exploratory rule "include a cumulative option").
- **P2 (isolates the combiner):** the prompts of the original pre-registration of brief 104 (private KB commit `00acde95`; unpinned, `FDA_PROMPTS_UNPINNED=1`, the file-to-manifest check stays). Case 1 arms A and B only.

Model `claude-sonnet-5-5` through the `options` purpose of the model table (endpoint `claude_code`), Claude Code 2.1.321, auto-update off, version checked before each run. Sequential. No Vivado,
no board, no heavy slot. 15 live runs (9 under P1, 6 under P2); none added or dropped after seeing a result, except an infrastructure re-run (CLI timeout or authentication), recorded as such.

## Scoring

Unchanged `flow/options/backtest.py`: `found(v)` = some option that passed every check touches exactly the stages of variant v (the scoring does not distinguish model and combiner options; the report
adds, per found variant, which origin matched, from the `origin` field); `in_range` = its range contains the measured cut. Variants: agent_cdc, hand_ref, agent_both, all3 (the brief names agent_cdc,
agent_both, all3). Counts per arm over three runs, no significance claim at k = 3. Nulls first. The measured values are in `truth/`, which the analysis and the combiner never read.

## Supplementary replay (labelled; not a new model call)

The combiner is code, so it can also be applied to the single options the 12 recorded brief-104 runs (arms A, B, A2, B2) already offered (their raw replies are in the private KB,
`results_private/b104_options/runs/`). It is a replay: those singles were produced before the combiner existed, and the same scoring is applied. It is reported separately from the live runs and cannot
replace them.

## Reading

- The result that matters: `agent_both`/`all3` appear in how many of the 3 runs per arm, from which origin, and whether the range contains the measurement and how far above it the high end is.
- A combined option found by code is a **menu entry from a ranked rule, not a discovery**: the combiner offers sums of what the model offered, and the stage file's text still names the mechanisms.
- Not claimed: that the gains are predictions (they are sums of ranges; interactions are not modelled), or that the combiner finds an unknown improvement.
