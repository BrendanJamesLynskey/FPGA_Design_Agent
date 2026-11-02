# Design standards (v1.0)

Versioned: **v1.0** (2026-11-02, brief 05d). The agent's RTL, and anything a human adds, follows these rules; the
flow checks the ones a program can check (`flow/standards_check.py`) and lists the rest for the human reviewer.
The rules come from the owner's plan, from the knowledge bank (the `reset-strategy`, `clock-domain-crossing` and
`clocking` skills: "clock enables, not gated clocks"; reset policy per the bank) and from the practice in Adam
Taylor's FPGA Horizons issue 5 article ("What Star Trek can teach us about using AI in FPGA design": keep it
synchronous, declare the clock domains, standard interfaces, and treat the AI as a junior engineer held to the same
gates as human RTL). A change to a rule bumps the version above and the checker's `VERSION`.

## The standards

1. **Synchronous design only.** No derived or gated clocks (use a clock enable on the declared clock), no latches, no
   combinational loops.
2. **Every clock domain is declared** in `architecture.yaml` (`clock_domains`), which the owner approves before RTL
   is written, and every crossing goes through a named CDC primitive from the bank, listed under `crossings`.
3. **Reset is synchronous** unless the spec says otherwise or the module is a declared reset synchroniser
   (`reset.synchronisers`); the bank's reset-strategy skill is the policy.
4. **New block interfaces are AXI4-Lite or AXI4-Stream** with AMBA port names (`<prefix>_awvalid`, `<prefix>_tdata` ...).
5. **No `initial` blocks in synthesisable RTL**, except ROM initialisation with `$readmemh` / `$readmemb`.
6. **A waiver is a comment on the line (or the line above): `// std-waive: STD-XXX-NN <reason>`.** A waiver without a
   reason is itself a failure.

## Rule table

`rtl` rules run when RTL is written (stage 2 gate `standards_rtl`); `post_synth` rules run on the Vivado reports of the
synthesised design (stage 4 gate `standards_post_synth`). A checkable rule that could not run (tool or report missing)
counts as a failure, not a pass.

| Rule | Stage | Rule text | How it is checked |
|---|---|---|---|
| `STD-ARCH-00` | rtl | architecture.yaml exists and has the shape the checker reads | flow/architecture.py check_architecture |
| `STD-CLK-01` | rtl | no derived or gated clocks: every clock a register uses is a clock input, an alias of one, or the output of a clock-network primitive (MMCM, PLL, BUFG) | static scan: edge signals of every always block against ports, assigns and instance outputs; clock-gating primitives (BUFGCE, BUFGMUX, BUFHCE) refused |
| `STD-CLK-02` | rtl | every clock of the top module is declared in architecture.yaml clock_domains | static scan against architecture.yaml |
| `STD-CLK-03` | post_synth | every clock source in the synthesised design's clock network is a declared domain | clock-net scan of report_clock_networks (clock_networks_synth.rpt) against architecture.yaml |
| `STD-RST-01` | rtl | synchronous reset: a reset is not in a sensitivity list (the bank's reset-strategy skill: follow the spec; FPGA default synchronous), except in a declared reset synchroniser | static scan of sensitivity lists; architecture.yaml reset.synchronisers or a waiver |
| `STD-LATCH-01` | rtl | no latches | Verilator -Wall LATCH warnings; Yosys proc (a $dlatch cell) |
| `STD-LOOP-01` | rtl | no combinational loops | Verilator UNOPTFLAT warnings; Yosys check (logic loop) |
| `STD-INIT-01` | rtl | no initial blocks in synthesisable RTL except ROM initialisation ($readmemh/$readmemb) | static scan; // synthesis translate_off regions are skipped |
| `STD-CDC-01` | rtl | every clock-domain crossing is a named CDC primitive from the bank, listed in architecture.yaml crossings, and instantiated; no module mixes two clocks outside one | architecture.yaml crossings against the instances in the RTL; static scan of clocks per module |
| `STD-CDC-02` | post_synth | report_cdc on the synthesised netlist has no Critical row | Vivado report_cdc (cdc_synth.rpt), gate post_synth_cdc_no_critical |
| `STD-METH-01` | post_synth | report_methodology on the synthesised netlist has no Critical Warning | Vivado report_methodology, gate post_synth_methodology_no_critical |
| `STD-AXI-01` | rtl | a new block interface is AXI4-Lite or AXI4-Stream with AMBA port names (prefix_awvalid, prefix_tdata ...) and the right direction | architecture.yaml interfaces against the module's ports |
| `STD-AXI-02` | rtl | ports named like an AXI interface belong to a declared interface | port-name pattern scan |
| `STD-WAIVE-01` | rtl | every waiver states a reason | static scan of std-waive comments |
| `STD-REV-01` | review only | a multi-bit crossing uses Gray code, a handshake or an asynchronous FIFO, never a bit-by-bit synchroniser | review only: the data type of a crossing is not in the netlist |
| `STD-REV-02` | review only | AXI protocol semantics: valid is not withdrawn before ready, no combinational ready-to-valid loop | review only (a formal property is the way to check it) |
| `STD-REV-03` | review only | reset values and enables follow the spec and the bank's reset-strategy skill | review only |

Tools: Verilator `--cc --Wall` warnings `LATCH` and `UNOPTFLAT`, Yosys `proc` and `check`, a SystemVerilog scanner in
the checker (comments removed; modules, ports, `always` sensitivity lists, assigns, instances), and the Vivado
`report_cdc`, `report_methodology` and `report_clock_networks` the build writes after synthesis.

## Limits of the static checks

The scanner reads one level of module hierarchy and plain-identifier aliases (`assign clk = CLK100MHZ;`); an expression
or a generate-built clock it cannot follow is reported as a derived clock, never passed. It checks that a crossing
names a primitive and that the primitive is instantiated, not that the primitive is the right one for the data
(STD-REV-01). AXI checks cover names, completeness and direction, not protocol behaviour (STD-REV-02).
