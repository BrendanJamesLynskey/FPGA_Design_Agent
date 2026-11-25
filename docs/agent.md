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

`work -> gate -> review -> advance`, looped over stages 0-9 (`agent/graph/run.py`), then `document` at the end of the run.

| Node | Does | Decided by |
|---|---|---|
| work | the stage's sub-agent(s) act; stage 2 runs the Modeller, the Verifier and the Designer as separate sub-agents | the model, inside its role's view and the stage's tool list |
| gate | runs the flow's checks (lint, simulate in the container, build, gates, verif gates, bring-up) and `exit_check` | the flow's gate output only (`agent/graph/stages.py`) |
| review | writes `build/review/<nn>_<stage>.html` and `review_index.html`, snapshots files + `.dcp`, pauses for approve / edit / rewind when `--review on` | the reviewer (human, planner script, or `auto`), recorded in `BUILD_NOTE.md` |
| advance | next stage on pass; on a failure, the stage that owns the cause (`route_failure`) | the stage machine |
| document | at the end of every run (brief 68 C, `--docs on`, the CLI default): code drafts `handover.yaml` from the run's records, the Designer writes its prose, the flow renders `README.md` and `AGENT.md`; the DOC gate must pass (up to three Designer passes; it also rejects a gap that quotes a gate detail the run's own build records contradict, and requires re-measuring as the first next step after a build from an earlier Vivado release). A stop before a stage's gate (the visit limit) is recorded as `gated: false` and is not a result of that stage. Writes `summary.json` first (the handover cites it) and `doc.json` (the DOC result and `signed_off`) | code for every fact and gate result; the model for the prose only |

Limits: turns, seconds and USD per stage visit (`stages.MACHINE`) and per run (`RUN_LIMITS`), enforced before each
model call by the `Meter` (`agent/graph/llm.py`); at most 4 visits per stage. Cost is only what the provider reports; for the `anthropic_api` endpoint (which reports tokens), it is computed from
the response `usage` and the model's price table, never estimated (brief 209b, [model_config.md](model_config.md#anthropic-api-cost-caching-temperature-budgets-brief-209b)).
The USD limits were sized for the default model (OpenRouter, a few hundredths of a USD per call, where the turn limits bind first); for a dearer model
`--budget-scale N` (or `budget_scale:` in a models file) multiplies every stage's USD limit and the default run cap by `N`, so a stage can use its turns.
An explicit `--max-usd` is kept as given. The run summary records `budget_scale` and `token_split` (input, output, cache write and cache read tokens).
Vivado builds are reused when the sources are unchanged and the earlier build went far enough.

### Documentation and resume (brief 68 parts C and D)

- `python -m agent document <run-dir>` runs the DOC step on a finished run (from its `summary.json`); `--replay
  <doc_calls.jsonl>` replays recorded Designer replies. What the code owns and what the Designer writes:
  [documentation_standard.md](documentation_standard.md#agent-produced-designs).
- `python -m agent resume <design-dir> ["<change request>"]` picks up older work from its handover
  (`agent/graph/pickup.py`). It reads `AGENT.md`, runs `flow.handover.freshness(deep=True)` and refuses a handover with
  errors. It then enters the graph at the earliest of: the change request's stage (keyword classes, earliest match;
  `--kind` overrides; goal classes area, latency, retarget, fmax, power, language and mapping since brief 149; a request that
  matches none is a question, `resume` exits 2 and stage 0 is no longer a silent default), the stage of every changed file and stale record, stage 3 when the recorded builds used another
  Vivado release or the build ID changed, and the first stage not yet passed (`--from-stage N` overrides the rule;
  `--dry-run` only reports). Every later stage runs again, so stale evidence is re-run, never trusted. The design is
  copied into a new run (renderings and `build/` left out, its old path rewritten in `build.yaml` and the test plan), the
  architecture approval is carried when the entry is after stage 1, and the change goes to the owning role as the owner's
  note and, for stage-2 roles, as a repair reason. Only designs in the agent's layout (`spec.md` and `spec.yaml`) can be
  resumed. A changed knowledge-bank pin is reported, not re-run. The minimal stage entry is the initial graph state
  (`stage`, `owners`, `note`, `note_role`, `resumed_from`); brief 62B's closure loop should reuse it.
