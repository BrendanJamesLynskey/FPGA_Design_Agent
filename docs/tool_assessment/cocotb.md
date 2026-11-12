# cocotb and cocotb-coverage

**Kind.** Verification tool: the Python test framework the benches are written in, and the functional-coverage library.

**Used for.** Driving the RTL, comparing every output with the blind golden model, reporting each test's pass or
fail per seed (`results.xml`), and recording functional-coverage bins (`coverage*.yml`).

**How its output is checked independently.**
- The gates refuse the cocotb outcomes that read as passes without checking anything: `expect_fail`, `expect_error`
  and `skip` are failures in V2 (`flow/verif_gates.py`), and a skipped test is not a pass.
- Each test's result is read from every seed and every simulator; a test missing from a seed counts as failed.
- Mutation testing checks that the tests can fail.
- The agent's own bench never counts as a pass on its own: hidden tests written by a separate author against an
  independent model decide.

**Known limits.**
- A test is only as good as its comparisons: a bench that compares too little passes a wrong design (mutation
  testing measures this).
- Functional coverage counts what the bench sampled, not what the design did.
