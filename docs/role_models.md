# Per-role model routing (brief 05f, F2 part 6)

Which harness, model and effort runs each sub-agent role. Code: `agent/graph/role_models.py`; dispatch and accounting in
`agent/graph/run.py` (`run_subagent`).

**Since brief 108 the role map is a view of the model table** ([model_config.md](model_config.md)): a role is a purpose (`clarify` is
`interpret`), the harness is `claude_code` for a `claude_code` endpoint and `deepagents` for any chat endpoint, and `--profile`, `--roles`,
`--harness`, `--cc-model` and `--model` are aliases into the table. What follows is unchanged in effect.

## Roles, orchestration and the oracle

- Roles (display name, record key): the Clarifier (`clarify`), the Modeller (`model`, a blind golden model), the Verifier
  (`tests`, including the stage-9 bring-up files) and the Designer (`rtl`; it writes architecture, RTL, constraints and
  probes and does every repair; Vivado implementation is run by the deterministic flow, not by this role).
- The **stage machine is plain code** (the "orchestration"): which role runs when, the gates, routing of failures to an
  owner role, review pages, rewind. No model drives it, so there is no orchestrator role to route.
- The interview **oracle** (user simulator) is not a role. It always runs on `--model` (luna by default), whatever the
  profile, so runs stay comparable with every earlier F2 run.

## Profiles

```
python -m agent run <spec.md> --profile single|cvdp [--roles '<json>']
```

| Profile | Map |
|---|---|
| `single` (default) | One harness and model for every role: today's behaviour (`--harness`, `--model`, `--cc-model`, `--cc-effort`). Existing runs and replays are unchanged. |
| `cvdp` | `rtl`: Claude Code + `claude-opus-5-5`, CLI-default effort (the `--effort` flag is omitted); `model`, `tests`, `clarify`: Claude Code + `claude-sonnet-5-5`, effort medium. The Modeller runs on a different LLM from the Designer on purpose: CVDP found same-model self-tests share the writer's misreadings. Claude Code runs the lean profile the arm already uses (our role prompt as `--system-prompt`, only our MCP tools, no settings, no slash commands). |

Mixed harnesses work in one run: the role's harness is chosen at dispatch, so a luna (Deep Agents, OpenRouter) role can sit
beside Claude Code roles. A Deep Agents role on a model other than `--model` gets its own OpenRouter client; models
containing `anthropic/`, `fable` or `opus` are refused through OpenRouter (owner rule). Opus and Fable run only through
Claude Code on the plan.

## Per-stage overrides

The routing key is the role, or `role@stage` for one stage of the machine (stage names: `clarify`,
`board-and-device-planning`, `rtl-design-creation`, `constraints`, `synthesis`, `implementation`, `timing-closure`,
`power-closure`, `drc-closure`, `configuration-and-debug`). Use it where another model may read STA, CDC or methodology
reports better than the same role elsewhere (stages 6 to 8), or constraints (stage 3):

```
--roles '{"rtl@timing-closure": {"model": "claude-fable-5-1", "effort": "high"},
          "rtl@constraints": {"harness": "deepagents", "model": "openai/gpt-6-luna"}}'
```

Each layer is partial (only the keys it names change). Precedence, lowest to highest: single base, profile `role`,
explicit `role`, profile `role@stage`, explicit `role@stage`. The profile `cvdp` sets no stage override. To make one
permanent, add the `role@stage` key to a profile in `PROFILES`. `config.json` stores `profile`, `roles` (the explicit
overrides, verbatim), and the resolved `role_models`; `resume` rebuilds the map from `profile` and `roles` (an older
`config.json` resumes as `single`).

## Accounting and records

- `runs/<id>/role_usage.jsonl`: one row per sub-agent call: stage, role, harness, model actually requested, effort,
  whether a stage override applied, turns, tokens, wall time, provider-reported USD (Deep Agents) or Claude Code's plan
  estimate. `summary.json` adds `per_role`, `per_stage`, `role_models`, `stage_overrides`, `profile` and `oracle_model`.
