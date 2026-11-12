# From one run to a design environment (brief 27, Part A: design)

The owner asked whether the agent could become a working design environment for an FPGA engineer, not only a
showcase. Routine work would be automated, the right know-how would be at hand, and each phase would use the better of
project mode and non-project mode. The proposed shape:

- a grill-me session for the specification;
- verified component modules produced in a loop, several in parallel, on hardware where possible;
- the same for the whole design, with the modules brought together;
- refinement by natural-language prompts, re-entering the flow at the right point.

This page is the design. **Nothing on it is built unless it is marked "exists" with a path.** Part B, a pilot on one
multi-module design, waits for the owner's approval of this page. Words used below:

- **exists**: in the repository today; the path is given;
- **new**: proposed here;
- **gap**: missing, and named so that a later brief can pick it up.

## Summary

- **A design is a git repository with a `design.yaml`.** Each module directory has the same shape as today's
  `designs/<name>/`, plus a `contract.yaml`. The existing single-spec run (`python -m agent run`) becomes the inner loop
  of each module, unchanged. The project layer sits above it, so the eval-1 request paths and the registered tools stay
  as they are.
- **Interfaces first.** Every escape recorded on the course tier so far happened at the spec/interface level: port
  names, a register map, a data format, a pin's electrical type. Phase 0 therefore settles contracts before any RTL is
  written.
- **Every stage's outputs are keyed by the hash of its inputs.** Re-entry after a change is worked out from the files
  that changed and the module graph, never from the model's opinion. The per-run caches that exist today
  (`_sources_hash`, `_evidence_key` in `agent/graph/run.py`) become one cache for the whole project.
- **Agent work is commits on branches; the user merges.** Files or regions the engineer marks as their own are never
  written by the agent; the agent proposes a patch instead.
- **Vivado is scheduled under the machine's rules** (at most two synthesis jobs, never two implementation runs).
  Simulation and model calls run in parallel.
- **The user surface:** a CLI first, then the existing MCP server pattern, then a static project dashboard built from
  the evidence files. No GUI framework.
- **"More than a showcase"**, cheapest first: (a) the owner uses it on his own portfolio projects; (b) other people run
  it, which needs a way round the private knowledge bank; (c) anything commercial, which needs the owner's own
  employment-contract check first. This page says nothing more about (c).

## 1. What exists, and what a real design needs

| Need | Exists today | Path | Missing |
|---|---|---|---|
| One spec to one bitstream | the stage machine (10 stages, 0 clarify to 9 configuration-and-debug), gates decide every exit | `agent/graph/stages.py` (`MACHINE`, `exit_check`, `route_failure`), `agent/graph/run.py` | more than one module |
| Spec interview | one question at a time, each with a default and a reason; answered by a human, an oracle or the default; capped at 12 questions | `agent/graph/interview.py` (`Interview`, `SpecOracle`, `max_questions = 12`) | requirement IDs are in `spec.yaml` (`spec_schema.requirement_errors`) but questions are not tied to them; no decomposition; no test plan per requirement at interview time |
| Stage review and rewind | a review page at each stage end; approve, edit (a prompt to one role), rewind, or supply the architecture | `agent/graph/review.py`, `node_review` in `agent/graph/run.py`, `resume --reply` in `agent/__main__.py` | review of a change across several modules |
| Snapshots | each stage end is a commit in a per-run bare repo `<run_dir>/snap.git`, with a SHA-256 manifest; `.dcp` files are copied; rewind is hash-checked | `agent/graph/snapshot.py` | the commits live outside the design; there are no branches and no merge |
| Owner edits | a change made while the run is paused is found against the manifest, committed with author `owner`, gated again and listed in `build/who_did_what.json` | `agent/graph/ownership.py` (`hand_edits`, `record`) | detection only while paused; files only, not regions; no rule against later overwriting |
| Roles and jails | clarify, blind model, test writer and RTL writer each work in a path jail; per-role models | `agent/graph/roles.py` (`ROLES`, `RoleJail`), `agent/graph/role_models.py` | none for this design |
| Repair, not regeneration | a failure is traced to the role that wrote the failing artefact; other artefacts stay frozen | `agent/graph/repair.py` (`stage2_owners`) | tracing to a *module* |
| Architecture as data | blocks, interfaces (protocol from `axi4-lite`, `axi4-stream`, `simple`, `uart`, `gpio`, `other`), clock domains, crossings, predicted resources; hash-pinned approval | `flow/architecture.py` (`PROTOCOLS`, `CDC_PRIMITIVES`, `write_approval`) | the blocks are inside one design; nothing checks a block against another design's contract |
| Build cache | a build is skipped when the hash of its sources matches a cached build that went at least as far | `_build` / `_sources_hash` in `agent/graph/run.py` (`build_cache_<variant>.json` in the run directory) | per run only; no key for tool versions or the knowledge bank |
| Verification | V0 to V3, mutation, structural CDC check, CDC delay injection, optional independent spec-only bench | `flow/verif_gates.py`, `flow/cdc_structure.py`, `flow/cdc_inject_run.py`, `agent/graph/spectest.py` | system-level tests across modules |
| Implementation | non-project Tcl in UltraFast stages; `post_synth.dcp` and `post_route.dcp`; gates per stage | `flow/build.tcl`, `flow/gates.py` | out-of-context (OOC) builds of a module (only `flow/ipgen/tcl/ip_flow.tcl` runs `synth_design -mode out_of_context`, for AMD IP); `read_checkpoint -incremental`; `read_ip` (brief 18: "gap") |
| Hardware in the loop | a UART register shell (window 0x80 to 0xFF, 32-bit data), bring-up script, ILA capture | `shell/rtl/fpga_shell.sv`, `shell/PROTOCOL.md`, `flow/bringup.py` | a wrapper that puts one *module* behind the shell |
| Cross-probing | worst paths and high-fanout nets with RTL file, line and module, as JSON; repair visits see `cross-probe:` lines | `flow/xprobe.tcl`, `flow/xprobe.py`, `_stage_pass` in `agent/graph/stages.py` | none for this design (module = first hierarchy level of the cell name, which is what integration tracing needs) |
| AMD IP from design tools | FIR, CIC, BMG and DDS adapters: spec, then `.coe`/`CONFIG.*`, then a bit-exact xsim check, then OOC synthesis | `flow/ipgen/`, `docs/ipgen.md` | not a module type the agent can choose |
| Version pin | `gates.json` records the Vivado version and the version the knowledge bank was measured on | `flow/version_pin.py` | none for this design (the cache key uses it) |
| Tools for other clients | the core's tools as an MCP server for one design directory | `agent/mcp_server/server.py` | run control (`run`, `resume`, the review reply) is CLI-only; nothing at project level |
| Heavy-job limits | the Vivado runner refuses to start above `FDA_VIVADO_MAX` (default 1) jobs or below `MIN_AVAIL_GB` (default 7) free; mutation takes the shared lock (`FDA_HEAVY_LOCK`) | `flow/run_vivado.sh` (`preflight`), `flow/mutate.py` | a scheduler across modules |