- `python -m agent revise <design-dir> --goal "latency<=10clk" [--goal ...] [--retarget <part|board>] [--dry-run]` (brief 159,
  `agent/graph/revise.py`) takes goals as data (`agent/graph/goals.py`). The same `goals:` block of `spec.yaml` (a list of
  `{metric, op, bound, unit, name?, priority, source}`; metrics lut, ff, bram_tile, dsp, fmax_mhz, power_w, latency_clk; priority
  `must` or `should`) is read by the closure loop (a `must` goal wins over `budget:` and `clocks:`, and the reason says so; a
  `should` goal and a latency goal are listed only, because the loop judges no latency), by the latency loop (`agent latency
  --goal latency<=N clk`, or the design's own goal: the loop stops at the target) and by the trace matrix (each goal is a `performance`
  requirement `GOAL-<metric>[-<name>]` that a verification item must still trace to). The plan compares each new goal with the
  handover's committed measurements: a goal the fresh evidence already meets re-runs nothing (stale evidence counts as none; fmax is
  met only when the committed build was timed at that clock and met timing); otherwise area and latency enter at stage 1, fmax and
  power at 3. A retarget inside one device family enters at 3, to another family (or an unknown one) at 1. Whatever the handover
  already reports stale is added as for `resume`, and the entry is the earliest reason. `--dry-run` prints the plan (per goal the
  verdict and why, per stage kept or re-run, the goal vector before and after with a SHA-256 of each) and exits 0; a goal that cannot
  be read exits 2 with the form to write. A run starts through `resume`'s path with the goals (and, for a retarget, the new part in
  `spec.yaml` and `build.yaml`) written into the RUN's copy; the source design is never edited. Not built: per-stage input hashes.
  Measured on ten scripted changes: [results/159_typed_goals](../results/159_typed_goals/README.md).

## The check suite (`flow/checks`, brief 71)

