# Traceability: requirements to tests to coverage

Traceability answers one question for every requirement in a design: which test or proof shows it is met, did that
evidence pass, and what did it cover? `flow/traceability.py` builds that table (the *matrix*) from `spec.yaml`, tags in
the tests, and the run records, and runs a set of gates that name any requirement, test or coverage hole left without
evidence.

The output is DO-254-style evidence. DO-254 (in Europe ED-80) is the design-assurance guidance for airborne electronic
hardware; much of its verification evidence is exactly this kind of table. What this flow produces is a record of what
was verified and how. It is **not** a claim of compliance with DO-254 or any other standard: only an assessor can
decide that, for a whole programme.

## Terms

| Term | Meaning here |
|---|---|
| requirement | one checkable statement in `spec.yaml` `requirements: [{id, text, proof}]`, with the methods that prove it |
| proof method | `simulation` (a cocotb test against the reference model), `formal` (a SymbiYosys job), `analysis` (a flow gate on the Vivado reports), `hardware` (a step of the board bring-up) |
| blind golden model, V0-V3, mutation testing | see [verification.md](verification.md) |
| tag | a comment or decorator in the source naming the requirement ids a test or property verifies |
| artefact | anything that can carry a tag: a cocotb test, an assertion or cover property (SVA), a formal job |
| coverage hole | a line, branch or signal bit (toggle) never exercised, a functional-coverage bin never hit, or a cover property never reached |
| justification | a written reason, with an owner and a date, that a hole is acceptable |
| baseline | an earlier `trace.json` that a new one is compared with |

## The matrix

```
python3 flow/traceability.py designs/t1_dimmer_counter --runs build/verif/verilator --also build/verif/icarus \
    --formal build/verif/formal --gates designs/t1_dimmer_counter/build/base/gates.json \
    --hw results/f0b_2026_1/t1_dimmer_counter_bringup.json --json build/trace/t1.json --md build/trace/t1.md
```

It writes `trace.json` (schema `fpga-design-agent/trace/v1`) and a Markdown table. The agent writes both to
`build/trace/` at stage 2 and at every later review, and the review index (`build/review/review_index.html`) shows the
matrix with its gates. In the agent the matrix is **recorded, not a stage-exit gate**: a run can finish with failing
traceability gates, and the index shows them (whether they should stop a run is an open decision).

| Column | Where it comes from |
|---|---|
| requirement | `spec.yaml` |
| design elements | `// req: REQ-01` in an RTL module's header or body; modules a tagged checker is bound into (`bind <module> <checker>`) |
| method | the requirement's `proof` list |
| verification | tests, formal jobs and testplan `proof:` entries that cite the requirement, and how each is linked (tag, testplan proof, re-plan) |
| result | every seed's `results.xml` (with `--also` simulators as a cross-check), SymbiYosys `status` files, `gates.json`, the bring-up JSON |
| supporting | assertions and cover properties that cite it; an assertion alone never proves `simulation`, which needs a test that drives the design |
| coverage | line, branch and toggle points of the design RTL, planned functional bins, cover properties; every hole with its justification |

A method passes when at least one cited verification passes and none fails: one failing requirements-based test fails
the method and the requirement, whatever the others did.

## Tags

The link from a test to a requirement lives in the test's own source, so it is checked every run and cannot drift
from a separate list.

| Artefact | Tag |
|---|---|
| cocotb test | `@req("REQ-01", "REQ-02")` from `flow/req.py`, **above** `@cocotb.test()`, or a `# req: REQ-01, REQ-02` comment directly above |
| SVA: `` `V_SAME/V_NEXT/V_RST/V_COVER`` macros and raw `assert/cover/assume property` | `// req: REQ-01` on its first line or the comment lines directly above it |
| SymbiYosys job | a `# req: REQ-01` line in the `.sby` file |
| RTL module | `// req: REQ-01` in its header comment (design-element column) |

