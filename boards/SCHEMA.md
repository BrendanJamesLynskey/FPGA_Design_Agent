# Board files: schema and how to add a board

Each board has a directory `boards/<board>/` with a `board.yaml`, and `boards/catalogue.yaml` lists them all with their trust label
(the generated table is [docs/board_catalogue.md](../docs/board_catalogue.md)). The first two boards (`nexys_a7_100t`, `kr260`) predate this
schema ("legacy": no per-fact sources in the file; their sources are in their README and inventory). Every other board uses the
schema below (`schema: fpga-design-agent/board/v2`). `flow/tests/test_95_boards.py` checks all of it.

## What the tools read (these keys are the interface; do not rename them)

| Key | Read by | Meaning |
|---|---|---|
| `part` | the flow (`flow/prepare.py`), the agent session | the device the board carries, exactly as Vivado names it |
| `master_xdc` | `agent/core/constraints.py` (`check_xdc`, `board_constraints`) | the file, relative to the board directory, from which every pin and I/O standard comes. A port listed there is a "resource" the agent can name. `null` for a board with no usable pin list |
| `clock` | `check_xdc` (clock only on the board's clock input) | `port`, `pin`, `freq_mhz`; a differential clock also has `port_n`, `pin_n`, `differential: true` and the `iostandard`. A board with no PL clock has `port: null`, `status: none` and says why |
| `resources` | `board_constraints` | named aliases and ordered buses over master-XDC ports; a list is an ordered bus, element 0 first |
| `slow_ports` | `flow/io_check.py` | regexes of user I/O with no timing relationship to a clock |
| `thermal` | `flow/build.tcl` via `flow/prepare.py` | the environment `report_power` is run in |
| `uart` | `check_top_ports` | `fpga_rx` and `fpga_tx` ports (the board's side), `default_baud`; a board without a PL UART says `pl_uart: none` |

## What the catalogue adds

- `facts`: a list of `{item, value, source: [ids]}`. Every fact names at least one id from `sources`; a fact the sources do not give is
  written `{item, status: unconfirmed, reason}`. A value that came from general knowledge and not a document is never written as a fact.
- `sources`: `{id: {title, version, url}}`. Versions are exact (a commit, a revision, a date). A document that could not be fetched is not cited.
- `master_xdc_source`: `kind: vendor_copy` (the vendor's file, copied unmodified, with its licence text beside it as `LICENSE-digilent-xdc.txt`),
  `kind: derived` (our own listing written by `tools/board_pins_import.py` from `pins_import.yaml`, which names each source by URL, commit and SHA-256 and states its licence), or `kind: none`.
- `pin_aliases`: a pin that two ports of the master XDC share (a header and an analogue input on the same pin, say). A pin shared without being listed here fails the test.
- `hardware_use`: `owned: true` only for the owner's boards, with the rule that applies. For every other board it says no supply or programming rule is recorded.
- `smoke`: `clk_hz` and `banner` for the generated smoke design (`tools/board_smoke.py`).
- `config`, `thermal`: where a value is an assumption it says `status: assumption` or `unconfirmed` and gives the reason.

## Adding a board

1. Find the part in the vendor's or AMD's documentation (not from memory) and the pins in a vendor constraints file or board file.
2. Copy a vendor XDC only if its licence allows (MIT for Digilent's repository: copy it with the licence text). Otherwise write `pins_import.yaml` and run
   `python3 tools/board_pins_import.py boards/<board>/pins_import.yaml` (it fetches the pinned source and checks its hash).
3. Write `board.yaml` with every fact cited or marked unconfirmed, add the board to `catalogue.yaml` with `trust: documented`, then run
   `python3 flow/board_catalogue.py check` and `python3 flow/board_catalogue.py table --write`.
4. For a board with a free-tier part and a PL clock: `python3 tools/board_smoke.py gen <board>`, build it with `flow/run_vivado.sh boards/<board>/smoke`
   through a heavy slot, then `python3 tools/board_smoke.py record <board>` and raise the label to `built`. A label is never raised without that record.
5. `hardware` needs run records of a real board the owner has; do not claim it for a build.

## Known conventions and gaps

- LED and button polarity is not stated by most vendor constraints files; the smoke design does not depend on it, and a design that does must find it in the schematic.
- Digilent's Zynq files set the PS-only pins aside: the PL pin list of a Zynq board is complete, but its UART, Ethernet, SD and DDR are on the PS and need a PS block design.
- A board whose pin standards depend on a jumper (the ZedBoard's Vadj banks) leaves those pins out of the master XDC until the owner has said which setting the board is on. The owner did on 2026-11-17 for both of his ZedBoards (J18 on 1V8, JP6 removed), so the buttons and switches are listed at LVCMOS18; that is a fact about those two boards and the file says so.
- On an UltraScale+ part Vivado 2026.1 prints a Vivado 12-1411 critical warning during `synth_design -rtl` for a differential input (the RTL view expands an IBUFDS into a DIFFINBUF that cannot take the port's LOC); the real synthesis does not print it and places the pin. `flow/exceptions_check.py` counts it as information (`EXC-XDC-RTL-DIFFINBUF`) only when it does not recur after the RTL stage. No XDC wording avoids it: XDC allows no `if`.
- `flow/program.py` judges XADC/SYSMON readings against limits per family (`roc_for`): the 7-series -1 table by default, AMD DS925 for Zynq UltraScale+ (the K26's -2LV is a 0.72 V part).
