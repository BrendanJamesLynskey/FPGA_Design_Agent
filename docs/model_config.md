# One model configuration for every model call (brief 108)

Every model call of the agent, the flow and the tools names a **purpose** (why it calls a model). A table maps each purpose to an
**endpoint** (where), a **model** and **call options**. Moving a purpose to another model, another provider or a local server is a
change to that table, not to the code. Code: `agent/models/` (`config.py` the table and its guardrails, `resolver.py` the one object
every call goes through, `endpoints.py` the clients, `claude_cli.py` the one place that builds a `claude -p` argv,
`inventory.py` the list of call sites). Tests: `agent/tests/test_108_model_config.py`. Report: `reports/108_model_config_report.md`.

```
python -m agent models show [--json] [--models-file F] [--model-config JSON]   # the resolved table, and where each value came from
python -m agent models check [--probe]                                         # validate; --probe makes one minimal call per endpoint (spends tokens)
```

## Purposes

| purpose | what it is | call sites need | built-in (today's behaviour) |
|---|---|---|---|
| `interpret` | NL request and spec interpretation: the Clarifier role, the project spec drafter, the plain-English debug parser | agent, chat | OpenRouter, `openai/gpt-6-luna` |
| `oracle` | the user simulator in evals | text, chat | OpenRouter, `openai/gpt-6-luna` |
| `model` | the Modeller role (blind golden model) | agent | OpenRouter, `openai/gpt-6-luna` |
| `tests` | the Verifier role | agent | OpenRouter, `openai/gpt-6-luna` |
| `spectest` | the independent spec-only bench writer and its triage | text | `claude_code`, `claude-sonnet-5-5`, effort medium |
| `rtl` | the Designer role and the single-shot RTL writers | agent, chat | OpenRouter, `openai/gpt-6-luna` |
| `constraints` | the Designer in the constraints stage | agent | inherits `rtl` |
| `closure` | the closure loop's writer (reads STA, area and power reports) | chat | OpenRouter, `openai/gpt-6-luna` |
| `latency` | the latency loop's writer | tool calls (chat endpoint only) | OpenRouter, `openai/gpt-6-luna` |
| `review` | the review judge | text | `claude_code`, `claude-sonnet-5-5`, effort medium |
| `doc` | the DOC step (handover, README, AGENT.md) | text | inherits `rtl` |
| `route` | the cheap skill-section classifier | chat | off (no model) |
| `options` | the strategy generator of `agent improve` (brief 104): two to four ways to improve a loaded design, checked by code | text | Claude Code, `claude-sonnet-5-5`, effort medium (a `default:` does not move it; name it explicitly) |
| `proof` | the Lean proof writer (brief 125, `formal/lean/tools/prove.py`): writes a proof for a theorem statement a human approved, with `lake build` feedback; the kernel is the checker | text | Claude Code, `claude-sonnet-5-5`, effort medium, 1500 s timeout (a `default:` does not move it; name it explicitly) |
| `doc_crossread` | the blind document reader (brief 114): sees only a vendor-document excerpt, writes the facts code depends on with citations; code does the comparison, never a model | text, chat | Claude Code, `claude-sonnet-5-5`, effort medium (opt-in like `options`: a `default:` does not move it; name it explicitly) |
| `assertgen` | the assertion writer (brief 218, `flow/sva_req.py`, behind `--req-sva on`): one SVA property from a requirement and the port list, never the RTL; the formal flow proves it, never a model | text | Claude Code, `claude-sonnet-5-5`, effort low (opt-in: a `default:` does not move it; name it explicitly) |
| `assertback` | the assertion reader (brief 218): reads the property alone and says in English what it requires; code compares that with the requirement, never a model. Keep it a different model from `assertgen` | text | Claude Code, `claude-haiku-5-5`, effort low (opt-in like `assertgen`) |
| `embed` | reserved: embeddings | chat | off; the only embedder is fastembed's local model in `agent/core/skill_index.py` (in-process, tied to the bank's stored vectors), not routed |

A key is a purpose, or `purpose@stage` for one stage of the machine (`rtl@timing-closure`; stage names as in `agent/graph/stages.py`).
Stage keys beat plain keys. The legacy role names are purposes: `clarify` is `interpret`; the Designer in the `constraints` stage is the
`constraints` purpose (the legacy key `rtl@constraints` still works). **Call sites needing "agent"** run a tool-using turn: the Claude Code
arm (a `claude_code` endpoint) or Deep Agents over a chat endpoint (the other kinds).

