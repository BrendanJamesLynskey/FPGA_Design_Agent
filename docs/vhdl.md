# VHDL designs

The flow supports VHDL-2008 designs; the agent can write them, but it has not yet passed an end-to-end VHDL task. Model
translations of five development tasks passed the same hidden tests and Vivado 2026.1 gates as their SystemVerilog references,
but only in an exploratory (post hoc) second arm, run after the model's first attempt failed all five on one naming mistake
([measured](#measured)).

The agent and the flow are SystemVerilog-first. A design may instead be written in VHDL-2008. The test shell (the UART register
window every board design instantiates) stays SystemVerilog. This page says how to ask for VHDL, what runs where, and where the
language boundary is.

## Try it

```
python -m agent run benchmark/tasks/t1_gray_stepper/spec.md --hdl vhdl --stop-after 2      # the agent writes VHDL
```

Or put `language: vhdl` in the design's `spec.yaml`; from the next stage on the run behaves as with `--hdl vhdl` (VHDL
conventions in the prompts, the sandbox image with GHDL). For an existing VHDL design, run the `lint` tool first, or directly:

```
python -m flow.vhdl lint rtl --top my_top
```

Score a VHDL design against a task's hidden tests: `python -m flow.vhdl_score <task_dir> --rtl <dir with *.vhd>`.

## The boundary

- The board top is a VHDL entity with the spec's top name and the board's master XDC port spellings (`CLK100MHZ`, `LED`,
  `UART_TXD_IN` ...). VHDL ignores case; the XDC, the GHDL netlist and the cocotb bench do not.
- The shell (`shell/rtl/fpga_shell.sv`) is instantiated from VHDL through a **component declaration**
  ([flow/vhdl.py](../flow/vhdl.py) `SHELL_COMPONENT`). Vivado binds a component to a Verilog module of the same name. Do not use
  `entity work.fpga_shell`: there is no such VHDL entity for GHDL, so the flow's lint and simulation fail on it. (AMD's synthesis
  guide UG901, in the edition brief 55 read (not re-read for 2026.1), calls direct entity instantiation of a Verilog module unsupported; Vivado 2026.1 accepted it in a
  probe. The component works in both tools.)
- VHDL and Verilog share one library, so no VHDL entity may take the name of a shell module (`fpga_shell`, `shell_core`,
  `uart_rx`, `uart_tx`, `sync2`, `reset_sync`). This was the most common error in the first translations.
  **When lint reports `[vhdl boundary]`:** either delete your entity and declare the shell's module as a component (for `sync2`:
  ports `clk`, `rst`, `d`, `q`; for `reset_sync`: `clk`, `rst_n_async`, `rst`), or rename your entity (for example `sync2_vh`).
- **When lint reports `[vhdl unbound]`:** a component has no entity. Only the shell's modules may stay unbound; write the entity
  or fix the component's name.
- `BUILD_STAMP` is a generic `std_logic_vector(31 downto 0)` of the top, passed on to the shell. The flow passes
  `-generic BUILD_STAMP=32'h<stamp>` to Vivado (measured: the value reaches the VHDL generic and the shell); for the GHDL
  netlist the literal becomes a VHDL bit string of the generic's width.

## What runs where