Evidence so far covers single designs only: T1, the board self-checks and the course-tier development tasks. Eval-1 was
stopped and reports nothing (README). No multi-module design has been shown.

## 2. The project, not the run

### Layout

```
my_design/                         a git repository; the user owns main
  design.yaml                      the module graph, the clock and reset plan, ownership marks, settings
  system/
    spec.md                        the user's words
    requirements.yaml              S-1, S-2 ...: system requirements, each with a proof method and the modules it touches
    system_tests/                  cocotb tests of the integrated top, against a system model made from the module models
  modules/
    <module>/                      the same shape as designs/<name>/ today:
      spec.md  spec.yaml           (M-<module>-1 ... requirements, each traced to an S- requirement)
      contract.yaml                NEW: the interface contract (below)
      model.py  tests/  verif/     blind model and tests, from spec.yaml and the contract only
      rtl/  build.yaml
      ooc.xdc                      NEW: module-boundary constraints (clocks from the contract; I/O budgets; brief 20 rules)
      architecture.yaml  ARCHITECTURE.md
      evidence/                    NEW: committed copies of gates.json, verif_gates.json, OOC timing and utilisation, HIL result,
                                   each with the input hash it was made from
  top/                             generated from the contracts (phase 2); a module like the others, with the board's XDC
  .fda/                            NEW: cache index (input hash -> outputs), scheduler state, run ids; not hand-edited
```

Every module directory works with today's single-design tools on its own (`flow/run_vivado.sh`, `python -m agent run`,
the MCP server with `--design`). The project layer only adds `contract.yaml`, `ooc.xdc` and `evidence/`, and drives the
existing loop. Nothing inside `agent/graph/` has to know about the project. That is how the eval-1 request paths stay
byte-for-byte the same (`agent/tests/test_08f_golden_requests.py`): the module loop *is* the eval-1 request path, with
new inputs.

### `design.yaml` (sketch)

```yaml
schema: fpga-design-agent/project/v1
name: video_median
board: nexys_a7_100t
clocks:                                   # one clock and reset plan for the whole design (phase 2 generates it)
  - {name: clk_sys, source: board, mhz: 100}
  - {name: clk_pix, source: mmcm, mhz: 74.25, from: clk_sys}       # M/D/O from flow/mmcm_search.py; wizard as checker
resets:
  - {name: rst_sys, domain: clk_sys, style: sync_active_high, from: board_button}
  - {name: rst_pix, domain: clk_pix, style: sync_active_high, from: rst_sys, via: reset_sync}
modules:
  - {name: timing_gen, kind: rtl,  domain: clk_pix}
  - {name: median3x3,  kind: rtl,  domain: clk_pix}
  - {name: regs,       kind: rtl,  domain: clk_sys}                 # host registers behind the test shell
  - {name: fir_lp,     kind: ipgen, adapter: fir}                   # brief 19 adapter: an AMD IP module
  - {name: sync_fifo,  kind: lib,   ref: ip_lib/axis_skid@1.2.0}    # brief 28 library module
connections:
  - {from: timing_gen.video_out, to: median3x3.video_in, contract: axis_video_rgb}
  - {from: regs.ctrl,            to: median3x3.ctrl,     contract: ctrl_word, crossing: {from: clk_sys, to: clk_pix, primitive: xpm_cdc_array_single}}
owned:                                    # the engineer's files and regions (section 7)
  - modules/median3x3/rtl/window_buf.sv
settings: {interview: on, review: on, profile: cvdp, verif_level: V3}
```

