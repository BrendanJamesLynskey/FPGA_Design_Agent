# Icarus Verilog

**Kind.** Verification tool: event-driven four-state simulator, used with cocotb.

**Trusted for.** Running the cocotb benches against the RTL and the blind model: the agent's own iterations (the fast
simulator) and the cross-check run of every bench.

**How its output is checked independently.**
- The same bench runs on Verilator; a test must pass on both (`flow/traceability.py --also`, `flow/verif_gates.py --also`).
  A disagreement between the two is a finding (a race in the bench, an X the two-state simulator hides, or a tool
  defect), never averaged away.
- The tests themselves are checked by mutation testing (`flow/mutate.py`): changes to the RTL must make a test fail.

**Known limits.**
- No `bind`, no concurrent assertions, no code coverage: the checkers and coverage run only under Verilator.
- Four-state: X propagation can differ from Verilator's two-state results; reset values matter.
- SystemVerilog support is partial (no classes, limited interfaces); the RTL stays in the subset both simulators read.
