# Block designs: the top level as text

When a design joins several blocks on a bus, the agent writes its top level as a **block design**: a YAML file of
instances, connections and an address map. The flow validates it, completes it (the interconnect, the clock and reset
wiring, the address map) and generates the top-level SystemVerilog, the wrappers, a C header, a manifest and the
diagram. It covers what Vivado 2026.1's IP Integrator does for a block design, in a form the agent can write and a
reviewer can diff, and adds checks IP Integrator does not make. The code is in [flow/blockdesign](../flow/blockdesign);
the worked example is [designs/b65a_axil_soc](../designs/b65a_axil_soc).

**Try it** (Python only):

```
python3 -m flow.blockdesign validate designs/b65a_axil_soc     # the checks; exit 1 on an error
python3 -m flow.blockdesign generate designs/b65a_axil_soc     # gen/ and build.yaml; gen/viewer.html to open in a browser
python3 -m flow.blockdesign check designs/b65a_axil_soc        # exit 1 if the committed gen/ differs from the generator
python3 -m pytest flow/blockdesign/tests                       # the adversarial tests, one or more per rule
python3 -m flow.blockdesign <command> --help                   # what each command does, with an example
```

## Words used here

| Word | Meaning |
|---|---|
| block design | a file that says which blocks a level of the design has and how they connect |
| instance | one use of a block (an `ip_lib` entry or a flow component) in a design |
| interface | a group of ports that work together: an AXI4-Lite or AXI4 bus, an AXI4-Stream, the test shell's register window, a clock, a reset or an interrupt |
| link | a connection between a master interface and a slave interface |
| conduit | a plain signal connection, port to port, possibly a slice |
| hierarchy | a block design used as one block inside another (its own file; reusable) |
| domain | a clock domain: one clock, its frequency and its synchronised reset |
| crossing | a signal entering a domain other than its own |
| automation | parts of the design the flow adds itself: the interconnect, reset synchronisers, clock and reset wiring, the address map |
| DECERR | the AXI response for an address no slave owns |

## The file

`blockdesign.yaml`, checked against [blockdesign.schema.json](../flow/blockdesign/blockdesign.schema.json) first (a
bad key is reported with its path). The sample, abridged:

```yaml
schema: fpga-design-agent/blockdesign/v1
name: b65a_axil_soc
top: b65a_axil_soc_top
part: xc7a100tcsg324-1
ports:                                   # board pins
  - {name: CLK100MHZ, dir: in, kind: clock, freq_mhz: 100}
  - {name: CPU_RESETN, dir: in, kind: reset, polarity: low, async: true}
clocks:                                  # domains; each with a reset gets a reset synchroniser (block automation)
  - {name: sys, port: CLK100MHZ, reset: CPU_RESETN}
instances:
  shell: {component: test_shell, params: {DESIGN_ID: 0x42363541}}
  host:  {component: bd_win_axil_master}
  tone:  {design: tone.yaml}             # a hierarchy
  la:    {component: logic_analyser, params: {ADDR_W: 8}, axi_lite: {window: window}}
connections:
  - {from: shell.window, to: host.window}                        # interface to interface
  - {from: tone.sample, to: la.sample}                           # port to port; la.WIDTH follows (propagation)
  - {from: tone.sample, bits: [15, 8], to: LED, to_bits: [15, 8]}
  - {const: 0, to: LED, to_bits: [7, 0]}
interconnect:                            # connection automation
  - {name: xbar, masters: [host.m_axil], slaves: [tone.s_dds, tone.s_fd, la.s_axil]}
address_map:                             # the address editor
  base: 0x40000000
  ranges: [{slave: tone.s_dds, base: 0x40000000}, {slave: tone.s_fd}, {slave: la.s_axil, base: 0x40010000}]
top_params: [shell.CLKS_PER_BIT, tone.fd.GATE_CLKS]             # raised to the top so a simulation can shorten them
```

- **Instances** name a component: an `ip_lib` entry, with its `variant` and `params` checked against the entry's
  declared space, or a flow component from [flow/blockdesign/components](../flow/blockdesign/components) (the test shell,
  `reset_sync`, `sync2`, the support RTL). A file there named after an `ip_lib` entry is an overlay that says what
  `ip.yaml` says only in words: inputs with their own synchroniser, parameters derived from the clock.
- **Interfaces** are inferred from port names, as a packager does: `<p>_awaddr ... <p>_rready` is AXI4-Lite (AXI4 with
  `awlen` or `awid`), `<p>_tdata`/`<p>_tvalid` is AXI4-Stream, `win_*` is the register window, `ip.yaml`'s clocks and
  resets are clocks and resets (with polarity), a one-bit `irq` or `*_irq` is an interrupt; every other port is a conduit.
