# Requirements readiness: build the requirements with the user until they are ready, then build (brief 227)

The agent's process has two stages, and an evaluation reports both:

1. **Requirements building (stage 0).** Iterate with the user until every requirement is unambiguous and the agent is satisfied by a stated measure. Then **freeze** the set.
2. **Build and verify (stages 1 onward).** Read the frozen set. A change after the freeze returns the design to stage 0 and is recorded.

The reason is the project's own measurements: a design that passes its own checks and fails an independent one almost always rests on a requirement that was missing or read two ways
(brief 215: 15 of 35 finished runs; brief 226: the agent's testbench shares the agent's reading of the spec; brief 218: most requirements could not even be stated at the ports).
A benchmark gives no user to ask. The agent has one, so it asks, and a fact that cannot be found is a question and never a default.

Off by default: `agent run ... --readiness on`. Code: [flow/readiness.py](../flow/readiness.py) (every check that needs no model), [agent/graph/readiness.py](../agent/graph/readiness.py)
(the roles, the rounds, the stop rule, the run hook). Tests: [flow/tests/test_227_readiness.py](../flow/tests/test_227_readiness.py),
[agent/tests/test_227_readiness_rounds.py](../agent/tests/test_227_readiness_rounds.py), [tools/tests/test_227_reviewer_testset.py](../tools/tests/test_227_reviewer_testset.py).
Measurements and the pre-registrations: [results/227_requirements_readiness](../results/227_requirements_readiness/README.md).

## What "ready" means

Every check below passes, else stage 0 asks another round of questions. Each is code where it can be and a role where it must be; none is a verdict by a model.

| Check | By | Level |
|---|---|---|
| **Six properties** per requirement: necessary (traces up to a user goal), verifiable (a method and named evidence), achievable (the reviewer's early compliance judgement), traceable (a source), unique (an id is never reused, even after deletion: `build/requirements/req_ids.json`), simple and clear (one property, no vague word) | code, and the reviewer for achievable | the core ones at `standard`; necessary, achievable, traceable and the evidence at `strict` |
| **SHALL, SHOULD or WILL.** SHALL: mandatory and verified. SHOULD: reviewed with the user, promoted to SHALL or recorded as not verified. WILL: descriptive, never verified | code | `strict` (a row with no modal word is read as SHALL at `standard`) |
| **Verification method: Test, Analysis, Inspection or Demonstration**, with the evidence named | code | method at `standard`, evidence at `strict` |
| **Implementation-specific wording** ("use the VDMA and MIG") is a question: a true design constraint (kept, labelled) or a function with measurable values | code | `standard` |
| **Interface contract**: every port with direction, width, clock domain and reset value; every output's latency from a named input event; every handshake rule; number formats | code | direction, width, clock, latency form at `standard`; reset value, latency and number format at `strict` |
| **Consistency**: the same quantity given two values, or the same wording under two ids | code | `standard` |
| **Two fresh readers agree** on a probe set; no probe is left undecided | two model calls, compared by code | `standard` and `strict` |
| **Every default confirmed**: a default the agent chose that became a requirement is *derived* and must be validated by the user; an unconfirmed one is listed in the handover at `standard` and blocks at `strict` | code | see left |
| **Three layers** per timing, protocol, reset and functional requirement: L1 EARS-style English the user confirms; L2 FRETish-shaped fields (scope, condition, component, timing {kind, n, clock, from}, response); L3 a generated property, a named check or a stated reason it is simulation only | code (completeness), `flow/sva_req.py` (the property), the third reader (L2 from L1) | `strict` |
| **Show-back packet** for each such requirement: the text regenerated from L2, a timing diagram from a cover trace, worked numbers and one "must never happen" example | code | `strict` |
| **Validated by the user** is a separate field from verified | code | `strict` |

## The measure "satisfactory to the agent"

Two readers, each a separate fresh call that sees **only the requirements' English and the interface table** (not the request, not the reviewer's findings, not each other), predict
the behaviour for the same **probe set**: edge cases, reset, back-pressure, overflow, simultaneous events, unmapped accesses, a reset in the middle of an operation, an invalid input.
A probe is a concrete scenario with a constrained answer (yes or no, a number, or one of listed choices) so that code can compare. `unspecified` is always an allowed answer, and it is not agreement.

- different values (including a value and `unspecified`): an **ambiguity**, which becomes a question;
- every reader says `unspecified`: a **gap**, which becomes a question;
- the gate passes only when there is no disagreement, no gap and no open question.

Each round records the probe set and its categories, both readers' answers and the agreement rate (`build/requirements/readiness.json`). At `strict` a **third reader**, a different
model, writes L2 from L1 alone; a difference from the first L2 (timing compared exactly, the prose fields by the words they share) is an ambiguity too.

## The roles

- **Requirements reviewer** (purpose `reqreview`): what an experienced FPGA engineer asks before building, by topic: clocks and sources, crossings, reset, I/O standards and pins, throughput and
  latency (and the two events it is measured between), the interface contract, number formats, errors and back-pressure, defaults, names and files, budget and timing risk, test strategy and what the
  board can measure. The checklist is the knowledge-bank skill `procedures/requirements-review/pre-build-review` (KB PR 108), cited by id and hash in every record; a short public topic list is
  the fallback. A finding is **blocking** only when a builder would have to guess a fact that a port, a file, a report or a test can observe. At `strict` it also gives the early compliance
  judgement per requirement (compliant, partial, non-compliant, to be confirmed), from analysis and not evidence; each partial, non-compliant or tbc row becomes a risk with an owner and a mitigation
  (prototype, change the implementation, or challenge the requirement and its margins). After the build the judgement is compared with the verified outcome (`flow.readiness.calibration`).
