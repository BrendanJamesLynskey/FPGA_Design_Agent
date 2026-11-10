# The project layer, stage P0 (brief 27 Part B)

[design_environment.md](design_environment.md) is the design: a design of many modules is a git repository with a
`design.yaml`, an interface contract per module, and evidence that counts only while the inputs it was made from are
unchanged. Stage P0 builds the file formats and the code that reads them, with no tool runs:

- the `design.yaml` and `contract.yaml` schemas and their checkers ([project/schema.py](../project/schema.py));
- the stage keys: the input hash of each (module, stage), chained ([project/stages.py](../project/stages.py));
- `project status` and a static dashboard, from evidence files ([project/status.py](../project/status.py),
  [project/dashboard.py](../project/dashboard.py));
- the contract-test generator and the checks it calls ([project/contract_test.py](../project/contract_test.py),
  [project/contract_bench.py](../project/contract_bench.py));
- a worked example, pilot 1 described but not built: [project/examples/video_median](../project/examples/video_median).

The package sits beside `agent/`, not inside it. It adds no registered tool, and it changes no request path; the eval-1
golden request test (`agent/tests/test_08f_golden_requests.py`) still passes.

## Commands

```
python -m project check     <dir> [--json OUT]               # design.yaml, each contract.yaml, system/requirements.yaml, the board
python -m project status    <dir> [--json OUT] [--html OUT]   # current / stale / missing evidence per module and stage; the dashboard
python -m project hash      <dir> [--module M] [--json]       # the stage keys of today's inputs
python -m project gen-tests <dir> [--module M]                # tests/contract_tb.py and tests/test_contract_rtl.py per module
python -m project spec      <dir> [--interview on|oracle|off] [--hidden-spec F] [--model M] [--usd-cap X]
                                                              # phase 0 (stage P1): requirements, design.yaml, contracts
```

`python -m agent project ...` is the same CLI. `check` and `status` exit with 1 when the checker finds a problem.

## Layout

```
<project>/
  design.yaml                    the module graph, the clock and reset plan, the shell, the board ports, assumptions
  system/spec.md                 the user's words
  system/requirements.yaml       S-<n> requirements: text, proof methods, the modules each one touches
  modules/<m>/spec.md            the module's spec
  modules/<m>/contract.yaml      the interface contract
  modules/<m>/tests/             contract_tb.py and test_contract_rtl.py (generated), later the role-written tests
  modules/<m>/evidence/status.json   evidence items, each with the stage key it was made from
```

Other module files (`spec.yaml`, `architecture.yaml`, `rtl/`, `model.py`, `verif/`, `ooc.xdc`, `build.yaml`) are the
same as in today's `designs/<name>/`. They enter the stage keys as soon as they exist.

## `design.yaml` (`fpga-design-agent/project/v1`)

| Key | Content | Checked |
|---|---|---|
| `name`, `board` | identifiers; `board` is a directory under `boards/` | the board has a `board.yaml` with a master XDC |
| `clocks` | `{name, source: board\|mmcm\|pll, mhz, port (board) \| from (mmcm, pll)}` | each derived clock comes from a declared clock; each board clock is driven by a board port of the same name |
| `resets` | `{name, domain, polarity, style: sync\|async, from, via}` | a reset derived in another domain needs `via` (a CDC primitive) |
| `shell` | `{design_id: 4 ASCII characters, clock, reset}`: `shell/rtl/fpga_shell.sv` | the shell's UART pins are on board ports |
| `modules` | `{name, kind: rtl\|ipgen\|lib, clocks: {contract clock: design clock}, resets: {...}, params, window_base, register_crossings}` | every contract clock and reset is bound; a bound clock is not faster than the contract's `max_mhz`; reset polarity, style and domain match; parameter overrides are in the contract's allowed values |
| `connections` | `{from: <module>.<interface>, to: <module>.<interface>, crossing: {primitive}}` | master to slave, the same protocol and `tdata` width and fields, the same `tuser` bits, both or neither with `tlast`, equal `packet_beats`, a sink that may stall only behind a source that can be stalled, a source with gaps only into a sink that allows gaps; a crossing exactly where the two ends are on different design clocks; every slave connected; each interface connected once |
| `board_ports` | `{name: NAME or NAME[hi:lo], dir, drive: push-pull\|open-drain\|pulled-up\|input, from \| to}` | every bit is in the board's master XDC; the width equals the width of what it is bound to (`<clock>`, `<reset>`, `<clock>.locked`, `shell.uart_rx`/`uart_tx`, `<module>.<port>`, `<module>.<interface>.tuser.<name>`, `<module>.<interface>.<signal>[hi:lo]`) |
| `owned` | paths or globs the engineer owns | inside the project |
| `assumptions` | `{id: A-<n>, text, default, reason, affects, status: open\|resolved}` | ids unique; the dashboard lists the open ones |

