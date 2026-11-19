# Record diff: 20261119-125254-2973 vs 20261119-125947-36b3

## config.json: differences the configuration explains

- `model_config.endpoints.or_compat.base_url`: `null` -> `"https://openrouter.ai/api/v1"`
- `model_config.endpoints.or_compat.key_env`: `null` -> `"OPENROUTER_API_KEY"`
- `model_config.endpoints.or_compat.kind`: `null` -> `"openai_compatible"`
- `model_config.endpoints.or_compat.note`: `null` -> `"OpenRouter through the generic OpenAI-compatible kind"`
- `model_config.purposes.rtl@rtl-design-creation.endpoint`: `null` -> `"or_compat"`
- `model_config.purposes.rtl@rtl-design-creation.model`: `null` -> `"openai/gpt-6-luna"`
- `models.hash`: `"13326b50c34752bb"` -> `"576d66a2976142a9"`
- `models.purposes.rtl@rtl-design-creation.base_url`: `null` -> `"https://openrouter.ai/api/v1"`
- `models.purposes.rtl@rtl-design-creation.deployment_note`: `null` -> `"OpenRouter through the generic OpenAI-compatible kind"`
- `models.purposes.rtl@rtl-design-creation.endpoint`: `null` -> `"or_compat"`
- `models.purposes.rtl@rtl-design-creation.key_env`: `null` -> `"OPENROUTER_API_KEY"`
- `models.purposes.rtl@rtl-design-creation.kind`: `null` -> `"openai_compatible"`
- `models.purposes.rtl@rtl-design-creation.model`: `null` -> `"openai/gpt-6-luna"`
- `models.purposes.rtl@rtl-design-creation.options.retries`: `null` -> `1`
- `models.purposes.rtl@rtl-design-creation.options.temperature`: `null` -> `0.2`
- `models.purposes.rtl@rtl-design-creation.options.timeout_s`: `null` -> `180`
- `models.purposes.rtl@rtl-design-creation.purpose`: `null` -> `"rtl"`
- `models.purposes.rtl@rtl-design-creation.stage`: `null` -> `"rtl-design-creation"`
- `name`: `"smoke_subscription"` -> `"smoke_split"`
- `run_limits.usd`: `3.0` -> `1.0`

## config.json: unexpected differences

- none

## Per role and stage (role_usage.jsonl): harness and model

| stage | role | A | B |
|---|---|---|---|
| board-and-device-planning | rtl | claude_code claude-sonnet-5-5 | claude_code claude-sonnet-5-5 |
| clarify | clarify | claude_code claude-sonnet-5-5 | claude_code claude-sonnet-5-5 |
| rtl-design-creation | model | claude_code claude-sonnet-5-5 | claude_code claude-sonnet-5-5 |
| rtl-design-creation | rtl | claude_code claude-sonnet-5-5 | deepagents openai/gpt-6-luna |  (differs)
| rtl-design-creation | tests | claude_code claude-sonnet-5-5 | claude_code claude-sonnet-5-5 |

## Call logs

- `model_calls.jsonl` in 20261119-125254-2973: 7 rows (interpret 1, model 1, rtl 3, tests 2)
- `model_calls.jsonl` in 20261119-125947-36b3: 124 rows (interpret 1, model 1, rtl 120, tests 2)
- `claude_code_calls.jsonl` in 20261119-125254-2973: 7 rows (interpret 1, model 1, rtl 3, tests 2)
- `claude_code_calls.jsonl` in 20261119-125947-36b3: 6 rows (interpret 1, model 1, rtl 2, tests 2)
