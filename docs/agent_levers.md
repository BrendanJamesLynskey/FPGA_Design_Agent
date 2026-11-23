# Input levers: fixed variables or LLM judgement (brief 194)

Owner, 2026-11-23: "Consider which 'input levers' to the agent should be deterministic (and so set up via a variable) and which should be
subject to LLM analysis. Offer those which are best suited to carrying a certain, static value as variables via the Navigator (part of the
profiles)."

Every input that changes what the agent does is classified here, with the reason. The test for the class is one question: **is the value a
requirement or a policy that the user owns, or does it come from reading this design and its evidence?**

- **Variable**: fixed and user-owned. The value is set before the run (command line, `--set`, spec, a policy file), recorded in the run
  record, and the model cannot change it. If the model's output disagrees (a spec file that names another profile, say) the run logs a
  *policy breach* and the pinned value wins.
- **LLM judgement**: the model decides, because the answer depends on the design. The decision is recorded where the user can read it, and
  the user can override it by editing the artefact at a review or by a change request.
- **Hybrid**: the model proposes a value with a reason (an interview question with a default); the user accepts or pins it; from then on it is
  a variable. `build/who_did_what.json` records who set it (`owner`, `auto` for an accepted default, `agent` for a model-made change).

## How a variable is enforced (version 1)

| Part | What exists |
|---|---|
| Schema | verification switches: [agent/graph/profiles.py](../agent/graph/profiles.py) (`SWITCHES`: name, type, allowed values or range, the default of each profile). Other variables keep the schema they already have (argparse choices, `flow/*.yaml`) |
| Command line | `--verif-profile <name>` and `--set <switch>=<value>` (repeatable; validated against the schema before anything runs; a value below a `flow/verif_floors.yaml` floor is refused). The older `--verif-level` and `--spec-tests` are overrides of their switches and are recorded as such. `--profile` is unchanged: it is the model routing of brief 05f |
| Pin | the harness writes `<run dir>/policy.json` (the effective switches, their hash, who set them) outside the design directory, so no role's file tool reaches it. `profiles.check_pin` compares the live settings and `spec.yaml` (which a role may write) with the pin; every disagreement is listed under `verification_profile.policy_breaches` in the run summary |
| Ledger | the harness records the profile and its overrides in `build/who_did_what.json` at the start of the run (`owner` when the user gave overrides, `auto` otherwise) |
| Navigator | the Start page picker and the profile drawer (per-switch controls generated from `SWITCHES`); the Live page shows the profile and overrides. Built in the Navigator worktree on `b182-navigator-s3`; see the report |
| Test | [agent/tests/test_194_run.py](../agent/tests/test_194_run.py) `test_the_pin_holds_and_a_role_cannot_move_it`; [test_194_profiles.py](../agent/tests/test_194_profiles.py) for the schema, the floors and the recorded overrides |

Version 1 covers the verification switches and the existing flags and policy files below. Rows marked *proposal* have no schema, `--set` or
drawer control yet.

## The table

V = variable, J = LLM judgement, H = hybrid.

### Command-line flags and run configuration (`agent/__main__.py`, `Config` in `agent/graph/run.py`)

| Input | Class | Reason | State |
|---|---|---|---|
| `--board`, the part (from the board catalogue) | V | the user's hardware; no evidence in the design can change it | flag exists |
| `--model`, `--cc-model`, `--cc-effort`, `--profile`, `--roles`, `--models-file`, `--model-config`, `--allow-fable`, `--allow-model-change` | V | which models run, at what cost, and the owner's rules on Fable and OpenRouter; a model must never pick its own model | flags exist; Navigator shows them as fixed fields |
| `--max-usd`, `RUN_LIMITS`, per-stage limits, `visits_per_stage` | V | the budget and loop limits protect the user's plan; the model must not extend them | exist |
| `--stop-after`, `--from-stage`, `--rewind`, `--review`, `--interview` | V | how much the user wants to be asked and where to stop | exist |
| `--verif-profile`, `--set`, `--verif-level`, `--spec-tests` | V | the confidence the user asks for; the model cannot lower its own bar | this brief |
| `--hdl`, `--no-shell`, `--data-dir` | V | the design language and the task's shape | exist |
| `--design-plan`, `--closure`, `--docs`, `--skill-routing`, `--router-model`, `--router-k`, `--harness`, `--harness-arm` | V | which agent features run: user policy, measured separately | exist |
| `--deterministic`, `--record`, `--replay`, `--tape` | V | reproducibility settings | exist |
| `--hidden-spec`, `--oracle`, `--oracle-cc-model` | V | benchmark and interview-oracle set-up: never the model's choice | exist |
| `--spectest-model`, `--spectest-max-loops` | V | the independent bench's model and loop limit | exist |
| Vivado version, strategy menu (`FDA_VIVADO_VERSION`, `flow/options`) | V | the tool the KB was measured on; the menu is a policy list | env var and files exist; *proposal*: `--set` |

