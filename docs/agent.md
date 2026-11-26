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

## Requirements strictness (`agent/graph/requirements.py`, brief 210)

`--interview` says who answers a question. `--requirements loose|standard|strict` says **what may be left unanswered**. Before brief 210 any
question, from a clock frequency to a register name, was settled by its default when nobody answered, and the defaults were recorded but
nobody had to read them.

**Risk class.** Every question gets one, by rules on its words (`classify`; the rule that set it is recorded with the question):

| Class | Meaning | Examples |
|---|---|---|
| `high` | changes behaviour, board safety or an interface others build against | a clock frequency or source, a pin or I/O standard, reset polarity and style, a protocol or handshake, a register map, a number format, a rate, delay or latency, what happens in a case the request left open |
| `medium` | changes size, speed or power, not what the design does (also any question no rule names) | resource budget, pipeline depth, buffer depth |
| `low` | cosmetic, or a choice of verification method | a name, a comment, an ordering |

The Clarifier may set `risk` (and `risk_reason`) on an open question in spec.yaml. The higher of its class and the rules' class counts: it can
raise a class, never lower one a rule set. Its prompt does not ask for one yet (prompts are pinned in the private knowledge repository, so a change
needs a pin), so today the rules decide. The rules are words, not understanding: a question phrased without any of them is `medium`, and
a `low` rule can be fooled by a name that is also a pin (the rules look for offsets, widths and pins first, but not for everything).

**Levels.**

| Level | `low` and `medium` question | `high` question |
|---|---|---|
| `loose` | defaulted and recorded | defaulted and recorded |
| `standard` | defaulted and recorded | answered, or waived; otherwise the run stops at clarify |
| `strict` | answered, or waived | answered, or waived |

A run that stops writes `REQUIREMENTS_NEEDED.md` in the design directory (each question, the default the agent would have used and why it
matters), keeps the question open in spec.yaml, builds nothing and **exits with status 3** (a usage error is 2, a crash is 1). To go on: put the answer in
the request and run again, use `--interview on`, or record a waiver.

