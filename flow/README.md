# flow/: the Vivado flow and its gates

Everything here runs **locally**: Vivado 2025.2 cannot run in GitHub Actions. CI covers simulation, lint and the
Python code only.

| File | What it does |
|---|---|
| `run_vivado.sh` | The memory-safe runner. `flow/run_vivado.sh designs/<name> [base\|ila\|both]` |
| `prepare.py` | `build.yaml` (+ `probes.yaml`) to `inputs.tcl` / `probes.tcl`; computes the build stamp |
| `build.tcl` | Non-project flow: read, `synth_design`, (ILA), `opt_design`, `place_design`, `phys_opt_design`, `route_design`, reports, `write_bitstream` |
| `debug.tcl` | Post-synthesis ILA insertion from `probes.yaml` (`create_debug_core`, `connect_debug_port`); writes `probe_map.txt` and, at the end, the `.ltx` |
| `gates.py` | Parses the reports into one JSON and passes or fails the build |
| `summarise.py` | Collects `gates.json` + `run.json` of the variants into `results/<milestone>/` |
| `cocotb_run.py` | Runs a cocotb module under Icarus from pytest (used by every RTL test) |
| `lint.sh` | Verilator `--lint-only -Wall` on the shell and every design's top |
| `bringup.py` | **F0B.** One command on the attached board: power gate, discover, program base, UART tests, program ILA, ILA captures, still alive; writes `results/f0b/<design>_bringup.json` |
| `hw_discover.py`, `hw_list.tcl` | Find the one JTAG target (refuses if there are several), check it is an xc7a100t, find its UART (FT2232 interface 1, same USB serial); record both in `~/.config/fpga_design_agent/boards.yaml`, outside the repo |
| `program.py`, `program.tcl` | Program a build into SRAM by cable serial, after the `power_ok_usb` gate (report_power total <= 0.5 W) and a build-stamp check; flash requests are refused. Also `run_vivado.sh designs/<name> program\|program-ila` |
| `ila_capture.tcl`, `ila.py` | Arm the ILA by Tcl, wait, upload, export CSV + VCD, in step with the UART stimulus; read the CSV back into probe values |
| `hw.py` | Shared hardware pieces: the Vivado hardware-manager runner (same guard rails), `hw_server`, the board file, the power gate, serial redaction |

## The runner's guard rails (16 GB build PC)

- Refuses to start while another Vivado runs (`pgrep -x vivado`) or when `MemAvailable` is below `MIN_AVAIL_GB`
  (default 7), and says why.
- Runs Vivado in a transient user scope: `systemd-run --user --scope -p MemoryMax=6G nice -n 15`, with
  `set_param general.maxThreads 1`, `synth.maxThreads 1` and `chipscope.maxJobs 1` in `build.tcl` (the first does not
  lower the other two). Multi-threaded Vivado gets OOM-killed on this PC.
- Records in `run.json`: the wall time; the largest Vivado process's peak RSS (`/usr/bin/time -v`); and, from the
  scope's cgroup polled every 2 s, the peak anonymous memory summed over all its processes (the ILA build spawns
  helper Vivado processes), the peak charged memory (`memory.peak`, page cache included), the peak swap, and how
  often the cap was reached and whether anything was OOM-killed (`memory.events`).
- Variants (`both`) run one after the other.

## Build stamp

`BUILD_STAMP` (shell register 0x02) is the first 8 hex digits of a SHA-256 over every source and constraint file
(path and content). The same sources give the same stamp, and therefore the same netlist, in any clone; `run.json`
also records the git commit and whether the tree was dirty.

## Gates (`gates.py`)

A build passes only if all of these hold after routing:

| Gate | Source report |
|---|---|
| setup WNS ≥ 0 and TNS = 0 | `timing_summary.rpt` (Design Timing Summary) |
| hold WHS ≥ 0 and THS = 0 | `timing_summary.rpt` |
| pulse width WPWS ≥ 0 and TPWS = 0 | `timing_summary.rpt` |
| no unconstrained endpoints (a false path alone does not satisfy `no_input_delay`; see `designs/t1_dimmer_counter/design.xdc`): `no_clock`, `unconstrained_internal_endpoints`, `no_input_delay`, `no_output_delay`, `partial_input_delay`, `partial_output_delay`, `multiple_clock`, `loops`, `latch_loops` all 0 | `check_timing.rpt` |
| DRC errors = 0 and DRC critical warnings = 0 (`NSTD-1`/`UCIO-1` are critical warnings in `report_drc` but stop `write_bitstream`) | `drc.rpt` |
| no critical-warning methodology violations | `methodology.rpt` |
| no critical CDC violations | `cdc.rpt` |
| bitstream present (and `.ltx` for the ILA variant) | build directory |

Warnings that do not fail a gate are still listed in the JSON, by rule, so a reader sees them.

## Hardware steps (F0B)

Every hardware step runs Vivado through `hw.py` with the runner's guard rails (one Vivado at a time, `systemd-run
--user --scope -p MemoryMax=6G`, `nice -n 15`, `general.maxThreads 1`); the hardware manager needs about 1.6 GB, so
its free-memory floor is `HW_MIN_AVAIL_GB` (default 3) instead of 7. `bringup.py` starts one `hw_server` for the
whole run and stops it at the end (it is a wrapper script: the process group is stopped, not just the wrapper).

Rules the code enforces: program only the target whose serial is in the board file, never "the first target";
SRAM only, never flash; a bitstream above 0.5 W total on-chip power (`report_power`) is not programmed, because the
board runs from its USB cable; committed files show the cable serial as its last 4 characters and never a `/dev`
path. The on-board tests are pytest tests marked `hw`, skipped unless `--hw-port` is given (see `conftest.py`), so
CI never touches a serial port.

