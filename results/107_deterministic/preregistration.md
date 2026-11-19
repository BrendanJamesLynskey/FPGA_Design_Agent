# 107 level 1 (temperature 0): pre-registration, written before any call (2026-11-19)

Question: which endpoint kinds can take temperature 0, and on those that can, how often are repeated identical requests
byte-identical?

## Documentation check (claude-api skill, cached 2026-11-03; no call)
- Claude Code `claude -p` (version 2.1.321): `claude --help` lists no temperature, seed or sampling flag. Level 1 is not available.
- Anthropic Messages API: a non-default `temperature` is a 400 on Claude Sonnet 5.5 and Claude Haiku 5.5, and `temperature`/`top_p`/`top_k`
  are removed (400) on Opus 5.5, Opus 5, Opus 4.8/4.7, Sonnet 5 and Fable/Mythos. Only Haiku 4.5, Sonnet 4.6 and Opus 4.6 and older
  still accept it, and on API version 2026-10-21 any sampling parameter is a 400 on every model. No Anthropic API key is configured, so
  none of this can be measured here.
- OpenRouter and openai_compatible: `temperature` and `seed` are accepted parameters; whether a provider honours them is what is measured.

## Design
- Endpoint: `openrouter`, model `openai/gpt-6-luna` (the repository's cheap default; no Anthropic model, no Fable or Opus).
- Five fixed prompts (`tools/determinism_probe.py`, PROMPTS), each sent N = 10 times, one at a time, `max_tokens` 256, data_collection deny.
- Arm A: `temperature 0`, `seed 1234`. Arm B (control, today's default): `temperature 0.2`, no seed. 100 calls in all.
- Measure per prompt and per arm: number of distinct reply texts among the 10; identical-output rate = the share of the 10 calls equal to the
  most common reply text; also the providers that served the calls (a provider change is a known source of drift).
- Headline: the pooled identical-output rate per arm (mean over prompts) and the number of prompts that were fully identical (10 of 10).
- No stopping rule beyond the fixed call count; a failed call is retried once, then recorded as a failure and excluded from that prompt's rate
  (the count is reported).
- Nothing in this probe is a quality score; no model judges anything.
