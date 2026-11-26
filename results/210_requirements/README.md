# Brief 210: requirements strictness, the requirements report, and what recorded runs say about defaults

This folder holds the evidence behind `--requirements loose|standard|strict` and `REQUIREMENTS_REPORT.md` (the design is in
[docs/agent.md](../../docs/agent.md#requirements-strictness-agentgraphrequirementspy-brief-210); the code is
[agent/graph/requirements.py](../../agent/graph/requirements.py) and [flow/requirements_report.py](../../flow/requirements_report.py)).
Everything here was produced on 2026-11-25 on the subscription harness (Claude Code, Sonnet 5.5, no API calls); no Vivado was used.

## Records

- [rescore.json](rescore.json) and [rescore.md](rescore.md): every recorded run that holds an interview (30 summary records under `results/`) and the
  pilot's runs read from the branch `origin/b209-kr260-pilot` (read only, `git show`; the head and the runs included are in `meta`), with each question
  classed now by the risk rules. Made by [tools/requirements_rescore.py](../../tools/requirements_rescore.py). The question text is not stored (some questions
  are written from private prompt templates): each run lists the rule that set the class of each high-risk default.
- [t1_before_board.json](t1_before_board.json), [t1_after_board.json](t1_after_board.json) and [REQUIREMENTS_REPORT_t1.md](REQUIREMENTS_REPORT_t1.md): the
  requirements report of `t1_dimmer_counter` built from its committed reference simulation run and, for the second, the f0b bring-up record. Made by
  [make_t1_records.py](make_t1_records.py). The first has 7 of 11 requirements passed and 4 pending; the second 9 of 11 passed, 2 pending, 0 failed. The two
  pending are the timing and resource checks, which need a build the reference run does not have.
- [live_runs/live_runs.json](live_runs/live_runs.json), [vague_standard_REQUIREMENTS_NEEDED.md](live_runs/vague_standard_REQUIREMENTS_NEEDED.md),
  [vague_strict_REQUIREMENTS_NEEDED.md](live_runs/vague_strict_REQUIREMENTS_NEEDED.md): six live runs of one vague request ([live/spec.md](live/spec.md): a
  pulse stretcher for a Nexys A7-100T), each stopped after the clarify stage (`--stop-after 0`), with the interview oracle (Sonnet) answering from a hidden spec.
  Two runs use a hidden spec that answers the behaviour questions ([live/hidden/spec.yaml](live/hidden/spec.yaml), `full_*`); four use one that also says nothing
  about the register map, the reset or the clock ([live/hidden_vague/spec.yaml](live/hidden_vague/spec.yaml), `vague_*`). Collected by
  [collect_live.py](collect_live.py). The Clarifier writes different questions each run, so the runs are not paired.

| Run | Hidden spec | Level | Exit | Questions: asked, answered, defaulted, waived, unresolved | What it did |
|---|---|---|---|---|---|
| full_loose | answers behaviour | loose | 0 | 4, 3, 1, 0, 0 | defaulted the one question the oracle could not answer (a high-risk one, the host interface) and went on |
| full_standard | answers behaviour | standard | 0 | 5, 5, 0, 0, 0 | the oracle answered every question, so nothing stopped it |
| vague_loose | silent on map, reset, clock | loose | 0 | 5, 3, 2, 0, 0 | defaulted two high-risk questions (the register map, whether the host may trigger) and went on |
| vague_standard | silent on map, reset, clock | standard | 3 | 6, 3, 0, 0, 3 | stopped at clarify with three high-risk questions unresolved, listed in REQUIREMENTS_NEEDED.md |
| vague_strict | silent on map, reset, clock | strict | 3 | 4, 1, 0, 0, 3 | stopped at clarify with three unresolved |
| vague_strict_waived | silent on map, reset, clock | strict, with [live_waived/requirements_waivers.yaml](live_waived/requirements_waivers.yaml) | 0 | 6, 4, 0, 2, 0 | two questions settled by a recorded waiver, the rest answered; went on |

The waiver file in `live_waived/` was written by the executor of this brief standing in for a user, with that said in each waiver's reason; it shows the path, and is not
a user's decision.

## Reproduce

```
python3 tools/requirements_rescore.py --pilot-repo <a checkout that has origin/b209-kr260-pilot>       # rescore.json, rescore.md
python3 results/210_requirements/make_t1_records.py                                                     # the t1_* records
python -m agent run results/210_requirements/live/spec.md --board nexys_a7_100t --name vague_standard --interview oracle \
  --hidden-spec results/210_requirements/live/hidden_vague/spec.yaml --requirements standard --harness claude_code \
  --cc-model claude-sonnet-5-5 --oracle claude_code --oracle-cc-model claude-sonnet-5-5 --stop-after 0 --review off --docs off
```

The last command needs the pinned private prompts (`FDA_PROMPTS_DIR`) and the access key; it exits 3 when the run stops for unresolved requirements. The pilot head moves
as the pilot runs: `rescore.json` `meta.pilot_head` says which records were read. Tests: `agent/tests/test_210_requirements.py`,
`flow/tests/test_210_requirements_report.py`.

## Known gaps and limits

- The re-scoring cannot show that a high-risk default causes failures: all but one of the 40 runs had a high-risk default, so there is almost nothing to contrast with, and
  failure and rework are coincidences by run (most of the main records are development runs that stopped at a limit). It does show that a high-risk default is the
  usual case: 200 of the 276 questions the agent settled with its own default were high risk, so `standard` as the default for a run nobody answers would stop
  nearly all of them at clarify. That is why the default is `loose` unless `--interview on`.
- The risk class comes from rules on a question's words. It was checked on the recorded questions and by the unit tests, not against a person's judgement of each
  question, and the Clarifier's prompt does not set a class.
- The six live runs are single runs of one small request; the counts of questions differ run to run because the Clarifier does. They show that each level does what
  it says, not how often.
- The requirements report's "where it came from" is a word match against the request and the interview. A requirement that matches neither is shown as
  unrecorded, not as a guess; the report cannot tell a requirement the user wrote from one the Clarifier inferred.
- The reference design's report is a committed reference run, not a board pilot's own results; the KR260 pilot's report replaces it on the Why page once its board
  results are in.
