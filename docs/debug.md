# Debug on the board from a plain-English request (brief 50A)

Ask for a capture in words; get back a checked plan, a debug build, a capture on the board, and an answer that quotes the
capture. The back end is the vendor ILA as an IP in the netlist (brief 48), within the limits of the Vivado 2026.1 Basic
licence tier: one ILA instance, so one clock domain per build, and at most 5 probe ports. A second back end, our own capture
core (brief 50B), will sit behind the same front end, plan, capture format and tools.

```
request (words) --LLM--> intent JSON --resolver--> plan (probes by RTL name, trigger, window, ports, fit)
     --> debug build (one ILA IP, packed ports, all gates; reused when an earlier build holds the probes)
     --> program SRAM + capture (hw_server, board.lock, register set-up and stimulus over the UART shell, XADC conditions)
     --> capture JSON + VCD + viewer page --> answer in plain words (every number quoted from the capture)
```

The language model only restates the request in a fixed schema. Everything after it is deterministic: names are resolved
against the RTL, the trigger is compiled to per-bit compare values, and the answer is written from facts computed from the
samples. Nothing the model says is trusted to exist.

## Commands

```bash
# plan only (shows the plan; nothing is built)
python -m debug_core plan designs/t1_dimmer_counter \
  "First write 3 to COUNT. Then capture count, win_wr and the shell's ADDR byte when the shell writes the COUNT register, 16 cycles before and 32 after. The write that triggers it puts 0x1234 in COUNT. Afterwards read COUNT back."

# the whole path; --build makes the debug build if none holds the probes (Vivado: take a heavy slot first)
python -m debug_core run designs/t1_dimmer_counter "<request>" --build --yes

# steps on their own
python -m debug_core build   <plan.json>              # Vivado, under a heavy slot
python -m debug_core capture <plan.json>              # board.lock, SRAM only
python -m debug_core answer  <capture.json>
python -m debug_core view    <capture.json> -o view.html
python -m debug_core query   <capture.json> '{"op": "first", "channel": "count", "cmp": "==", "value": "0x1234"}'
python -m debug_core plan    designs/<d> --intent intent.json   # a structured request, no language model
```

Outputs of a run go to `designs/<d>/build/debug/runs/<time>_<probeset>/`: `plan.json`, `plan.txt`, `capture.json`,
`capture.vcd`, `answer.txt`, `view.html`, and the instrument's raw files (`ila/`: the ILA CSV, probe maps, XADC readings,
the Vivado log).

## 1. Request to intent (the only model step)

