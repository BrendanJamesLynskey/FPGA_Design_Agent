# Documentation standard: for the next engineer (brief 68)

The owner, 2026-11-13: "Every example/showcase project should have some kind of documentation, with a clear
description of what it does, the technical parameters, what's been measured/verified, known gaps etc. Anything the agent
produces should be as thorough as a human engineer would be expected to be. The idea is to enable the 'next person' to
pick up the work."

This page says what each kind of folder must document, and how `flow/doccheck.py` checks it. CI runs
`python3 flow/doccheck.py --check --strict` on every push and pull request (strict: a record or source file that changed
after its handover fails too; refresh with `python3 flow/doccheck.py --write`).

## The rule for every number and every claim

- Every number comes from a committed record (`results/...` or an IP entry's `char/` file). A design's numbers live in
  its `handover.yaml` and are **read from the record by code** (`python -m flow.handover fill`), never typed.
- Every verification claim names its evidence: a record in `results/`, or a test that CI runs.
- Whatever was not verified or not measured is written down under **Known gaps and limits**, with nulls, failing or
  waived gates and assumptions. A blank is not allowed: a quantity that was never measured is a gap that says so.
- Hardware evidence states its operating conditions (power source, temperature and rails, or that they were not read).
- Published text names only Vivado 2026.1 (owner, 2026-11-11). Raw records keep the version they were made with.
- Anything a user could reasonably guess wrong about behaviour (unmapped or reserved accesses, read side effects,
  same-clock priorities, partial writes, reset, interrupts, latency, clock domains) is stated, or listed as a gap.

## Designs (`designs/<d>/`): one source, two readers

Each design has three files that go together:

| File | Reader | Written by |
|---|---|---|
| `handover.yaml` | the source of truth (schema: `flow/handover.schema.json`) | an engineer or the agent; numbers and hashes by `fill` |
| `README.md` | an engineer: easy to read, with graphics | `python -m flow.handover write designs/<d>`; prose kept between markers |
| `AGENT.md` | the agent: compact, every claim with its record and hash | `python -m flow.handover write designs/<d>` |

The README's sections, in this order (the generator writes them; you add narrative between the
`<!-- prose:NAME -->` and `<!-- /prose:NAME -->` markers, which regeneration keeps):

1. **What it does**: one paragraph a newcomer can read (`summary`), then what it is not (`scope_not`). Prose block
   `what` holds any longer narrative (a glossary, how the path works).