### `contract.yaml`: the interface contract

One per module, approved by the user in phase 0 and hash-pinned the way the architecture approval is
(`flow/architecture.py` `write_approval`, which stores the SHA-256 of the files; a later edit fails the gate). Fields:

| Field | Content | Why (the evidence) |
|---|---|---|
| `ports` | name, direction, width, signedness, the clock it belongs to; for top-level ports also the board resource and electrical type (push-pull, open drain, pulled up) | c12 run 1 (a missing `LED` port), c12 run 2 (an open-drain pin driven as `1'bz` read as Z), c14 tiny CNN run 1 (missing `UART_TXD_IN`), c14 int8 run 2 (`LED0` against `LED[15:0]`) |
| `clocks`, `resets` | the domain of every port; reset style and polarity | the CDC gate (brief 16) needs the declared crossings |
| `protocol` | one of `PROTOCOLS` in `flow/architecture.py`: AXI-Stream (`tdata` width and packing, `tuser` and `tlast` meaning, back-pressure allowed or not) or AXI4-Lite (address map); brief 17's skills give the handshake rules | brief 17: the hold-rule monitor and skid-buffer checks run against this |
| `registers` | offset, width, access, reset value, bit fields: the same form `interview.answer_register_rows` reads | c15 softmax run 2 (invented register map), c10 DDS run 1 (bit layout of a packed register) |
| `data_formats` | number format of every data field and file (signed, width, fraction bits, how it is packed in a word) | c14 tiny CNN run 2 (8-bit signed weights stored zero-extended in 32-bit words, read as sign-extended) |
| `latency`, `throughput` | cycles from input to output (a number, a range or a formula in the parameters); beats per cycle, and the duty cycle the source may use | the system model needs them to line up module outputs |
| `parameters` | the module's parameters with their allowed values | brief 28's declared parameter space |

The contract is the interface the blind model, the tests and the RTL writer all read. A contract test (new) is
generated from it mechanically, not by a model: port list and widths at elaboration, register reset values and access,
the AXI handshake rules under random `tvalid`/`tready`. It runs before any role-written test.

### Module graph

```
              system/spec.md -> requirements.yaml (S-1 .. S-n)
                                     |
            +------------------------+-------------------------+
            v                        v                         v
   modules/timing_gen        modules/median3x3            modules/regs
   spec, contract, tests     spec, contract, tests        spec, contract, tests
   OOC evidence              OOC evidence                 OOC evidence (+ HIL via shell)
            |  axis_video_rgb        |                         |  ctrl_word
            +----------------------->+<------------------------+  (clk_sys -> clk_pix, xpm_cdc_array_single)
                                     |
                                     v
                     top/  (generated: instances, clocks, resets, CDC, board XDC)
                     system tests, full implementation, board run
```

Arrows are contracts. A contract change marks both ends and the top as stale (section 6).

### Status and evidence per module

`evidence/status.json` (new) holds, per module: the stage reached, the V-level, the OOC WNS and resources against the
architecture's prediction, the HIL result, and for each item the input hash it was made from. A status is **current**
only when its input hash equals the hash of today's inputs. The dashboard (section 9) reads nothing else.

### Branches and commits

Today's per-run `snap.git` (`agent/graph/snapshot.py`) is replaced by the project repository itself. Each agent task
runs on a branch `fda/<phase>/<module>/<run-id>` in its own git worktree. Each stage end is a commit by `fda-agent`
(the same `Snapshots.take` call, pointed at the project repository), and each owner hand edit is a commit by the
owner (as `ownership.py` does now). The agent never pushes to `main`. The user merges, after seeing the diff and the
evidence (section 6). Rewind stays as it is: check out the stage's commit and verify the manifest.

## 3. Phase 0: the grill-me session

The interview (`agent/graph/interview.py`) becomes a structured spec session in four passes. Each pass ends with a
review the user approves (the existing `node_review` interrupt).

1. **Requirements with IDs.** The clarify role turns `system/spec.md` into `requirements.yaml`: S-ids, text, a proof
   method each (`spec_schema.PROOF_METHODS`, defaulted by `propose_proof` as now). Every question it asks names the
   S-id it settles.
2. **Interface-first decomposition.** The role proposes modules, connections and a `contract.yaml` each, before any
   behaviour. The user approves the graph and the contracts. Questions in this pass are driven by the contract fields
   rather than left to the model: every field of every contract that is not stated in the spec becomes an explicit
   question with a default and a reason. This generalises `ensure_register_question` (today the harness adds the
   register-map question itself when the request names a host interface without offsets) to ports, electrical types,
   data formats and latency.
3. **A test plan per requirement.** For each S- and M-requirement, the planned tests and their proof method (the
   `verif/testplan.yaml` form, `agent/core/artefacts.py` `check_testplan`), written before the RTL.