| Step | SystemVerilog design | VHDL design |
|---|---|---|
| lint (the agent's `lint` tool) | Verilator `--lint-only -Wall`, Icarus elaboration | GHDL analysis, then GHDL synthesis of the top; see below |
| simulation with the shell | Icarus or Verilator | the GHDL netlist of the VHDL beside the shell, under Icarus or Verilator |
| simulation without the shell | Icarus or Verilator | GHDL itself (`SIM=ghdl`), cocotb through VPI |
| hidden tests | `benchmark/tools/run_task.py` | [flow/vhdl_score.py](../flow/vhdl_score.py): the netlist, then the same unchanged `run_task.run` |
| design standards | a scan of the RTL | the same scan of the GHDL netlist (signal initial values removed: they are INIT values) |
| mutation | operators on `.sv` | VHDL operators in [flow/mutate.py](../flow/mutate.py), GHDL analysis as the compile check, `--sim ghdl` for a shell-less block |
| formal | SymbiYosys | SymbiYosys through the GHDL Yosys plugin, PSL properties ([fixture](../flow/tests/fixtures/vhdl_formal)) |
| code coverage | Verilator | statement lines from GHDL 4.1.0's `--coverage` (a hit flag per line, no merge command that works) or from NVC's `--cover` (statement, branch, toggle, expression; merges); [measured](../results/156_vhdl_tools/README.md) |
| Vivado | `read_verilog -sv` | `read_vhdl -vhdl2008` ([flow/build.tcl](../flow/build.tcl)); VHDL after the SystemVerilog, packages first |
| sandbox image | `fda-sim:2` | `fda-sim:2-ghdl` ([agent/container/Dockerfile.vhdl](../agent/container/Dockerfile.vhdl)) |

The VHDL lint:

- refuses latches and signals with two drivers (GHDL synthesis does; Vivado only warns);
- refuses a VHDL entity named like a shell module (`[vhdl boundary]`) and an unbound component that is not the shell
  (`[vhdl unbound]`);
- checks the top's ports against the spec and the board's UART pair (the rules FDA-CON-8 and FDA-CON-9 of
  [agent/core/constraints.py](../agent/core/constraints.py)).

Vivado's `check_syntax` is not part of the lint; the flow relies on the build's first stage instead
(`synth_design -rtl` after `read_vhdl -vhdl2008`), which is Vivado's own reading of the VHDL.

The netlist route checks the VHDL as GHDL synthesises it: a synthesis view, not Vivado's, and not VHDL simulation semantics. An
incomplete sensitivity list or a 'U' start value is invisible in it, and it can differ the other way too: an asynchronous FIFO
block that passes its test natively under GHDL fails it as a netlist under Icarus, reading 'X' early in the run (cause not
investigated). Use the native route
for a block without the shell.

Tools:

| Tool | Version | Where | Source and checksum |
|---|---|---|---|
| GHDL | 4.1.0 (mcode) | Ubuntu 24.04 package `ghdl` 4.1.0+dfsg-0ubuntu2.1; the pin in CI and in the image; `~/.local/bin/ghdl` here | distribution package |
| GHDL | 7.0.0-dev (6.0.0.r729.g8e642a9a5, LLVM 21.1.8) | OSS CAD Suite, `~/.local/opt/oss-cad-suite` | measured only; not a pin |
| NVC | 1.23.1 (LLVM 18.1.3) | `~/.local/opt/nvc-1.23.1` (the official release `.deb` for Ubuntu 24.04, extracted without root; `source ~/.local/opt/nvc-1.23.1/env.sh`) | https://github.com/nickg/nvc/releases/tag/r1.23.1, `nvc_1.23.1-1_amd64_ubuntu-24.04.deb`, sha256 `836b86c93d7ac0fa6d6313b651c0409476f04f59718fb270515e6bc6232477cd` |
| cocotb | 2.0.1 | pip | VPI for GHDL, VHPI for NVC |

Locally also VUnit 4.7.1, OSVVM 2026.09, and the GHDL Yosys plugin (Ubuntu `yosys-plugin-ghdl`); `flow/formal.sh` uses
`$FDA_GHDL_PLUGIN` for a job's `plugin -i ghdl` when the plugin is not in Yosys's own plugin directory. CI runs the formal test
only where SymbiYosys is installed (it is not in the CI image), so VHDL formal is checked locally.

NVC is installed and measured, not yet in the flow: the flow's VHDL simulation is still GHDL. What the measurement found, and what
to do with it, is in [results/156_vhdl_tools](../results/156_vhdl_tools/README.md) (brief 156): the same six cocotb benches pass on all
three simulators with identical per-clock traces; with cocotb in the loop the simulator is not the bottleneck, but a pure-VHDL
testbench ran 95 times faster on NVC than on GHDL mcode; PSL works in both simulators and in SymbiYosys, with different subsets.

## What the checks do with VHDL

Before brief 153 several checks and gates found their RTL with a `*.sv` glob, so a VHDL design had no files to read and passed
([results/153_vhdl_parity](../results/153_vhdl_parity/README.md): 12 of 17 readers did this). Now every reader asks
[flow/sources.py](../flow/sources.py) for the design's files by language, and a reader that cannot read VHDL says so: the check is
PARTIAL or NOT RUN with `no reader for .vhd (...)`, never a clean pass. `python -m flow.sources [design]` prints the table (and the
design's files by language); its `--help` lists what a user could guess wrong. In short:

- **Read in VHDL:** the lint (GHDL, when the build's top is a VHDL entity), the design standards, the reset check, the XPM
  `SIM_ASSERT_CHK` check, the derived constants (the shell's `DESIGN_ID` in the `generic map`, as a literal or a literal constant), the
  CDC detection, the spec-test role (through the GHDL netlist), the evidence keys, the trace matrix (`-- req:` tags and
  `-- std-waive:` waivers), the build-stamp check and the review's top.
- **No reader, said so:** the AXI profile check (it compares generated SystemVerilog blocks; the generator writes no VHDL), the FSM
  coverage (the state table is a SystemVerilog `typedef enum`), the managed RTL import, and the schematic pages.
- **Fails closed:** the CDC injection run. A VHDL design with a clock-domain crossing fails it, because there is no injector for VHDL;
  this is not a defect in the design.
- **A SystemVerilog top over VHDL entities** has no lint that reads both languages: the lint is NOT RUN.

## Measured

- First translations by a model (openai/gpt-6-luna, given the spec and the SystemVerilog): 0 of 5 board tasks, all on the
  shell-name clash. With that rule and the VHDL skills in the prompt (an exploratory, post hoc arm): 5 of 5 passed the unchanged hidden tests and every Vivado 2026.1
  gate, with equal flip-flops and LUTs within 14 of the references; one ran on the board.
- The end-to-end agent with `--hdl vhdl`: 0 of 4 runs passed; the VHDL built but failed the register tests, as the same model's
  SystemVerilog runs do.

Details, the mistakes and the rules they produced: [results/55_vhdl](../results/55_vhdl/README.md).
