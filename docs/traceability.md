# Traceability: requirements to tests to coverage (brief 53)

The flow already had the parts: `spec.yaml` requirements with ids and proof methods, the V0-V3 verification gates,
coverage, formal and mutation testing, review pages and run records. Brief 53 adds the thread that ties them together
and the checks a reviewer would ask for. What it produces is **DO-254-style evidence**: a record of what was verified
and how. It is not a claim of compliance with DO-254 or any other standard; only an assessor can decide that, for a
whole programme.

## The matrix

`flow/trace.py` builds, for one design, requirement -> design elements -> test or proof -> result -> coverage, and
writes `trace.json` (schema `fpga-design-agent/trace/v1`) and a Markdown table. The agent writes both to
`build/trace/` at stage 2 and at every later review, and the review index (`build/review/review_index.html`) shows the
matrix with its gates.

```
python3 flow/trace.py designs/t1_dimmer_counter --runs build/verif/verilator --also build/verif/icarus \
    --formal build/verif/formal --gates designs/t1_dimmer_counter/build/base/gates.json \
    --hw results/f0b/t1_dimmer_counter_bringup.json --json build/trace/t1.json --md build/trace/t1.md
```

| Column | Where it comes from |
|---|---|
| requirement | `spec.yaml` `requirements: [{id, text, proof}]` |
| design elements | `// req: REQ-01` in an RTL module's header or body; modules a tagged checker is bound into (`bind <module> <checker>`) |
| method | the requirement's `proof` list: simulation, formal, analysis, hardware |
| verification | tests, formal jobs and testplan `proof:` entries that cite the requirement; how each was linked (tag, testplan proof, replan) |
| result | every seed's `results.xml` (and `--also` simulators as a cross-check), SymbiYosys `status` files, `gates.json`, the bring-up JSON |
| supporting | assertions and cover properties that cite it (an assertion alone never discharges `simulation`: it needs a test that drives it) |
| coverage | line, branch and toggle points of the design RTL, planned functional bins, cover properties; every hole with its justification |

## Tags

Every test and property names the requirement ids it verifies, in the source, so the link is checked and cannot drift
from a separate list:

| Artefact | Tag |
|---|---|
| cocotb test | `@req("REQ-01", "REQ-02")` from `flow/req.py` above `@cocotb.test()`, or a `# req: REQ-01, REQ-02` comment directly above |
| SVA (`` `V_SAME/V_NEXT/V_RST/V_COVER``) | `// req: REQ-01` on the macro's line or the comment lines directly above it |
| SymbiYosys job | a `# req: REQ-01` line in the `.sby` file |
| RTL module | `// req: REQ-01` in its header comment (design-element column) |

A test or property that verifies no requirement is marked `robustness: <reason>` (behaviour outside the spec: bad
inputs, stress) or `structural: <reason>` (it exists to reach code or export coverage). `flow/trace_tag.py <design>
[--write]` migrates an existing design: it inserts `# req: ... (from testplan)` tags from what the testplan already
says and lists anything it cannot map.

## Gates

Each gate fails with the ids it is missing.

| Gate | Passes when |
|---|---|
| `requirements_verified` | every requirement has at least one passing verification of each stated method (a method in `--defer` may be pending: its evidence comes from a later stage) |
| `artefacts_cite_requirements` | every test, assertion, cover and formal job cites a known requirement, or is robustness/structural with a reason |
| `coverage_holes_justified` | every unhit point is closed or matches a justification in the testplan waivers or `verif/justifications.yaml` (`item`: a glob with literal brackets, or `re:<regex>`) |
| `waivers_complete` | every waiver, justification, lint waiver and inline `std-waive` comment has an owner, a reason and a date |
| `changed_requirements_reverified` | with `--baseline`: no requirement whose text changed while its evidence did not, unless re-confirmed (owner, reason, date) |

## Requirement quality (the clarify stage)

`agent/graph/spec_schema.py requirement_quality_errors` (part of `validate`, so the clarify gate applies it): one
checkable statement per requirement (no `;`, `, and`, `, but`, `as well as` or second sentence), no vague word
(should, fast, robust, appropriate, support, etc), at least four words. Ids are never reused; when T1's REQ-01, REQ-02
and REQ-08 were split, the new halves took REQ-09, REQ-10 and REQ-11.

## Configuration and change record

`flow/change_record.py` records what the evidence was made from: input file hashes, tool versions, the knowledge-bank
pin and the flow commit. Brief 54 writes a build manifest (`manifest.json`); the record reads it when present
(`build/base/manifest.json`, `build/manifest.json` or `manifest.json` in the design) and needs only its `inputs`,
`tools`, `kb_pin` and `flow` keys; until then it computes the same four groups itself and says so
(`"source": "computed"`). Each requirement carries a hash of its text and proof methods and a hash of its evidence;
`--baseline <old trace.json>` lists added, removed, text-changed and evidence-changed requirements and marks *stale*
any requirement whose text changed while its evidence did not.

## Also in brief 53

- The HDL coding standard FDA-HDL v1.0: [docs/hdl_coding_standard.md](hdl_coding_standard.md), checked by
  `flow/lint_ruleset.py` against `flow/hdl_rules.yaml`.
- Tool-assessment notes, one page per tool: [docs/tool_assessment/](tool_assessment/README.md).
- Results (T1 and two dev-set agent designs, the known-bad runs): [results/53_traceability](../results/53_traceability/README.md).
