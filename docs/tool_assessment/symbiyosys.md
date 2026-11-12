# SymbiYosys (Yosys, smtbmc, z3)

**Kind.** Verification tool: bounded model checking and cover of SVA properties on small blocks.

**Trusted for.** The `formal` proof method: a job in `verif/formal/*.sby` whose `bmc` and `cover` tasks both PASS
(`flow/formal.sh`).

**How its output is checked independently.**
- Every bounded proof is paired with a cover task on the same checker, so a property that can never trigger (a
  vacuous pass) shows as an unreached cover.
- The same checkers are bound in the Verilator simulation, so a property that fails in simulation and passes in
  formal (or the reverse) is visible.
- The flow never claims a proof when sby did not run: a missing tool is reported and the method must be re-planned
  in the testplan with a reason (`replan:`).

**Known limits.**
- Bounded depth only: a proof holds for the depth given (24 or 40 cycles in T1's jobs). Time constants are shrunk for
  formal (small `CYCLES`), so the proof is of the structure at that parameter, not of the board value.
- Read with `read_verilog -formal -sv`: the SystemVerilog Yosys accepts is a subset.
- Only small control blocks are in reach; datapaths and the whole design are not proved.
