# results/209b_anthropic_smoke: the one live smoke of brief 209b (anthropic_api, claude-sonnet-5-5)

Brief 209b made the `anthropic_api` endpoint report real cost from the response usage, mark the stable prefix for prompt caching, leave
`temperature` out for models that reject it, and scale stage budgets. This folder holds the one live run that checked it against the API: a
clarify-only run (`--stop-after 0`) of the pilot design `p1_clkmeter` on 2026-11-25, model `claude-sonnet-5-5`, with `--max-usd 0.9 --budget-scale 3`.
The run was stopped by hand (SIGTERM) after 17 calls because the run cap did not stop it (see Known gaps), so there is no `summary.json`.

## Records

| File | What |
|---|---|
| `model_calls.jsonl` | one row per call: tokens (input, cache write, cache read, output), `cost_usd` computed from usage and the price table, seconds |
| `role_usage.jsonl` | one row per role visit (turns, tokens, cost) |
| `totals.json` | the sums of `model_calls.jsonl` (written by the one-line script in Reproduce) |

## Measured totals

All numbers are in `totals.json`: 17 calls, no HTTP error (`http_errors` 0; no `temperature` was sent), 1.0113 USD in all. Cache: 15 of the 16 calls after
the first read from the cache (the other one started a new conversation); cache reads were 0.739 of all input tokens. The same tokens at
the full input price would have cost 1.214 USD; the input side cost 0.116 USD and the output side 0.896 USD. 9 of the 17 calls ended at about the output
cap (`max_tokens` 8192; 8,000 or more output tokens), which is where nearly all the money went.

## Reproduce

A paid run, not regenerable in CI. Command (key from the owner's key file, `FDA_KNOWLEDGE` the read-only knowledge worktree):

```
python -m agent run pilots/209/p1_clkmeter/spec.md --name p1_clkmeter_smoke --board kr260 --review off --interview off --verif-level V2 \
  --stop-after 0 --max-usd 0.9 --budget-scale 3 --model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}'
```

`totals.json` is the sum of the columns of `model_calls.jsonl`.

## Known gaps and limits

- One run of one stage (clarify), so the cache split is that of a short conversation of 7 to 16 thousand prompt tokens; later stages have larger prompts and a higher share of cache reads.
- The run cost 1.0113 USD, 0.0113 above the brief's 1 USD. The run cap (0.9) did not stop it: when a stage and the run limit were both exceeded, the stage message was raised and treated as a stage stop. Fixed in the same brief (`Meter.check` tests the run limit first; test `test_the_run_limit_wins_when_stage_and_run_limits_are_both_exceeded`).
- `claude-sonnet-5-5` with the default thinking spends the 8192 output-token cap on most calls of this stage; whether that is thinking or output text is not recorded here (usage does not split it).