## `contract.yaml` (`fpga-design-agent/contract/v1`)

| Key | Content | Checked |
|---|---|---|
| `module`, `hdl_top` | the directory name; the HDL top (default: `module`) | the name matches the directory |
| `parameters` | `{name, default, values \| min, max}` | integers; the default is allowed |
| `clocks`, `resets` | `{name, port, max_mhz}`; `{name, port, clock, polarity, style}` | the ports exist and are 1-bit inputs |
| `ports` | `{name, dir, width (an integer or an expression in the parameters), clock (or async), reset_value}` | unique names; every width evaluates; a `reset_value` only on an output, and it fits |
| `data_formats` | `{name, format: u<N> \| s<N> \| s<I>.<F>, packing}` | the format parses |
| `interfaces` | `{name, protocol (flow/architecture.py PROTOCOLS), role, prefix, clock, reset}` plus, for AXI4-Stream: `tdata {width, fields [{name, bits, format}]}`, `tuser [{bit, name, meaning}]`, `tlast` (its meaning), `packet_beats`, `backpressure`, `source_gaps`; for AXI4-Lite: `addr_width`, `data_width`; `protocol: simple, kind: shell-window` for the test shell's window | every port the protocol needs is in the port list, with the right direction for the role, the right width and the interface's clock; fields fit and do not overlap; a field's format has the field's width |
| `registers` | `{bus: top \| <interface>, map: [{name, offset, access: RW\|RO\|WO\|W1C, reset, width, volatile, fields [{name, bits, port}]}]}` | unique names and offsets, alignment, the reset fits; `bus: top` (the generated top decodes the shell window): every field names the module port it drives (RW, WO: an input) or is read from (RO: an output), of the field's width, and `design.yaml` places the map with `window_base` inside 0x00-0x7F without overlaps and names a CDC primitive for every register whose ports are not on the shell's clock |
| `latency` | `{from, to, cycles: N \| [lo, hi] \| expression}` | interfaces exist; the expression evaluates |
| `throughput` | `{interface, beats_per_cycle, from, out_per_in}` | interfaces exist; `beats_per_cycle` in (0, 1] |

## Evidence and status

`modules/<m>/evidence/status.json` (`fpga-design-agent/evidence/v1`) holds items `{stage, kind, result, key, ...}`
(the format is in the docstring of [project/status.py](../project/status.py)). An item is **current** only when its
`key` equals the stage key computed from today's files. A stage is `pass`, `fail`, `not-run`, `stale` (some item is not
current) or `none`. A module has **reached** the last stage of the unbroken run of passes from stage 0, and **re-enters**
at the earliest stale stage, or else at the first stage without a pass.