- Review pages carry a "Models by role" table (with that stage's use); the review index carries the map; `BUILD_NOTE.md`
  starts with it.
- `summary.json` `knowledge_use`: per role and stage, the calls to `load_skill`, `search_docs` and `board_constraints`,
  and for `load_skill` the section names and skill files returned (from `build/audit.jsonl`, whose records now carry
  the role), so you can see whether the Designer uses the family and device layers.

## What this deliberately does not copy from CVDP

CVDP's nulls (see `cvdp_rtl_recommendation.md`): no lessons memory, no self-check or verify-before-submit loop, no spec
vectors, no knowledge-pack injection into prompts, no skills beyond what the agent already loads by tool. None is added
here.

**Device know-how stays on.** The CVDP null was for generic RTL problems. The knowledge tools (`load_skill`,
`search_docs`, `board_constraints`) and the family (`artix7`) and device (`xc7a100tcsg324-1`) layers behind them are
unchanged for every role and profile (tested: the tool lists and prompts are identical under `single` and `cvdp`).
Primitives, MMCM/PLL configuration, LUT6-aware design and DSP48E1 inference matter to our Vivado gates, which CVDP never
measured.

## Cost routing by stage and k-way attempts (brief 214)

Both are **off by default** (`--routing off`, `--kway 0`); every run behaves as before unless asked. The code is `agent/models/routing.py`;
`agent/tests/test_214_cost_routing.py` tests it with recorded results.

**The routing table** says which tier of model a sub-agent call uses, by role, stage and kind of visit. `standard` is the role's own resolved model
(whatever the model table gives; this module never changes it). `cheap` is `claude-haiku-5-5` at effort low; `strong` is `claude-opus-5-5` at effort
medium. Both are `claude_code` models: a role on a chat endpoint (Deep Agents over OpenRouter or the API) is not routed, and its call records
`routing.skipped`. Opus is never reachable through OpenRouter or the `anthropic_api` kind (owner rule); here it is on the Max plan only, as in the `cvdp` profile.

| role | stage | kind of visit | tier | why |
|---|---|---|---|---|
| rtl | rtl-design-creation | repair of a lint or design-standards failure only | cheap | a mechanical edit the finding names |
| rtl | rtl-design-creation | repair of anything else | standard | a simulation or verification mismatch needs the model that reads the spec best |
| rtl | rtl-design-creation | first write | standard | |
| rtl | board-and-device-planning | any | standard | architecture stays on the configured model; a strong tier is measured by escalation only |
| model, tests, clarify | any | any | standard | spec readings stay on the configured model |

With `--routing on` a call takes its row's tier. The DOC step is not routed by this table: it runs on the `doc` purpose, which a `models.yaml` sets
like any other (see [model_config.md](model_config.md)).

**Escalation.** When the same failure has begun two visits of a stage (the stage-2 signature of `state['sig']`, else the gate lines with numbers removed),
the next visit of that stage uses `strong` whatever the table says, until the failure changes or the stage passes. The count is per stage and is kept in
memory: a resumed run starts it again from zero.

**k-way attempts.** `--kway K` (K > 1): when stage 2 has failed on two visits, the third visit runs K independent attempts at the stage's work instead of
one, once per run. Each attempt starts from the same snapshot of the design taken before the first (restored before every attempt; the attempts run
one after another, so one never sees another's edits; build products are left alone) and is evaluated by stage 2's own gates (lint, simulate,
standards, constants, verification; no Vivado). The kept candidate is chosen by, in order: a verdict from a check the Designer did not write (the
fresh-stimulus regrade, the independent spec-only bench) where one ran, then the most gates passed, then the fewest findings, then the lowest LUT count.
A choice that no independent check supported is labelled `own_gates_only` in the record: in CVDP, choosing among three by the model's own check gained 1.3
points where an independent check gained 10.8, so treat such a choice as weak evidence. The normal gate then runs on the kept files.

**Records.** `role_usage.jsonl` rows carry `routing` (tier, reason, kind, streak, escalated, the model the table would have used) and `kway_attempt`;
`routing_events.jsonl` has `route`, `kway_start` and `kway_chosen`; `kway.jsonl` has one row per candidate (gates passed, findings, LUTs, independent
verdict, wall time, plan-estimated cost) and one row for the choice; `summary.json` `cost_routing` has calls and plan-estimated cost per tier, the
escalated calls and every candidate. Cost comes from provider usage, as everywhere.

**Limits.** Attempts of one round differ only by the model's own variation (a Claude Code call has no temperature). Stages other than 2 are not k-way
(their gates run Vivado). Whether either feature helps is measured in `results/214_cost_routing/`; the defaults stay off until that says otherwise.
