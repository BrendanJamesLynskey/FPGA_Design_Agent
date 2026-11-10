# ipgen: external design tools driving AMD IP configuration (brief 19)

The owner's idea (2026-11-10): link the filter-design tools in Python to the AMD filter IP, and extend that to any IP
block that can take its configuration from an external tool. `flow/ipgen/` is that link, with one adapter per IP and one
runner for all of them.

## The pipeline (one shape for every IP)

```
spec (plain numbers)
  -> Python design tool                    adapter.design()          scipy / numpy
  -> IP config (CONFIG.* + data files)     adapter.props(), design_artifacts()   e.g. fir.coe
  -> batch create_ip + set_property        flow/ipgen/tcl/ip_flow.tcl  stage "create"
  -> read back what the IP computed        readback.json (CONFIG.* and the generated model parameters of the .xci)
  -> bit-accurate check in xsim            flow/ipgen/harness.py       stage "sim"   (file-driven AXI-Stream testbench)
  -> out-of-context synthesis              ip_flow.tcl stage "synth"   utilisation, post-synthesis WNS
  -> record                                results/19_ipgen/<example>/*.json
```

```
python3 -m flow.ipgen.run fir results/19_ipgen/fir/spec.yaml results/19_ipgen/fir          # design, create, sim, synth
python3 -m flow.ipgen.run cic results/19_ipgen/cic/spec.yaml results/19_ipgen/cic --stages design,create,sim
python3 -m flow.ipgen.chain results/19_ipgen/chain/chain.yaml results/19_ipgen/chain      # no Vivado: the chain model
```

The Vivado stages need a heavy slot (`_handoff/take_heavy_slot.sh`; put `Vivado impl` in the text for the synthesis stage)
and run under `systemd-run --user --scope -p MemoryMax=6G nice -n 15`, one thread. The design tool needs `numpy` and `scipy`
(BSD-3): `pip install -e '.[ipgen]'`. The tests skip themselves without scipy.

## The xsim file-I/O harness

Proposed in brief 13 (`reports/13_expertise_report.md`, "ipgrade"), built here. The DSP cores are IEEE-1735 encrypted VHDL, so
Icarus, Verilator and GHDL cannot run them; only xsim can.

1. Python writes `stim.txt` (one beat per line: `<tdata hex> <tlast>`) and a seeded `sched_*.txt` (per cycle: valid allowed,
   ready allowed).
2. `flow/ipgen/tb/tb_axis_io.sv.tmpl` is a generic SystemVerilog testbench. `harness.render_tb()` fills in the widths, the
   file paths and the adapter's instance of the IP. The testbench reads the stimulus with `$fscanf`, drives `tvalid` by the
   schedule (a beat offered and not accepted stays offered, as AXI-Stream requires), drives `tready` by the schedule when the core
   has one, and writes every accepted output beat with its cycle to `resp_*.txt`. It judges nothing.
3. `ip_flow.tcl` stage `sim` adds the testbench to `sim_1` and runs the behavioural simulation in batch (`launch_simulation`,
   `run all`).
