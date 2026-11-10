# FPGA_Design_Agent

An open-source agent that turns a plain-English spec into verified RTL and a bitstream for AMD FPGAs, with every result measured.
Site: **[fpga-design-agent.vercel.app](https://fpga-design-agent.vercel.app)** (built from [site/](site)).

**What it does today.** Given a short request, the agent interviews the user (or, in an evaluation, a stand-in that
answers only from a hidden full spec), plans the design, writes SystemVerilog and its tests, and drives Vivado 2025.2
through synthesis and place and route to a bitstream, stage by stage in the order of AMD's UltraFast methodology. Each
stage ends in a gate run by code, and the agent's own tests never count as a pass: hidden tests written against an
independent model of the spec decide, and those tests are themselves checked by mutation testing. It targets a
Digilent Nexys A7-100T (Artix-7) today. The development runs used Anthropic's Claude Sonnet (`claude-sonnet-5-5`)
through Claude Code.

**What has been measured.** On 11 development tasks, 13 of 21 agent runs passed every hidden test. In 6 more the
agent's own checks passed and the hidden tests failed, each time because it read the spec differently from the test
author; the fixes made since are not yet measured ([results](https://fpga-design-agent.vercel.app/results),
from `results/course/*/run_*.json`). A hand-written reference design passes all its tests on the board
([F0B](#bring-up-on-hardware-f0b)); no agent-built design has been on a board yet.

**What is not yet shown.** There is no held-out score. Development tasks are the ones used to find and fix faults,
so their results are a record of the work, not a measure of how the agent does on new tasks. The first held-out
evaluation (`eval-1`) was stopped on 2026-11-09 before any result was analysed and reports nothing; a baseline
evaluation on a larger benchmark comes next.

The flow itself was proven first, by hand on one small design (milestones **F0A** and **F0B**), with machine-checked
gates, before any model touched it. Everything the agent produces has the same shape as `designs/t1_dimmer_counter/`.

## The flow

```
  spec.md (natural language)
     |
     v
  [1] clarify ......... spec.yaml: ports, pins, clocks, reset, latency, assumptions + reasons,
     |                  open questions; a human signs it off
     v
  [2] architecture .... block diagram, clocking plan, every clock-domain crossing
     |
     +-------------------------------+
     v                               v
  [3] golden model               [4] RTL + XDC
      model.py, from spec.yaml       SystemVerilog, pins from the board XDC,
      alone (never sees the RTL)     false paths for asynchronous inputs
     |                               |
     +---------------+---------------+
                     v
  [5] verify ........ cocotb + Icarus: RTL against the model, directed + random;
                     |  Verilator lint; deliberate mutants must fail the tests
                     v
  [6] implement ..... flow/run_vivado.sh: non-project Vivado Tcl in UltraFast stages (UG949): RTL DRCs,
                     |  synth + QoR assessment, place, route, closure reports, bitstream
                     |  (memory-guarded: one job, 1 thread, 6 GB cap; optional ILA from probes.yaml)
                     v
  [7] gates ......... flow/gates.py, stage by stage: RTL methodology; post-synthesis coverage, DRC,
                     |  methodology, QoR score; post-place hold; post-route slack, CDC, junction
                     |  temperature; bitstream present. Names the first stage that failed
                     v
  [8] bring-up ...... BRINGUP.md for a tester who did not design it, plus the test shell:
                     |  every design answers over the USB-UART, so a script can test the board
                     v
  [9] on the board .. flow/bringup.py: discover, program SRAM by cable serial, UART tests against
                        the model, ILA captures against the model, one JSON result       (F0B)
```

Steps 1-8 were done by hand for F0A. Since F2 the agent does steps 1-8 itself, and only the passes of the
**independent** checks (the blind model's tests, the gates, the hardware) count; its own testbench never does.

## What F0A proves

| Piece | Where | Checked by |
|---|---|---|
| Memory-safe Vivado runner (refuses to start beside another Vivado or below 7 GB free; 6 GB cap; records time and peak memory) | [flow/run_vivado.sh](flow/run_vivado.sh) | local builds, [results/f0a](results/f0a) |
| Non-project Tcl flow with the reports the gates need | [flow/build.tcl](flow/build.tcl) | local builds |
| Gates over the reports, one JSON per build | [flow/gates.py](flow/gates.py) | CI: parser tests against real passing **and** deliberately failing Vivado reports |
| ILA insertion from a probe list, built both ways, cost recorded | [flow/debug.tcl](flow/debug.tcl) | local builds |
| A reusable on-board test shell (UART register protocol, host driver, model) | [shell/](shell/), [PROTOCOL.md](shell/PROTOCOL.md) | CI: cocotb against the model, including 115200-baud bit timing |
| One hand-written T1 design from spec to bitstream | [designs/t1_dimmer_counter](designs/t1_dimmer_counter) | CI: cocotb against the model + mutants; local: gates |
| Board files | [boards/nexys_a7_100t](boards/nexys_a7_100t) | Digilent master XDC (MIT) at a pinned commit |

The T1 build numbers (timing, utilisation, ILA cost, run time and memory) are in
[results/f0a/t1_dimmer_counter.md](results/f0a/t1_dimmer_counter.md); every one comes from the JSON next to it
([results/f0a/README.md](results/f0a/README.md) lists the files).
Programming the board and testing on hardware is milestone F0B (below).

## Bring-up on hardware (F0B)

```bash
python3 flow/bringup.py designs/t1_dimmer_counter
```

One command, no human in the loop: it checks the power gate (`power_ok`: on USB power, as in F0B, a bitstream is
programmed only if `report_power` says at most 0.5 W; see "Board onboarding" below for wall power), finds the one attached board by its JTAG cable serial and
its UART, programs the base build into SRAM (never flash), runs 8 UART tests that compare every response byte with
the shell and T1 models (identity and build stamp, 1,004 scratch loopbacks, error responses, timeouts, framing
errors, the T1 registers), programs the ILA build, arms the ILA by Tcl in step with UART writes, and checks four
captures cycle by cycle against the model (a COUNT write; the PWM at three dimmer levels). It writes
[results/f0b/t1_dimmer_counter_bringup.json](results/f0b/t1_dimmer_counter_bringup.json).

Measured ([results/f0b](results/f0b/README.md)): three runs in a row all PASS in 110.7-114.6 s, with identical
results: 8 of 8 UART tests, 4 of 4 ILA captures, LED on-time 32, 256 and 640 of 1024 clocks at DUTY 0x08, 0x40 and
0xA0, exactly as the model predicts. The tests that need the board are marked `hw` and skipped in CI; CI re-checks
the committed captures instead.

Manual checks by the owner (buttons count as specified, three visibly different dimmer levels):
[results/f0b/manual_checks.md](results/f0b/manual_checks.md).

![T1 running on the Nexys A7-100T: display 40 (brightness) and 0000 (count), DONE and POWER LEDs lit](docs/img/t1_on_nexys_a7.jpg)

## Board onboarding (04c)

Before an agent designs for a board it must know what is on it. For the Nexys A7-100T:

- [boards/nexys_a7_100t/inventory.yaml](boards/nexys_a7_100t/inventory.yaml): every peripheral a design can reach
  (temperature sensor, accelerometer, PDM microphone, PWM audio, Ethernet PHY, USB HID host, USB-UART, QSPI flash,
  DDR2, microSD, XADC) with part, interface, pins, I/O standard, IDs, reset, pull-ups, clocking, a self-check,
  current and whether it is safe on USB power, and a source for every field (reference manual, schematic Rev D.0
  and D.3, data sheets). [tools/inventory_check.py](tools/inventory_check.py) checks every pin against the master
  XDC in CI. Digilent's own demo projects are listed by name only, so later benchmarks can avoid them.
- [boards/nexys_a7_100t/power_budget.md](boards/nexys_a7_100t/power_budget.md): regulators, shared rails, the
  FPGA's thermal limit in still air (thetaJA 18.2 C/W, so about 2.5 W reaches 85 C in a 40 C room). The power gate
  (`flow/hw.py` `power_ok`) now depends on how the board is powered (0.5 W on USB, 2.0 W on wall power, junction
  temperature and rail currents too), and `report_power` is run for the board's real thermal environment.
- Four read-only self-check designs, each with its pass rule pre-registered and a device model in simulation,
  proven on the board 3 times each with `flow/board_check.py` ([results/board_v2](results/board_v2/README.md)):
  [b2_tmp_adt7420](designs/b2_tmp_adt7420), [b2_acl_adxl362](designs/b2_acl_adxl362),
  [b2_qspi_jedec](designs/b2_qspi_jedec) (flash ID only: no write or erase opcode exists in its RTL, which a test
  checks) and [b2_mic_pdm](designs/b2_mic_pdm).

## The UltraFast methodology as the backbone (04e)

The flow and the agent's stage machine follow AMD's UltraFast Design Methodology (UG949 v2025.2) stage by stage:
board and device planning, RTL, constraints, synthesis, implementation, timing closure, power closure, DRC
closure, configuration and debug. [docs/methodology.md](docs/methodology.md) maps UG949's chapters to the plan's
flow steps, the reports `flow/build.tcl` writes and the gates `flow/gates.py` applies (with every threshold cited
to UG949), says where the flow deviates from UG949 and why, and defines the agent's stage machine for F2. The
per-stage procedures the agent reads (exact Tcl, thresholds, common failures) are nine skills in the private
knowledge bank. T1 rebuilt through the staged flow passes every stage with timing and utilisation identical to F0A
([results/ultrafast](results/ultrafast/README.md): +4 s and +168 MiB for the added reports; the power figures
changed because `report_power` now uses the board's thermal environment).

## Knowledge packs (F1A)

The agent's know-how is a set of frozen, hashed knowledge layers in Agent Skills format: generic RTL skills, an AMD
vendor layer built from AMD's open Ross skills (as shipped, and distilled for this batch flow), an Artix-7 device
layer, a Nexys A7 board layer, and an offline searchable library. Since F1A2 the generic layer is a pinned tag of a
separate private generic RTL pack. They summarise AMD and Digilent documents, so they live in a
private repository; [knowledge/PACKS.md](knowledge/PACKS.md) lists each layer's size and hash, which every scored
run will record. [docs/debug_playbook.md](docs/debug_playbook.md) is the human companion to the gates.

Since brief 31 the bank also holds a device-family matrix (where AMD advice differs between 7-series, UltraScale+
and the two Zynq processing systems). The agent reads the target `part` from `build.yaml` and the bank loads only that
family's layer ([agent/tests/test_31_family_selection.py](agent/tests/test_31_family_selection.py)); each area on the
expertise page lists its family differences from [site/data/family_diffs.json](site/data/family_diffs.json).

## The agent core (05a, F2 part 1)

The flow's tools as a harness-neutral core: typed functions with JSON schemas, the same tools as an MCP server
(`python -m agent.mcp_server`), a security layer enforced in code (path jail, no free-form Tcl or shell, hardware
policy, redaction, audit log), and one trace format with replayed-trace CI. No language model is called.
[docs/agent_core.md](docs/agent_core.md) has the tool list, the security rules with their tests, the known gaps
and the trace format; results of the real-tools smoke run are in [results/f2](results/f2).

## The agent (05b, F2 part 2)

A LangGraph + Deep Agents agent over the stage machine: gates decide every stage exit; the blind model, the test
writer and the RTL writer are separate sub-agents whose inputs are enforced in code; a "grill me" spec interview
(human, or a spec oracle that answers only from a hidden full spec); a review page at every stage end with approve /
edit / rewind (files and Vivado checkpoints restored and hash-checked); agent-written benches run in a no-network
container. `python -m agent run|resume`; details in [docs/agent.md](docs/agent.md).

### The Claude Code arm (05c, F2 part 3)

The same graph with each sub-agent turn run by headless `claude -p` on a Claude subscription, configured to
approximate a plain API call: our system prompt replaces the default, built-in tools off, only our MCP server, an empty
home and config. `python -m agent run ... --harness claude_code --cc-model claude-haiku-5-5`; details in
[docs/claude_code_arm.md](docs/claude_code_arm.md). The same release has four agent fixes from the 05b diagnosis (spec
schema, model API contract, integer cycle-count timing parameters, superseded files).

## The benchmark (06a, F3 part 1)

Benchmark v1 for scoring the agent: 24 natural-language tasks for the Nexys A7 (12 T1 blocks, 12 T2 peripherals),
each with a hidden full spec, an independent golden model, cocotb acceptance tests, deliberate mutants, a trap test
where a textbook or demo twin exists, an on-board check and a reference design built through every flow gate. A
third of each tier is held out by a seeded draw and lives in the private repository; a 40-spec training pool for
P1 and an 18-task contamination probe sit beside it. Frozen and hashed: [benchmark/README.md](benchmark/README.md),
[benchmark/FROZEN.md](benchmark/FROZEN.md), the owner's checklist [benchmark/OWNER_REVIEW.md](benchmark/OWNER_REVIEW.md).

A separate course tier (07a1) ports the course projects of Parts 9-16 to the same layout, with its own split and freeze:
[benchmark/course/README.md](benchmark/course/README.md), [benchmark/course/FROZEN.md](benchmark/course/FROZEN.md).

Each course run is recorded in `results/course/<task>/run_N.json` with the escape-rate fields (internal pass, hidden
pass, outcome, escape level, tool runs, tokens, cost; 08a): [tools/run_record.py](tools/run_record.py) derives and
back-fills them, [results/course/summarise.py](results/course/summarise.py) prints per-task pass counts, pass@1/pass@k
and escapes by level.

## From one run to a design environment (brief 27)

[docs/design_environment.md](docs/design_environment.md) proposes how the single-spec run becomes the inner loop of a
project of many modules: a `design.yaml` module graph with an interface contract per module, an interface-first spec
session, parallel module loops under the machine's Vivado limits, a top generated from the contracts, natural-language
changes that re-enter at the earliest stage whose inputs changed (worked out from input hashes, not by the model), and
ownership marks so that the engineer's own edits are never overwritten.

Stage P0 of the pilot is built ([docs/project_layer.md](docs/project_layer.md)): the `design.yaml` and `contract.yaml`
schemas and checkers, stage keys from input hashes, `python -m project status` with a static dashboard, and a generator
that turns a contract into a cocotb contract test (proved on fixture RTL with ten deliberate violations). The worked
example is pilot 1, a 720p test pattern through a 3x3 median filter ([project/examples/video_median](project/examples/video_median)),
described with hand-written evidence; nothing in it is measured yet.

Stage P1 adds phase 0, the spec session (`python -m project spec`, [docs/project_layer.md](docs/project_layer.md#phase-0-the-spec-session-stage-p1)):
from the user's `system/spec.md` it writes the requirements, `design.yaml` and the contracts, all checked; the harness
asks one question per contract field the spec does not state, and every unanswered question is written down as an
assumption. Measured on two development-split specs with the spec oracle: [results/27b_p1](results/27b_p1/results.md).

## Reproduce

Simulation, lint and the Python tests (what CI runs):

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pyserial pytest cocotb==2.0.1   # plus iverilog (apt)
.venv/bin/python -m pytest -q                                   # models, gates parser, host driver, cocotb
designs/t1_dimmer_counter/tests/run_mutants.sh                  # every deliberate bug must be caught
flow/lint.sh                                                    # needs Verilator
```

The bitstream (local only: **Vivado 2025.2** at `/opt/Xilinx/2025.2`, at least 7 GB of available memory (the runner checks), Linux
with `systemd-run --user`):

```bash
flow/run_vivado.sh designs/t1_dimmer_counter both     # base, then the ILA build; gates run after each
python3 flow/summarise.py designs/t1_dimmer_counter --out results/f0a
```

Vivado does not run in GitHub Actions (the install is about 100 GB); its results are committed under `results/`.

## Layout

```
flow/        runner, Tcl flow, ILA insertion, gates, summaries, lint, cocotb helper; board discovery,
             programming, ILA capture and bringup.py (F0B); board_check.py (04c)
flow/ipgen/  external design tools driving AMD IP configuration (brief 19): the xsim file-I/O harness, FIR and CIC adapters
             (scipy design -> .coe/CONFIG.* -> create_ip read-back -> bit-exact xsim check -> OOC synthesis), the signal-chain
             model and diagram; worked examples in results/19_ipgen/
shell/       the test shell: RTL, protocol, host driver, model, tests
boards/      board files (Nexys A7-100T): board.yaml, master XDC, inventory.yaml, power_budget.md
tools/       inventory_check.py (board inventory against the master XDC)
agent/       core/ (tools, security, trace, replay, smoke) and mcp_server/ (05a); tests/ with the replay fixture
project/     the project layer (brief 27 P0): design.yaml and contract.yaml checkers, stage keys, status and dashboard,
             the contract-test generator; examples/video_median (pilot 1, described); tests/ with fixture RTL;
             phase0.py (brief 27 P1: the spec session) and phase0_format/ (the drafter's format example)
designs/     one directory per design: spec.md, spec.yaml, model.py, rtl/, design.xdc, probes.yaml,
             build.yaml, tests/, BRINGUP.md
benchmark/   benchmark v1: tasks (development split), training pool, bench library and tools, manifest, owner review;
             benchmark/course/: the course-tier tasks (Parts 9-16), splits, manifest
results/     committed build and bring-up results, per milestone
hil/         hardware-in-the-loop rigs: cdc_soak/ (the CDC soak rig, brief 11b: RTL, simulation, Vivado builds, run plan)
site/        the showcase site (static, Vercel): export.py (results -> data), build.py (pages, number check),
             leak_guard.py, src/, data/, public/, tests/; the preview link is in the pull request;
             problem catalogue: catalogue.yaml + catalogue_parts/ (domains, descriptions), catalogue_pages.py,
             traces/ (one adapter per task that runs its hidden/model.py for the page animation)
knowledge/   PACKS.md: names, sizes and hashes of the private knowledge packs (no pack content)
docs/        methodology.md (UG949 -> flow stages, gates, deviations, the agent's stage machine);
             verification.md (V-stages, proof methods, the simulator-portable stack, gates, mutation);
             design_standards.md (v1.0: the rule table and how each rule is checked);
             agent_core.md (tools, MCP server, security rules, traces); agent.md (the 05b agent graph; benchmark tasks as agent runs, 07a2-prep); claude_code_arm.md (the 05c Claude Code arm); role_models.md (the 05f per-role model routing); test_writer.md (the 05g test-writer diagnosis, turn trace, formal re-plan, QoR gate);
             project_mode_parity.md (what project mode and the wizards give that non-project mode does not, measured; cross-probing);
             ipgen.md (the ipgen pipeline, the adapter interface, candidate IPs); ipgen_tradeoffs.md (design only: the drop-down trade-off view);
             design_environment.md (design only, brief 27: projects of many modules, contracts, re-entry by input hash, the engineer's own edits);
             project_layer.md (brief 27 P0 and P1: the design.yaml and contract.yaml formats, status, the contract test, phase 0);
             debug_playbook.md (for humans: what each gate rule ID means); img/ photos (metadata stripped);
             eval/eval1_preregistration.md (the eval-1 held-out evaluation, fixed before any scored run)
```

## Status

| Milestone | What | Status |
|---|---|---|
| F0A | Repo, CI, runner, flow, gates, ILA, test shell, T1 by hand | done |
| F0B | Automated bring-up on the Nexys A7: program by cable serial, UART tests, ILA capture | done |
| F1A | Knowledge packs (generic, AMD vendor from Ross, Artix-7 family) and a search library, in a private repo; names and hashes in [knowledge/PACKS.md](knowledge/PACKS.md); human [debug playbook](docs/debug_playbook.md) | done |
| F1B | Model screen on CVDP's 86 problems ([results/f1b/REPORT.md](results/f1b/REPORT.md)): no cheap candidate eligible (DeepSeek V4.1 Flash −12.4 points; GLM-5.3-Flash −4.1, not detectable, but 48.5 reliability failures per 86); pick luna | done |
| 04c | Board onboarding: Nexys A7 inventory, power budget and source-aware power gate, four read-only peripheral self-checks on the board | done |
| 04e | UltraFast (UG949) backbone: stage-grouped gates and reports in the flow ([docs/methodology.md](docs/methodology.md)), nine stage procedures in the knowledge bank, T1 rebuilt through the stages ([results/ultrafast](results/ultrafast/README.md)) | done |
| 04f | Verification backbone: OpenTitan-style V0-V3 plus V-HW on a simulator-portable stack (cocotb bench, bound assertion checkers, SymbiYosys, Verilator coverage, mutation score); T1 reaches V3 ([docs/verification.md](docs/verification.md), [results/04f](results/04f/README.md)) | done |
| 05a | F2 part 1: the harness-neutral core, MCP server, security layer and replayed-trace CI ([docs/agent_core.md](docs/agent_core.md)) | merged |
| 05d | F2 part 4: proof method per requirement, architecture-first gate, design standards v1.0 and checker, resource sanity gate, upgraded review pages, owner-edit ledger ([docs/methodology.md](docs/methodology.md), [docs/design_standards.md](docs/design_standards.md), [results/f2](results/f2/README.md)); live luna runs null at stage 2 | merged |
| 05f | F2 part 6: per-role model routing (profiles `single`, `cvdp`; `role@stage` overrides), per-role and per-stage accounting, knowledge-tool use log ([docs/role_models.md](docs/role_models.md)) | merged |
| 05g | F2 part 7: test-writer diagnosis and fixes (turn reserve, repair no longer deletes, shell fixtures, checklist, formal re-plan), per-role turn trace, knowledge-use log, QoR gate moved to after routing ([docs/test_writer.md](docs/test_writer.md)) | merged |
| 08f | `eval-2` build: independent spec-only test role and gate after V2/V3 (`--spec-tests`, off by default), golden request test against `eval-1`, offline replay on saved designs ([docs/verification.md](docs/verification.md), [results/08f](results/08f/), [agent/graph/spectest.py](agent/graph/spectest.py), [tools/spectest_replay.py](tools/spectest_replay.py)) | merged |
| 11b | CDC soak rig, phase 2a: the 13 correct variants and 11 mutant types (28 codes) on three clock domains, checkers, UART readout, Tj stop; simulated with metastability injection and reset storms, built in Vivado; no board run yet ([hil/cdc_soak](hil/cdc_soak/README.md)) | merged |
| 16 | Stronger CDC gate: structural check of every asynchronous path in the netlist ([flow/cdc_structure.py](flow/cdc_structure.py), [flow/cdc_paths.tcl](flow/cdc_paths.tcl)) and the design's own tests with synchroniser-delay injection ([flow/cdc_inject.py](flow/cdc_inject.py), [flow/cdc_inject_run.py](flow/cdc_inject_run.py)), proved against the rig's mutants ([flow/tests/fixtures/cdc_mutants](flow/tests/fixtures/cdc_mutants), [results/16_cdc_gate](results/16_cdc_gate/mutant_table.md)) | merged |
| 27 P0 | Project layer: `design.yaml` and `contract.yaml` checkers, stage keys from input hashes, `project status` and a static dashboard, a contract-test generator proved on fixture RTL; pilot 1 described with hand-written evidence ([docs/project_layer.md](docs/project_layer.md), [project/](project/)) | merged (#98) |
| 27 P1 | Phase 0, the spec session: requirements, `design.yaml` and contracts written and checked, one harness-made question per unstated contract field, unanswered questions kept as assumptions, a question log per pass; measured on pilot 1 and `c12_nexys_pwm_audio` ([project/phase0.py](project/phase0.py), [results/27b_p1](results/27b_p1/results.md)) | PR open |
| 18 | Project-mode parity: inventory of what project mode and each wizard give, measured in batch (Clocking Wizard against the hand M/D/O search, MIG through implementation, FIFO/XADC/GT/PS7/block automation); machine-readable cross-probing (`xprobe.json`, SVG device map, evidence for the repair visit) ([docs/project_mode_parity.md](docs/project_mode_parity.md), [flow/xprobe.py](flow/xprobe.py), [results/project_parity](results/project_parity)) | merged (#89) |
| 19 | External design tools driving AMD IP: xsim file-I/O harness, FIR and CIC adapters (spec to .coe to IP to bit-exact check), PDM-microphone signal chain with SINAD/ENOB per node ([docs/ipgen.md](docs/ipgen.md), [results/19_ipgen](results/19_ipgen)) | merged (#92) |
| 20 | Timing exceptions proved, part A: 15 one-fault Vivado fixtures (multicycle, false path, max delay, clock groups, the slow-FSM clock-enable pattern), an exception gate after synthesis and routing (`report_exceptions -ignored/-coverage`, XDC messages, TIMING-24/29/47, XDCH-1, and our own clock-enable check because Vivado raised no TIMING-46 on tied CE), FDA-CON-5/-10, and a dev drill with a constraint grader ([flow/exceptions_check.py](flow/exceptions_check.py), [flow/tests/fixtures/timing_exceptions](flow/tests/fixtures/timing_exceptions), [results/20_timing_exceptions](results/20_timing_exceptions/exceptions_table.md), [benchmark/drills](benchmark/drills/README.md)) | PR open |
| F2 | Agent v1: interview, plan, RTL, tests and the full Vivado flow (05a-05g above); 21 development runs on 11 course-tier tasks ([results/course](results/course), [site results](https://fpga-design-agent.vercel.app/results)) | built; development runs recorded |
| 06a | F3 part 1: benchmark v1 (T1-T2) authored and frozen, held-out split, training pool, contamination probe ([benchmark/](benchmark/README.md)) | merged |
| F3 | Scored runs | `eval-1` stopped 2026-11-09 before analysis, no score ([pre-registration](docs/eval/eval1_preregistration.md)); baseline evaluation on a larger benchmark next |

## Licence

MIT (see [LICENSE](LICENSE)). `boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc` is Digilent's, MIT, with its licence
alongside.