4. **Open questions as assumptions.** A question the user does not answer is never silently defaulted. It becomes an
   entry `assumptions: [{id: A-3, text, default, reason, affects: [S-2, median3x3.contract.latency]}]`. The dashboard lists
   the open assumptions, and a change that resolves one is an ordinary phase 3 change.

The 12-question cap (`Interview.max_questions`) becomes a per-pass budget, and the count is recorded.

### What the record says so far (prior evidence, not a measurement of this design)

`python3 results/course/summarise.py`, on the committed course-tier runs: 21 runs scored, 13 hidden passes, and 6 escapes,
**all at level `spec-interpretation`**. The records' `failure` fields, with the contract field that would have carried
each one (that column is my classification, not a measurement):

| Run | Recorded cause (short) | Contract field |
|---|---|---|
| c10_dds_sine run 1 | DATA register packed as two sign-extended halves; the map has 12-bit samples with the other bits 0 | `registers` (bit fields) |
| c12_nexys_pwm_audio run 1 | the hidden bench connects `LED`; the top has no such port | `ports` |
| c12_nexys_pwm_audio run 2 | the open-drain pin was driven `1'bz` and read as Z | `ports` (electrical type) |
| c14_int8_dot_requant run 1 | "spec ambiguity plus clarify-stage gap" (no further detail recorded) | unclear |
| c14_int8_dot_requant run 2 | the task names `LED0`; the board convention is `LED[15:0]` | `ports` |
| c14_nexys_tiny_cnn run 1 (fail) | `UART_TXD_IN` missing from the top | `ports` |
| c14_nexys_tiny_cnn run 2 | weights stored zero-extended, read as sign-extended by both model and RTL | `data_formats` |
| c15_softmax_unit run 2 (fail) | the register map was never asked for and was invented | `registers` |

So 7 of these 8 non-passing runs failed on a fact that a contract field names, and one is unclear. This is why phase 0
is interface-first. It does not show that a grill-me would have caught them: in several runs the fact was absent from
the public spec, so only a human (or the oracle) could have answered.

### Measurement (Part B, pre-registered here)