### Spec fields (`spec.yaml`)

| Input | Class | Reason | State |
|---|---|---|---|
| clock targets, `timing.clock_constraint`, `timing.latency` budgets, interface protocol, register map | V | requirements; the interview may ask for them, the user answers | exist |
| `verif_profile`, `timing_sim` | V | see above | this brief |
| `requirements[].proof` (the method that will prove each) | H | the agent proposes a method with a reason (`propose_proof`); the interview records the answer | exists |
| `parameters` given as rates (converted to cycle counts) | H | the agent computes the integer and asks | exists |
| `reliability` (which blocks get which structure) | H | the agent lists candidate blocks and the measured cost; the user names the blocks | this brief |
| pipeline depth, FIFO depth, buffer sizes the spec does not give | H | the agent proposes with a reason inside the latency budget; once accepted it is pinned | exists as `open_questions`; *proposal*: a pin per value in `spec.yaml` |
| reset policy (synchronous, except in synchronisers), AXI as the default interface | V | house rules (owner, 2026-11-13 and 2026-11-21): the agent may depart only where meeting them is impossible, and says so | rules in the house file and lint rules; *proposal*: `--set reset_policy` |

### Policy files

| File | Class | Reason |
|---|---|---|
| `flow/verif_floors.yaml` | V | the V3 floors; the model never writes it, and a profile may only raise them |
| `flow/method_mix_policy.yaml` | V | what makes a requirement `verified` (decision 25) |
| `flow/gates.yaml`, `flow/hdl_rules.yaml` | V | the gates and coding rules |
| `flow/ip_tcl_allow.yaml`, the IP list the agent may use | V | the allowed-IP list is the user's to extend; *proposal*: `--set allowed_ip` |

### Decision points inside a run

| Decision | Class | Reason | Where it is recorded, how the user overrides |
|---|---|---|---|
| decomposition and architecture | J | depends on the spec and the part | `architecture.yaml`, `ARCHITECTURE.md`; the stage-1 review approves or edits (hand edits are listed in `who_did_what.json`) |
| which repair to try after a failure | J | depends on the failing evidence | role traces (`runs/<id>/role_usage.jsonl`), the build note; `--review on` stops after each stage |
| test scenarios beyond the plan | J | depends on what the design does | `verif/testplan.yaml`; the independent bench (`--spec-tests`) is the check on it |
| where pipelining goes inside the latency budget | J | depends on the timing report | closure loop records; the budget itself is V |
| whether a failure is the design or the test | J | needs the evidence | the triage record of the spec-test role |
| interpreting an ambiguous spec | H | never silent: an interview question with a default | `resolved_questions` in `spec.yaml` and the run summary |
| which blocks get TMR or ECC when the spec does not say | H | the profile decides *whether* the structures are offered (V); the interview decides *where* | `spec.yaml` `reliability`, the interview record |
| profile choice for a new block | H | the interview proposes one from the spec's words, with its measured extra time | the interview record and `policy.json` |
| request a change to an LLM-judgement value | *proposal* | a Navigator control that files a change request for the next visit of the stage | not built |

## Proposals, not in version 1

1. `--set` for the Vivado version, the strategy menu, the allowed-IP list and the reset policy.
2. A per-value pin for accepted hybrid values (pipeline depth, FIFO depth) in `spec.yaml`, with the same policy-breach check.
3. A Navigator view of the LLM-judgement decisions with a change-request button.