## Endpoint kinds

| kind | what | options it accepts | key |
|---|---|---|---|
| `claude_code` | the Max subscription, headless `claude -p` ("API-like mode"); no dollars are reported, only the plan's estimate | `effort`, `timeout_s` | the plan's token (`CLAUDE_CODE_OAUTH_TOKEN`, or the mode-600 file) |
| `anthropic_api` | the Messages API; reports tokens, so the agent computes each call's dollars from the response `usage` and the model's price table (see [Anthropic API: cost, caching, temperature, budgets](#anthropic-api-cost-caching-temperature-budgets-brief-209b)) | `temperature`, `max_tokens`, `stop`, `thinking_budget`, `timeout_s`, `retries`, `effort` | `key_env` (default `ANTHROPIC_API_KEY`) |
| `openrouter` | OpenRouter chat completions, data collection denied, provider cost reported | `temperature`, `seed`, `max_tokens`, `stop`, `effort`, `timeout_s`, `retries` | `key_env` (default `OPENROUTER_API_KEY`, or the owner's mode-600 file) |
| `openai_compatible` | any base URL: vLLM, a local model, a specialist fine-tune (brief 107's hook). OpenRouter's extra fields are sent only when the host is `openrouter.ai` | as `openrouter` | `key_env`; none needed on `localhost` |
| `replay` | recorded replies in order (`path:` of a fixture) | none | none |

The endpoint table has four built-in names (`openrouter`, `claude_code`, `anthropic_api`, `replay`); add your own under `endpoints:`.

## Anthropic API: cost, caching, temperature, budgets (brief 209b)

The `anthropic_api` kind is a first-class endpoint. Four things are decided by the configuration, not by catching an error.

**Cost from usage.** Each response reports `input_tokens` (uncached), `output_tokens`, `cache_creation_input_tokens` and
`cache_read_input_tokens`. The call's cost is `(input x p_in + output x p_out + cache_write x p_write + cache_read x p_read) / 1e6`, from a
price table in USD per million tokens. It is the call's reported cost: the meter charges it, and the per-call ceiling is not used for this endpoint.
`model_calls.jsonl` rows of an `anthropic_api` call carry `prompt_tokens` (the sum of the three input fields), `input_tokens`,
`completion_tokens` (output), `cache_write_tokens`, `cache_read_tokens`, `cost_usd` and `cost_basis: "usage*price"`; the run summary
(`summary.json`) carries `token_split` (the same four numbers summed over the run) and `budget_scale`.

The price table is the `models:` section of any layer, matched by the longest model-name prefix, and merged key by key over the built-in rules:

```yaml
models:
  claude-sonnet-5-5:
    price: {input: 2.00, output: 10.00, cache_write: 2.50, cache_read: 0.10}   # USD per million tokens
    temperature: false                                                        # the API rejects a temperature for this model
  claude-haiku-5-5:
    price: {input: 0.10, output: 0.50}                                        # no cache prices given: write = 1.25 x input, read = 0.10 x input
```

Built in: `claude-sonnet-5-5` (prices above), `claude-haiku-5-5` (input 0.10, output 0.50; cache prices derived as stated). A price needs `input` and
`output`; `cache_write` (the 5-minute write) and `cache_read` are optional. A model with **no price keeps today's behaviour**: the call's cost is
unreported, each call is charged at the per-call ceiling of 0.05 USD, and a line `FDA_NO_PRICE` is printed once per model. Prices are not part of the
model-table hash: a changed price changes the dollars, not which model runs.

**Prompt caching.** The client marks the stable prefix with `cache_control: {"type": "ephemeral"}` (the 5-minute cache entry), at most four markers,
the API limit: the last tool definition, the system prompt (the prefix is rendered tools, then system, then messages), the last block of the last
message (the conversation so far) and the last block of the user turn before the previous assistant turn, which is where the previous call wrote its
entry (so a turn that appends more than 20 blocks still finds it). A prefix shorter than the model's minimum cacheable length is silently not
cached (no error; `cache_creation_input_tokens` is 0). A cache entry lives 5 minutes after its last use; a pause longer than that between calls pays
the write price again. Caching is on for every `anthropic_api` call and has no switch in the file.

**Temperature.** The rule is per model: `temperature: true` in `models:` for models that accept one (the built-in list is Haiku 4.5, Sonnet 4.5/4.6,
Opus 4.5/4.6 and the Claude 3 family); everything else rejects it with HTTP 400, so the client leaves it out, and the soft default of 0.2 is not set
in the entry. A `temperature` you set on such a model is also not sent (it never reaches the API); `--deterministic` level 1 already refuses these models.
An unknown model counts as one that rejects it.

**Output limit, effort and cut-off replies (brief 209b).** `max_tokens` is a hard cap on thinking plus text. The per-model rules in `models:` take
`max_tokens`, `effort` (`low`, `medium`, `high`, `xhigh`, `max`, sent as `output_config.effort`; thinking stays adaptive, never `budget_tokens`, which
Sonnet 5.5 rejects) and `timeout_s`; a purpose's own `options:` beat them, and they beat the kind's defaults (8192 tokens, 180 s). Built in for
`claude-sonnet-5-5`: `max_tokens` 16000, `effort` medium, `timeout_s` 300. Why: the first smoke run had 9 of 17 replies stop at the old 8192 cap, so
normal replies need more than that, and the largest output it saw below the cap was 8141 tokens; 16000 is about twice that, and is the size the API
guide gives for a non-streaming request (above about 16000 it asks for streaming, which this client does not do). At the measured 8192 tokens in about
55 s (150 tokens per second) 16000 tokens take about 110 s, so the 300 s timeout leaves a wide margin. `medium` is the guide's setting for agentic
coding and tool-heavy work at moderate cost (the default of the model is `high`). A reply that stops with `stop_reason` `max_tokens` is **not** retried
(the guide: a cut-off is a failed attempt, not to be retried at the same cap, and a larger cap would need streaming): its tool calls are dropped (their
arguments are incomplete), the role gets the partial text plus a note saying the reply was cut off and to do less in one reply, the call is paid and
charged, a line `FDA_TRUNCATED` is printed, the `model_calls.jsonl` row has `stop_reason: "max_tokens"`, and the run summary counts `truncated_calls`.

**Long replies: streaming, the writing roles' limit, file by file (brief 224).** Every `anthropic_api` request is **streamed** (server-sent events through the
same `urllib` call; no second code path), so a long reply is not killed by `timeout_s`, which now is the longest wait between two events (300 s for
`claude-sonnet-5-5`), not the length of a reply. Usage and cost are taken from the stream (input and cache tokens from the first event, output tokens from
the last) and recorded per call as before; from brief 234 a row also carries `thinking_tokens` (the API's `usage.output_tokens_details.thinking_tokens`, only when the response gives it), `thinking_blocks` and `visible_chars` (characters of text and tool-call arguments in the reply; output tokens that are not visible text are thinking). A stream that drops, ends before `message_stop`, or carries an `overloaded_error`/`api_error` event is asked
for again once (`retries`), logged as `FDA_STREAM_DROPPED`, counted in `stream_retries` of the `model_calls.jsonl` row, and after the second failure raised as an
error: a partial reply is never returned as a success (the dropped attempt's tokens are billed by the API but not in the run's cost; the cost
guard sees them only through the account). The writing purposes (`rtl`, `tests`, `constraints`) take the model's `writing_max_tokens` in place of
`max_tokens`: built in for `claude-sonnet-5-5`, **64000** (four times the 16000 of the other purposes; brief 224 set 32000 after the pilot's 16000 limit cut off every whole-design reply of the
FIR, async FIFO and glitch-free mux designs after about 134 s, and brief 234 doubled it because 4 of 999 Designer calls of the 224 arm still stopped at 32000 while the
largest finished RTL file was 9.7 KB: the reply was mostly thinking, see `reports/234_run_limits_report.md`). It is not the largest value the model may accept (128K): the cost of one full 64000-token reply is
64000 x 10 USD per million = 0.64 USD, which a stage USD budget (scaled by `budget_scale`) and the run cap still bound. Order of precedence: a purpose's own
`options: {max_tokens: N}` (config or CLI), then `writing_max_tokens` (writing purposes only), then the model's `max_tokens`, then the kind default. A `models:`
layer that sets `max_tokens` without `writing_max_tokens` means it for every purpose (it removes the built-in writing limit).

What a user could get wrong: (1) a high `max_tokens` with a low per-run cap (`--max-usd`) stops a run early, because one cut-off reply costs the full limit
(0.32 USD at 32000, 0.64 at 64000, the built-in writing limit) and the Meter charges it; raise `budget_scale` or the cap with the limit. (2) A limit the model does not accept is a
non-retried HTTP 400 on the first call. (3) The Verifier (`tests`) writes its files through an in-memory backend that is copied to disk when the role
ends, so a cut-off there loses every file of the reply; only the Designer is called again inside the visit.

**Budgets that follow the model's price.** Stage USD budgets (`stages.MACHINE`) and the run cap (`RUN_LIMITS`) were sized for the cheap default model.
`budget_scale` (top-level key of any layer, or `--budget-scale N` on `run` and `resume`) multiplies every stage's USD budget and the default run cap by
`N`; it is recorded in the run summary and, when not 1, in the table record. Turns and seconds are not scaled. An explicit `--max-usd` is kept as given, and
the closure and latency loops keep their own caps (`closure_usd`, `--max-usd` of their commands). The default is 1: nothing changes for the default model.

*Choosing the scale for `claude-sonnet-5-5` (brief 209b; modelled from the first pilot run's recorded token counts, one stage only).* With the default
model, a call cost a median 0.00078 USD over two whole runs (`results/68_agent_docs`), so a stage's 0.40 USD never binds: the turn limit (30, or 20,
80 and 45 for the clarify, verification and configuration stages) does. To give Sonnet 5.5 the same calls per stage, the stage USD budget must cover
`turn limit x cost per call`. Priced with caching (first call of a conversation at the cache-write price, the rest as cache reads), stage 1 of the pilot
averaged 0.020 USD per call (32 calls) and the clarify stage 0.033 (11 calls, with two large outputs), so: stage 1, 30 x 0.020 = 0.61 against 0.40 (x1.5);
clarify, 20 x 0.033 = 0.65 against 0.20 (x3.3); stage 2 (no data; assume 0.030 as the context grows), 80 x 0.030 = 2.4 against 0.80 (x3.0). A scale of **3.5**
covers all three (stage budgets 0.70, 1.40, 2.80; 1.40 for the other stages) and gives a default run cap of 10.5 USD, about twice the 5.3 USD a
210-call run would cost at 0.025 USD per call. A call that ends at the 8192 output-token cap costs 0.082 USD on its own; a stage that does that repeatedly
(the smoke run did, 9 times in 17 calls) spends any budget, so the scale does not replace looking at why.

## The file

`~/.config/fpga_design_agent/models.yaml` (the user file; `FDA_MODELS_FILE` overrides the path) and the project file (`models.yaml` next
to the spec, or `--models-file`) use one format. Both are optional.

```yaml
version: 1
endpoints:
  vllm:
    kind: openai_compatible
    base_url: http://localhost:8000/v1
    note: "vLLM 0.x, batch-invariant, greedy"        # free text; recorded, never interpreted; one line, 240 characters at most
  spark:                                             # user file only:
    kind: openai_compatible
    base_url: http://spark.lan:8000/v1
    key_env: SPARK_KEY                               # the NAME of the variable; never the key
    host_class: work_hardware                        # refused for live runs; batch replay only
work_hardware_hosts: [other.lan]                     # user file only
default: {endpoint: claude_code, model: claude-haiku-5-5}   # every purpose the kind can serve; skips the opt-in ones and `latency`
purposes:
  rtl: {endpoint: vllm, model: my-fine-tune, options: {temperature: 0, seed: 7}}
  rtl@timing-closure: {endpoint: claude_code, model: claude-sonnet-5-5}
```

`--model-config '<JSON in the same format>'` is the command-line layer.

## Layers

Lowest to highest: **built in**, **command defaults** (a few commands), **user file**, **project file**, **command line**. A layer
changes only the fields it names; `options` merge key by key. Naming a new `endpoint` in a layer drops the options that lower layers
set explicitly (they belonged to the old endpoint). A stage key (`rtl@stage`) applies on top of the plain key of every layer.

**The flags that existed before are aliases into the same table**, in the command-line layer, and keep working:
`--harness claude_code --cc-model M --cc-effort E` sets `interpret`, `model`, `tests`, `rtl`; `--model M` sets those on OpenRouter when the
harness is not `claude_code`, and the `oracle`, `closure` and `latency` purposes always; `--oracle claude_code --oracle-cc-model M`;
`--spectest-model`, `--spectest-effort`; `--router-model` (turns `route` on); `--profile` and `--roles`. **A flag overrides the user and
project files only when it is given on the command line** (or, in the library, differs from the `Config` default): a flag left at its
default does not hide the file.

## What you could guess wrong

- **An option an endpoint does not support is an error when the table is built**, naming the option, the layer it came from and what the
  kind supports. The one exception is the built-in soft defaults (`temperature 0.2`, `timeout_s 180`, `retries 1` on chat kinds, `effort
  medium` on `claude_code`): they are dropped when the kind cannot take them, so switching a purpose from one kind to another is a one-line change.
- **`effort: null` means unset** (the CLI default), not "medium".
- **`default:` skips** the opt-in purposes (`route`, `embed` stay off; `options`, `doc_crossread`, `assertgen` and `assertback` keep their own entries, Claude Code on the plan) and any purpose the kind cannot serve (`latency` needs
  tool calls through a chat endpoint). Naming such a purpose explicitly on `claude_code` is an error at load.
- **`doc` and `constraints` inherit `rtl`** until a layer sets them. A `default:` sets them explicitly.
- **`anthropic_api` and `claude_code` calls are counted differently:** the run's USD cap counts dollars: provider-reported (OpenRouter) or, for
  `anthropic_api`, computed from the response `usage` and the price table below. An `anthropic_api` call to a model with no price is charged at the
  per-call ceiling (0.05 USD) and warns once; `claude_code` calls are counted in turns and tokens, with the plan's estimate beside them.
- **A resume rebuilds the table from the run's `config.json`** and refuses if the table's hash differs from the run's (`--allow-model-change`
  overrides it); the user file is part of the table, so editing it between a run and its resume is a change.
- **The review benchmark scripts pin their model and effort as aliases**; if the user file moves `review` off `claude_code`, a pinned scored run
  is no longer the pinned CLI. Scored evals use `--model-config` on the command line, never the user file.
- **`--replay`** serves every chat-style call from the fixture in order, whatever the table says; `claude_code` purposes still call the CLI.
- **Embeddings are not routed** (see `embed` above).

## Guardrails (code, applied to the final table whatever layer a value came from)

- Never Fable or Opus through OpenRouter, through an `openai_compatible` endpoint on the OpenRouter host, or through the Anthropic API; never
  an Anthropic model (`anthropic/...`) through OpenRouter.
- `claude_code` runs `claude-*` models only. **Fable needs the owner's `--allow-fable` flag**, which no file can carry (a file with `allow_fable`
  is an error).
- Keys are named by environment variable (`key_env`, upper case). A key-like value anywhere in a file is an error; a field called `api_key`,
  `token`, `secret` or `password` is an error. A record that would contain a key-like string, or the value of a configured key variable,
  is refused.
- An endpoint marked work hardware (`host_class: work_hardware`, or its host listed in `work_hardware_hosts`) is refused for live calls and
  allowed for batch replay. **A project file cannot set `host_class` or `work_hardware_hosts`, cannot unmark an endpoint (it can re-point one;
  the mark stays by name and by host), and cannot grant Fable.**
- Notes are one line; prompt text never belongs in a configuration (prompts stay in the private knowledge repository, brief 99).

## The run record

`config.json` holds the file layers (path and SHA-256), the fully resolved table (endpoint, kind, model, options, deployment note, per
purpose and stage) and its hash. `model_calls.jsonl` has one row per chat-style call: purpose, stage, endpoint, kind, model, the hash of the
resolved entry and of the table, tokens, provider-reported cost, seconds. `summary.json` carries `model_table_hash`. No key, prompt or
reply is in any of them. Calls on a `claude_code` endpoint are also in the existing `claude_code_calls.jsonl` and `role_usage.jsonl`.

## The gate

`test_gate_no_model_client_or_claude_argv_outside_the_resolver` scans every tracked and untracked Python file outside `agent/models/` and
the tests and fails on: constructing a model client, importing an LLM SDK, looking up the `claude` binary, a `claude -p` argv, or any of the
`claude` isolation flags. A new call has to go through `Resolver` (`chat`, `text`, `oracle`, or `agent_spec` for a role) and be added to
`agent/models/inventory.py`, which another test checks against the files and the purpose list.