On two real specs (the pilot's, and one more the owner writes), with the owner as the user, record:

- questions asked per pass, answered, and left as assumptions; the owner's minutes in the session;
- for every later change to a requirement or contract (phase 3, or a repair routed to stage 0 or 1), whether a phase 0
  question had covered it: **asked and answered differently**, **asked and left as an assumption**, or **never asked**.

"Changes it would have prevented" = the third class, judged by the owner at the end against the question log (no model
judges this). Null first: if phase 0 asks more questions and the "never asked" count does not fall against the plain
interview on the same spec, the structured session is not worth its time.

## 4. Phase 1: the module loop

```
for each module, in dependency order where needed, else in parallel:
   reuse before generate: a library module whose ip.yaml matches the contract?  -- yes --> use it (kind: lib), go to release
   kind ipgen?  -- yes --> flow/ipgen adapter: design, create_ip, bit-exact xsim, OOC synth (brief 19)
   else  python -m agent run modules/<m>/spec.md  in module mode:
            stage 0  takes the approved spec.yaml and contract (no new interview unless a field is missing)
            stage 1  architecture inside the module
            stage 2  contract test first; then blind model, tests and RTL; V0..V3 (unchanged)
            stage 3  ooc.xdc instead of pins: clocks from the contract, I/O budgets at the boundary (brief 20 rules)
            stages 4-8  OOC synthesis and implementation; gates as now, minus the board-only ones
            stage 9  HIL behind the shell when the contract allows (below), else skipped and recorded
   release when: contract test pass, V-level reached, OOC timing met at the contract clock, resources in range
   promote to ip_lib when it passes brief 28's reuse checks (below)
```

- **Module mode (new) changes inputs, not prompts.** The stage machine, prompts and gates stay as they are. The
  differences are: the spec and contract come in approved; `build.yaml` gets `mode: ooc` (a new switch in
  `flow/build.tcl`: `synth_design -mode out_of_context`, the form `flow/ipgen/tcl/ip_flow.tcl` already uses); the board
  pin checks (`check_constraints`, `FDA-CON-*` pin rules) are skipped because there are no pins; and stage 9 uses the
  HIL wrapper. Whether module mode counts as a new evaluation under the golden-request rule is decided when it is built.
  Today's rule is that any changed request path is a new evaluation.
- **HIL where the shell allows (new wrapper).** The shell gives the design a 7-bit window address and 32-bit data
  (`shell/rtl/fpga_shell.sv`: `win_addr`, `win_wr`, `win_rd`, `win_wdata`, `win_rdata`). A generated wrapper maps an
  AXI-Lite contract onto the window directly. For an AXI-Stream contract it puts a small input FIFO and an output FIFO
  behind registers, so the host pushes beats, pulses a start and reads results. Each window access is an 8-byte request
  and a 7-byte response at 115200 baud, about 1.3 ms (150 bits; arithmetic from `shell/PROTOCOL.md`). That rules out
  testing throughput, and real-time modules (video timing) are checked by ILA capture instead (`flow/ila.py`). A module
  that drives board pins directly is tested at integration only.
- **Reuse before generate.** Before stage 2 writes new RTL, the agent looks in the library for an entry whose `ip.yaml`
  matches the contract (interface type, clocks and resets, parameter range, latency). The lookup goes through evidence
  files and a KB index skill, not a new registered tool (brief 28, section 3). A match becomes `kind: lib` at a pinned
  version, and only its contract test and the module's own requirements run.
- **The library's cost tables feed choices made from the spec.** The per-parameter tables of resources and Fmax
  (brief 28, section 2, in the format of `docs/ipgen_tradeoffs.md`) let the architecture stage choose parameters such
  as width, depth and pipelining from the spec's clock and resource budget. The architect then predicts from measured
  data instead of guessing.

### Parallelism and the machine

The work falls into resource classes with fixed limits:

| Class | Examples | Limit (house rules, 2026-11-04) | How it is held |
|---|---|---|---|
| model calls | role turns, oracle | the per-run and project USD/token caps; the Max-plan usage schedule | `Meter` in `agent/graph/llm.py`, plus a project meter |
| simulation | cocotb on Icarus or Verilator, formal, mutation | CPU cores; mutation and Verilator builds count as heavy | mutation already takes `FDA_HEAVY_LOCK` (`flow/mutate.py`) |
| Vivado synthesis (OOC or full) | stages 4, ipgen synth | two at once; the second only while more than 12 GB is free | `_handoff/take_heavy_slot.sh`, `FDA_VIVADO_MAX=2` (`flow/run_vivado.sh`) |
| Vivado implementation | stages 5 to 9, full top | one at a time, never two | the `Vivado impl` lock text |
| board | HIL, bring-up | one board, the owner's OK for any run | `HardwarePolicy`, stage 9 pause |

The scheduler (new, in the project layer, not in the graph) is plain code. Model and simulation work runs as wide as
the caps allow. Vivado jobs are queued longest first: the module with the largest predicted resources
(`architecture.yaml` prediction) and its OOC synthesis go first, so the long jobs do not end up last on two slots.
Recorded scale on this PC (Vivado 2026.1): the T1 base build took 168.9 s of Vivado wall time and the ILA build 424.1 s
(`results/f0a_2026_1/t1_dimmer_counter.md`); MIG example synthesis took 349 to 509 s (`docs/project_mode_parity.md`, section 2).
Modules never share a worktree, so parallel module work cannot write the same file.

### Promotion to the library

After a module is released it may be promoted to `ip_lib/`. It enters the library only when it passes brief 28's reuse
checks: its declared parameter space (`ip.yaml`), elaboration guards for every value outside that space, sweep
verification at the corners and at random points, and the sweep cost table from OOC synthesis. A module that passes at
its default parameters only is released for this design and is not promoted. The details are in brief 28
(`_handoff/fpga_agent/28_design_for_reuse_ip_library_brief.md`, sections 2 and 3).

## 5. Phase 2: integration

- **The top is generated from the contracts, not written by a model.** The project layer emits `top/rtl/top.sv`: one
  instance per module, connections from `design.yaml`, the clock plan (an MMCM instantiated directly, values from
  `flow/mmcm_search.py`, with the Clocking Wizard as a batch checker as brief 18 recommends), reset synchronisers per
  domain, and an XPM CDC macro at every declared crossing (`CDC_PRIMITIVES` in `flow/architecture.py`). An undeclared
  crossing is a phase 2 failure through the structural CDC gate (`post_synth_cdc_structure_clean`, brief 16).
- **Interconnect.** AXI-Stream links are wired point to point, or through a generated register slice when a contract
  needs one. AXI-Lite with several targets uses a generated 1-to-N decoder (brief 17's survey row F56 describes the
  block). AMD SmartConnect or the AXI-Stream switch IP need `read_ip` or block-design input in `build.yaml`, which
  brief 18 lists as a gap, so they come after that gap is closed (owner decision 3).
- **System tests.** `system/system_tests/` run the generated top against a **system model** built by chaining the
  module models (`Model.step` from `agent/graph/contract.py`), lined up by the contracts' latencies. The run checks every
  internal boundary as well as the outputs: a monitor at each connection records the beats and compares them with the
  producing module's model.
- **Full implementation and the board run** go through today's stages 3 to 9 on `top/`, with the board XDC, the
  ILA variant and `flow/bringup.py`.

### Tracing a failure to its module

| Failure | How the owning module is found | Then |
|---|---|---|
| a system test | the first connection whose recorded beats differ from the producer's model output names the producer; matching beats with a wrong consumer output name the consumer | replay the recorded boundary trace into **both** sides' contract tests: if the producer violates the contract it is the producer's repair; if the trace is legal and the consumer fails, the consumer's; if both pass, the contract itself is wrong (back to phase 0 for that connection) |
| timing | `xprobe.json`: the start and end cells' module (first hierarchy level) and RTL file and line | a path inside one module goes to that module's stage 6; a path across a boundary goes to the contract (registered outputs?) and both modules |
| CDC | `cdc_structure.py` names the cells, and so the instance | an undeclared crossing is a `design.yaml` error; a declared one built wrong goes to the generator |
| resources, power | `utilization_hier.rpt` (already written by `flow/build.tcl`) per instance, against each module's prediction | the module over its prediction |
| board | a UART register read or an ILA capture against the system model | the probe's module |

This is `agent/graph/repair.py`'s rule (a failure is evidence about one artefact) applied to the module graph instead
of the roles.

## 6. Phase 3: refinement by natural language

A change request is handled in two steps, and only the first uses a model.

1. **Proposal.** The clarify role turns the request into edits to `requirements.yaml`, contracts, `design.yaml` or a
   module `spec.yaml`, with a list of the questions it raises (phase 0 rules). The user approves the edits.
2. **Impact, computed.** From the approved edits the project layer computes the impact itself: which requirements,
   contracts, modules, tests and constraints change, and the earliest stage that must run again in each affected
   module. It uses the input table and the module graph below. The model's own claim about the impact is shown next to
   the computed one, and a difference between them is reported, but only the computed impact is used. This is the same
   rule as `route_failure`: routing is decided from tool output, never by the model.

### What each stage reads (the input hash)

| Stage (module) | Inputs hashed | Re-entry when these change |
|---|---|---|
| 0 clarify | `spec.md`, the approved contract, the parent S-requirements | requirement or contract edit |
| 1 architecture | `spec.yaml`, `contract.yaml`, library cost tables | contract, parameter or resource budget |
| 2 RTL and verification | `spec.yaml`, `contract.yaml`, `architecture.yaml`, `rtl/`, `model.py`, `tests/`, `verif/` (today's `_evidence_key` plus the contract) | behaviour, RTL or tests |
| 3 constraints | `ooc.xdc` (module) or the board XDC (top), the clock plan | clock, I/O budget, exception |
| 4 synthesis | the RTL and constraint sources (today's `_sources_hash`), `build.yaml` | any source |
| 5 to 8 implementation and closure | the post-synthesis checkpoint hash, directives | synthesis output changed |
| 9 HIL and board | the bitstream, `hw_checks.py`, probes | anything upstream |

Every key also includes the tool fingerprint: the Vivado version and the knowledge bank's measured version
(`flow/version_pin.py`), the simulator versions (the runner already reads the Verilator version), the knowledge-pack
hashes (`knowledge/PACKS.md`) and the commit of the `flow/` scripts the stage runs. A tool upgrade therefore invalidates
exactly what it should, and a cached result is never reused across Vivado versions.

### Re-entry logic

```
 change request (NL)
      |
      v
 [model] proposed edits ---- user approves ----+
                                               v
 [code]  diff the edited files -> stage input hashes -> stale (module, stage) pairs
                                               |
              contract edited? -- yes --> both ends of the connection + top: stale from stage 1
                                               |
              requirement edited? --> its traced modules: stale from stage 0; their tests regenerate
                                               |
              parameter only? --> module stale from stage 2 (tests at the new value) or 4 (if behaviour unchanged)
                                               |
                                               v
 for each stale module: earliest stale stage = min over its stale inputs
 modules with no stale input: cached evidence reused, NOT rebuilt
                                               |
                                               v
 re-run (scheduler, section 4) --> every unaffected test runs again as regression (simulation is cheap; it is never skipped)
                                               |
                                               v
 top: re-integrate if any module changed; implementation incremental when the change is small (below)
                                               |
                                               v
 review page: the diff, the impact (computed against proposed), the evidence, the time against a full rebuild --> user merges
```

- **Incremental implementation.** For a small change, the top's implementation uses `read_checkpoint -incremental` with
  the last routed checkpoint (`post_route.dcp`, already written by `flow/build.tcl`). Brief 18 lists this as a gap. Its
  benefit on this PC and these designs has not been measured. Part B measures it against a full run on the same change,
  and drops it if it does not help.
- **OOC reuse.** An unchanged module's OOC checkpoint is kept in the cache by its input hash and linked into the top
  rather than re-synthesised. Whether to link checkpoints or re-synthesise the top flat from cached sources is decided
  by measurement in Part B. Flat is the default because it needs no new Tcl.
- **What is not cached:** tests. Every simulation test of every module runs on every change. Board runs need the
  owner's OK each time (house rules).

## 7. The engineer's own edits

- **Any file can be edited by hand,** at any time, not only while a run is paused. The project layer compares the
  working tree with the last agent commit on each branch (today's `ownership.hand_edits`, run before every agent task
  rather than only at a review). A change is committed with author `owner` and makes the stages that read it stale,
  like any other input change.
- **Ownership marks.** `design.yaml` `owned:` lists files (globs). Inside a file, a region is marked:

  ```systemverilog
  // fda:owner begin window_buf   -- hand-written line buffer; the agent may not change it
  ...
  // fda:owner end window_buf
  ```

  The role jail (`RoleJail` in `agent/graph/roles.py`, which already refuses writes to the approved architecture files)
  refuses a write to an owned file. A write to a file with owned regions is accepted only if every owned region is
  byte-identical afterwards. Otherwise the write is refused with the region's name, and the role's repair note says why.
- **Never overwrite without asking.** When a repair is routed to an owned file or region, the agent writes the change as
  a patch (`evidence/proposals/<n>.patch`) and pauses for the owner: apply, edit or refuse. The ledger
  (`build/who_did_what.json`) records the outcome as today (owner, agent or auto).
- **Re-verify.** A hand edit is gated like the agent's work, from the earliest stage its file feeds. An owner edit that
  breaks a contract is reported against the contract, and both ends are re-tested.

## 8. The best of both modes, by phase

The rows are brief 18's inventory (`docs/project_mode_parity.md`, section 1 and the wizard table in section 3).

| Brief 18 row | Phase 0 | Phase 1 (module) | Phase 2 (integration) | Phase 3 (refinement) | Status |
|---|---|---|---|---|---|
| IP management, OOC synthesis and caching | the IP catalogue's licence flag when a module is `kind: ipgen` | OOC synthesis per module; ipgen IP synthesised OOC (exists, `flow/ipgen/`) | cached OOC results linked or re-synthesised | input-hash cache replaces project mode's out-of-date status | ipgen exists; module OOC new |
| Incremental compile | - | - | - | `read_checkpoint -incremental` for small changes, if Part B shows a gain | gap (brief 18) |
| Per-stage checkpoints and reports | - | today's report groups and two checkpoints; `post_place.dcp` added only if a repair needs to resume there | the same on the top | the checkpoints are what incremental and rewind use | exists, small gap |
| Cross-probing (xprobe) | - | repair visits get `cross-probe:` lines (exists) | names the module that owns a failing path | the review page shows the paths a change moved | exists (`flow/xprobe.py`) |
| Wizards as checkers | the Clocking Wizard checks the clock plan in batch (about a minute, `flow/clkwiz_probe.tcl`) | MIG pin rules (`mig_pin_rules.py`, KB) for a memory module | the Timing Constraints Wizard's detections are already the gate reports (`check_timing`, `report_clock_interaction`, `report_cdc`) | re-run the clock check when the plan changes | exists (probes); not wired |
| Run management and strategies | - | - | a directive sweep only if a design fails to close | - | gap, not needed yet |
| Source management | content hashes (`sources_sha256`, `BUILD_STAMP`) | the same per module | the same | the same keys drive the cache | exists, extended |
| Block designs, `read_ip` | - | - | SmartConnect or AXIS switch, if the owner chooses them | - | gap (brief 18) |
| Timing simulation | - | - | post-implementation timing simulation of the top, if a board failure points to it | - | gap |

What stays non-project in every phase: the inputs of a build are a list of files and a hash, one capped process per
job, every check a command with a file, and the constraint order is set exactly.

## 9. The user surface

1. **CLI first** (new subcommands beside today's `run` and `resume` in `agent/__main__.py`):

   ```
   python -m agent project init <dir> --board nexys_a7_100t      # design.yaml skeleton, git init
   python -m agent project spec <dir>                            # phase 0, interactive (replies as today: --reply / --replies)
   python -m agent project build <dir> [--module m] [--jobs N]   # phase 1, scheduler
   python -m agent project integrate <dir>                       # phase 2
   python -m agent project change <dir> "<request>"              # phase 3: proposal, impact, re-entry
   python -m agent project status <dir> [--json]                 # current / stale per module and stage, open assumptions
   python -m agent project review <dir> <branch>                 # diff + evidence page for a merge
   ```

2. **MCP next.** The existing server (`agent/mcp_server/server.py`) exposes the core tools for one design directory and
   is not changed. A second server, `agent.project_server` (new), exposes the project commands above as tools, so Claude
   Code or another client can drive a design. Being a separate server, it adds nothing to the core registry (`TOOLS`,
   `SCHEMA_VERSION` in `agent/core/registry.py`) and leaves the golden-request test alone.
3. **A local dashboard as a static page,** written by `project status --html` from `design.yaml` and `evidence/`. It
   shows the module graph as an SVG (boxes coloured by status, edges by contract), a table of stage and evidence per
   module, the open assumptions, and links to the review pages (`agent/graph/review.py` already writes self-contained
   monochrome pages with light and dark modes, which the dashboard reuses). No server and no GUI framework; it opens
   from the file system.

## 10. What "more than a showcase" means

| Option | What it takes | Cost (estimate, not measured) | Main risk |
|---|---|---|---|
| (a) the owner uses it on his own portfolio projects; the polyphase channeliser first (`_handoff/portfolio_skills/`) | this design built to Part B quality; ipgen gets the FFT adapter (brief 19 lists it as not built) | the build order below, then the channeliser as the second pilot; model spend inside the existing caps | the environment slows the owner down more than it helps; Part B's measures say so early |
| (b) other people run it | an install guide; their own Vivado install and licence (a check of the `REQUIRES_LICENSE` flag before using an IP is a gap: briefs 13, 17 and 21 listed the licensed IP, and nothing in `flow/` refuses it yet); model and cost settings (OpenRouter or a Claude subscription, caps, per-role routing already exist in `role_models.py`); a licence decision for the repository (the code is MIT now) | moderate for the guide and settings. **The blocker is the knowledge bank:** it is private because it summarises AMD and Digilent documents (`knowledge/PACKS.md`). Others get it only if it is rewritten to cite rather than summarise, or each user builds their own from the public procedure, or they run without it (unmeasured) | support load; a public KB with copyright exposure |
| (c) anything commercial | **the owner's own employment-contract check first.** This page goes no further. | - | - |

## 11. Measures of success

| Measure | Definition | Where it comes from |
|---|---|---|
| wall time per module and per design | from task start to release (module) or to the board pass (design), split into model, simulation, Vivado and waiting for a slot | the scheduler's log and `run.json` (Vivado wall time and memory, exists) |
| tokens and cost | per module and per design; cost only from provider-reported usage, tokens from the trace | `agent/core/trace.py` model records (exists) |
| user interventions per phase | questions answered, reviews that were not plain approvals, hand edits, refused patches | the question log and `build/who_did_what.json` (exists) |
| bugs that escape to HIL or the board | a failure first seen at HIL or on the board, traced to a module and a cause | the board result and the failure trace (section 5) |
| re-entry cost | for each change: wall time and tokens of the re-run against a full rebuild of the same edited design, measured, not estimated | both runs, done in Part B |

The baseline is single-module and comes from the committed course-tier records (`python3 results/course/summarise.py`):
mean wall time 2.01 h (18 runs with a value), mean 2,923,111 tokens (21 runs), and mean `plan_cost_estimate_usd` 3.21
(the records' estimate for subscription runs, not a provider bill). A multi-module design has no baseline yet; Part B
makes the first one.

## 12. Build order and the pilot

| Step | What | Needs |
|---|---|---|
| P0 | `design.yaml` and `contract.yaml` schemas and checkers; contract-test generator; `project status` and the dashboard on hand-written evidence (**exists**: [project_layer.md](project_layer.md), `project/`) | code only; CI |
| P1 | phase 0 passes on top of `interview.py`; assumptions; the question log (**exists**: `python -m project spec`, [project_layer.md](project_layer.md#phase-0-the-spec-session-stage-p1), [results/27b_p1](../results/27b_p1/results.md)) | model runs (small) |
| P2 | module mode (`mode: ooc` in `build.tcl`, pin checks skipped), project cache keyed by input hash, scheduler with the slot rules | Vivado; heavy slots |
| P3 | top generator (instances, clock plan, resets, XPM CDC, point-to-point AXIS, AXI-Lite decoder), system model and boundary monitors | simulation |
| P4 | phase 3: proposal, computed impact, re-entry, regression, review page; ownership marks and patch proposals | model runs |
| P5 | the Part B pilot with the owner; then incremental implementation measured | the owner's time, board runs with the owner's OK |

The library work (brief 28) runs in parallel with P0 to P2, and the promotion step joins at P2.

**Choice of pilot (Part B).** The brief suggests the PDM microphone chain from brief 19 (PDM front end, CIC, FIR and an
output stage) or a two-module video pipeline. **The course tier holds out `c10_cic_decimator` and `c12_pdm_decimator`**
(`benchmark/course/split_c9_c12.yaml`). Developing the environment on a PDM-to-CIC chain would mean tuning the agent on
the subject of two held-out tasks, so the PDM pilot should wait unless those tasks are retired from the held-out set. A
video pipeline built from development-split subjects avoids this: timing generator, test pattern and 3x3 median
(`c9_nexys_vga_720p` and `c9_median3x3` are both development tasks), plus a host register block behind the shell.
It should not include an RGB-to-YCbCr stage, because `c9_rgb2ycc` is held out. The three refinements for Part B: a
parameter change (window size or test-pattern colours), an interface change (pixel width or `tuser` meaning on the
video link), and a new feature (a register-selected bypass or a second filter).

## 13. Known gaps and risks

- **Module mode changes request paths.** Any change to what a role is sent is a new evaluation under the golden-request
  rule. Part B runs are design work, not scored evaluations, and the report must say so.
- **Encrypted AMD IP simulates only in xsim.** A `kind: ipgen` module's own tests are the brief 19 xsim harness, while
  the system tests run on Icarus or Verilator. A design with IP in the data path therefore needs either a system test in
  xsim or a bit-exact Python stand-in for the IP in the system model (the ipgen golden models are exactly that for FIR
  and CIC).
- **The system model is only as good as the module models.** Two models that share a misreading pass together. The
  contract tests and the independent spec-only bench (`agent/graph/spectest.py`, `--spec-tests`) are the checks that do
  not share it.
- **The HIL shell is slow** (about 1.3 ms per register access). Module HIL checks function, not rate.
- **Incremental implementation and OOC checkpoint linking are unmeasured** here. They stay optional until Part B
  measures them.
- **One PC.** Two synthesis slots and one implementation slot bound the parallelism. More modules mean a longer queue,
  not more speed.

## 14. Open decisions for the owner

1. **Approve this design for Part B.**
2. **The pilot design:** the video pipeline (recommended), or the PDM chain after retiring `c10_cic_decimator` and
   `c12_pdm_decimator` from the held-out set.
3. **Interconnect:** generated RTL (point-to-point AXIS, AXI-Lite decoder) first, with SmartConnect and the AXIS switch
   after `read_ip` support (recommended); or close the `read_ip` gap before the pilot.
4. **User surface order:** CLI, then a separate project MCP server, then the dashboard (recommended); the core MCP
   server is unchanged.
5. **Scope of "more than a showcase":** (a) only for now, with (b) reconsidered after the pilot once the knowledge-bank
   question has an answer; (c) only after the owner's own contract check.