The Designer (and the closure loop) has one tool for design checks, `check(names, scope, level)`, over a registry:
`lint`, `standards`, `resets`, `cdc`, `methodology`, `drc`, `exceptions`, `io`, `clocking`, `dsp_ram_mapping`,
`control_sets`, `fsm`, `axi`, `axi_profile`, `gt_plan`, `doc`. It returns a digest (each check pass, fail, partial or not run with the
reason; each finding's rule, place, one-line fix and KB skill) and writes the full result to `build/checks/`. Source
checks run concurrently; reports a build did not write are made in one Vivado session on the stage's checkpoint. The
sign-off gates call the same registry: `post_synth_resets_clean` (builds with the reset scan) and the DOC gate. The
older tools (`lint`, `gates`, `check_constraints`, `report_digest`) stay, because the graph's gates and the recorded runs
call them. The Designer also gets `gt_plan` at stages 1 to 3. Details: [check_suite.md](check_suite.md).

**AXI4-Lite interface profile (brief 73).** A design with an AXI4-Lite register block states one profile in `spec.yaml`:
`interfaces: {axi_lite_profile: house | amd_compatible | strict}`, optionally with `blocks:` (a profile and single
settings per register map) and `amd_ip_acknowledged:`. The Clarifier's prompt says when to choose each (`amd_compatible`
when software already written for AMD IP will drive the block, `strict` for bring-up, safety or verification-heavy work,
`house` otherwise); `spec_schema.validate` refuses a bad section; the Designer's `axi_profile` check regenerates each
generated block under that profile and compares it with the file, so a block cannot claim a profile and behave as
another. The profiles, their settings and costs: [hwsw.md](hwsw.md#interface-profiles-brief-73).

## Report gates (brief 209a)

The report checks of brief 204a feed the stage machine. After each synthesis build of stages 2, 3 and 4 the graph reads the post-synthesis
reports (`flow.checks` `logic_levels`, `control_sets`, `synth_log`; no Vivado session): a blocking RPT-LL-02 (a setup path fails even with no net delay,
so the design cannot close at its clock), RPT-CS-02 (control sets above 15 % of capacity) or RPT-LOG-03 (a generic the build sets that the top lacks) fails
the `report_gates` gate. The failure goes to the Designer with the finding's text and one-line fix, plus the advisories of the same checks
(RPT-LL-01 and the rest, which never block). Stage 2 is where the first synthesis build exists, so a design that cannot close is caught there, before the
constraints, implementation and timing-closure stages spend their visits. A build that wrote no synthesis timing report is not judged, and a waived finding does not block.
Tests: `agent/tests/test_209a_report_gates.py`, on the recorded c15 report of brief 204a.

## Boards with no UART: the JTAG register bus (brief 209a)

`flow/host_transport.py` chooses how the host reaches the design from the board file: `uart` (a `uart:` block in board.yaml; the test shell is built in) or
`jtag_bus` (`host_access` names the BSCANE2 USER4 register bus and there is no `uart:` block: the KR260). For `jtag_bus` the run is built without the test
shell (`.no_shell` is set by the board, so `--no-shell` is not needed), the Designer and Verifier are told the register port and the common map
(ID 0x000, BUILD 0x004 = USR_ACCESS, SCRATCH 0x008; the design's registers from 0x010), and the stage-9 bring-up files differ:

| | `uart` | `jtag_bus` |
|---|---|---|
| host files | `tests/test_*_hw.py` (pytest over the shell), `hw_checks.py` `CAPTURES` (ILA) | `hw_checks.py` with `DESIGN_ID`, `make_mock()`, `run(bus)` |
| builds | base and ILA | base only (no ILA) |
| CI check | none: the board is needed | every check against the mock bus (`gates(kind=bringup_ready)` and the graph run `flow.host_transport.run_mock` in the sandbox) |
| `flow/bringup.py` | power_ok, discover, program_base, uart_tests, program_ila, ila_captures, still_alive | discover (needs `--cable-serial`), program_base, bus_checks, still_alive |

`ip_lib/jtag_regs` holds the bus (`jtag_bus.sv` from designs/b58a_trigger, unchanged) and the common map. The real bus, `host_transport.VivadoBus`, runs
`designs/b58a_trigger/host/jtag_regs.tcl` in a Vivado hardware-manager child; it needs the board and is never used in CI.
Tests: `flow/tests/test_209a_jtag_bringup.py`.

## Separation (`agent/graph/roles.py`)

| Sub-agent | Reads | Writes |
|---|---|---|
| Clarifier (key `clarify`) | spec.md | spec.yaml |
| Modeller (key `model`) | spec.yaml only | model.py |
| Verifier (key `tests`) | spec.yaml, model.py, its own tests | tests/, verif/ |
| Designer (key `rtl`), in every later stage | the design, `@shell/` (read-only) | RTL, build.yaml, XDC, probes, notes |

The Modeller and the Verifier run on an in-memory file backend that holds only their inputs (so `ls`, `grep`
and `glob` cannot reach anything else); the graph copies their outputs in through the role jail. The hidden full
spec is outside every design directory and is read only by the spec oracle. `agent/tests/test_roles.py` and
`test_episode.py` check each sub-agent's inputs.

## Interview (`agent/graph/interview.py`)

Stage 0 asks the open questions in `spec.yaml` one at a time, each with a proposed default and its reason:
`--interview on` asks the human (a LangGraph interrupt), `oracle` asks the spec oracle (it answers only with a
verbatim quote from the hidden spec, otherwise "not specified" and the default stands), `off` takes every default.
The record (asked / answered / defaulted, by whom) goes into `spec.yaml` `resolved_questions`, the stage 0 review
page and `summary.json`.

**New-protocol intake (brief 190).** When the request names an exchange or messaging protocol (market data, order entry, a feed handler, a binary
wire format, sequence numbers, a datagram feed, or ITCH, OUCH, FIX or SBE in capitals; a bare "protocol" or "framing" does not count), the harness adds
six standing questions the spec has not already asked, each with a default and the reason for it (`ensure_protocol_questions`, run beside the
register-map question): how a session is set up and ended; how messages are delimited; how each field is encoded (width, byte order, signedness,
scale); the largest message and packet; how sequence numbers behave; what happens on a gap, duplicate or overlap. The defaults are the smallest
checkable choice (one established session, a length prefix, big-endian unsigned fields listed in a byte map, per-packet numbering from 1, drop duplicates
and stop and flag on a gap). The byte map and a golden model come before any RTL. The interview's limit of twelve questions still applies, so on a request
that already has many open questions the later intake questions are defaulted and the record says "limit". The question text is in
`agent/graph/interview.py`, in public code and not in the pinned private prompts (the register-map question's text is a private prompt); it names no protocol by brand. Moving it to the private prompt set is a planner decision (it needs a pin change). The idea of asking these six first is
from Edwards 2026, ch 7; the wording, defaults and reasons are ours.

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

## Permission modes (brief 222)

What a run may do without asking is set by a **mode**, with optional per-action **overrides**, and a short list of things that are **never** allowed. The code is
`agent/core/permissions.py` (no model involved); the Navigator's **Permissions** page sets it ([navigator/README.md](../navigator/README.md#permission-modes-brief-222)).

```
python -m agent run spec.md --permissions ask                     # plan | ask | auto | full
python -m agent run spec.md --permissions auto --deny run_vivado --allow read_board --ask-above-usd 2
python -m agent resume <run-id> --permissions auto                # change the mode of a run (what the old mode had granted is dropped)
python -m agent resume <run-id> --reply '{"decision": "allow"}'   # answer a permission question
```

### The modes

| Mode | In plain words |
|---|---|
| **Plan** | Reads and plans only. The interview and the architecture run, and an estimate of time and cost is written (`plan_estimate.json`: the stage limits and run caps, labelled as limits, not a prediction). No file is changed after the architecture stage, no simulation or build runs, the board is not touched. The run stops with the architecture written and **not approved**. |
| **Ask** (the Navigator's default) | Runs simulation and checks itself; asks before every other gated action. |
| **Auto within limits** (the command line's default) | Edits, Vivado and model spend run without asking, inside the run's budgets. Still asks before programming a board, writing registers, driving an instrument and raising a budget. This is what a run did before brief 222, so a command with no flag behaves as it always did. |
| **Full auto** | Also programs SRAM, writes registers and drives instruments (inside the lab file's safety limits), and stops at the budget caps: it never raises one. |

### The gated actions, and what each mode does with them

`allow` = runs without a question; `ask` = the run pauses and asks; `deny` = the run stops at that point with the reason.

| Action | What it covers | Plan | Ask | Auto | Full |
|---|---|---|---|---|---|
| `edit_design_files` | writing RTL, tests, constraints, scripts (stage 2 on; the spec and architecture the first two stages write are the plan) | deny | ask | allow | allow |
| `run_simulation` | simulation, formal, mutation, lint, open-source synthesis and equivalence checks | deny | allow | allow | allow |
| `run_vivado` | Vivado synthesis, implementation, bitstream (stage 3 on) | deny | ask | allow | allow |
| `spend_model_money` | going on once the run has spent more than `--ask-above-usd` (default $1.00) | deny | ask | allow | allow |
| `raise_budget` | `resume` with a higher `--max-usd` or `--budget-scale` than the run started with | deny | ask | ask | deny |
| `approve_architecture` | accepting the architecture as the plan the RTL is written from | deny | ask | allow | allow |
| `approve_stage` | a person's approve/edit/rewind at the end of every stage (as `--review on`) | allow | ask | allow | allow |
| `program_board_sram` | loading the bitstream into the board's SRAM (never flash) | deny | ask | ask | allow |
| `write_board_register` | the bring-up, which writes the design's registers on the board | deny | ask | ask | allow |
| `drive_instrument_output` | enabling a lab instrument output (brief 221) | deny | ask | ask | allow |
| `read_board` | the Navigator's read-only board actions | deny | ask | allow | allow |
| `use_knowledge_bank` | the private knowledge bank and the IP library (today a local clone behind the access key; the switch for any remote fetch) | allow | ask | allow | allow |

Overrides (`--allow`, `--ask`, `--deny`, or the Navigator's per-action column) replace one cell. A `deny` from the mode or an override is never lifted by a question: nobody is asked about it.

### Never, in any mode

Code checks, run before the mode is read (`never_violation`, `check_script`, `lab_limits_violation`, `check_hard_cap`), so no flag, file or answer reaches them. The Navigator lists them as fixed.

- writing flash or configuration memory (QSPI, `.pof`, `.mcs`), an SD card or eMMC (`program` takes only `target: sram`);
- writing a boot image (`BOOT.BIN`, `.bif`, `.jic`);
- programming eFUSE or BBRAM, or loading a key into a device;
- enabling a laser anywhere except the design's own bring-up step;
- driving an instrument output beyond the lab file's limits, or one the lab file lists as never enabled by a script (a limit the file does not state is zero, never assumed free; brief 221 calls `lab_limits_violation` before an output is enabled);
- a cost cap above the hard cap (`HARD_CAP_USD`, $35: the FPGA share of the key).

The scan covers the arguments of the tools that touch a board or an instrument and the path of any file the agent writes. It does not read file contents (an AES core's RTL may say `key`) or the
arguments of the simulation tools, and it is not a sandbox: it stops the agent's own tool calls, not a person's shell.

### Where it is decided

- **The start of every stage** (`permission_entry`): the stage's actions are looked up (the graph's own gates count: stage 2 simulates, stage 3 on runs Vivado). A `deny` stops the run (`stop` starts
  `permission denied:`, with `stop_detail.permission` naming what is needed and how to change it); an `ask` pauses on a `permission` interrupt; an `allow` goes to the log.
- **The end of a stage**: `approve_stage` and (stage 1) `approve_architecture` set `ask` pauses for a person (the existing review interrupt); in Plan, `approve_architecture` is `deny`, so the run stops after stage 1 with
  the architecture left unapproved (no `architecture_approval` is written).
- **The stage-9 hardware approval** asks for `program_board_sram` and `write_board_register` together, with the bitstream in front of the person (so the board is not asked about at the start of stage 9). In Full, or with both
  allowed by an override, there is no pause: the run records "allowed by mode full" and goes on.
- **Every tool call** (`registry.dispatch` calls `tool_gate`; the Claude Code arm's tool server calls it too, through the run directory): the never-rules, then the run's `permissions.json`. A call that needs an action
  the run has not been granted is refused with the reason (`permission-not-granted` or `permission-denied`), never a crash; the model is told not to retry.
- **A tool added later** (brief 221's instrument tools) is gated by `register_tool_action(tool, "drive_instrument_output")`, and is also scanned by the never-rules.

### Asking, in practice

In the Navigator the question appears on the Live page, in the question panel, with the actions in plain words and *Allow and resume* or *Deny*. **Headless** (`python -m agent run|resume` with no reply),
the run stops at the first ungranted action: it prints `{"status": "needs_permission", "needs": [...], "how": ..., "or": ...}`, writes `pending.json`, and **exits 3**; a run stopped by a refused or denied
permission **exits 4**. Nothing is skipped silently and nothing crashes. Reply with `--reply '{"decision": "allow"}'` (all it asked), `{"allow": ["run_vivado"]}` (only those; the rest are declined), or `{"decision": "deny"}`; or
resume with `--allow <action>` or another `--permissions`. A raised budget on a resume asks the same way (`--allow raise_budget`).

### The record

- `runs/<id>/config.json` has `permissions` (mode, overrides, source, threshold); `permissions.json` is the run's live state (what it was granted or refused, and mode changes on resume);
  `permissions.jsonl` has **every decision**: when, the action, allowed / asked / denied / granted / refused / approved, who or which rule decided (`mode ask`, `override deny run_vivado (command line)`,
  `granted by planner at <time>`), and the stage.
- `summary.json` carries `permissions` (the same, deduplicated) and, in Plan, `plan_estimate`. The handover lists the mode, its source, the overrides and one line per distinct decision in
  `agent_run.permissions` (the times stay in `permissions.jsonl`), and the DOC step's re-check compares it with the run's record.
- A resume keeps the run's own policy, grants included. A different `--permissions` on a resume replaces it and drops the grants.

### What a user could get wrong

- **Full auto on a shared bench.** Nothing asks first: it programs the board and runs the bring-up (register writes) when the bitstream is ready. Use it only when you are watching that board and nobody else is using the
  bench. The board rules of the house (SRAM only, power limit, one board job at a time) are checks of their own and still apply; Full does not suspend them.
- **A deny that blocks a gate the run needs.** `--deny run_vivado` on a run that must build stops the run at stage 3, on purpose. The same for `--deny edit_design_files` at stage 2, or `--deny write_board_register` at stage 9. Remove the
  override and `resume`.
- **Plan is not "no model".** The interview and architecture still call the model and spend (below the threshold; at it, Plan stops). Plan's estimate is the stage limits, not a forecast.
- **The default differs between the two front ends.** The Navigator starts at Ask; the command line with no flag is Auto, so existing scripts and evaluations are unchanged. Set `mode:` in `permissions.yaml` to change the command line's default.
- **A saved setting is not a running run's.** The run keeps the mode it began with.
- **`ask` answered "allow" lasts for the run**, not for one call. Granting `run_vivado` allows every build after it.
- **The never-list is a filter on the agent's tool calls**, not a guarantee about the machine: it does not stop a person, another program, or a script the owner runs.
- **Settings file location.** `permissions.yaml` is in `~/.config/fpga_design_agent/` (`FDA_PERMISSIONS_FILE` for the command line). The command line wins over a project's entry, which wins over the file's default.

@@MEASURED@@

## Benchmark tasks as agent runs (brief 07a2-prep)

`python -m agent run <task>/spec.md --interview oracle --hidden-spec <task>/hidden/spec.yaml ...` runs a benchmark task.
Four gaps found by the course-tier port are closed; each has a test in `flow/tests/test_07a2_prep.py` or
`agent/tests/test_07a2_prep.py`.

- **Task data.** A `data/` directory next to `spec.md` (or `--data-dir`) is copied to `<design>/data`, read-only for the agent
  (`data` is in the path jail's write-deny list; the Clarifier, Modeller, Verifier and Designer roles may read it), and listed at the end of
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