The stage key hashes the stage's own inputs and the previous stage's key, so an edit restarts its stage and everything
after it. The inputs per stage are in the docstring of [project/stages.py](../project/stages.py): stage 0 reads the
module's spec, its contract and the system requirements that name it; stage 1 also reads the module's binding in
`design.yaml` and the far end of each connected interface, so a change to one side of a link restarts the other at
stage 1; stage 3 reads the clock and reset plan. The tests pin these rules
([project/tests/test_27b_project.py](../project/tests/test_27b_project.py)).

`provenance: hand-written` marks evidence nobody measured. The status output and the dashboard say so wherever it
appears. All the evidence in the example is hand-written.

## The contract test

`gen-tests` writes, per module, `tests/contract_tb.py` (cocotb; the contract embedded as data) and
`tests/test_contract_rtl.py` (the pytest runner through `flow/cocotb_run.py`, Icarus by default). Both carry the
SHA-256 of the contract. No model writes or reads them.

| Contract content | Generated test | What fails it |
|---|---|---|
| `ports` | `contract_ports` | a missing port, a wrong width (parameters applied) |
| always | `contract_reset` | a master's `tvalid` not 0 during or just after reset, a slave's `tready` unknown, an output not at its `reset_value` |
| AXI4-Stream slave | `contract_axis_slave_<i>` | `tready` unknown; `tready` low when `backpressure: false` |
| AXI4-Stream master | `contract_axis_master_<i>` | `tvalid` unknown; a stalled beat that drops `tvalid` or changes `tdata`, `tuser` or `tlast`; a gap after the stream started when `source_gaps: false`; a packet that is not `packet_beats` long |
| `latency` | `contract_latency_<n>_<from>_<to>` | the first output beat not exactly `cycles` (or within `[lo, hi]`) after the first input beat; output before input |
| `throughput` with `out_per_in` | `contract_throughput_<n>_<i>` | output beats not equal to the input beats times the ratio, under random `tready` where the contract allows it |
| `registers` on an AXI4-Lite or shell-window bus | `contract_registers` | a wrong reset value, an RW register that does not read back, an RO register that changes, a response other than OKAY |

