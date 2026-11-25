# Open synthesis into Vivado, and formal equivalence for every non-standard flow (brief 101)

Two tools and one rule. `flow/oss_synth.py` maps a block with Yosys and ABC for delay and writes an EDIF that Vivado
implements. `flow/eqy_gate.py` proves a netlist equivalent to its RTL with `eqy`. The rule: any flow that changes logic
outside Vivado's own synthesis (Yosys, direct primitives, RapidWright, hand edits) passes `eqy` before its result is
reported. Measured results: [results/b101](../results/b101/README.md). The comparison method and its limits are below;
the report is `reports/101_oss_synth_eqy_report.md` in the planner's folder.

## What runs where

| Piece | File | Needs |
|---|---|---|
| Yosys + ABC synthesis, EDIF and Verilog netlist | [flow/oss_synth.py](../flow/oss_synth.py) | OSS CAD Suite 20261112 (`FDA_OSS_CAD`, as [flow/checks/elab.py](../flow/checks/elab.py)) |
| Yosys against Vivado comparison, one part | `python3 -m flow.oss_compare.run --part <part> [--perturb]` | Vivado 2026.1 (one thread, out of context) |
| Vivado post-synthesis funcsim netlists | `python3 -m flow.oss_compare.netlist --part <part>` | Vivado 2026.1 |
| eqy gate | [flow/eqy_gate.py](../flow/eqy_gate.py) | OSS CAD Suite 20261112 |
| eqy sweeps and fault table | `python3 -m flow.oss_compare.eqy_run --yosys`, `--faults`, `--vivado <dir>...`, `--table` | the suite (the Vivado netlists come from `netlist.py`) |
| Agent tools `oss_synth`, `eqy_check` | [agent/core/oss_tools.py](../agent/core/oss_tools.py) | a stage or role that opts in; the prompt text is in the private knowledge base |
| Sign-off gate `post_synth_oss_netlist_equivalent` | [flow/gates.py](../flow/gates.py) | none (reads `eqy_result.json`) |

## Part 1: the Yosys synthesis flow

`oss_synth.py` reads the RTL with the slang front end, runs `synth_xilinx` for the part's family (`xc7` for 7-series,
`xcup` for UltraScale+) and writes `netlist.edif` (for `read_edif`) and `netlist.v` (the same cells, for `eqy`). The ABC
script is the whole choice, and each result records it verbatim in `synth.json`:

| Script | What it does |
|---|---|
| `abc9` | `synth_xilinx -flatten`: the timing-driven ABC9 flow, LUT, CARRY and MUX delays from the `specify` blocks of `cells_sim.v`, no delay target (the best delay it finds, then area recovery off the critical path) |
| `abc9_dff` | the same with `-dff`: flip-flops are boxes, so ABC's sequential steps may move or merge registers; register names can then differ from the RTL |
| `abc_d` | the classic `abc` pass with a delay target (`-D <ps>`, default 1 ps, "as fast as possible"); it sees LUT depth only, with no timing for CARRY or MUX |

Yosys's own LUT, FF and CARRY counts are recorded, and are not used for any comparison. Vivado's timing analysis of the
placed and routed EDIF is the referee.

### How the comparison is made

Each block gets a wrapper (`flow/oss_compare/rtl/wrap_<block>.sv`): an input register, the block, and an output register,
so every path is register to register and the latency is two clocks in every arm. The same wrapper, the same one-clock
constraint, the same default `opt_design`, `place_design` and `route_design`, the same part and one Vivado thread apply to
all six arms:

* `viv_default`, `viv_perf` (`-directive PerformanceOptimized`), `viv_perf_retime` (`-directive PerformanceOptimized -retiming`):
  Vivado synthesises the RTL;
* `ys_abc9`, `ys_abc9_dff`, `ys_abc_d`: Vivado reads the Yosys EDIF (`read_edif`, then `link_design -mode out_of_context`;
  `-top` is not given: with it, an EDIF read in non-project mode fails with "Project 1-68").