- **Probe writer** and **amender** (the same model and purpose): the probes above; the change an answer makes to a row. Code checks the amender: an id is never reused, only an answered row changes.
- **Readers** (`reqreader`, two calls) and **third reader** (`reqreader3`, a different model: readers of one model share misreadings).

None of them sees the RTL.

## Rounds, the stop rule and the files

Each round: mechanical checks, the reviewer, the probes and the two readers (and the third reader), then the questions go to the **oracle** (`--interview oracle`: it answers only with a
verbatim quote from the hidden spec) or to a **person**, then the amender applies the answers. Limits are stated and recorded: `--readiness-rounds` (default 4) and `--readiness-calls` (default 60);
at a limit, or when nobody can answer, the run stops with `REQUIREMENTS_NEEDED.md` and **exit status 3**. It never guesses.

| File | What |
|---|---|
| `build/requirements/readiness.json` | every round: mechanical problems, review findings, probes, both readers' answers, agreement, questions with their answers and who gave them, amendments, calls |
| `REQUIREMENTS_READINESS.md` | the readable form: rounds, agreement per round, the freeze |
| `REQUIREMENTS_NEEDED.md` | the open questions of a stopped run, with ids Q1, Q2, ... |
| `requirements_answers.yaml` | **your** answers: `answers: {Q1: "...", Q2: {answer: "...", who: "you"}}`; the next run applies them first |
| `requirements_confirmations.yaml` | your confirmations (`confirmed: {REQ-01: {who, when, shown: <packet hash>}}`); a confirmation of an earlier version of the packet is stale |
| `build/requirements/frozen.json` | the frozen set (hash, ids, version) and every return to stage 0 |
| `build/requirements/req_ids.json` | the id ledger |

## The verification cross-reference matrix

`flow.readiness.vcrm_markdown` writes the requirements as the document an FPGA team already uses: id, SHALL, SHOULD or WILL, text, method, evidence named, validated by the user, verified, the early
compliance judgement, and which check was independent of the RTL's author. Independence is stated per requirement: the checks written by a different role (the blind golden model, the spec-only
bench, a property written without the RTL and read back by a different model) and the hardware; the agent's own testbench is never counted as independent.

## Two scores

A run reports **requirements quality** (rounds, questions, reader agreement per round, and on a benchmark with hidden tests how many of the facts those tests check were covered by a frozen
requirement) and **build and verify given the frozen requirements** (the agent's own checks against the independent ones, and their agreement). A failure is attributed to **one stage**: a requirement
missing or wrong (stage 0), or the design not meeting a correct requirement (stage 2). A fact that is nowhere in the problem or the oracle's source is **benchmark-limited**, counted apart, never as an
agent failure (`flow.readiness.attribute_failure`, `fact_coverage`, `two_scores`).

## What a user could get wrong

- **Confirming a default without reading it.** A default the agent chose that becomes a requirement is marked *derived*. It needs your confirmation from its show-back packet; the report flags an
  all-"OK" confirmation of eight or more requirements in one batch with no edit and no question, because that is how a wrong requirement gets through. A passing test of a guess you did not read
  shows the design matches the guess.
- **A probe set that is too small.** Two readers agreeing on twelve probes have not shown there is no ambiguity, only none among those twelve. The set's size and categories are in the record; a design
  with several interfaces needs more. Agreement can also be a shared misreading, since the readers are one model; that is why validation by you is a separate field and not inferred.
- **"Within n" against "after n".** *Within 2 cycles* means some time in cycles 1 to 2; *after 2 cycles* means exactly at cycle 2. The structured layer requires the kind, the clock and the event the count
  starts from; the text regenerated from it is what you read. A tick is one cycle of a stated clock, never "a cycle" in general.
- **Leaving the scope out.** A requirement with no scope holds always; if you meant "after reset" or "while busy", say so (`always` is a valid scope but must be written).
- **A vacuous property.** A property whose trigger can never happen is proved vacuously and shows green. The gate asks about it (a saturation requirement on a counter that cannot reach the limit is the
  example); it is never counted as evidence.
- **A requirement that names an implementation** ("use the VDMA"). Say whether it is a true constraint; otherwise say what the function must achieve (resolution, rate, latency, bandwidth).
- **Trusting the early compliance judgement.** It is analysis, not evidence, from one model; it is compared with the verified outcome after the build and the agreement rate is reported.
- **Answering the oracle's silence.** `not specified` leaves the question open; the agent does not take its default under this gate.
- **A requirement stated at registers.** The formal step can state only what is on the ports (brief 218: 60 of 76 candidate rows were unusable, 38 because the requirement gave no register address or bit
  encoding). Give addresses and bit encodings, or accept that the row is checked by simulation only.
- **Changing the requirements after the freeze.** It returns the design to stage 0 and is recorded; earlier evidence for a changed row is stale.

## Sources

EARS (Mavin et al., 2009) and FRETish (NASA FRET; the grammar is re-implemented here, the tool is not bundled), research/228 (the three layers, the show-back packet, the mechanical checks),
INCOSE-style requirement quality properties, DO-254 practice (the upward trace, the verification cross-reference matrix), and the MicroZed Chronicles article "Getting the Foundations Right"
(Adiuvo Engineering, 2026-11-26), cited and not copied.
