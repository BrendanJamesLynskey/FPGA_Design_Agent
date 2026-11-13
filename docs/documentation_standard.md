# Documentation standard: for the next engineer (brief 68)

The owner, 2026-11-13: "Every example/showcase project should have some kind of documentation, with a clear
description of what it does, the technical parameters, what's been measured/verified, known gaps etc. Anything the agent
produces should be as thorough as a human engineer would be expected to be. The idea is to enable the 'next person' to
pick up the work."

This page says what each kind of folder must document, and how `flow/doccheck.py` checks it. CI runs
`python3 flow/doccheck.py --check` on every push and pull request.

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
   measurement or a gap that says why not. A resource and timing chart is drawn from the measurements; a block diagram
   from the brief 65A viewer where a block design exists (`gen/graph.json`), else from `architecture.yaml`.
3. **How to build, run and reproduce**: exact commands, whether each needs a heavy slot, expected time, the tool
   (Vivado 2026.1), the build ID at handover (`flow/manifest.py show`, brief 54) and the file map.
4. **Verified**: each activity (simulation, formal, seeded faults, CDC, lint, build, board, review) with its result,
   its evidence and, for hardware, its operating conditions; a verification matrix graphic; the gates at handover.
5. **Measured**: each number with its record, the field it was read from, the number of runs and its conditions.
6. **Known gaps and limits**: everything not verified or measured, nulls, failing or waived gates, assumptions, and
   behaviour a user could guess wrong.
7. **Next steps**: what the next engineer should do first; open questions.
8. **History**: dates, briefs, PRs, and the agent run when the agent produced the design (`agent_run`).

`AGENT.md` has the same facts without prose: `identity`, `summary`, `state` (stage, gates, Vivado version,
knowledge-bank pin, build ID), `interface`, `files` (with hash prefixes), `commands`, `records` (path and hash prefix,
numbered R1, R2, ...), `evidence`, `measured`, `gaps`, `next_actions`, `open_questions`, `history`. Its size target is
under 2,000 tokens (characters / 4) for a typical design.

### What `doccheck` (through `flow/handover.py`) fails a design for

- missing `handover.yaml`, `README.md` or `AGENT.md`; a schema error; an `id` that is not the directory name;
- placeholder text (TODO, TBD, FIXME, "n/a", "none", "...") or too-short text in the summary (20 words), a gap (5),
  a next step (4) or an evidence entry (4);
- a measurement whose value is not its record's value at `field` (or `match`), while the record's sha256 is unchanged;
  a measurement whose record is not a results file (a README, AGENT.md or handover.yaml cannot vouch for a number);
- a record, file or interface document that does not exist; a clock that disagrees with its source;
- any of resources, timing, power, latency, throughput with neither a measurement nor a gap `about` it;
- an evidence entry that did not pass, or a gate in `state.gates` that did not pass, with no gap `about` its id;
- hardware evidence without conditions; evidence marked `how: ci` that CI does not run;
- a number in a README prose block that is not in `handover.yaml`, in a cited record, or in `numbers_allow` (each
  with a reason);
- `README.md`, `AGENT.md` or a `docs/handover/*.svg` that differs from a fresh rendering; a Vivado release other than
  2026.1 named; the retired role name "Implementer".

A record whose sha256 changed since the handover makes its claims **stale**: `doccheck` prints a warning (and fails
under `--strict`). Stale is not wrong: re-run the evidence, then `fill`. Resume (brief 68 part D) reads the same list
through `flow.handover.freshness()`.

Limits of the checks, so nobody over-trusts them: a gap's text is checked for length and placeholders, not for being
true; a prose number passes if it occurs anywhere in a cited record, so small integers almost always pass; the
checker cannot tell that a list of gaps is complete. Review still matters.

## IP library entries (`ip_lib/<entry>/`)

Generated from `ip.yaml` by `flow/net/ipdoc.py` (do not edit the README by hand). Sections: summary and status,
**Parameters**, **Interfaces**, **Registers** (for a register interface; brief 64A2), **Latency and throughput**,
**Evidence** (tests, simulated points, seeded faults), the measured cost (**Variants** or **Cost (out of context)**),
**Boundary and reuse**, **Cost table**, **Known gaps and limits** (the declared limits; whether a board run is
recorded; whether the cost was measured; seeded faults not run; extra `gaps:` from `ip.yaml`), **Next steps**
(`next_steps:` in `ip.yaml`, required) and **History** (from `CHANGELOG.md`). `doccheck` checks that each README is
current and that each of these sections has content. `ip.yaml` itself is the agent's view of an entry; there is no
separate AGENT.md.

## Results folders (`results/<folder>/`)

A hand-written `README.md` with:

- a **lead paragraph** (at least 15 words) saying what the folder holds, which brief made it and on what;
- **Records** (or **Files**): each file or group of files and what it is;
- **Reproduce**: the commands that regenerate the records, with heavy-slot and hardware needs; when a record cannot be
  regenerated (a board run, a paid agent run) say so;
- **Known gaps and limits**: what the records do not show, nulls, and the conditions they hold under;
- optionally **Measured**: every number in that section must occur in a file of the folder (checked).

Folders that are pure data read by a tool (for example a `faults.json` that `ipdoc.py` reads) may be listed in
`docs/doccheck_allow.yaml`, each with a reason, instead of having a README.

## Agent-produced designs

The same `handover.yaml` and renderings as any design, with `produced_by: agent` and `agent_run` naming the run record.
Brief 68 part C adds a sign-off step: the Designer role writes `handover.yaml` (prose and structure), code fills every
number from the run's records (spec, `gates.json`, test and fault results, closure and traceability records), and a
`DOC` gate runs this checker. Every failed, waived or skipped gate and every requirement without passing evidence must
appear under Known gaps.

## Commands

```bash
python3 flow/doccheck.py --check            # everything; exit 1 on a problem
python3 flow/doccheck.py --coverage         # coverage table
python -m flow.handover write designs/<d>   # fill numbers and hashes from the records, render README, AGENT and SVGs
python -m flow.handover check designs/<d>   # one design
python -m flow.handover fresh designs/<d>   # what changed since the handover (stale records, files, pins, build ID)
python3 flow/net/ipdoc.py                   # regenerate the ip_lib READMEs
```