2. **Technical parameters**: part and board, top, tool; clocks (each checked against its XDC period) and resets;
   interfaces with links to their datasheets; parameters and their legal ranges; then a table with resources, timing
   (WNS and WHS at which clock), power (and whether vectorless), latency and throughput. Each of these five has a
   measurement or a gap that says why not ("not applicable" is allowed only with the reason, as a gap). A resource and
   timing chart is drawn from the measurements; a block diagram from the brief 65A viewer where a block design exists
   (`gen/graph.json`), else from `architecture.yaml`. A design with neither has no diagram yet: adding an
   `architecture.yaml` (the agent's format, `flow/architecture.py`) is the way to get one.
3. **How to build, run and reproduce**: exact commands, whether each needs a heavy slot, expected time, the tool
   (Vivado 2026.1), the build ID at handover (`flow/manifest.py show`, brief 54) and the file map.
4. **Verified**: each activity (simulation, formal, seeded faults, CDC, lint, build, board, review) with its result,
   its evidence and, for hardware, its operating conditions; a verification matrix graphic; the gates at handover.
5. **Measured**: each number with its record, the field it was read from, the number of runs and its conditions.
6. **Known gaps and limits**: everything not verified or measured, nulls, failing or waived gates, assumptions, and
   behaviour a user could guess wrong.
7. **Next steps**: what the next engineer should do first; open questions.
8. **History**: dates, briefs, PRs, and the agent run when the agent produced the design (`agent_run`).
   `produced_by: agent` (or `human+agent`) means this repository's agent produced it and needs `agent_run`; a design
   written by an engineer in a planned brief session is `human`.

`AGENT.md` has the same facts without prose: `identity`, `summary`, `state` (stage, gates, Vivado version,
knowledge-bank pin, build ID), `interface`, `files` (with hash prefixes), `commands`, `records` (path and hash prefix,
numbered R1, R2, ...), `evidence`, `measured`, `gaps`, `next_actions`, `open_questions`, `history`. Its size target is
under 2,000 tokens (characters / 4) for a typical design; it is measured and reported, not enforced (the backfilled designs are about 1,700 to 2,700).

### What `doccheck` (through `flow/handover.py`) fails a design for

- missing `handover.yaml`, `README.md` or `AGENT.md`; a schema error; an `id` that is not the directory name;
- placeholder text (TODO, TBD, FIXME, "n/a", "none", "...") or too little text, counted as distinct words that are
  not filler ("n/a n/a n/a" counts as none): summary 12, a scope item 3, a gap 4, a next step 4, an evidence entry 4,
  board conditions 8;
- a missing `sha256` or measurement `value` (run `fill`); a record that is a directory, or the design's own README,
  AGENT.md or handover.yaml; a measurement in resources, timing, power, latency or throughput that is not a number;
- a measurement whose value is not its record's value at `field` (or `match`), while the record's sha256 is unchanged;
  a measurement whose record is not a results file (a README, AGENT.md or handover.yaml cannot vouch for a number);
- a record, file or interface document that does not exist; a clock that disagrees with its source;
- any of resources, timing, power, latency, throughput with neither a measurement nor a gap `about` it;
- an evidence entry that did not pass, or a gate in `state.gates` that did not pass, with no gap `about` its id;
- hardware evidence without conditions; evidence marked `how: ci` that CI does not run;
- a number in a README prose block or in a free-text field of `handover.yaml` (summary, notes, `what`, conditions,
  gaps, next steps, history notes) that is not vouched for: it must occur in a cited record, a listed design file, a
  local interface document, a structured field (parameters, clocks, measured values, history dates, paths, commands),
  the CI workflow (pinned tool versions), or `numbers_allow` with a reason. Free text never vouches for a number.
  HTML tags and entities are removed first; 1000 and 1000.0 are the same number; a word such as 0x1F40 or 1e9 must be
  vouched for whole; hashes and build IDs are identifiers, not numbers;
- `stage: board-verified` without a passing board evidence entry, `stage: signed-off` with a gate that did not pass,
  `produced_by: agent` without `agent_run`, no clock on a design built with Vivado; a clock whose frequency is not the
  period of an XDC `create_clock` on that port (or a value in a results record);
- `README.md`, `AGENT.md` or a `docs/handover/*.svg` that differs from a fresh rendering; a Vivado release other than
  2026.1 named; the retired name for the Designer role.

A record whose sha256 changed since the handover makes its claims **stale**: `doccheck` prints a warning (and fails
under `--strict`). Stale is not wrong: re-run the evidence, then `fill`. Resume (brief 68 part D) reads the same list
through `flow.handover.freshness()`.

Limits of the checks, so nobody over-trusts them (brief 68's adversarial review):
- a gap's text is checked for length and placeholders, not for being true or for covering what its `about` names;
  the checker cannot tell that a list of gaps is complete, or that an evidence entry's `result` matches its record;
- a number passes if it occurs anywhere in a vouching file, so small integers almost always pass;
- numbers written as words, and identifiers that start with a letter (x4999, ADXL362), are not checked;
- a record is trusted by its path: a hand-written file placed under `results/` can vouch for a number (review the
  records a PR adds);
- `activity` labels are not checked against the record (a board run labelled as simulation escapes the conditions
  rule). Review still matters.

## IP library entries (`ip_lib/<entry>/`)

Generated from `ip.yaml` by `flow/net/ipdoc.py` (do not edit the README by hand). Sections: summary and status,
**Parameters**, **Interfaces**, **Registers** (for a register interface; brief 64A2), **Latency and throughput**,
**Evidence** (tests, simulated points, seeded faults), the measured cost (**Variants** or **Cost (out of context)**),
**Boundary and reuse**, **Cost table**, **Known gaps and limits** (the declared limits; whether a board run is
recorded; whether the cost was measured; seeded faults not run or not caught; extra `gaps:` from `ip.yaml`),
**Next steps** (`next_steps:` in `ip.yaml`, required, each with content) and **History** (from `CHANGELOG.md`; at
least one version entry). `doccheck` checks that each README is
current and that each of these sections has content. `ip.yaml` itself is the agent's view of an entry; there is no
separate AGENT.md.

## Results folders (`results/<folder>/`)

A hand-written `README.md` with:

- a **lead paragraph** (at least 15 words) saying what the folder holds, which brief made it and on what;
- **Records** (or **Files**): each file or group of files and what it is;
- **Reproduce**: the commands that regenerate the records, with heavy-slot and hardware needs; when a record cannot be
  regenerated (a board run, a paid agent run) say so;
- **Known gaps and limits**: what the records do not show, nulls, and the conditions they hold under;
- optionally **Measured** (any `## ` heading that starts with "Measured"): every number in it must occur in a file of
  the folder other than README.md (checked as above).

Section headings inside fenced code blocks do not count, and a repeated `## ` heading is an error.

Folders that are pure data read by a tool (for example a `faults.json` that `ipdoc.py` reads) may be listed in
`docs/doccheck_allow.yaml`, each with a reason, instead of having a README; only `results/<folder>` entries with no
`.md` file are accepted.

## Agent-produced designs

The same `handover.yaml` and renderings as any design, with `produced_by: agent` and `agent_run` naming the run record
(`summary.json`). The agent writes them itself at the end of every run (brief 68 part C, `agent/graph/document.py`):

- **Who writes what.** Code drafts the facts from the run's records: target, clocks (from the XDC's `create_clock`), the
  file map, commands, evidence (`summary.json`, `build/verif/verif_gates.json`, `build/verif/mutation.json`,
  `build/<variant>/gates.json`, the bring-up record), measurements as record + field, `state.gates` (one entry per stage:
  pass, fail or not-run) and `state.stage`. The Designer writes only the prose fields (title, summary, scope, resets,
  interfaces, parameter ranges and notes, extra gaps, next steps, open questions); whatever else its reply says, the
  code's facts are kept.
- **Required gaps.** Code adds a gap for every stage that did not pass, every evidence entry that did not pass, every
  requirement with a non-passing row in the traceability table of `verif_gates.json`, and every one of resources,
  timing, power, latency and throughput that was not measured. The Designer cannot remove or reword them; it adds
  its own (behaviour a user could guess wrong, assumptions).
- **Vivado release.** Build numbers (timing, resources, power) are published only from a build made with the release
  the flow pins (2026.1). A recorded build from an earlier release is a `partial` evidence entry with a gap, its numbers
  are withdrawn, and `state.evidence_vivado: earlier` makes a resume rebuild it. The evidence entry says, without numbers, what
  the earlier build reached; re-measuring (`python -m agent resume`) is the first next step, and the DOC gate requires it.
- **What the records must not be contradicted by (68F).** A gap that quotes a gate detail the same run's build records contradict
  (for example "bitstream: did not run" while `build/base/gates.json` shows the bitstream stage ran) must carry the
  reconciliation ("Build records: ..."), which names the build that did fail; `document.contradictions` checks it in the DOC
  gate and in `doccheck`. A stop before the gate (the visit limit, the run budget) is not a failure of that stage: the review
  entry is marked `gated: false` and `gates_last` leaves it out. Verification evidence names the V-stage reached and what did
  not run; it is `pass` only at V3. Coverage numbers, the mutation sample, the ILA probes and the run's provenance (model, loops,
  turns, wall time, tokens, cost) are filled from the records; build time and peak memory only for a build on the pinned release.
