# flow/: the Vivado flow and its gates

Everything here runs **locally**: Vivado (2026.1 since brief 48; `version_pin.py` picks the install) cannot run in GitHub Actions. CI covers simulation, lint and the
Python code only.

| File | What it does |
|---|---|
| `run_vivado.sh` | The memory-safe runner. `flow/run_vivado.sh designs/<name> [base\|ila\|both]` |
| `prepare.py` | `build.yaml` (+ `probes.yaml`) to `inputs.tcl` / `probes.tcl`; computes the build stamp |
| `build.tcl` | Non-project flow in UltraFast stages ([docs/methodology.md](../docs/methodology.md)): read, `synth_design -rtl` + RTL methodology DRCs, `synth_design` + post-synthesis reports (incl. `report_qor_assessment`), (ILA), `opt_design`, `place_design`, `phys_opt_design` + post-placement timing, `route_design`, closure reports, `write_bitstream` |
| `version_pin.py` | **Brief 21.** The Vivado version the knowledge bank was measured on (`KB_MEASURED_VERSION`) and the record `gates.py` writes into `gates.json` (`vivado_version`, `kb_measured_version`, `kb_version_match`); a console note when they differ. Never a gate. |
| `xpm_cdc.tcl` | The timing exceptions of AMD's `xpm_cdc_*` macros, applied by cell name right after `synth_design` (the non-project flow does not apply their scoped constraints; QR1 measured -1.364 ns on a correct crossing without it); sourced by `build.tcl` |
| `cdc_paths.tcl`, `cdc_structure.py` | **Brief 16.** Every register-to-register path whose launch and capture clocks are asynchronous, from the synthesised netlist (`cdc_paths_synth.rpt`), classified with the `report_cdc -details` rows of every severity: ASYNC_REG chain, XPM macro, Gray/handshake/FIFO with its exception, reset bridge, or unsafe (rules U1-U7). Gate `post_synth_cdc_structure_clean`; waivers in `architecture.yaml` `cdc_waivers` with a reason |
| `cdc_inject.py`, `cdc_inject_run.py`, `cdc_models/` | **Brief 16.** Synchroniser-delay injection (cycle-level; run under Icarus, written to also suit Verilator): every first-stage `ASYNC_REG` register and every XPM macro stand-in gets a random extra 0 or 1 destination cycle (`FDA_CDC_INJECT_SEED`, wired into `cocotb_run.py`); `cdc_inject_run.py` runs a design's own tests plain and with N seeds and writes `build/verif/cdc_inject.json` for `verif_gates.py --cdc-inject` (checks `cdc_structure_clean`, `cdc_injection_clean`). The harness runs it in `v3_evidence` (not a registered tool: a new tool would change the model's tool list, which the eval-1 golden request test freezes) |
| `exceptions_check.py`, `mcp_paths.tcl` | **Brief 20.** The exception gate (`post_synth_exceptions_clean`, `exceptions_clean` after routing): `report_exceptions -ignored` empty, every exception covers an endpoint (`-coverage`), no CRITICAL WARNING or ERROR from an XDC line in `vivado.log` (a typo drops the exception), no TIMING-24/-29/-47 or XDCH-1, and every multicycle path's registers share a real clock enable (`mcp_paths_<stage>.txt`; Vivado 2026.1 raised no TIMING-46 for tied CE, after synthesis or placement). Failures name the XDC file and line. Fixtures and measured table: `tests/fixtures/timing_exceptions`, `results/20_timing_exceptions` **Brief 45:** ignored exceptions that come from AMD's debug cores (the ILA's own scoped constraints: Position after the last timing command of our XDC, and every cell pattern inside `ila_core_inst`/`dbg_hub`/...) are `EXC-IGNORED-DEBUG-IP`, listed under `info`, not failures; the same rows from our XDC still fail. Fixture: `tests/fixtures/ila_exceptions/`. |
| `io_check.py`, `io_paths.tcl` | **Brief 20 part B.** The I/O gate (`post_synth_io_constraints_clean`, `io_timing_clean` after routing): no non-zero delay on a slow or asynchronous port (`boards/<board>/board.yaml` `slow_ports`), every non-zero delay with a data-sheet formula in a comment, no `-min` above `-max`; for the interfaces a design declares (`io_interfaces` in spec.yaml or build.yaml: kind, ports, clock, data sheet) both `-max` and `-min` per edge, the values the data sheet gives, the right reference clock and period, IOB packing, a synchroniser where the device has its own clock, and setup and hold slack reported separately. After routing `gates.json` also records the worst paths' uncertainty breakdown and corner, and the implementation-only margin (`timing_margin_ns` in build.yaml: applied for opt/place/phys_opt, removed before routing, UG949 ch. 6). A forwarded-clock port no longer counts as an output without a delay. Fixtures and measured tables: `tests/fixtures/io_timing`, `results/20_timing_exceptions/io_table.md`, `uncertainty.md` |
| `xprobe.tcl`, `xprobe_run.tcl`, `xprobe.py` | **Brief 18.** Cross-probing as data: RTL file and line, module, site, clock region and routed tiles of the worst setup and hold paths and the high-fanout nets, as `build/<variant>/xprobe.json`, plus an SVG device map. `FDA_XPROBE=1` makes `build.tcl` write it after the routed reports; `gates.py` adds the summary to `gates.json` as evidence (no gate reads it) |
| `mmcm_search.py`, `clkwiz_probe.tcl`, `mmcm_timing_probe.tcl`, `cmt_check.tcl`, `cmt_check_probe.tcl`, `wizard_probe.tcl`, `wizard_probe2.tcl`, `mig_impl_check.tcl` | **Brief 18.** Measurement scripts for the wizard comparison ([docs/project_mode_parity.md](../docs/project_mode_parity.md)): the Clocking Wizard in batch against the KB's M/D/O search, timing jitter on a hand-instantiated MMCM, the other wizards' `CONFIG.*` readback, the MIG example design through placement. Not part of a normal build |
| `ipgen/` | **Brief 19.** External Python design tools driving AMD IP configuration: `harness.py` + `tb/tb_axis_io.sv.tmpl` (the xsim file-I/O harness: stimulus and a seeded valid/ready schedule from files, every output beat to a file, word-for-word comparison in Python), `run.py` (the common runner: create_ip + read-back, xsim, out-of-context synthesis), `fir_design.py`/`fir_adapter.py` (FIR Compiler 7.2), `cic_design.py`/`cic_adapter.py` (CIC Compiler 4.0), `chain.py`/`chain_svg.py` (signal-chain predicted and measured numbers, block diagram). Heavy-slot rules apply to the Vivado stages. [docs/ipgen.md](../docs/ipgen.md) |
| `debug.tcl` | Post-synthesis ILA insertion from `probes.yaml`: by default one ILA IP added to the netlist, the probes packed into at most 5 ports (`insert_ila_ip`, brief 48: what the free Basic tier of 2026.1 allows); `FDA_ILA_INSERT=core` keeps the `create_debug_core` / `connect_debug_port` route for a tier that allows it; writes `probe_map.txt` and, at the end, the `.ltx` |
| `gates.py` | Parses the reports into one JSON and passes or fails the build, stage by stage (`rtl`, `post_synth`, `post_place`, `post_route`, `bitstream`), naming the first stage that failed |
| `summarise.py` | Collects `gates.json` + `run.json` of the variants into `results/<milestone>/` |
| `cocotb_run.py` | Runs a cocotb module under Icarus from pytest (used by every RTL test) |
| `lint.sh` | Verilator `--lint-only -Wall` on the shell and every design's top |
| `bringup.py` | **F0B.** One command on the attached board: power gate, discover, program base, UART tests, program ILA, ILA captures, still alive; writes `results/f0b/<design>_bringup.json` |
| `hw_discover.py`, `hw_list.tcl` | Find the one JTAG target (refuses if there are several), check it is an xc7a100t, find its UART (FT2232 interface 1, same USB serial); record both in `~/.config/fpga_design_agent/boards.yaml`, outside the repo |
| `program.py`, `program.tcl` | Program a build into SRAM by cable serial, after the `power_ok` gate (report_power total and junction temperature within the limits for the board's power source) and a build-stamp check; flash requests are refused. Also `run_vivado.sh designs/<name> program\|program-ila` |
| `ila_capture.tcl`, `ila.py` | Arm the ILA by Tcl, wait, upload, export CSV + VCD, in step with the UART stimulus; read the CSV back into probe values |
| `build_cache.py` | Brief 33: decides whether a build reuses the previous build of the same inputs (hit, resume from a checkpoint, or fresh) |
| `result_hash.tcl`, `result_hash.py` | Brief 33: dump and hash a build's placement and routing, to compare builds |
| `hw.py` | Shared hardware pieces: the Vivado hardware-manager runner (same guard rails), `hw_server`, the board file, the power gate, serial redaction |

## The runner's guard rails (32 GB build PC since 2026-11-04)

- Refuses to start while more Vivado jobs run than `FDA_VIVADO_MAX` allows (default 1) or when `MemAvailable` is below
  `MIN_AVAIL_GB` (default 7), and says why.
- Runs Vivado in a transient user scope: `systemd-run --user --scope -p MemoryMax=6G nice -n 15`, with
  `general.maxThreads` and `synth.maxThreads` set from `FDA_VIVADO_THREADS` (1-8; the runner's default is 2,
  `build.tcl` on its own uses 1; the first does not lower the second) and `chipscope.maxJobs 1` at every thread count
  (the ILA build otherwise synthesises its debug cores in parallel helper processes). On the shared PC,
  `eval "$(_handoff/take_heavy_slot.sh --env "<text>")"` takes a heavy slot and sets `FDA_VIVADO_THREADS`: 4 when the
  other slot runs no Vivado job, 2 when it does. Brief 33's measurements, repeated on Vivado 2026.1
  ([results/33_vivado_speed_2026_1](../results/33_vivado_speed_2026_1/results.md)): 1, 2 and 4 threads gave the same placement,
  routing and WNS on the small and mid designs, with peak memory flat (about 2.1 and 2.3 GB); the 36k-LUT CDC rig took 3.9 GB at
  1 thread and was not run at 2 or 4 within the 6 GB cap (memory grows with the thread count on a large design, so give it a larger
  `MEM_MAX` and run it alone). The old pin of 1 dated from
  the 16 GB PC, where builds above one thread were OOM-killed at 5-6 GB.
- **Build cache** (brief 33, `build_cache.py`): a build whose inputs (sources, XDC and data contents, build.yaml
  settings, every `flow/*.tcl`, the thread count, the Vivado binary, the FDA_XPROBE/FDA_RESULT_HASH/FDA_INCREMENTAL
  switches) match the previous build of the same variant reuses it. If that build already reached the requested
  stage, Vivado is not run and only the gates re-run (`cache_hits` in run.json); if it reached an earlier stage, the
  new build opens its `post_synth.dcp` or `post_route.dcp` and copies that build's reports for the stages it skips.
  The ILA variant starts from the base build's `post_synth.dcp` when the synthesis inputs match. `FDA_BUILD_CACHE=0`
  turns it off. The resumed builds gave the same placement, routing and WNS as fresh builds (results/33_vivado_speed_2026_1).
- `FDA_INCREMENTAL=1` (off by default) runs `read_checkpoint -incremental` against the previous build's
  `post_route.dcp` when the inputs changed; the gates' reference builds never use it.
- `FDA_RESULT_HASH=1` writes `result_dump.txt` (`result_hash.tcl`) and the placement and routing hashes
  (`result_hash.py`) into run.json, for checking that two builds gave the same result.
- Records in `run.json`: the wall time; the thread count; the cache decision; the scope unit; the largest Vivado
  process's peak RSS (`/usr/bin/time -v`); and, from the scope's cgroup polled every 2 s, the peak anonymous memory
  summed over all its processes (the ILA build spawns helper Vivado processes), the peak charged memory
  (`memory.peak`, page cache included), the peak swap, and how often the cap was reached and whether anything was
  OOM-killed (`memory.events`).
- Variants (`both`) run one after the other.

## Build stamp

`BUILD_STAMP` (shell register 0x02) is the first 8 hex digits of a SHA-256 over every source and constraint file
(path and content). The same sources give the same stamp, and therefore the same netlist, in any clone; `run.json`
also records the git commit and whether the tree was dirty.

## Gates (`gates.py`)

Since 04e the checks are grouped by UltraFast stage (AMD UG949 v2026.1; the mapping, thresholds and sources are in
[docs/methodology.md](../docs/methodology.md)). `gates.json` carries `stages` (per stage: `ran`, `pass`, its gates
and the parsed reports), `first_failed_stage`, and the flat `gates` dict (the F0A names for the post-route and
bitstream checks, stage-prefixed names for the rest). A stage whose reports are missing (a build made before 04e)
is `ran: false` and skipped.

| Stage | Gate | Threshold | Source report |
|---|---|---|---|
| `rtl` | `rtl_methodology_no_critical` | `report_methodology` on the elaborated RTL: 0 critical warnings | `methodology_rtl.rpt` |
| `post_synth` | `post_synth_no_unconstrained_endpoints` | the nine `check_timing` categories below all 0 | `check_timing_synth.rpt` |
| `post_synth` | `post_synth_methodology_no_critical` | 0 critical warnings | `methodology_synth.rpt` |
| `post_synth` | `post_synth_drc_clean` | 0 errors, 0 critical warnings | `drc_synth.rpt` |
| `post_synth` | `post_synth_qor_assessment` | `report_qor_assessment` score >= 4 (of 5; UG949 ch. 5: 1-2 have no chance of closing timing, 3 is unlikely to) | `qor_assessment_synth.rpt` |
| `post_synth` | (recorded, not gated) | post-synthesis WNS/TNS, utilisation, clock networks and interaction, high-fanout nets | `timing_summary_synth.rpt`, `utilization_synth.rpt`, `clock_*_synth.rpt`, `high_fanout_synth.rpt` |
| `post_place` | `post_place_hold` | WHS > -0.5 ns after `phys_opt_design` (WNS recorded) | `timing_summary_place.rpt` |
| `post_route` | the table below, plus `power_junction_ok` | `report_power` made for the board's thermal environment (still air, no heat sink) with the junction <= 85 C; post-route QoR score recorded | `power.rpt`, `qor_assessment_route.rpt` |
| `bitstream` | `bitstream_present` (+ `debug_probes_present` for `ila`) | files present | build directory |

The post-route gates (unchanged since F0A):

| Gate | Source report |
|---|---|
| setup WNS ≥ 0 and TNS = 0 | `timing_summary.rpt` (Design Timing Summary) |
| hold WHS ≥ 0 and THS = 0 | `timing_summary.rpt` |
| pulse width WPWS ≥ 0 and TPWS = 0 | `timing_summary.rpt` |
| no unconstrained endpoints (a false path alone does not satisfy `no_input_delay`; see `designs/t1_dimmer_counter/design.xdc`): `no_clock`, `unconstrained_internal_endpoints`, `no_input_delay`, `no_output_delay`, `partial_input_delay`, `partial_output_delay`, `multiple_clock`, `loops`, `latch_loops` all 0 | `check_timing.rpt` |
| DRC errors = 0 and DRC critical warnings = 0 (`NSTD-1`/`UCIO-1` are critical warnings in `report_drc` but stop `write_bitstream`) | `drc.rpt` |
| no critical-warning methodology violations | `methodology.rpt` |
| `post_route_qor_assessment` (routed `report_qor_assessment` score >= 4) | `qor_assessment_route.rpt`. **Not run on Vivado 2026.1 with the free Basic licence tier** (Implflow 47-2944): `build.tcl` writes `qor_unavailable_route.txt`, `gates.json` records `qor_assessment: {available: false}` and the gate is absent, not passed (owner's decision, 2026-11-11, brief 48: no licence upgrade, no fallback to an earlier release). |
| no critical CDC violations | `cdc.rpt` |
| bitstream present (and `.ltx` for the ILA variant) | build directory |

Warnings that do not fail a gate are still listed in the JSON, by rule, so a reader sees them. The post-synthesis
WNS is not gated: UG949 ch. 1 lets a design with a small negative margin continue to implementation, and gives no
number.

The gates are **neutral**: `gates.py` reports the tool's own rule IDs, severities, descriptions and counts, and
the slack numbers, with no advice on how to fix anything, so the agent arms without a knowledge pack learn nothing
from the harness. For a person reading a failed gate, [docs/debug_playbook.md](../docs/debug_playbook.md) explains
each rule ID and what to try (it is never given to the agent in scored runs).

## Hardware steps (F0B)

Every hardware step runs Vivado through `hw.py` with the runner's guard rails (one Vivado at a time, `systemd-run
--user --scope -p MemoryMax=6G`, `nice -n 15`, `general.maxThreads 1`); the hardware manager needs about 1.6 GB, so
its free-memory floor is `HW_MIN_AVAIL_GB` (default 3) instead of 7. `bringup.py` starts one `hw_server` for the
whole run and stops it at the end (it is a wrapper script: the process group is stopped, not just the wrapper).

Rules the code enforces: program only the target whose serial is in the board file, never "the first target";
SRAM only, never flash; a bitstream is not programmed unless it passes the **power gate** `power_ok` (below);
committed files show the cable serial as its last 4 characters and never a `/dev`
path. The on-board tests are pytest tests marked `hw`, skipped unless `--hw-port` is given (see `conftest.py`), so
CI never touches a serial port.

## The power gate (`power_ok`, brief 04c)

`hw.power_ok(build_dir, board)` reads the build's `power.rpt` and passes only if:

| Check | USB power | Wall power |
|---|---|---|
| total on-chip power | <= 0.5 W | <= 2.0 W (interim, until the owner accepts the final limit) |
| junction temperature | <= 85 C | <= 85 C |
| the report's thermal environment | still air (0 LFM), no heat sink | same |

The power source comes from the local board file: `boards.<name>.power_source: usb | wall` in
`~/.config/fpga_design_agent/boards.yaml`. A missing file, board or key, or an unknown value, means `usb` (the
lower limit), so a mistake fails safe; `hw_discover.py` keeps the key when it rewrites the board's entry.
`flow/build.tcl` runs `set_operating_conditions` with the board's `thermal` block from
`boards/<board>/board.yaml` (still air, no heat sink, small 4-7 layer board, 40 C ambient) before `report_power`,
because Vivado's defaults (250 LFM airflow, a medium heat sink, a 10x10 in 12-15 layer board) understate the
junction temperature of a bare board; the gate refuses a report made with the defaults. The derivation of the
limits is in `boards/nexys_a7_100t/power_budget.md`.

## Board self-checks (`board_check.py`, brief 04c)

`python3 flow/board_check.py designs/<name> [--runs 3]`: power gate, discover, program the base build, run the
design's `selfcheck.py` over the UART, check the design is still alive; one JSON per run in
`results/board_v2/runs/`, the last in `results/board_v2/<name>.json`. Used by the read-only peripheral checks
`designs/b2_*` (temperature sensor, accelerometer, flash JEDEC ID).


## The ILA on Vivado 2026.1 with the free Basic licence tier (brief 48)

Measured on 2026.1 Basic (exact texts in the knowledge repo's `docs/VIVADO_2026_1_BASIC_TIER.md`): `create_debug_core` is refused
(Vivado 12-29205), and an ILA IP is allowed, but only **one instance, at most 5 probe ports**, with no width or depth limit
found up to 256 bits by 4096 samples. So the ILA build (`flow/debug.tcl`, `insert_ila_ip`, the default; `FDA_ILA_INSERT=core`
selects the old `create_debug_core` path for a tier or version that allows it):

- packs the probes of `probes.yaml` into at most 5 ports (`flow/prepare.py` `pack_probes`: a `group` key names a port, else
  1-bit probes share `flags` and wider ones `data`) and writes `probe_map.txt` with each probe's port, offset and width; the host
  side (`flow/ila.py`, `flow/bringup.py`, `flow/ila_capture.tcl`) cuts the named probes back out, so designs and gates still see
  every named probe;
- keeps one clock domain: a probe whose optional `clock` differs from `ila.clock_net` is refused, and no CDC path is added for debug;
- fixes the `.ltx` (`flow/ltx_fix.py`) where `write_debug_probes` loses the name of a bus bit, and fails the build on any gap;
- passes the build only if the debug hub's TCK crossings are timed as asynchronous (`ila_hub_crossing_async`, from
  `clock_interaction_route.rpt`). The hub's own constraint script prints CRITICAL WARNINGs on this route; the exception gate lists
  those from the hub's `xsdbm_*.xdc` as `EXC-XDC-DEBUG-HUB` (info) only in an ILA build, and every other message still fails.

`report_qor_assessment` is also not run on the Basic tier, so the `post_route_qor_assessment` gate is absent (see the gate table).
