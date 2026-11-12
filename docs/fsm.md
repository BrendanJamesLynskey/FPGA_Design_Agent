# FSMs as an area of expertise (brief 24)

What the repo has for state machines beyond the code in `designs/`: a reference controller measured in variants, an FSM coverage
check for the V2 stage, two agent drills, and the knowledge-bank skills and course lesson that go with them. The synthesis and routed
numbers of the controller variants on Vivado 2026.1 are in [results/24_fsm_2026_1](../results/24_fsm_2026_1/README.md)
(brief 49); this page says how to reproduce them and use the check. Brief 24's other Vivado measurements (the I/O study on real
pins and the runs on other families) were made on an earlier release and are not quoted here.

## The reference controller

`flow/tests/fixtures/fsm_discipline/rtl/`: a bus sequencer with two handshakes (command in, response out), a bus request/grant, four
beats, an eight-clock acknowledge window with retry and timeout, and a three-clock cool-down. 11 states (IDLE, LOAD, REQ, ADDR, DATA,
TURN, WACK, RETRY, RESP, ERR, COOL), 13 transitions.

| File | What |
|---|---|
| `ctl_sep.sv` | the FSM with a separate 4-bit counter it loads and runs (parameters: output style `OUT`, input style `IN`, reset style `RST`, registered zero flag `ZREG`, clock enable `USE_CE`) |
| `ctl_mono.sv` | the same behaviour with the counter folded into 23 states |
| `fsm_front.sv` | the reset styles, the input stage, the registered-output primitive |
| `top_ratio.sv`, `top_cdc.sv`, `top_io.sv` | the one-in-N enable, an input from another clock, the controller on real pins |
| `tb_equiv.sv`, `tb_reset_ce.sv`, `tb_ctl.sv` + `bench/ctl_cocotb.py` | equivalence and latency, reset with an enable, the cocotb bench |
| `formal/ctl.sby` | SymbiYosys jobs: bounded, cover, k-induction at each depth, separated and monolithic |
| `variants.txt`, `run_all.sh`, `measure.tcl`, `measure_io.tcl`, `make_table.py` | the Vivado runs and the tables |

Output styles: 0 combinational Moore (and Mealy `cmd_ack`), 1 registered decode of the state (one clock late), 2 lookahead (registered
decode of the next state, no added latency). Reset styles: 0 asynchronous, 1 synchronous over the enable, 2 none, 3 asynchronous assert
with synchronous release, 4 synchronous reset gated by the enable.

```
flow/tests/fixtures/fsm_discipline/run_all.sh <dir> 0 [variant ...]      # Vivado 2026.1 (flow/version_pin.py), out of context, ~40 s a variant (heavy slot)
python3 flow/tests/fixtures/fsm_discipline/make_table.py <dir> <out.md> <out.json>
```

## The FSM coverage check

No free simulator reports FSM coverage (measured on Icarus, Verilator and the xsim of an earlier Vivado release: `results/24_fsm/simprobe/survey.txt`). `flow/fsm_coverage.py` reads the value
changes of the state register and compares them with the state table `<design>/verif/fsm.yaml`:

```
FDA_FSM_TRACE=build/fsm pytest designs/b2_tmp_adt7420/tests          # cocotb_run writes build/fsm/<run>.fsmtrace for each register in fsm.yaml
python -m flow.fsm_coverage designs/b2_tmp_adt7420 --trace build/fsm/b2_tmp_adt7420.fsmtrace --json build/fsm/cov.json
python flow/verif_gates.py <design> ... --fsm-coverage build/fsm/cov.json    # adds the V2 check fsm_state_transition_coverage (off unless given)
```

It fails on a state never visited, a legal transition never taken, a transition taken that the table does not list (a change into
`reset_state` is allowed) and a waiver without a reason. Illegal transitions are for formal. VCDs from other simulators work too.
`flow/fsm_cov_cocotb.py` is the in-bench route (cocotb-coverage points, read by the V3 `bins:` gate). Both are evidence files: no
agent tool was added, so `agent/tests/test_08f_golden_requests.py` is unchanged.

Measured on two repo designs: the existing tests reach every state and legal transition of the I2C pointer-read engine (7/7, 11/11)
and the QSPI flash reader (8/8, 11/11). Removing one test makes the check fail by name (`flow/tests/test_24_fsm_rtl.py`).

## Drills

[benchmark/drills/d24_registered_outputs](../benchmark/drills/d24_registered_outputs/spec.md) (pins must come straight from flip-flops;
one clock of lag allowed) and [d24_no_extra_latency](../benchmark/drills/d24_no_extra_latency/spec.md) (no output later than the state
table, `cmd_ack` in the clock of the command). Hidden bench: cycle-exact against a model under random open-loop inputs, plus the
counters; the reference's run also reaches every state and legal transition. Ten functional mutants each (all killed).
`benchmark/drills/lib/grade_fsm.py` adds the pin check from the routed checkpoint and records the choice: registered (flop-driven,
lag 1), lookahead (flop-driven, lag 0) or combinational (LUT-driven, lag 0). Outside every split, like the brief 20 drills.
