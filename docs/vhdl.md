# VHDL designs (brief 55)

The agent and the flow are SystemVerilog-first. A design may instead be written in VHDL-2008: `--hdl vhdl` on
`python -m agent run`, or `language: vhdl` in `spec.yaml`. The test shell stays SystemVerilog. This page says what runs
where, where the language boundary is, and what was measured.

## The boundary

- The board top is a VHDL entity with the spec's top name and the master XDC's port spellings (`CLK100MHZ`, `LED`,
  `UART_TXD_IN` ...). VHDL ignores case; the XDC, the GHDL netlist and the cocotb bench do not.
- The shell (`shell/rtl/fpga_shell.sv`) is instantiated from VHDL through a **component declaration**
  ([flow/vhdl.py](../flow/vhdl.py) `SHELL_COMPONENT`), never `entity work.fpga_shell`: Vivado binds a component to a Verilog
  module by name; direct entity instantiation of a Verilog module is not supported (AMD UG901, mixed-language chapter).
- VHDL and Verilog share one library: no VHDL entity may take the name of a shell module (`fpga_shell`, `shell_core`,
  `uart_rx`, `uart_tx`, `sync2`, `reset_sync`). The lint refuses one (mistake M1 below).
- `BUILD_STAMP` is a generic `std_logic_vector(31 downto 0)` of the top, passed on to the shell. The flow passes
  `-generic BUILD_STAMP=32'h<stamp>` to Vivado; for the GHDL netlist the literal becomes a VHDL bit string.

## What runs where

| Step | SystemVerilog design | VHDL design |
|---|---|---|
| lint (`lint` tool) | Verilator `--lint-only -Wall` + Icarus elaboration | GHDL `-a --std=08 -Wall`, then `ghdl --synth` of the top (refuses latches and multiple drivers), the shell-name check, FDA-CON-8/9 on the entity's ports |
| simulation with the shell | Icarus / Verilator | the GHDL netlist of the VHDL (`ghdl --synth --out=verilog`, generics fixed, the shell a black box) beside the shell under Icarus / Verilator |
| simulation without the shell | Icarus / Verilator | GHDL natively (`SIM=ghdl`), cocotb through VPI |
| hidden benches | `benchmark/tools/run_task.py` | [flow/vhdl_score.py](../flow/vhdl_score.py): the netlist, then the same frozen `run_task.run` |
| design standards | static scan of the RTL | the same scan of the GHDL netlist (signal initial values removed: they are INIT values) |
| mutation | operators on `.sv` | VHDL operators (`=`/`/=`, and/or, `'0'`/`'1'`, ...) in [flow/mutate.py](../flow/mutate.py); GHDL analysis as the compile check |
| formal | SymbiYosys | SymbiYosys through the GHDL Yosys plugin, PSL properties ([fixture](../flow/tests/fixtures/vhdl_formal)) |
| code coverage | Verilator | none (GHDL mcode has none); waive with the reason |
| Vivado | `read_verilog -sv` | `read_vhdl -vhdl2008` ([flow/build.tcl](../flow/build.tcl)); VHDL after the SystemVerilog, packages first |
| sandbox image | `fda-sim:2` | `fda-sim:2-ghdl` ([agent/container/Dockerfile.vhdl](../agent/container/Dockerfile.vhdl)) |

The netlist route checks the VHDL as GHDL synthesises it, which is what the hardware does, but not VHDL simulation
semantics: an incomplete sensitivity list or a 'U' start value is invisible in it. A VHDL block without the shell can be
run natively to see those.

Tools: GHDL 4.1.0 (Ubuntu 24.04 package `ghdl` 4.1.0+dfsg-0ubuntu2.1, mcode back end; the same pinned package in CI and the
image). Locally also VUnit 4.7.1, OSVVM 2026.09, and the GHDL Yosys plugin (Ubuntu `yosys-plugin-ghdl`); `flow/formal.sh`
substitutes `$FDA_GHDL_PLUGIN` for a job's `plugin -i ghdl` when the plugin is a user-level install.

## Measured

See [results/55_vhdl](../results/55_vhdl/README.md): the translations of development drills, their hidden-bench results, the
Vivado comparison with the SystemVerilog references, the board run, and the mistakes the model made in VHDL.