The clock search is the house pulse-width-aware one (`designs/b87_ml_trading/ooc`, brief 89): an arm closes when setup, hold
and pulse width are all met; the next period is `period - min(WNS, 2 * WPWS)` rounded up to 0.05 ns; an arm is never tried
faster than a period that failed. Latency is two clocks at the arm's own closed period. Vivado has no user placement seed,
so the seed variation is the spread of the achievable period over three runs: the closed clock, +0.01 ns and +0.02 ns
(a different clock constraint changes the placer's cost function). The three runs are not the same experiment across arm types:
the Vivado RTL arms read the clock before `synth_design`, so a perturbed run re-synthesises, while an EDIF arm only re-places; the
spread is a measure of how much each arm's result moves under a small constraint change, not a like-for-like placer-seed spread.

The blocks: `crc64_rx` (the 96 RX CRC stage, an XOR network), `pcs_tx` (the 96 PCS transmit path with the gearbox, registers
and a state machine), `lg_small_comb` (the 89 combinational LUT network, adders and compare chains), `adder_tree8` (eight
8-bit values summed, three levels of two-input adds; the 16 x 12-bit tree of the first attempt could not be proved by `eqy`
within an hour and was replaced).

## Part 2: the eqy gate

`eqy_gate.check(top, gold_sources, netlist, work, strategy, depth, timeout)` returns an `EqyResult` with one of four
statuses: `PASS` (proved under the stated strategy), `FAIL` (a difference; the counterexample is in the work directory),
`SKIPPED` (the suite is not installed: a notice, nothing is claimed) and `ERROR` (the tool failed or timed out: never a
pass). Gold is the RTL; gate is any Yosys-readable Verilog netlist whose primitives (`LUT1..6`, `FDRE/S/C/P`, `CARRY4/8`,
`MUXF7/8/9`, `GND`, `VCC`) are modelled by the suite's `cells_sim.v`, written from the vendor-neutral public behaviour of the
primitives. No AMD simulation model (UNISIM) is read or shipped. A primitive that `cells_sim.v` does not model (DSP48E, RAMB,
GT, clocking; the suite's file models only the Spartan-6 DSP48A) makes a netlist `ERROR`, not a pass.

The Vivado funcsim netlist ends with the simulation scaffolding module `glbl` (global set and reset nets with `tri1` and
`tri (weak1, strong0)` strengths that Yosys cannot parse). The gate reads a copy without it; the recorded hash is of the
netlist as written. Nothing in the netlist instantiates `glbl`.

### Sequential designs: matching strategies and their limits

Both sides first run `sim -w` for two reset clocks, so every register starts from its post-reset value, not unknown.

| Strategy | Correspondence | Engine | Proves | Limit |
|---|---|---|---|---|
| `name` | registers by name; the gate's own cell and net names are hidden first, so the surviving name is the RTL one | induction, depth 2, bitwuzla, one proof per register cone | unbounded, fast (seconds to minutes) | matched registers are treated as free: two registers that differ only in a state the design can never reach fail although the circuits behave the same. A register that was moved, merged, duplicated or renamed has no partner by name: it sits inside a larger partition (a harder proof, not a weaker one) |
| `bmc` (inside `auto` only, not a command-line choice) | none (one partition) | bounded model checking, 24 clocks from the post-reset state | nothing; a counterexample is a real difference | no counterexample proves nothing: it is only the quick first step of `auto` |
| `group` | none (all state in one partition) | `abc pdr` | the outputs equal for every input sequence from the post-reset state | slow, and some cones (large XOR networks, multi-operand adders restructured by the vendor) do not finish |
| `auto` (default) | `name`, then `bmc` for a real counterexample, then `group` | | | |

Limits that hold for every strategy:

* INIT values are not compared: the RTL of these designs has no initial values (`rtl.initial_values` allows them, [design_standards.md](design_standards.md#initial-values-rtlinitial_values)), so what is proved is the post-reset state and every input
  sequence after it. A design whose reset is asynchronous, or whose reset input is not named `rst` and the clock `clk`, is
  not covered (`reset=` changes the name).
* The proof is of the netlist's function, not of its timing or placement.
* The equivalence is of the netlist text given. A routed design is covered only when it is written out as Verilog.
* A `PASS` under `name` or `group` is a proof; a timeout is `ERROR` and is reported as unproved, never as a pass.
* A proof that does not finish is a real limit: [results/b101/eqy/summary.md](../results/b101/eqy/summary.md) lists which
  netlists proved and which did not, with the times.

### Planted faults

`eqy_gate.plant(text, kind, which)` edits a netlist: `lut_init` (one INIT bit flipped), `swap_regs` (two registers' D
inputs exchanged), `reset_value` (a register that reset sets becomes one that reset clears) and `reset_drop` (a register's
reset pin tied low, so the reset value is lost; the nearest a netlist edit gets to a retimed register that lost its reset).
`python3 -m flow.oss_compare.eqy_run --faults` plants two of each kind in every block's Yosys `abc9` UltraScale+ netlist
and records the verdict next to the clean netlist's. A fault that cannot be planted (no register, or no FDSE) is recorded
as `N/A`, not as caught.

## The gate in the flow

`post_synth_oss_netlist_equivalent` (in `flow/gates.py`, evaluated with the post-synthesis stage): a flow that leaves a
netlist under `build/<variant>/oss_netlists/<name>/` passes the gate only with an `eqy_result.json` in that directory whose
status is `PASS` and whose recorded SHA-256 of the netlist and of the RTL sources equal the files now on disk (an edited
netlist or changed RTL must be proved again). A build with no such netlist has no gate. The agent's `eqy_check` tool writes
the record when the netlist lives under `oss_netlists/`. Where the suite is absent the check returns `SKIPPED` with a notice (the command line exits 0), and the gate fails closed: a
netlist with no `PASS` record is not reported as checked. The record also holds the hash of every `.v` and `.edif` in the netlist's
directory, so the EDIF that Vivado implements is bound to the proof.

CI (job "Reset check by elaboration", which already installs the pinned suite): `eqy --version` and
`flow/tests/test_101_eqy.py`. Forks and runs without the suite skip those tests with a notice.

## For RapidWright-modified designs (brief 100, merged)

Write the modified design out with `write_verilog -mode funcsim` (or the RapidWright Verilog writer), put it under
`oss_netlists/<name>/netlist.v`, and run `eqy_check` with the RTL sources. The gate treats it like any other netlist. This
has not been exercised on a brief-100 design; see the report's known gaps.
