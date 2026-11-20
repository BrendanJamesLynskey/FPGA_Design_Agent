# 124 Lean experiment: records

Run records of brief 124's one experiment: a model (Claude Sonnet 5.5, through the 108 table's `claude_code` endpoint) writes the Lean 4 proofs
of the human-approved statements in `formal/lean/Cksum/Spec.lean`, with the Lean checker's errors fed back after each attempt. The statements
are about the checksum equations of brief 119's TCP fast path (`tcp_fast.sv`). The project, its trust tiers and its gaps are described in
[formal/lean/README.md](../../formal/lean/README.md); the assessment is [docs/lean_assessment.md](../../docs/lean_assessment.md).

## Records

| File | What it is |
|---|---|
| `run1/` | the first attempt: `spec_handed_to_model.lean` (the file with every proof `sorry`), `round1_answer.lean` and `round1_build.log` (the model's first try and the checker's 27 errors), `round2_answer.lean` (rejected by a bug in `tools/statements.py`, fixed afterwards), `claude_code_calls.jsonl` (wall seconds, tokens and the plan's cost estimate per call). Stopped by its pid after round 2; `run1_stdout.log.txt` is its output |
| `run2/` | the same loop with the fixed statement check, seeded with run 1's round 1 as its round 1: rounds 2 to 5, `result.json` (per round model seconds, build seconds, error counts), `proved_Spec.lean` (the file that builds, the same as `Cksum/Spec.lean` apart from comments (the `req:` tags and corrected RTL line numbers were added afterwards)), `round*_build.log` |
| `run2_proved_with_bv_decide.lean` | a copy of run 2's proved file, the starting point of run 3 |
| `run3_kernel_only/` | a second loop, asking for the same theorems without `bv_decide` (kernel-checked tactics only); six rounds, none built (see Known gaps and limits) |
| `lean_evidence.json` | the evidence record computed from `lake build` and `#print axioms` by `formal/lean/tools/lean_evidence.py`: status per theorem (the proposed `formal_lean` evidence) |

First try against after the checker's feedback (Claude Sonnet 5.5, effort medium, no tools; counts of the word "error" in the `lake build` log):

| Round | Model seconds | Errors | Outcome |
|---|---|---|---|
| 1 (first try) | 815.7 | 27 | did not build (missing `import Std.Tactic.BVDecide`, tactic syntax errors, a wrong field name) |
| 2 | 57.5 | 4 | did not build |
| 3 | 61.8 | 7 | did not build |
| 4 | 50.6 | 2 | did not build |
| 5 | 59.9 | 0 | built, no `sorry`; statements unchanged by `tools/statements.py` |

Round 1 is run 1's; rounds 2 to 5 are run 2's (run 2's own wall time was 255.2 s, including the builds of about 6 s each). Model time in all: 1,045.5 s; the plan's cost
estimate per call is in each `claude_code_calls.jsonl`. The model's first try did not compile; it needed four rounds of checker feedback; the human-approved statements never changed.

## Reproduce

Install Lean 4.36.0 with elan into the home directory, build the project, regenerate the evidence record, and optionally rerun the model loop (it needs the Claude Code plan token and takes minutes):

```
curl -sSfL https://elan.lean-lang.org/elan-init.sh | sh -s -- -y --no-modify-path --default-toolchain stable   # Lean 4.36.0 into ~/.elan
export PATH=$HOME/.elan/bin:$PATH
cd formal/lean && lake build                                    # about 6 s plus about 11 s for the cross-check
python3 -I tools/lean_evidence.py                               # rewrites results/124_lean/lean_evidence.json
python3 -I tools/statements.py ../../results/124_lean/run1/spec_handed_to_model.lean Cksum/Spec.lean
python3 tools/llm_prove.py --out /tmp/try --rounds 8            # the model loop (needs the Claude Code plan token; takes minutes)
```

## Known gaps and limits

- One proof task, one model, one run of the loop (run 1's round 1 plus run 2's rounds 2 to 5): the table shows what happened once, not a rate. Model time varies a lot: the first attempt took 13.6 minutes of model time, the later rounds about one minute each.
- The error counts are crude (the number of "error" words in the build log); one mistake can print several.
- Round 2 of run 1 was wasted by a bug in the statement check (a helper `macro` made the `namespace` block compare unequal); the model was told the wrong reason. The check was fixed and run 2 continued from run 1's round 1. Run 1's round 1 is therefore the only unaffected first try.
- Run 3 shows the model did not manage kernel-only proofs of the three bit-vector lemmas in six rounds. The even-numbered rounds were rejected by the ban on `bv_decide` before building, so the checker's feedback in those rounds was the rule message, not Lean's errors.
- The human role (writing and approving the statements) was played by the brief's executor, not by the owner; the statements have not been approved by the owner.
