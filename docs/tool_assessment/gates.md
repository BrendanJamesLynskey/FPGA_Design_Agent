# Our gates and checkers

**Kind.** Verification tools: `flow/gates.py` (Vivado reports), `flow/verif_gates.py` (V0-V3 and sign-off),
`flow/trace.py` (traceability), `flow/standards_check.py` (design standards), `flow/lint_ruleset.py` (FDA-HDL),
`flow/cdc_structure.py`, `flow/fsm_coverage.py`, `flow/exceptions_check.py`. They decide pass or fail, so an error in
one hides a fault.

**Trusted for.** Turning tool outputs into named pass or fail checks with a plain reason on failure.

**How their output is checked independently.**
- **Known-bad fixtures.** Each parser and gate is tested in CI on inputs that must fail, with the failing ids named:
  real failing Vivado reports (`flow/tests/data/bad_*.rpt`), broken testplans and specs, CDC and FSM mutants, timing
  exception fixtures, and for brief 53 a deleted test, an untagged test, an unjustified coverage hole, a waiver
  without owner or date and a changed requirement (`flow/tests/test_53_trace.py`). A gate that only ever saw passing
  inputs is untested.
- **Real known-bad runs.** Brief 53 also ran the three known-bad cases on T1 itself with real simulations
  (`results/53_traceability/known_bad/`).
- **Floors the agent cannot lower** (`flow/verif_floors.yaml`), and a failed check that cannot be evaluated says so
  instead of passing.

**Known limits.**
- The gates read what the tools report; a tool defect that produces a plausible passing report passes the gate
  (see the other pages for the independent checks).
- The traceability tags are read statically: a tag says what a test is meant to verify; whether it really checks it is
  what the comparisons, the mutation score and review decide.
- The requirement-quality check is a word and punctuation check: it rejects common compound and vague forms, not every
  bad requirement.
