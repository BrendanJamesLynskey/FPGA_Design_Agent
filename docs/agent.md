# The Deep Agents agent (brief 05b, F2 part 2)

A LangGraph graph (1.2.19) over the stage machine of [methodology.md](methodology.md), with Deep Agents (0.7.32)
sub-agents doing the work in each stage and the 05a core ([agent_core.md](agent_core.md)) as the only way to touch
files, tools and the board.

```
python -m agent run designs/t1_dimmer_counter/spec.md --board nexys_a7_100t \
    --interview oracle --hidden-spec <full spec> --review off --model openai/gpt-6-luna
python -m agent resume <run-id> [--rewind N] [--reply '{"decision": "approve"}']
```

Runs live in `runs/<run-id>/` (not committed): the design directory, `snap.git` (stage snapshots), `dcp/` (the
Vivado checkpoints of each stage end), `checkpoints.sqlite` (LangGraph), `summary.json`.

## The graph

`work -> gate -> review -> advance`, looped over stages 0-9 (`agent/graph/run.py`).

| Node | Does | Decided by |
|---|---|---|
| work | the stage's sub-agent(s) act; stage 2 runs the blind model, the test writer and the RTL writer as separate sub-agents | the model, inside its role's view and the stage's tool list |
| gate | runs the flow's checks (lint, simulate in the container, build, gates, verif gates, bring-up) and `exit_check` | the flow's gate output only (`agent/graph/stages.py`) |
| review | writes `build/review/<nn>_<stage>.html` and `review_index.html`, snapshots files + `.dcp`, pauses for approve / edit / rewind when `--review on` | the reviewer (human, planner script, or `auto`), recorded in `BUILD_NOTE.md` |
| advance | next stage on pass; on a failure, the stage that owns the cause (`route_failure`) | the stage machine |

Limits: turns, seconds and USD per stage visit (`stages.MACHINE`) and per run (`RUN_LIMITS`), enforced before each
model call by the `Meter` (`agent/graph/llm.py`); at most 4 visits per stage. Cost is only what the provider reports.
Vivado builds are reused when the sources are unchanged and the earlier build went far enough.

## Separation (`agent/graph/roles.py`)

| Sub-agent | Reads | Writes |
|---|---|---|
| clarify | spec.md | spec.yaml |
| blind model | spec.yaml only | model.py |
| test writer | spec.yaml, model.py, its own tests | tests/, verif/ |
| RTL writer and later stages | the design, `@shell/` (read-only) | RTL, build.yaml, XDC, probes, notes |

The blind model and the test writer run on an in-memory file backend that holds only their inputs (so `ls`, `grep`
and `glob` cannot reach anything else); the graph copies their outputs in through the role jail. The hidden full
spec is outside every design directory and is read only by the spec oracle. `agent/tests/test_roles.py` and
`test_episode.py` check each sub-agent's inputs.

## Interview (`agent/graph/interview.py`)

Stage 0 asks the open questions in `spec.yaml` one at a time, each with a proposed default and its reason:
`--interview on` asks the human (a LangGraph interrupt), `oracle` asks the spec oracle (it answers only with a
verbatim quote from the hidden spec, otherwise "not specified" and the default stands), `off` takes every default.
The record (asked / answered / defaulted, by whom) goes into `spec.yaml` `resolved_questions`, the stage 0 review
page and `summary.json`.

## Review and rewind (`agent/graph/review.py`, `snapshot.py`)

Each stage end writes a self-contained page (light and dark, no external assets): gates, inputs and outputs, the
spec summary, the block diagram from `ARCHITECTURE.md`, testplan and coverage, a waveform, timing / utilisation /
power from `gates.json`, the budget and the decision. The snapshot is a commit in the run's own git directory plus
the stage's `.dcp` files and a SHA-256 manifest. Rewind to stage N restores the files and checkpoints of the end of
stage N, checks every hash, and continues at stage N with the reviewer's note (`resume --rewind N` also restores the
LangGraph checkpoint saved there). Before stage 9 programs the board the graph always pauses for approval, because
`hw_checks.py` runs on the host (see the isolation note in [agent_core.md](agent_core.md)).

