# results/107_deterministic: deterministic mode, measured (brief 107)

The records behind [docs/deterministic_mode.md](../../docs/deterministic_mode.md): whether a recorded run and its replay are identical (level 2), and how
often repeated identical requests at temperature 0 give identical replies (level 1). The numbers are in `results.md`, generated from the JSON records by
`analyse.py`. The level-1 probe made live calls (a few hundred cheap OpenRouter calls, no Anthropic model); the level-2 proof made none.

## Records

- `preregistration.md`: the level-1 design, written before any call, with the documentation check of which endpoints can take temperature 0, and a
  dated amendment for the second model.
- `level1_probe.json`, `level1_probe_deepseek.json`: per prompt and arm, the calls made, the distinct replies, the identical-output rate and the providers
  that served the calls. Produced by `tools/determinism_probe.py`.
- `replay_proof.json`: the recorded and the replayed scripted T1 episode, with the tape counts and the equality of the tool calls and files written, and the
  plan-repeatability score of the pair. Produced by `tools/determinism_replay_check.py`.
- `results.md`: the tables; `analyse.py` rewrites it from the three JSON files.

## Reproduce

The level-2 proof needs the private prompts at the pinned commit (`FDA_PROMPTS_DIR`) and no model call, key or board; the probe needs an OpenRouter key.

```
FDA_PROMPTS_DIR=<private prompts dir> python tools/determinism_replay_check.py results/107_deterministic/replay_proof.json
python tools/determinism_probe.py results/107_deterministic/level1_probe.json [--model openai/gpt-6-luna] [-n 10]
python results/107_deterministic/analyse.py
python -m pytest agent/tests/test_107_deterministic.py -q
```

## Known gaps and limits

- The level-2 proof is the scripted T1 episode (24 model calls, a fake simulator runner), not a live agent run: it proves the tape and the resolver hooks
  across the whole stage graph, not that every live tool result repeats. A live run whose tool results differ stops at the first differing call.
- Level 1 was measured on OpenRouter models only: `claude_code` has no temperature setting, and the Anthropic API has no key here (and Sonnet 5.5 and
  Haiku 5.5 reject a temperature). Five short prompts, ten calls each, one task type; the rates describe those models on that route on that day, and OpenRouter
  may route a call to another provider (recorded per call).
- The `claude_code` sub-agent arm cannot be taped (its tool loop is inside the CLI); a tape records only the chat, text and oracle calls.
- Level 3 (vLLM) is a plan only; no instance was started.
