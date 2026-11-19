# results/108_model_config: one model configuration (brief 108)

Records of the model-configuration refactor. Docs: [docs/model_config.md](../../docs/model_config.md). Report: `_handoff/fpga_agent/reports/108_model_config_report.md`.

## Records
- `replay_before.json`, `replay_after.json`: hashes of the scripted T1 episode's model-reply tool calls and dispatched tool calls, and of six replayed NL debug intents, from the origin/main checkout (4a7951de) and from the refactored one; made by `tools/model_config_replay_check.py` (`--compare` prints `identical: true`).
- `smoke/spec.md`: the smoke task (8-bit enable counter). `smoke/records/subscription` and `smoke/records/split`: `config.json` (resolved table and hash), `role_usage.jsonl`, `model_calls.jsonl`, `claude_code_calls.jsonl` of the two live runs. `smoke/record_diff.md`: their difference (`tools/model_config_record_diff.py`). `smoke/*.log`: run output, including the two failed attempts (Haiku everywhere; luna as Designer in every stage).

## Measured
All-subscription run (Claude Sonnet 5.5 on the plan): stages 0 to 2 passed, 58 turns, 612,067 tokens, no dollars reported. Split run (stage-2 Designer on `openai/gpt-6-luna` through an `openai_compatible` endpoint): routing and records as configured; the stage-2 gate was not reached before I stopped it; OpenRouter cost 0.0742 USD for 118 calls. Table hashes: subscription 13326b50c34752bb, split 576d66a2976142a9.

## Reproduce
`python tools/model_config_replay_check.py out.json` in each checkout, then `--compare`. Smoke: `python -m agent run results/108_model_config/smoke/spec.md --stop-after 2 --verif-level V1 --docs off --model-config '<JSON>'` (needs the access key, the private prompts and the plan token).

## Known gaps and limits
One tiny task, one run each; models differ in capability, so nothing here ranks them. The split run is incomplete. See the report.
