# Deterministic mode (brief 107)

`--deterministic` makes a run's *model calls* repeatable: the same request and project state give the same replies, so the same plan, the same
files the model writes, and the same tool calls. It is built on the model table of brief 108 ([model_config.md](model_config.md)). Code:
`agent/models/tape.py` (the tape), `agent/models/determinism.py` (levels, pins, refusals), `agent/models/resolver.py` (the hooks), `agent/__main__.py`
(`tape_spec_from`). Tests: `agent/tests/test_107_deterministic.py`. Measurements: `results/107_deterministic/`. Report: `reports/107_deterministic_mode_report.md`.

```
python -m agent run SPEC --deterministic [--tape DIR]       # replay the tape in DIR when it has one (level 2), else run at temperature 0 and record one (level 1)
python -m agent run SPEC --record-tape DIR                  # record every model call, sampling as configured (level 0, recorded)
python -m agent run SPEC --replay-tape DIR                  # serve every model call from DIR (level 2); a call with no recording stops the run
python -m agent resume RUN_ID --deterministic ...           # the same options on resume
```

The default tape directory is `~/.local/share/fpga_design_agent/tapes/<design name>` (`$FDA_TAPE_DIR` moves the root).

## The three levels

| level | what | exact? | status |
|---|---|---|---|
| 2, record and replay | every model call stored under the hash of its resolved request; a replay serves each call from the tape and makes no live call | yes, for the model calls, whatever the provider does | built, proved (below) |
| 1, temperature 0 | live calls with `temperature: 0` (and `seed` where the endpoint takes one) on every purpose; recorded to a tape so the run can be replayed exactly | **no**: measured identical-output rates are in `results/107_deterministic/results.md` | built; only on endpoint kinds that take a temperature |
| 3, self-hosted vLLM | greedy decoding, batch-invariant kernels, pinned weights and versions, one GPU model | designed to be bit-exact, unmeasured | a plan only ([below](#level-3-plan-vllm-on-the-owners-aws)); nothing started |

## What `--deterministic` does

1. A tape exists in the tape directory: **level 2**. The run starts with the model table the tape was recorded with (a level-1 recording
   carries its `seed`, so the table is rebuilt the same way); a different table is refused (`replay: the model table differs ...`).
2. No tape: **level 1**. Every purpose the run uses must sit on an endpoint kind that takes a temperature (`openrouter`, `openai_compatible`,
   `anthropic_api` on a model that accepts one). If one does not, the run **stops before its first call**, naming each purpose, endpoint and reason
   (a `claude_code` endpoint has no temperature setting; Claude Sonnet 5.5, Haiku 5.5, Opus 5.5 and later reject a temperature). It does not fall
   back to sampling. The calls are recorded to the tape directory.
3. Whatever happens, `config.json` carries a `determinism` block (level, mode, seed, the tape's path and SHA-256 at the start, and every pinned
   version: the agent commit, the model-table hash, each endpoint and model, the `claude` CLI version when a claude_code endpoint is in the table)
   and `summary.json` carries `model_tape` with `level_at_end`, computed from what happened: 2 only if every call came from the tape, none was live and
   none missed; 1 only if every live call ran at temperature 0 and no sub-agent turn escaped; otherwise 0.
4. Runtime guards, so nothing samples silently: at level 1 the resolver refuses any live call whose entry is not at temperature 0 (even for a purpose
   the start-up check did not list); at level 2 the resolver builds no live client, so a call with no recording is an error, not a live call.

## What a user could guess wrong

- **Level 1 is not bit-exact.** Temperature 0 asks for the most likely token; provider-side batching, kernel order and model routing can still change a
  reply, and some models ignore the setting. The measured identical-output rate for the model tried is in `results/107_deterministic/results.md`. Only a
  replay (level 2) or a self-hosted batch-invariant server (level 3, unmeasured) is exact.
- **The `claude_code` arm cannot be recorded.** A Claude Code sub-agent turn (selected with `--harness claude_code`, or a `claude_code` endpoint on an agent role) runs its own tool loop
  inside the CLI. Recording counts such turns (`unreplayable_calls`); replay and level 1 refuse them. Put the role on a chat endpoint to get an exact
  replay. A headless `claude -p` *text* call (spec tests, oracle, DOC step) is recorded and replayed like any other call, but is not level 1 (no temperature).
- **Replay covers the model, not the world.** Tool results (Vivado, simulators, timestamps, random seeds in tests) are executed again. If a tool result
  differs, the next request differs and the replay stops at that call with a miss that names the purpose, the stage and the first message that differs.
  Run and repository paths are replaced by placeholders before hashing, so a replay in another run directory or checkout still matches.
- **A tape is private.** It stores each reply (which can quote a private prompt) and only *hashes* of the messages. It is refused inside a git checkout
  unless git-ignored; `runs/` is ignored, and the default location is outside the repository. Nothing that looks like a key is ever recorded (the call is
  refused instead). Do not commit a tape; a tape worth keeping goes to the private knowledge repository.
- **The key is the resolved request**: purpose, stage, endpoint, kind, model, options (not `timeout_s` or `retries`), messages and tool schemas. A
  changed prompt, option, model or tool list is a miss. The n-th call with a given key gets the n-th recording for it, so a repeated identical request
  replays its different replies in order.
- **Replayed calls cost nothing**: the replayed reply reports cost 0.0 and the provider `replay:<original>`; token counts are as recorded.
- **`--deterministic` does not change the table of a replay**: a recording made at level 1 replays with the level-1 table; a recording made by
  `--record-tape` replays with the table it was recorded with.
- Not covered: the review judge (`flow/review`) and the experiment scripts that run `claude -p` themselves are outside the resolver's tape.

## Level 3 plan: vLLM on the owner's AWS

Nothing here has been started or priced by a live quote. The owner starts and pays for the instance (house rules; owner decision 2026-11-19, item 13: this
PC by default, AWS for bursts, never work hardware). Versions and prices are to be re-read on the day.

**Why**: level 1 is not exact and level 2 cannot make a *new* run deterministic. A self-hosted open-weights model with greedy decoding and a
batch-invariant server can be bit-exact, so a new run can be repeated, and two agent versions can be compared without sampling noise.

**What it measures is a different agent.** An open-weights model is weaker than the Claude models the agent uses today. Every result is reported as a
pair: quality and determinism side by side (below), never determinism alone.

**Model**: one open-weights coder model that fits one GPU: first choice `Qwen/Qwen3-Coder-30B-A3B-Instruct` in FP8 (about 31 GB of weights; mixture of
experts, 3B active); fallback a dense 14B coder model in bf16. Both are re-checked against the vLLM batch-invariance support list before the first
instance starts (a mixture-of-experts model may not be on it; the fallback is dense for that reason). Weights pinned by revision hash.

**Instance**: one AWS `g6e.xlarge` (one NVIDIA L40S, 48 GB), on demand, one availability zone, a stopped-not-terminated EBS volume holding the weights. One
GPU model for every run of a study: a different GPU or driver gives different bits. No tensor parallelism (it changes the reduction order).

**Pinned versions** (written into `config.json` through the endpoint's `deployment_note` and into the study record): the vLLM release, the container image
digest, the CUDA and driver versions, the PyTorch version, the model revision hash, the GPU model, the instance type and region.

**Settings** (the vLLM batch-invariant mode and its prerequisites; to be confirmed against that release's documentation): `VLLM_BATCH_INVARIANT=1`;
`--seed 0` and a `seed` in every request; `temperature: 0`; prefix caching off (a cache hit can change the numerics); a fixed `--max-num-batched-tokens`;
a single GPU; `PYTHONHASHSEED=0`. A fallback that does not need the mode: `--max-num-seqs 1`, one request at a time (slow, but order-independent).
Never share the server with another client during a study.

**How the PC reaches it**: an SSH port forward from the PC to the instance (the owner opens it), so the agent sees `http://localhost:8000/v1` as an
`openai_compatible` endpoint with `temperature: 0` and `seed` set in the table. A localhost endpoint needs no key and is not work hardware.

**Cost estimate** (a planning figure; the on-demand price of `g6e.xlarge` is about USD 1.9 per hour in us-east-1 as last known, re-read it): setup and a
first determinism probe about 2 h; one full agent run through stages 0 to 2 about 1 h of GPU time (108's smoke made 118 chat calls and 2.8 M tokens, mostly
prompt, and the simulations run on the PC while the GPU idles); a 10-run study (5 pairs of identical runs on one task) about 10 h; storage and egress about USD 3.
Total about 13 h, roughly **USD 25 to 30**, with a hard stop of USD 50 (the owner stops the instance after each session: it is not left running).

**How quality and determinism are reported side by side**, for one task set:

| row | determinism | quality |
|---|---|---|
| vLLM greedy, batch-invariant (level 3) | identical-output rate over the 5-prompt probe at N = 10 (`tools/determinism_probe.py`, to be given a `--base-url`); plan repeatability and whole-run file hashes over 5 repeated pairs (`flow/plan_repeat.py`, `tools/determinism_replay_check.py` fingerprints) | gate pass rate and stage reached, same tasks, same limits |
| the same model through OpenRouter at temperature 0 (level 1) | same probe, same measures | same |
| Claude through Claude Code (today's default) | not available (no temperature) | same |

The claim the study can support: whether a self-hosted run is bit-exact (identical-output rate 1.0 and equal run fingerprints in every pair), and what
the exactness cost in quality, on these tasks. Nulls are reported first. Stop condition: if the first probe at N = 10 is not 1.0, stop and report which
setting is missing before any agent run.