- **Where records may live.** For an agent run a measurement's record must be one the flow wrote for that run
  (`flow.handover.in_run_records`): a file of the run directory (the directory of `agent_run.record`) outside the design
  directory, or a file under the design's `build/`, which the path jail denies to every role. The design directory must be
  inside that run directory. A file a role writes (RTL, tests, spec) is never a measurement record.
- **The DOC gate.** `flow.handover.problems` returns nothing, every required gap is present and no field still holds
  the draft's `WRITE` marker. A failing gate goes back to the Designer with the problems, at most three passes. The run is
  signed off (`doc.json` `signed_off`) only when stage 9 passed and the DOC gate passed.
- **In CI.** Agent-produced designs kept as records (`results/**/handover.yaml`, for example `results/68_agent_docs/`)
  are checked like `designs/`, and `doccheck` re-derives their code-owned facts from the run's records
  (`document.recheck`): a hand edit that turns a failed gate into a pass, or drops a required gap, fails.
- **Limit.** The Designer's prose is checked for numbers, placeholders and length, not for truth: a behavioural claim in
  a gap or summary that no record shows is the reviewer's to catch.

## Commands

```bash
python3 flow/doccheck.py --check            # everything; exit 1 on a problem
python3 flow/doccheck.py --coverage         # coverage table
python -m flow.handover write designs/<d>   # fill numbers and hashes from the records, render README, AGENT and SVGs
python -m flow.handover check designs/<d>   # one design
python -m flow.handover fresh designs/<d>   # what changed since the handover (stale records, files, pins, build ID)
python3 flow/net/ipdoc.py                   # regenerate the ip_lib READMEs
```