- **`axi_lite`** puts a generated AXI4-Lite wrapper in front of a block that has none: `window` (an adapter for a
  register window) or `registers` (a register bank: each `control` register drives inputs, each `status` register
  reads outputs, `tick` adds a sample-rate divider). The generated header lists every register's offset.
- **Hierarchies** are separate files with `kind: hierarchy`. They take their parent's clock domain (`clk`, `rst`), have
  boundary `ports`, and export inner interfaces with `interfaces: [{name, export: inst.iface}]`. One file used twice is
  one module.

## Validation (IP Integrator's validate, and more)

Every rule has its own code, a message that names the culprit and, where there is one, the fix. The tests in
[test_65a_blockdesign.py](../flow/blockdesign/tests/test_65a_blockdesign.py) build an adversarial design for each, and
[test_65a_adversarial.py](../flow/blockdesign/tests/test_65a_adversarial.py) holds the designs an independent review found
that an earlier version got wrong.

| Code | Severity | What |
|---|---|---|
| BD-SCHEMA | error | the file breaks the schema (the path of the bad key is given) |
| BD-COMP-01, -02 | error | unknown component; unknown variant |
| BD-PARAM-01 | error | unknown parameter; a value outside the entry's declared range or set, including one reached by propagation or derived from the clock; a string for an integer parameter that is not a Verilog literal or constant expression (`8'h8` and `$clog2(256)` are read as 8) |
| BD-PARAM-02 | error | a parameter given in the file contradicts the one derived from the clock (for example the shell's baud divider) |
| BD-REF-01, -02 | error | an endpoint that does not exist; a name used twice |
| BD-IF-01 | error | interface types differ (AXI4-Stream into AXI4-Lite), an interrupt into a data input or the reverse, a bus type the interconnect does not join |
| BD-IF-02 | error | master to master, or slave to slave |
| BD-IF-03 | error | an interface connected to a plain port; a plain connection to a port of a bus interface that is already on a link, an interconnect or an export (it would be a second driver). A bus interface on no link may be tied off port by port |
| BD-WIDTH-01 | error | widths differ on a signal; the hint says which parameter was set by hand and blocks propagation |
| BD-WIDTH-02 | error | bus data widths differ, or the slave's ID width cannot hold the master's |
| BD-WIDTH-03, -04 | error | a slice outside its port; a register field that does not fit 32 bits |
| BD-UNCONN-01 | error | an input (or some of its bits) not driven |
| BD-UNCONN-02 | error | a bus interface on no link |
| BD-UNCONN-03 | error | a design output (or some of its bits) not driven |
| BD-DRV-01 | error | two drivers on one bit; a slave with two masters (use an interconnect) |
| BD-DRV-02 | error | driving an output, or reading from an input |
| BD-CDC-01 | error | a signal from one clock domain into another with no synchroniser |
| BD-CDC-02 | error | an asynchronous input (`async: true`) into an input that has no synchroniser of its own |
| BD-CDC-03 | error | a bus link between two domains (no clock converter is generated yet) |
| BD-CDC-04 | error, warning | several bits from another domain (or asynchronous) into one synchroniser input: an error through a bit-wise synchroniser (`sync2`), a warning into a block's own per-input synchroniser. The bits can arrive in different clocks: use a handshake, a gray-coded count or an asynchronous FIFO; for independent level signals, connect each bit on its own |
| BD-RST-01 | error | reset polarities differ on a hand-made connection without `invert` |
| BD-RST-02 | error | a reset from another domain's synchroniser |
| BD-CLK-01..-04 | error, warning | a clock input driven by a non-clock; an unknown domain, or a block's domain clock wired by hand to a clock other than its domain's (that would hide every crossing into it); an instance in no or an ambiguous domain; a clock with no frequency |
| BD-ADDR-01 | error | address ranges overlap |
| BD-ADDR-02 | warning | a hole between ranges (an access there gets DECERR) |
| BD-ADDR-03 | error | a base not aligned to its size (the hint gives the two nearest legal bases) |
| BD-ADDR-04 | error | a range outside the masters' address space |
| BD-ADDR-05, -06, -07 | error, error, warning | a range for a slave on no interconnect; a size not a power of two; a range smaller than the slave decodes |
| BD-HIER-01..-03 | error | a missing or wrong hierarchy file; a hierarchy that includes itself; a hierarchy declaring its own clock |
| BD-OPEN-01, -02 | info, warning | an output left open; a design input not used |

Errors stop generation. A width mismatch is not then reported a second time as an undriven input.

## Automation

- **Connection automation.** Each `interconnect` entry becomes an `ip_lib/axil_xbar` instance (N masters to M slaves,
  a round-robin write and read arbiter per slave, DECERR for unmapped addresses), with its address width propagated
  from the masters and its map from the address editor. Verified on its own with the AXI4-Lite protocol checker
  (`axi_tx/rtl/axil_checker.sv`) on every link and ten seeded faults ([ip_lib/axil_xbar](../ip_lib/axil_xbar/README.md)).
- **Clock and reset.** A block's domain clock (its first clock input, or a hierarchy's `clk`), if unconnected, gets its
  domain's clock; any other clock input (`clk90`, a receive clock) is never tied automatically and is reported
  unconnected until it is wired by hand. Every unconnected reset input gets the domain's synchronised reset, inverted
  for an active-low input. One `reset_sync` per domain that has a reset port.
- **Parameter propagation.** A sink port whose width is `[P-1:0]` with `P` not set takes its driver's width (`la.WIDTH`
  from the tone's 16-bit sample), repeated until nothing changes, so a chain of any length settles; the interconnect takes the masters' address width; a component's clock-derived
  parameters follow its domain's frequency (`test_shell.CLKS_PER_BIT = round(f / 115200)`). The viewer shows, for
  every parameter, where its value came from.
- **Address editor.** Fixed bases are kept; the rest are placed at the lowest free aligned address from `base`, at the
  larger of `min_size` (4 KB by default) and the slave's own span. Exports: `gen/addrmap.h` (bases, sizes and register
  offsets), `gen/address_map.md`, `gen/address_map.json`.

## Generation

`gen/rtl/`: the top module, one module per hierarchy, one wrapper per `axi_lite` instance. Instances are `u_<name>`
(inside a wrapper: `u_ip`, `u_regs` or `u_win`), nets `<inst>__<port>` and `<link>__<signal>`. `build.yaml` is
generated too (sources from the components). `gen/manifest.json` records the input files' SHA-256, every component
with its version, variant and parameters, every output's SHA-256 and the diagnostics. CI fails if the committed
`gen/` differs from what the generator writes (`flow.blockdesign check`).

The support RTL in [flow/blockdesign/rtl](../flow/blockdesign/rtl): `bd_win_axil_master` (the shell's window as an
AXI4-Lite master: ADDR, WDATA, CTRL, STATUS and RDATA registers), `bd_axil_win` (an AXI4-Lite slave in front of a
register window) and `bd_axil_regs` (the register bank). `bd_axil_win` decodes its whole 4 KB range: window word w is
at offset 4 x w (0x000 to 0x1FC), and an access from 0x200 up answers SLVERR, so the rest of the range never aliases the
window (the C header gives `<SLAVE>_WINDOW_OFFSET` and `<SLAVE>_WINDOW_WORDS`). The parameter guards in this RTL and in
`axil_xbar` are `initial` blocks: they stop a simulation, and synthesis ignores them; the generator's own checks run
first.

## The viewer

`gen/graph.json` is the diagram's data; [viewer.py](../flow/blockdesign/viewer.py) draws each level as SVG (left to
right, and top to bottom for a phone) and the site's script adds level tabs and a drawer per block: variant and the
other variants' cost, every parameter and its origin, interfaces, address range and registers, the measured cost of
the variant (`flow/ipvariants`), and, after a build, the block's LUT, FF, block RAM and DSP and the worst setup slack
of the paths ending inside it. `python3 -m flow.blockdesign view` writes a stand-alone page; the site has one page
per block design.

`python3 -m flow.blockdesign annotate designs/<name> --build <build dir>` reads the routed checkpoint (Vivado), runs a
second synthesis of the same sources with the hierarchy kept (for the connectivity, which the routed netlist's rebuilt
boundaries hide), and writes `results/blockdesign/<name>/build.json` with the **graph check** (`hiercheck.py`). The check
takes nothing about the design's structure from the graph itself:

- **instances:** every block of the graph (and each wrapper's library block and register bank or window adapter) is in
  the synthesised netlist at its instance path with the module the graph names; every netlist cell directly inside the
  top or inside a generated module (a hierarchy or a wrapper, known from `gen/rtl`, not from the graph) is in the graph;
- **links:** each link the graph draws between two blocks is a net between their cells in the direction drawn (the
  master's `AWVALID` out to the slave's; each signal bit from its source to its sink), and every net between two blocks'
  cells is drawn. A link through logic (an inverted bit) or whose pins synthesis removed is counted as not visible, not
  passed; the reset synchroniser's fan-out is not drawn and not compared;
- **address map:** each crossbar slave's base and size in the graph equal the `S_BASE` and `S_BITS` of the generated top
  that was built (its SHA-256 is in the build record; a changed file fails the check).

`python3 -m flow.blockdesign hiercheck designs/<name> --record results/blockdesign/<name>/build.json` re-runs the check
without Vivado. Links to the design's own ports and constants are not compared.

## Not yet

- Importing an IP Integrator `.bd` for viewing; a GUI editor; a diff view between two designs.
- AXI4 and AXI4-Stream interconnects, clock converters and width converters (point-to-point links of those types are
  checked and wired); multi-domain hierarchies.
- Interrupt concatenation; a debug core added by block automation.