## Review replies, the architecture gate and the owner ledger (brief 05d)

A review reply is `{"decision": "approve" | "edit" | "rewind" | "supply", "by": ..., "note": ..., "role": ..., "to": N,
"files": {...}}`.

- **approve** at stage 1 writes the architecture approval (`build/approvals/architecture.json`: who, whether the agent
  or the owner wrote it, the SHA-256 of `ARCHITECTURE.md` and `architecture.yaml`). `--review off` writes it at once as
  `auto`. Stage 2 will not start RTL without a matching record; a later change reopens stage 1.
- **edit** takes `note`, the owner's prompt, given to `role` (`clarify`, `model`, `tests`, `rtl`; default the stage's
  writer). With no note, the owner's hand edit is gated again and the agent does not touch the files.
- **supply** (stage 1): `files` holds the owner's own `architecture.yaml` and/or `ARCHITECTURE.md`; they are validated
  when written and recorded as an owner contribution.
- **Hand edits.** The agent does nothing while a review is paused, so any file that differs from the stage snapshot at
  the reply (outside `build/` and `BUILD_NOTE.md`) is an owner edit: committed separately in the run's snapshot
  repository with author `owner`, then gated again. `agent/graph/ownership.py` keeps the ledger
  `build/who_did_what.json` and the "Who did what" table in `BUILD_NOTE.md` (owner, agent, auto), which the gallery reads.

The page also shows, for line-by-line review, the RTL diff against the previous stage, the requirements with their
tests and bins, buses as hex waveforms, `design.xdc` in full with each pin traced through the master XDC to the board
inventory, the proof-method traceability table and the design-standards results.

## Benchmark tasks as agent runs (brief 07a2-prep)

`python -m agent run <task>/spec.md --interview oracle --hidden-spec <task>/hidden/spec.yaml ...` runs a benchmark task.
Four gaps found by the course-tier port are closed; each has a test in `flow/tests/test_07a2_prep.py` or
`agent/tests/test_07a2_prep.py`.

- **Task data.** A `data/` directory next to `spec.md` (or `--data-dir`) is copied to `<design>/data`, read-only for the agent
  (`data` is in the path jail's write-deny list; the clarify, model, tests and rtl roles may read it), and listed at the end of
  the design's `spec.md`. The simulators find it: `flow.cocotb_run.run` links the files into the simulator's working directory
  (`test_dir`) for the length of a run as `data/<name>` and `<name>`, so `$readmemh("x.hex")` and `$readmemh("data/x.hex")` both
  open it; `flow/prepare.py` copies them into the Vivado build directory (and into the build stamp); the course scoring tool
  links them into `hidden/` for the length of a scoring run.
- **UART-subject designs (`no_shell`).** `--no-shell`, or a `bench.yaml` with `no_shell: true` next to `--hidden-spec`, writes
  the marker `.no_shell` into the design. With it, `flow.cocotb_run.run`, `lint`, the standards check, `flow/mutate.py` and
  `flow/prepare.py` leave out `shell/rtl`, and no `BUILD_STAMP` generic is passed; the prompts' flow conventions say so.
- **Compile order.** `flow/srcorder.py` `order_sv` puts packages and interfaces before the files that import or use them
  (stable; a cycle keeps the input order) for simulation, lint, the standards check, Vivado and the course scoring tool.
- **Register maps.** The interview oracle's text now ends with `registers.map` rendered one register per line, and a quote
  that differs from the file only in white space is accepted (an invented quote is still refused).
- **No OpenRouter.** `--oracle claude_code` (needs `--harness claude_code`) runs the oracle as a tool-less headless
  `claude -p` call (`agent/claude_code_arm/oracle.py`, Haiku by default); any OpenRouter call raises.
