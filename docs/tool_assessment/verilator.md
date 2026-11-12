# Verilator

**Kind.** Verification tool: cycle-based two-state simulator (with cocotb), code-coverage recorder, and lint
(`--lint-only -Wall`).

**Trusted for.** The seeded runs that count for V2 and V3 with the bound checkers (assertions fire as failures),
line, branch, toggle and cover-property coverage (`coverage.dat` per seed), and the Verilator part of the FDA-HDL
coding standard.

**How its output is checked independently.**
- Simulation results are cross-checked on Icarus (the same bench must pass on both).
- Coverage numbers are read by `flow/verif_gates.py` and `flow/traceability.py`; CI tests the readers on a committed
  coverage database (`flow/tests/data/ref_t1_sim`) and on generated ones with known holes (`flow/tests/test_53_trace.py`).
- Assertions are checked for vacuity by cover properties on the same conditions, and by formal cover tasks where a
  formal job exists.
- Lint findings are cross-checked by the design-standards checker (Yosys `proc` for latches, `check` for loops).

**Known limits.**
- Two-state: X and Z are not modelled; a reset bug that leaves X can pass.
- Covergroups are parsed and ignored: functional coverage comes from the Python bench (cocotb-coverage).
- cocotb 2 needs Verilator 5.036 or newer; the apt version (5.020) cannot run the benches.
- A Verilator build is a heavy job on the build PC (memory), so coverage runs take a heavy slot.