Proof that the generated tests check what they claim to: four fixture modules
([project/tests/fixtures](../project/tests/fixtures)) with ten deliberate contract violations, selected by a `MUT`
parameter. The correct RTL passes every generated test, and each mutant fails exactly the tests listed for it
([project/tests/test_27b_contract_tests_rtl.py](../project/tests/test_27b_contract_tests_rtl.py), CI's rtl-sim job).

## The worked example: pilot 1

[project/examples/video_median](../project/examples/video_median) describes the first pilot from the owner's decision
of 2026-11-10: a CEA-861 720p60 timing generator with a test pattern (`video_src`), a 3x3 median filter per colour
channel (`median3x3`), and the test shell's registers, on the Nexys A7-100T. The subjects come from the development split
only (`c9_nexys_vga_720p`, `c9_median3x3`). There is no RGB-to-YCbCr stage (`c9_rgb2ycc` is held out).

- The video link is AXI4-Stream with one beat on every pixel clock, blanking included: `tuser` = {`de`, `vs`, `hs`},
  `tlast` at the end of each 1650-beat line, no back-pressure, no gaps. The median delays the sideband with the pixels
  (latency `H_TOTAL + 2`), so the board ports take the colours and syncs straight from its output.
- `video_src`'s registers (`PATTERN`, `FRAMES`) are on `bus: top`: the generated top (P3) decodes the shell window and
  crosses to the pixel clock (`xpm_cdc_array_single` for `PATTERN`, `xpm_cdc_gray` for the frame counter).
- Two open assumptions (edge handling, the pattern selected by a register rather than the switches) are listed in
  `design.yaml` rather than guessed.
- The evidence is hand-written: `video_src` has current entries for stages 0 and 1 and a contract test not yet run;
  `median3x3` has a stage 0 entry recorded before its spec gained the edge-handling sentence, so it shows as stale.

```
python -m project status project/examples/video_median --html build/project_dashboard.html
```

## Phase 0, the spec session (stage P1)

`python -m project spec <dir>` ([project/phase0.py](../project/phase0.py)) reads the user's words in
`<dir>/system/spec.md` and writes `system/requirements.yaml`, `design.yaml`, and `modules/<m>/contract.yaml` and
`modules/<m>/spec.md` per module. The drafter is a model (the clarify role); every file it proposes goes through
`check_project`, and the checker's messages go back to it as repair notes (at most three repairs per step).

| Pass | The drafter does | The questions | Log |
|---|---|---|---|
| 1 requirements | S-requirements with proof methods (a missing proof gets `propose_proof`'s default) | its own, each naming the S-ids it settles; budget 12 | `phase0/pass1_requirements.json` |
| 2 decomposition and contracts | modules, connections, a contract per module, the clock and reset plan, the shell and the board pins, with the pass 1 answers; for every field, a word-for-word quote of the spec (`sources`) or a reason (`reasons`) | **made by the harness, not the model:** one per field of the inventory (below) that no quote states; the drafter's value is the proposed default; budget 40 | `phase0/pass2_contracts.json` |
| assumptions | - | every question nobody answered (`not specified`, over the budget, `--interview off`) becomes `assumptions: [{id: A-n, text, default, reason, affects, status: open, by}]` in `design.yaml`; the drafter's own assumptions are dropped | `design.yaml` |

The field inventory (`phase0.inventory`): per contract, each parameter, each clock's `max_mhz`, each reset, each port
outside an interface, each data format, each interface's protocol and role, and for AXI4-Stream its `tdata`, `tuser`,
`tlast`, `packet_beats`, `backpressure` and `source_gaps`, for AXI4-Lite its widths; the register map (one question,
worded so that the oracle answers it with the hidden spec's whole map, as `ensure_register_question` does today); each
latency and throughput. Per design: each clock, each reset, the shell's design ID, each module's `window_base`, each
board pin. The six stream fields that both ends of a connection must share are asked once per connection and settle both
ends. A quote counts only when it is in `system/spec.md` (whitespace and quote marks normalised, at least three
words), the rule the oracle's quotes already follow. A quote proves that the words are in the spec, not that the value
matches them (see the measurement).

After the answers, the drafter applies them. A field it changes without an answer naming it goes back to it as a
repair note (put the draft value back); what is still changed after three repairs is listed under `unasked_changes`
in the pass 2 log. `phase0/session.json` holds the check result and the token and cost totals,
`phase0/llm_calls.json` every call, `phase0/oracle_log.json` the oracle's own record.

**`spec.yaml` stays the stage 1 input.** Phase 0 does not write it. Today's stage 0 clarify writes it per module from
`modules/<m>/spec.md` and the approved contract, and `phase0.spec_contract_errors` holds the two together (the same port
names, directions and widths with the parameter defaults, the same register offsets, names and access). The reason: the
roles and gates after stage 0 (model, tests, RTL, `flow/verif_gates.spec_items`, the spec-test role) read `spec.yaml`'s
behaviour, timing and M-requirements, which a contract does not hold, and replacing it would change every role's request
(the eval-1 golden request test). The contract is the authority on the interface.

Measured on two development-split specs: [results/27b_p1/results.md](../results/27b_p1/results.md). The test-plan pass
(design section 3, pass 3) and an interactive review of the decomposition are not in P1.

## Not in P0

- No module has RTL; the contract tests are generated, not yet run on the pilot (they run on the fixtures).
- Traffic in a contract test runs on one clock per check; interfaces on other clocks are held idle. Registers on
  `bus: top` are checked at integration (P3), with the generated top.
- No tool versions in the stage keys yet (P2 adds the tool fingerprint).
- Port directions are checked against the contract by the contract's own checker, not against the RTL (the existing
  STD-AXI-01 rule checks AXI port directions in the RTL).
- `kind: ipgen` and `kind: lib` modules have no contract checks yet.