**Waiver.** A recorded decision, not a default: the question (its id, words of it, or `*` with the class it covers), the value chosen (or "agent's
default accepted"), who, when and why. At the interview, "accept default" or `{waive: true, why: ...}` records one. For a non-interactive run
write `requirements_waivers.yaml` beside the request or in the design directory:

```yaml
waivers:
  - match: clk_sys                       # an id (q3), words of the question, or "*" with `risk: low`
    value: agent's default accepted      # or the value you choose
    who: <name>
    when: 2026-11-25
    why: the bench oscillator is fixed at 10 MHz
```

A waiver with a missing field, a date that is not YYYY-MM-DD or a reason under eight characters is not used; the problem is listed in
`REQUIREMENTS_NEEDED.md` and the run summary. Waivers and the level are written to `build/requirements/state.json`. `standard` lets a waiver settle a
`high` question: an explicit decision is not a silent default, so only the unanswered-and-unwaived case stops the run.

**Which level.** The command line wins; then a line `Requirements: strict` in the request, `requirements_strictness` in spec.yaml, or the design
package's `requirements` field in `package.yaml`; then the default. `production_secure` and the higher verification profiles
(`thorough`, `ip_release`, `high_dependability`) raise any result to at least `standard`. The default is `standard` with `--interview on` and `loose` otherwise,
and always `loose` for a run with `--hidden-spec` (every benchmark run), so earlier numbers stay comparable. Why: re-scoring the recorded runs
(`tools/requirements_rescore.py`, `results/210_requirements/rescore.md`) found a high-risk default in nearly every run, so `standard` as the default
for a run nobody answers would stop nearly all of them at clarify. Under `standard` or `strict` the oracle's "not specified" on a high question is a
stop, which is the honest result for a vague request.

**What each level can get wrong.**

- `loose` never stops, so a wrong default reaches the design. The handover and `REQUIREMENTS_REPORT.md` list every default with its class, and a pass on a
  requirement that rests on a default is marked; nothing obliges you to read them.
- `standard` decides by the class, and the class is by words. A question the rules call `medium` or `low` may matter to you (a `medium` "FIFO depth" can
  decide whether the design fits); read the assumptions list. The question limit (twelve) still applies: a high question dropped by the limit is
  unresolved, not defaulted.
- `strict` makes you answer or waive every question, including verification-method ones; a `*` waiver for the `low` class settles them in one line. A waiver is
  the user's word: it is recorded and shown, and it does not make the value right.
- A waiver that only says "accepted" is recorded as such. The record shows who and when, not whether they understood the choice.

**Assumptions you did not confirm.** In every level the handover (README.md, AGENT.md, `handover.yaml` `assumptions`) lists each question settled by
a default or a waiver, with its class and how it was settled, highest class first. A handover from before brief 210 has none.

**The requirements report (`flow/requirements_report.py`).** `REQUIREMENTS_REPORT.md` at the design root, linked from the README, has one row per
requirement: id, text, **where it came from** (a line of the request, an answered question, a default with its class, a waiver, or "unrecorded": the request or
the Clarifier's reading, which spec.yaml does not tell apart; a requirement may carry an explicit `origin`), the method(s), the evidence as links, and the
result: `pass`, `fail` or `pending` (the evidence does not exist yet, for example a board check before the visit). The first line reads "N of M requirements
verified and passed; K pending; F failed", and counts the passes that rest on a default you did not confirm. The agent's trace step rewrites it after every stage
from stage 2 on, and `build/requirements/report.json` holds the same data. After a board run,

```
python -m flow.requirements_report <design> [--hw <bring-up JSON>]
```

rebuilds the matrix from the design's `build/` evidence and turns the pending hardware rows into pass or fail from `build/bringup/<design>_bringup.json`
(or `--hw`), with no other edit (exit status 1 when a row failed). The handover is not regenerated by this: run `python -m agent document <run-dir>` or
`python -m flow.handover write <design>` again, or `doccheck --strict` will flag it as stale. The origin of a requirement is found by matching its words against
the interview and the request, so it is a pointer, not proof. The "traced to a test" line of the strict level is the `unverified` list of the report: requirements no
test or check cites.

**A fix against a requirement.** In brief 209a's live run the Designer met the report gate by pipelining a chain the request said must have no register, and
left the conflict for someone else. Now a blocking report finding whose fix would break a stated requirement is checked against spec.yaml
(`fix_conflicts`: pipelining against "no register", "combinational", "single cycle" and similar). At `standard` and `strict` the run stops, names the
conflict in `REQUIREMENTS_NEEDED.md` and exits with status 3, unless a waiver names the requirement (`requirement: REQ-08`); at `loose` it goes ahead, records the
conflict in `build/requirements/state.json` and the report marks that requirement `fail` with the reason, whether or not it was waived. The check is by the
requirement's words and covers the fixes of RPT-LL-02 and RPT-CS-02 only.

Tests: `agent/tests/test_210_requirements.py` (rules, levels, waivers, the stop and its exit status, the conflict on the recorded c15 report),
`flow/tests/test_210_requirements_report.py` (the report on t1_dimmer_counter's reference run: a pending row, a failed row, regeneration after the board).

## The lab: instruments the agent can use (`hil/lab.py`, brief 221)

The agent knew the board (`boards/*/board.yaml`) but not the bench, so a check that a scope, counter or logic analyser would settle in seconds was skipped or
done indirectly. A **lab file** records the bench; the interview reads it and asks only about gaps; stage 9 picks, per requirement, the best method and writes the
instrument steps into `BRINGUP.md`; the requirements report shows the method on each row. Nothing here touches an instrument: the agent writes and **dry-runs**
the steps against mock instruments, and the owner runs every instrument script, one step at a time, as for every board command.

**The two files.** The owner's lab profile lives in the user's config folder, never in the repository (it describes a private bench):
`~/.config/fpga-force/lab.yaml`, or the file named by `FDA_LAB_FILE` (`none` means no profile; the test suite sets it so). `hil/lab.example.yaml` is the template,
seeded from the owner's bench. A design may carry its own `lab.yaml` (in the design directory or `package/`): its `connections` say which instrument channel
probes which pin for this design, and an instrument entry with the same `id` overrides the fields it states. Each instrument entry has: `kind`, make and
model, `onboarded`, `connection` (`usb`, `lan` with an address, or `none`), `control` (`scripted` with a `driver`, or `manual`: the owner types the reading),
`channels`, `capabilities` (what it can measure, with limits such as `max_hz` and `accuracy_ppm`) and `outputs` (what it could drive into a board: each with a limit, or
`never_by_script: true`). `python -m hil.lab [--design <dir>] [--usb]` shows the lab a design would see and checks the file; `--usb` runs `lsusb` (a listing) to say
which instruments are plugged in.

**The interview** (`agent/graph/lab_interview.py`) asks, in the spec's `open_questions` with a default and a reason like any other question:
`[lab:connect:<instrument>:<requirement>]`, once per onboarded instrument that could check a requirement stating a frequency or a level and is not recorded as
connected ("the 25 MHz clock on pin C3: the counter as an independent check beside the on-chip count? Answer `counter: A -> pin C3` or `not connected`", default
not connected, on-chip only); and, only to a person (`--interview on`) and only when there is no lab file at all, `[lab:record]` (default: no, on-chip measurement
only; a "no" is written to the design's `lab.yaml` so it is not asked again). Answers are recorded with who gave them in the design's `lab.yaml`. The tag makes the
requirement-risk rules class these questions `low` (a verification-method choice), so a default never stops a run at `standard`; at `strict` they must still be
answered or waived. An instrument that is **not onboarded is never asked about and never chosen**: the plan lists it as "available after onboarding".

**Method choice** (`hil.lab.plan_need`), per requirement whose proof includes hardware and whose text states a frequency (with a unit) or a level: a scripted,
onboarded instrument connected for this design; else a manual one (the owner types the reading); else the on-chip method, which is always there and is always kept.
So a requirement keeps its on-chip evidence, and gains an independent check beside it when one is wired. An instrument whose range or accuracy cannot meet the
requirement is left out with the reason (an accuracy figure must be three times better than the tolerance). The choice is `build/lab/plan.json`, the steps are
`lab_steps.yaml` in the design, and `BRINGUP.md` gets a `Lab instruments` section between two marker lines, regenerated at every visit of stage 9 so a rewrite of the
file by the model does not lose it. A design with no lab at all gets nothing written. `flow/bringup.py` runs the steps as a step `lab_instruments` (after the UART tests or
the bus checks; present only when `lab_steps.yaml` exists) and `python -m hil.lab_bringup run <design>` runs them alone.

**Safety** (`hil.lab.check_drive`, called by every adapter before any `configure` that drives, and by the runner before the owner is even asked). Refused: an output the
lab file does not list; one marked `never_by_script`; an instrument not onboarded; a value above the output's `max_v`, `max_a`, `max_dbm` or `max_hz`; a limit that
needs a value the step does not state; RF without 30 dB of attenuation or a declared dummy load; a voltage above the VCCO of the pin it is wired to. Every step that
drives a signal into the board is marked `DRIVES` in `BRINGUP.md`, carries the permission action `drive_instrument_output` (brief 222's permission modes list it and
its `lab_limits` never-rule stands for these checks), needs the owner to type `yes` at run time, and every output is switched off at the end of the run whatever happened.
A manual instrument is set by the owner, never driven. No input of this module reaches a supply: the example profile lists the M2K supplies as `never_by_script`.

**Readings.** A scripted step returns `fda-measurement/1` (one value, its unit, channel, instrument, uncertainty if known) through the instrument contract
(`describe`, `configure`, `arm`, `capture`, `close`; `hil/lab_drivers.py`: adapters for the Red Pitaya and the M2K over the existing `hil/instruments` modules, a manual
adapter and a mock). A manual reading must carry its unit (`25.0001 MHz`): a bare number is refused, a unit of another quantity is refused, and a reading about a
thousand times off the expected value is flagged as a probable unit slip. Each row of `build/lab/results.json` records the method (`scripted`, `manual`, or `dry_run`),
what was typed and the error in ppm. A dry run (mock instruments) is marked `dry_run`, has `evidence: false` and is never counted.

**The requirements report** gains the method on each row: `instrument (counter A on pin C3, scripted): pending | pass | fail`, `dry run against a mock, not evidence`, or
`instrument: none, on-chip only (<why>)`. A failed instrument reading fails the requirement; a passed one does not pass it alone (the design's own evidence is still
needed); a dry run changes nothing.

**What a user could get wrong, and what happens.**

- *A probe on the wrong pin.* Not detectable by the harness. The wiring step asks you to confirm each channel's pin before the first reading, and the plan prints the pin it
  assumed; a wrong pin shows as a reading nowhere near the expected value or "not enough edges".
- *A manual reading in the wrong unit* (kHz for MHz): a bare number is refused, a wrong quantity is refused, a value about 10^3 or 10^6 off is flagged and fails.
- *A lab file with an output that has no limit*: a validation error, and the file is not used. A wrong limit that is too high is yours: the harness enforces the number
  you wrote, and the example profile's `max_v` for the M2K AWG is a starting value the owner confirms per design.
- *An accuracy left out.* The step carries the caveat "the instrument's accuracy is not recorded: a pass is a coarse independent check". Do not read it as an
  instrument-grade measurement. A figure you put in (`accuracy_ppm`) is trusted, not measured.
- *An instrument marked onboarded that was never connected.* The harness cannot tell: `--usb` only shows what is plugged in. The first real run fails at the first reading.
- *A mock instrument (`mock: true`) in a real profile*: it answers dry runs and CI only; a real run of a mock row is marked `mock` and the report does not count it.
- *Two lab files.* The design's file wins for the fields it states. A connection to a channel the instrument lacks is dropped with a problem listed (`python -m hil.lab`).
- *The measurement needs are found by rules on the requirement's words* (a frequency with a unit near "measures", "within", "ppm", "clock"; a level with a voltage). A
  requirement phrased otherwise gets no instrument step; the plan lists none for it.

Tests: `hil/tests/test_221_lab.py` (file schema, merge, method choice, safety limits, adapters on fakes, steps, dry runs, manual prompts), `agent/tests/test_221_lab_interview.py`
(gap questions, risk class, answers recorded, report column), `flow/tests/test_221_bringup_lab.py` (the bring-up step). Example: `results/221_lab_instruments`.

## The Red Pitaya as a target and an instrument (brief 225)

The owner's Red Pitaya STEMlab 125-14 (original generation, v1.1) is a board the agent can target (`--board redpitaya_stemlab_125_14`, [boards/redpitaya_stemlab_125_14](../boards/redpitaya_stemlab_125_14/README.md))
and, in the same box, a lab instrument (brief 221's `redpitaya` entry). Two build modes (shell: the design is a block in the vendor's FPGA project, for instruments; bare: the agent owns the whole PL), volatile loading
by a script the owner runs, and the rule that the box is never both at once.

- **Board file.** Part, clock, fast ADC and DAC, E1 and E2, LEDs, the PS-side address window, power and loading, each with its source (the vendor's BSD-licensed FPGA repository at a pinned commit and its documentation read on 2026-11-26) or marked unconfirmed.
  The Vivado 2026.1 Basic tier covers the part (brief 95's licence probe). A smoke design was built through the bitstream. A request naming another Red Pitaya model (Gen 2, PRO, Z7020, 4-Input, SDRlab) is not taken for this one (`other_models_after` in the catalogue).
- **Shell builds.** `python3 tools/rp_shell.py prepare <dir> [--block FILE.sv --slot7 MODULE --slot6 MODULE]`, `build <dir>` (the vendor's script, one heavy slot, under a memory-capped scope), `package <dir> <out>` (`fpga.bit.bin`, `build.json`).
  The block has the ports of [rp_user_block](../boards/redpitaya_stemlab_125_14/shell/rp_user_block.sv): the shell's bus (a one-cycle access, `ack` in the next cycle, `err` with `ack` on failure), IN1 and IN2 samples, and two DAC terms added after the factory generator and PID.
- **Loading.** `python3 -m hil.redpitaya_load script <package> --block <name>` writes the owner's script (volatile load with `overlay.sh v0.94 <file>` or `fpgautil`, verification from the loader's files, on-board checks, `RESTORE=1`). `DRY_RUN=1` prints every board command and calls none.
- **Mode in the lab file.** An instrument entry with `is_board: <board>` may carry `mode: {state: factory_instrument}` or `mode: {state: target_loaded, build_id: ...}`; the design's lab file or its `build.yaml` names the `target_board`, and may say `design_is_instrument: true`.
  Such an instrument is never planned, asked about or run for a design that runs on it (or while it is loaded); the plan says why, and every run row has `instrument_mode`.
- **The lab tool and `lab_limits`.** `drive_instrument` (permission action `drive_instrument_output`) is registered; the `lab_limits` never-rule calls `hil.lab.check_drive` over the lab merged for the design, so an over-limit request, an unknown or not-onboarded instrument,
  an output a script may never enable, or a value the request omits is refused in every mode, `full` included. The tool records an approved request in `build/lab/drive_requests.json` and enables nothing; the owner-run bring-up script does.
- **The `redpitaya_os` never-rule.** Writing the board's SD card, boot files or OS image, running its updater (`ecosystem-update`, `apt upgrade`), or turning its factory SCPI server on, is refused in every mode (in tool arguments, in a script, and for a file the agent writes).
  `overlay.sh` and `fpgautil` are not matched.
- **Self-test loop.** OUT1 into IN1 with a short lead (IN1 is on LV: +-1 V) lets a design generate and measure without another instrument. The owner fits the lead with the board unpowered; the pulse generator's self-test uses 0.25 V and refuses above 0.5 V.

What a user could get wrong: loading a design and then expecting the factory oscilloscope (it is gone until a power cycle or `RESTORE=1`); a signal above +-1 V into IN1 (LV); a design driving OUT1 into something unprotected;
reading an unmapped slot from Linux (the stub answers with a bus error and the PS's reaction is not documented); trusting the 125 MHz oscillator for a ppm claim (the vendor states no accuracy).
Measured examples and their status: [results/225_redpitaya](../results/225_redpitaya/README.md).

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
| `run_vivado` | Vivado synthesis, implementation, bitstream (from stage 2: once lint and simulation pass, the RTL stage's gate runs a synthesis) | deny | ask | allow | allow |
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
- driving an instrument output beyond the lab file's limits, or one the lab file lists as never enabled by a script (a limit the file does not state is zero, never assumed free; brief 225: `never_violation` calls `hil.lab.check_drive` for the lab tool `drive_instrument` over the lab merged for the design);
- changing the Red Pitaya's SD card, boot files or OS image, running its updater, or turning its factory SCPI server on (brief 225; a volatile `overlay.sh` or `fpgautil` load is not matched);
- a cost cap above the hard cap (`HARD_CAP_USD`, $35: the FPGA share of the key).

The scan covers the arguments of the tools that touch a board or an instrument and the path of any file the agent writes. It does not read file contents (an AES core's RTL may say `key`) or the
arguments of the simulation tools, and it is not a sandbox: it stops the agent's own tool calls, not a person's shell.

### Where it is decided

- **The start of every stage** (`permission_entry`): the stage's actions are looked up (the graph's own gates count: stage 2 simulates and, once that passes, synthesises; stage 3 on runs Vivado). A `deny` stops the run (`stop` starts
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
- **A deny that blocks a gate the run needs.** `--deny run_vivado` on a run that must build stops the run at stage 2, on purpose. The same for `--deny edit_design_files` at stage 2, or `--deny write_board_register` at stage 9. Remove the
  override and `resume`.
- **Plan is not "no model".** The interview and architecture still call the model and spend (below the threshold; at it, Plan stops). Plan's estimate is the stage limits, not a forecast.
- **The default differs between the two front ends.** The Navigator starts at Ask; the command line with no flag is Auto, so existing scripts and evaluations are unchanged. Set `mode:` in `permissions.yaml` to change the command line's default.
- **A saved setting is not a running run's.** The run keeps the mode it began with.
- **`ask` answered "allow" lasts for the run**, not for one call. Granting `run_vivado` allows every build after it.
- **The never-list is a filter on the agent's tool calls**, not a guarantee about the machine: it does not stop a person, another program, or a script the owner runs.
- **Settings file location.** `permissions.yaml` is in `~/.config/fpga_design_agent/` (`FDA_PERMISSIONS_FILE` for the command line). The command line wins over a project's entry, which wins over the file's default.

### Measured

One real `--harness claude_code` run per mode on a small design (a 4-bit Gray counter; records and the table in [results/222_permission_modes](../results/222_permission_modes/README.md)):
**Plan** ran stages 0 and 1, asked nothing, wrote its estimate and stopped with the architecture unapproved; **Ask** paused for the knowledge bank (stage 0), the architecture review (stage 1) and edit plus Vivado (stage 2), then only
for the per-stage reviews; **Auto** and **Full** asked nothing. None of the four reached the stage-9 hardware pause (Ask and Auto stopped on a failing ILA debug build, Full on a constraints gate at stage 3, by its own `--stop-after 8` choice
it was kept away from the board), so what Ask, Auto and Full do at the board is shown by `agent/tests/test_222_permission_modes.py` with a scripted model and a fake programmer, not by a run. The first Ask runs also found that the stage-2 gate
synthesises: before the fix the tool gate refused that build and the run looped at stage 2.

- **Claude Code runs on the subscription report no cost**, so `spend_model_money` never triggers for them; the stage caps on turns and time still apply.

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