[debug_core/request.py](../debug_core/request.py) sends the request with a menu of the design's names: the probes.yaml
names and their meanings, every register by hierarchical path and width, the 1-bit top-level pins, and the register map
(shell registers and the design's window from `spec.yaml`). The reply must be one JSON object in
[schemas/intent.schema.json](../debug_core/schemas/intent.schema.json): `probes`, `trigger` (`combine` AND/OR and
conditions `signal op value`, with `op` one of `== != < <= > >= rise fall change`), `pre`/`post` cycles, `setup`
(register operations before arming), `stimulus` (after arming: what makes the event happen), `readback` (after the
capture, to compare), `question`, and `unclear` for anything the parser could not map. An invalid reply is asked for
again once, then refused.

The client is the project's OpenRouter client ([agent/graph/llm.py](../agent/graph/llm.py)): the cheap default model
(`openai/gpt-6-luna`), `provider: {data_collection: deny}`, cost only as the provider reports it, Fable and Opus refused.
The five recorded requests cost 0.0003 USD or less each (provider-reported; see the report). Tests replay the recorded
replies, so CI calls no model.

The agent never uses this step: it writes the intent itself (the `debug_plan` tool takes the intent), so no second model
is called from inside a tool and the run's own meter sees all spend.

## 2. Names to probe pins (the resolver)

[debug_core/rtl_index.py](../debug_core/rtl_index.py) indexes the design's SystemVerilog sources (the build.yaml list):
modules, ANSI ports, `logic`/`reg`/`wire`/`bit` and enum declarations, parameters with `$clog2` and instance overrides
(top-level generics from build.yaml), named-port instances, `always_ff` / `always @(posedge ...)` left-hand sides with
their clock, and `assign` aliases. It is not a full SystemVerilog front end: generate blocks, interfaces and structs are
not elaborated, and a name inside them is reported as unresolved, never guessed.

The probe is a **register output pin**, as in the rest of the flow (`designs/*/probes.yaml`, `flow/debug.tcl`): cell names
survive synthesis and net names do not. Rules:

| Name in the request | Result |
|---|---|
| a register `x` in instance `a.b` (`a.b.x`, `a/b/x`, or a bare `x` if only one register has that name) | `a/b/x_reg[*]/Q` (`x_reg/Q` for one bit) |
| one bit `x[3]` | `a/b/x_reg[3]/Q` |
| an element of an unpacked array `frame[1]` | `.../frame_reg[1][*]/Q`; the bare array is an error that names an element |
| a port or wire | followed through port connections and plain `assign` aliases to the register that drives it, with the trace shown (`u_dut.win_wr -> win_wr -> u_shell.win_wr -> u_shell.u_core.win_wr`) |
| a probes.yaml name (`addr`, `rx_valid`, ...) | that file's pins (vetted by an earlier build) |
| a 1-bit top-level input | `<PORT>_IBUF_inst/O`, with a warning that it is asynchronous to the ILA clock |
| a multi-bit top-level input | error; suggests the registers that first sample it (its synchroniser) |
| a combinational signal | error ("may not exist under this name after synthesis"); suggests the registers in its expression |
| the same bare name in several places that reach different registers | error listing the candidates |
| an unknown name or a phrase | error with close matches (edit distance, and names sharing a word of the phrase) |
| an enum state register | resolved, with a note that FSM extraction may rename or re-encode it |

Every register's clock is followed up to a top-level port; that is the probe's clock domain. The ILA clock net is
`<port>_IBUF_BUFG` (or the design's probes.yaml `ila.clock_net` for that port) and the frequency comes from the XDC
`create_clock`. Clocks made inside the design (an MMCM output) are not supported in 50A and are reported as such.

The insertion step checks every pin again after synthesis (`flow/debug.tcl` stops with close matches if a pattern does not
match exactly the expected number of pins), so a resolver mistake cannot probe the wrong thing silently.

## 3. The plan

[debug_core/plan.py](../debug_core/plan.py) `make_plan(design, intent)` returns a plan in
[schemas/plan.schema.json](../debug_core/schemas/plan.schema.json), validated before it is returned, and `render(plan)`
prints it for the person or the agent before anything is built:

- **Probes:** label (the requested name if it is an identifier), RTL path, width, pins, kind, role (trigger, data or
  both), clock and notes.
- **Trigger:** per probe, a compare pattern of `0 1 X R F B` (most significant bit first). `==` takes integers, `0x..`,
  `0b..` with `x` for don't-care bits, `8'hA5` or a character; `rise`/`fall`/`change` need a 1-bit signal; `!=` only on
  1 bit; `<` and `<=` only when the bound is a power of two (`x < 64` on 8 bits is `00XXXXXX`); `>`/`>=` are refused.
  This is because a packed port holds several named probes and one probe can be split over several hardware probes (brief
  48), so the compare is per bit. Conditions on the same probe under AND are merged (a contradiction is an error). OR is
  allowed only across 1-bit terms, because OR over a bus split across hardware probes would fire on part of the value.
- **Window:** the ILA depth is the smallest of 1024, 2048, ... 131072 samples that holds `pre + post + 1`; the trigger
  position is `pre`; the capture keeps the whole depth and the answer covers the cycles that were asked for.
- **Ports:** 1-bit probes share a `flags` port; wider ones fill `data`, `data2`, ... (at most 1024 bits each), packed by
  `flow/prepare.py pack_probes` exactly as the build will pack them.
- **Fit:** one clock domain, at most 5 ports, and a block-RAM estimate (`ceil(bits x depth / 36864)` BRAM36 tiles; T1's
  measured ILA builds agree, see the report) within a budget (32 tiles by default; the xc7a100t has 135). Wider than 256
  bits per port or deeper than 4096 is allowed by the IP but flagged as not measured on the Basic tier.
- **Errors with the cut that would fit:** probes in two clock domains (keep the trigger's domain, drop the others, or a
  second build); more than 5 ports (keep the trigger probes, then the requested data probes in order); too much block RAM
  (a smaller depth if the window still fits, else the probes to drop); a window deeper than 131072 (the largest window
  with the same pre-trigger); compares the per-bit trigger cannot express (what to write instead); unknown registers in
  the set-up or stimulus (the register names). A plan with errors is shown and never built.
- **Probe set:** a hash of the pins in port order, the clock net and the depth. The trigger, window position and stimulus
  are run-time settings, so plans that differ only in those share one bitstream.

## 4. Build

[debug_core/build.py](../debug_core/build.py) writes the plan's probes into `designs/<d>/build/debug/<probeset>/probes.yaml`
and makes that directory an overlay of the design (its `build.yaml` with `probes` pointing there; every other design file
a link), so `flow/run_vivado.sh <overlay> ila` is the normal ILA build: the ILA IP inserted after synthesis with packed
ports, the debug hub's properties, `flow/ltx_fix.py`, the hub-crossing gate and every other gate, and the normal build cache
(`build/base` links to the design's base build so synthesis can be reused). The build is a Vivado run: take a heavy slot.

Before building, `find_build` looks for a finished debug build that already holds every probe of the plan (by pins), on
the same clock, at least as deep. If there is one, no rebuild is needed: the capture maps the plan's labels to that build's
probe names. Every debug build is kept, so the set of builds is a cache keyed by probe set.

## 5. Capture

[debug_core/instruments.py](../debug_core/instruments.py) `VendorIla` programs the build into SRAM (`flow/program.py`: by
cable serial, power_ok, build ID over JTAG and over the shell), then runs `flow/ila_capture.tcl` in step with the UART:
set-up writes, arm, stimulus, wait for the trigger (1 minute), upload, readback. Brief 50A extended `ila_capture.tcl` in a
backward-compatible way: a compare can carry a per-bit pattern (with the edge letters), and the XADC is read through JTAG
when the ILA is armed and after the upload (`<name>.cond_armed.txt`, `<name>.cond_done.txt`: temperature, VCCINT, VCCAUX,
VCCBRAM now, the min and max latched since configuration, and the alarm flags). Each capture records the conditions at
programming, armed and done, and a verdict against the recommended operating conditions (ROC: VCCINT and VCCBRAM 0.95 to
1.05 V, VCCAUX 1.71 to 1.89 V, Tj at most 85 C on this board; from the knowledge bank's Artix-7 skills via
`flow/program.py`). The XADC samples at about 1 MSPS across channels, so it cannot see nanosecond supply droop.

The whole capture runs inside `board.lock` (`hil/instruments/board_lock.py`), one board job at a time.

## 6. The capture format, the VCD and the viewer

Every instrument writes one format, [schemas/capture.schema.json](../debug_core/schemas/capture.schema.json)
(`fda-capture/1`): a time base (unit, clock, samples, the trigger sample), typed channels (`digital` integers per sample;
`analog` values in a unit, for the XADC and the bench boxes later), the trigger, the window, the instrument and its
settings, the build (build ID, probe set, Vivado version), the conditions, the stimulus log and the readback. Sample `i`
is at cycle `i - trigger_sample`.

`capture.vcd` is written from it (one time unit per clock period, signals under their plan labels, a `TRIGGER` wire).
`view.html` is a single static page ([debug_core/viewer.html](../debug_core/viewer.html)) with the capture embedded:
lanes for 1-bit signals and buses (hex), the trigger line, zoom, drag, a cursor readout, the answer, the conditions and
the readback. It opens any other capture JSON from disk, loads nothing from the network, and follows the system's dark
mode in black and white.

## 7. The answer

[debug_core/answer.py](../debug_core/answer.py) reduces the capture to facts: each channel's value at the trigger, its
changes (cycle, old, new), the high runs of a 1-bit signal, the values a bus took and for how many samples, and whether
the trigger condition actually holds at cycle 0. The answer is written from those facts as sentences, channels named in
the question first, over the window the request asked for. A check (`unquoted_numbers`) lists any number in a text that
is not a value, change cycle, count, readback or condition of the capture; the generated answer must pass it, and so
must any later phrasing step.

Queries for the agent, without raw samples: `value_at`, `first` (first cycle where a compare holds), `count`, `changes`,
`runs`, `summary`, and `diverge` (the first cycle where two captures of the same probes differ: hardware against a
simulation in the same format).

## 8. Agent tools

Three tools in the core registry, served by the MCP server like every other tool
([agent/core/debug_tools.py](../agent/core/debug_tools.py)):

| Tool | Does | Guards |
|---|---|---|
| `debug_plan` | intent -> checked plan, saved under `build/debug/plans/<probeset>.json`; returns the rendered plan, errors, warnings | none (builds nothing) |
| `debug_capture` | builds the probe set if asked (`build: true`, a Vivado run), programs SRAM, captures, returns the answer, facts, conditions verdict and the capture path (never raw samples) | stage `configuration-and-debug`, board file, power_ok on the debug build, hardware budget, board.lock |
| `debug_query` | a query on a capture under `build/debug/` | path confined to `build/debug/`, `.json` only |

No role is offered them yet: they are not flow tools of any stage, so the request paths of earlier evaluations are
unchanged (only the registry hash differs; `agent/tests/fixtures/b50a_request_golden.json`). Offering them to the repair
loop is a change to what a role is asked, so it belongs to a pre-registered evaluation (the A/B the brief describes).

## 9. Results on the Nexys A7

See [results/50a_nl_debug](../results/50a_nl_debug/README.md) for the board runs: requests, plans, answers, the shell's
readback, conditions and the build costs.

## 10. Limits (Basic tier, vendor ILA)

- One ILA instance: one clock domain per build, and no cross-triggering between captures.
- At most 5 probe ports; per-bit compares only (see the plan rules above); no storage qualification or advanced trigger
  (the build disables them).
- A new probe set is a new build (about 7 minutes for T1). The trigger, window and stimulus are run-time settings.
- XADC samples on the capture timeline are not in 50A (the XADC is read through JTAG at arm and done). The capture format
  has `analog` channels for when they are.

## What comes next (brief 50B and later)

Our own capture core behind the same plan, format and tools: triggers changed at run time without a rebuild, change-only
storage, no port limit, several clock domains, XADC samples on the same timeline, sequence triggers. The plan's
`backend` field and the instrument contract (`describe`, `configure`, `arm`, `capture`, `close`) are where it plugs in.