4. Python reads the response and compares it with the golden model **word for word** (`harness.compare`). The adapter
   searches the decimation phase (which input sample the first output belongs to is the core's choice) and records the
   first mismatch if there is one.
5. Two schedules run: continuous (every cycle valid and ready) and random (seeded gaps). Both must match the golden, and
   they must agree with each other.

The latency recorded is from the first accepted input beat to the first output beat, in clock cycles. It is **not** the
IP's `C_LATENCY` parameter (which is read back too): for a decimator the first output also waits for the filter to fill.

The golden model is an integer Python model of the same filter (FIR: exact convolution; CIC: the length-(R M) box
convolved N times). The core's own C model is not used: the CIC has none in the install, and an exact integer model needs
none for a full-precision filter. Adding rounding or truncated outputs would need the C model or a model of the core's
rounding (`Output_Rounding_Mode`), which this brief did not do.

## The adapter interface

An adapter is a subclass of `flow.ipgen.adapter.IpAdapter`, registered in `run.adapters()`. The runner never knows which IP it
is running.

| Hook | Job |
|---|---|
| `design(spec)` | the Python design tool: plain numbers in, a design out (`summary` is the JSON-safe part) |
| `design_artifacts(spec, design, outdir)` | write the data files the IP reads (a `.coe`, a table, a `.prj`) and plot data |
| `props(spec, design, artifacts)` | the flat `CONFIG.*` list for `set_property`. Set together: some depend on each other (`CoefficientSource COE_File` is refused until `Coefficient_File` is set in the same call) |
| `predicted(spec, design)` | what the tool expects the IP to report; compared with the read-back |
| `readback_keys()` | `CONFIG.*` values and generated model parameters (`MODEL.C_LATENCY`, `MODEL.C_NUM_MADDS`, ...) to record |
| `dut_inst(module, ports)` | the SystemVerilog instance of the IP with the testbench's fixed signal names |
| `stimulus(spec, design)` | the seeded input, including worst-case segments |
| `check(spec, design, samples, response, out_width)` | compare against the golden; returns a dict with `match` |

What the runner provides: the Vivado `create`/`sim`/`synth` stages, the read-back (CONFIG.* from `list_property`, generated
parameters parsed from the `.xci`), the port widths (parsed from the generated `sim/<ip>.vhd`), the schedules, the OOC
numbers, and the JSON records.

Facts worth knowing, measured in 2025.2:

- `list_property $ip` shows no `CONFIG.*` until the IP has a `-dir`; use `[get_ips name]`, not the object `create_ip` returns.
- The IP's output width and the generated parameters (`C_LATENCY`, `C_NUM_MADDS`, `C_OVERSAMPLING_RATE`) are in the `.xci`
  JSON after `generate_target`; `CONFIG.HardwareOversamplingRate` is **not** recomputed in batch (it stays 1) while
  `C_OVERSAMPLING_RATE` is.
- `Clock_Frequency` and `Sample_Frequency` are in MHz; the oversampling and the number of DSP slices follow their ratio.
- `tdata` is padded to whole bytes (a 35-bit output is a 40-bit `m_axis_data_tdata`, sign-extended).
- An IP instance may not be named like a unisim primitive (`fd`).

## Where pyfda fits

pyfda (open-source filter design GUI, exports `.coe`) is a human front end for the same step: a person designs the
filter with sliders and exports the coefficient file; the pipeline takes it from `Coefficient_File` onwards (set the
`CoefficientSource` to `COE_File` and skip `design()`). It is not used here: the design step is the one the agent can run
from a spec. It was not installed; its licence was not checked.

## Agent integration

The agent already builds through `flow/` and its existing tools; ipgen adds a flow step, not a registered tool (a new tool
changes the model's tool list, which the eval-1 golden request test freezes: brief 16). An agent that needs a filter writes
`spec.yaml` and runs `python3 -m flow.ipgen.run ...`; the generated IP directory (`work/ip/<name>/<name>.xci` and the
`.coe`) is then read by the design's own build (`read_ip`; this input kind is not wired into `build.yaml`, see brief 18's
list of unwired project-mode features). One KB note per adapter is in the private knowledge repository
(`vendor/amd_ip_cores/ip-cores/ipgen-<ip>-adapter`).

## Candidates beyond FIR and CIC (listed, not built)

| IP | What an external tool would compute | Config it feeds |
|---|---|---|
| DDS Compiler 6.0 | phase width and output width from an SFDR and a frequency-resolution target; phase increment | `Phase_Width`, `Output_Width`, `PINC` |
| CORDIC 6.0 | iterations and widths from a precision target | `Functional_Selection`, `Input_Width`, `Output_Width`, iterations |
| FFT 9.1 | point size and a scaling schedule from an overflow analysis | `transform_length`, `scaling_options`, `scaling_schedule` |
| Block Memory Generator | a sine or window table from Python | `.coe` initial contents |
| Clocking Wizard | a clock plan from an M/D/O solver; jitter read back | `PRIM_IN_FREQ`, `CLKOUTn_REQUESTED_OUT_FREQ`, read `MMCM_*` (brief 18: batch read-back works) |
| MIG (7-series) | a `.prj` from the pin planner | the `.prj` file (no Tcl validation command exists: brief 18) |
| XADC wizard | the channel sequencer, alarm limits | `CONFIG.CHANNEL_ENABLE_*`, `CONFIG.*_ALARM_*` |
| Transceiver wizard | line rate and reference clock from a link budget | `CONFIG.*LINE_RATE`, `REFCLK` |
| Multiplier, divider, floating point | widths from a range analysis | `CONFIG.*Width` |

## What is not done

DDS, CORDIC, FFT, Block Memory Generator and Clocking Wizard adapters (the brief's step 3, "as far as the budget allows").
The chain's xsim runs are per stage, not for the cascade. Output rounding and coefficient reload are not exercised.