A comment line holding only ids (`// REQ-01`) also counts; prose that mentions an id does not. A test or property
that verifies no requirement is marked `robustness: <reason>` (behaviour outside the spec: bad inputs, stress) or
`structural: <reason>` (it exists to reach code or export coverage). `python3 flow/trace_tag.py <design> [--write]`
migrates an existing design: it inserts `# req: ... (from testplan)` tags from what the testplan already says and
lists anything it cannot map.

## Gates

Each gate fails with the ids it is missing.

| Gate | Passes when |
|---|---|
| `requirements_verified` | every requirement has a passing, and no failing, verification of each stated method (a method listed in `--defer` may be pending: its evidence comes from a later stage) |
| `artefacts_cite_requirements` | the bench has tests, every bench module could be read, and every test, assertion, cover and formal job cites a known requirement or is marked robustness/structural with a reason |
| `coverage_holes_justified` | every hole is closed or matches a justification in the testplan waivers or `verif/justifications.yaml` (`item` is a glob in which square brackets match literally, or `re:<regex>`) |
| `waivers_complete` | every waiver, justification, lint waiver and inline `std-waive` comment has an owner, a reason and a date |
| `changed_requirements_reverified` | with `--baseline`: no requirement whose text changed while its evidence did not, unless re-confirmed (`reconfirmed:` in `verif/justifications.yaml`, with owner, reason and date) |

## Requirement quality (the clarify stage)

The clarify gate checks each requirement of the agent's `spec.yaml` with `requirement_quality_errors`
(`agent/graph/spec_schema.py`). It sits beside `validate`, not inside it, because `validate` also checks the
benchmark's frozen hidden specs. A requirement is rejected when it:

- joins two statements: a semicolon, a second sentence (a trailing "See ..." reference is allowed), "as well as",
  "and also", or "and"/"but" followed by a clause with its own verb (the last item of a list, "R, G, and B are driven",
  is allowed);
- uses a word in the `VAGUE` list of `spec_schema.py` (for example should, fast, robust, appropriate, support,
  approximately; "may not" is allowed);
- has fewer than three words.

It is a word-and-punctuation check: it catches the common forms, not every bad requirement. Ids are never reused:
when T1's REQ-01, REQ-02 and REQ-08 were split, the new halves took REQ-09, REQ-10 and REQ-11.

## Configuration and change record

`flow/change_record.py` records what the evidence was made from: input file hashes, tool versions, the knowledge-bank
pin and the flow commit.

- **Source.** A build manifest (`manifest.json` in `build/base/`, `build/` or the design folder, written by the
  reproducible-build work) is read when present; only its `inputs`, `tools`, `kb_pin` and `flow` keys are used. Without
  one, the same four groups are computed and the record says `"source": "computed"`.
- **Fingerprints.** Each requirement carries a hash of its text and proof methods, and a hash of its evidence: the
  source of every artefact that cites it plus their results. Any edit to a citing test, a comment included, counts as
  changed evidence.
- **Baseline diff.** `--baseline <old trace.json>` lists added, removed, text-changed and evidence-changed
  requirements, and marks *stale* any requirement whose text changed while its evidence did not. In the agent the
  baseline is fixed (the last record with nothing stale), so a stale requirement stays stale on every later record
  until its evidence changes or a person re-confirms it.

## Using it on a new design

1. Write one checkable statement per requirement, each with its proof methods.
2. Tag every test, property and formal job with the ids it verifies (`flow/trace_tag.py --write` migrates an existing
   testplan's mapping).
3. Run `flow/traceability.py` and fix what each gate names: a missing test, an untagged check, an unjustified hole.

Worked example: the T1 matrix, [results/53_traceability/t1_dimmer_counter_trace.md](../results/53_traceability/t1_dimmer_counter_trace.md).
The HDL coding standard that goes with it is [hdl_coding_standard.md](hdl_coding_standard.md); the tool-assessment
notes are in [tool_assessment/](tool_assessment/README.md).
