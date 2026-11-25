# results/209b_anthropic_smoke2: second live smoke of brief 209b (anthropic_api, claude-sonnet-5-5 with max_tokens 16000 and effort medium)

The first smoke (`../209b_anthropic_smoke/`) had 9 of 17 replies stop at the 8192 output cap. After brief 209b item 7 (per-model `max_tokens` 16000,
`effort` medium, `timeout_s` 300, and a cut-off reply recorded with `stop_reason` and handed back with a note), the same clarify-only run of the pilot
design `p1_clkmeter` was repeated on 2026-11-25 with `--stop-after 0 --max-usd 1.2 --budget-scale 3.5`. The clarify stage passed on its own (`stop: done`),
then the DOC step made three more calls (it failed its own gate, as expected for a stage-0 stop; not part of this check).

## Records

| File | What |
|---|---|
| `model_calls.jsonl` | one row per call: the four token fields, `cost_usd`, `seconds`, `stop_reason` |
| `role_usage.jsonl` | one row per role visit |
| `summary.json` | the run summary, written before the DOC step: its `cost_usd` and `turns` cover the 13 clarify calls only |
| `totals.json` | sums of `model_calls.jsonl` (all 16 calls) |

## Measured totals

All numbers are in `totals.json`: 16 calls (13 clarify, 3 DOC), 0 truncated, no HTTP error, largest output 5886 tokens (the cap is in the table, not a record), 0.4358 USD in
all of which 0.217 USD is the clarify stage. Cache reads were 0.735 of all input tokens and 13 of the 15 calls after the first read from the cache; the same
tokens at the full input price would have cost 0.736 USD. Time per call: median 3.67 s, mean 10.1 s, longest 38.45 s (a 5886-token reply); 162.1 s in all.

## Reproduce

This is a paid agent run that CI cannot regenerate; run this command with the key file and the knowledge worktree in place:

```
python -m agent run pilots/209/p1_clkmeter/spec.md --name p1_clkmeter_smoke2 --board kr260 --review off --interview off --verif-level V2 \
  --stop-after 0 --max-usd 1.2 --budget-scale 3.5 --model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}'
```

## Known gaps and limits

- One run of the clarify stage: it shows no truncation at 16000, not that no later stage ever truncates. The run cap (1.2) was never reached, so the cap itself is shown only by the unit test `test_the_run_limit_wins_when_stage_and_run_limits_are_both_exceeded`.
- The three DOC calls are in `model_calls.jsonl` but not in `summary.json` (written before the DOC step).
