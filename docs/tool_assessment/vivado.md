# AMD Vivado 2026.1

**Kind.** Design tool (synthesis, place and route, bitstream generation, IP generation) and verification tool
(`report_timing_summary`, `check_timing`, `report_drc`, `report_methodology`, `report_cdc`, `report_power`,
`report_utilization`).

**Used for.** Producing the bitstream, and the timing, utilisation, power, DRC, methodology and CDC reports that
`flow/gates.py` reads for the `analysis` proof method (timing closure, resources, no unconstrained path). That the
bitstream's function matches the RTL is checked only through the board tests below, for the behaviours they exercise.

**How its output is checked independently.**
- Function: the design built from the same RTL is tested on the board against the blind golden model
  (`flow/bringup.py`: UART register tests and ILA captures compared cycle by cycle). This is independent of Vivado's
  own analysis. It covers the behaviours the board tests exercise, not every netlist path.
- Reports: the parsers in `flow/gates.py` are tested in CI against real passing and deliberately failing reports
  (`flow/tests/data/bad_*.rpt`), so a parser that misreads a failing report fails a test.
- Timing: static timing is Vivado's own engine; there is no second timing tool here. Closing with margin, the
  methodology and `check_timing` gates (no unconstrained endpoint, no missing clock) and board tests at speed are
  what stand behind it.
- CDC: `report_cdc` is supplemented by a structural check of our own (`flow/cdc_structure.py`) and by synchroniser
  delay injection in simulation (`flow/cdc_inject_run.py`), because `report_cdc` alone passes a bus crossed bit by bit.

**Known limits.**
- The behaviour of the netlist is not simulated in the flow (no post-synthesis or post-route simulation step);
  board tests are the functional check after implementation.
- A run is deterministic only for fixed inputs, options and thread count; the reproducible-build work measures what changes.
- Memory: it needs `general.maxThreads`, `synth.maxThreads` and `chipscope.maxJobs` limits on the build PC
  (`flow/build.tcl`).
- Licence edition: the edition in use limits some debug and IP features; a feature outside it fails the build rather
  than being silently dropped.
