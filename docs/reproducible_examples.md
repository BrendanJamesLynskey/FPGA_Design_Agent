# Reproducible examples (brief 195)

Four small development tasks that a user can re-run to see, for themselves, which results reproduce and which do not. Each has **reference runs** made with a pinned setup
and committed (`results/195_repro_examples/`). A re-run uses the same pinned setup and is compared with the references, with **what should match** and **what should vary** kept
apart. Code: `agent/repro/` (the registry and pins `examples.yaml`, `registry.py`, `extract.py`, `compare.py`, `runner.py`, `record.py`, `tools.py`, `cli.py`) and the navigator's
Examples page (`navigator/examples.py`, `navigator/static/app.js`). Tests: `agent/tests/test_195_repro_examples.py`, `navigator/tests/test_195_navigator_examples.py`.
Measurements and screenshots: [results/195_repro_examples](../results/195_repro_examples/README.md).

```
python -m agent example list                       # the examples, and what their reference runs measured
python -m agent example run <name> [--max-usd N]   # re-run with the pinned setup (about an hour; spends the plan's tokens; takes a heavy slot where _handoff/take_heavy_slot.sh exists)
python -m agent example compare <run directory>    # the same comparison again, from the run's example_result.json
python -m agent example tools <name> --ref N       # the deterministic part only, no model call: re-score a stored reference RTL
python -m agent example finish <name> <run dir>    # score and record a run that was started with the pinned command by other means
python -m agent example record <name> <run dir>    # keep a finished run as a reference (the maintainer's step; see "Adding a reference run")
```

## The examples

| Name | Task (development split) | What it covers |
|---|---|---|
| `gray_stepper` | `benchmark/tasks/t1_gray_stepper` | a counter with a debounced button, an automatic mode and a Gray-coded output; every step of the count checked |
| `elevator_fsm` | `benchmark/tasks/t1_elevator_fsm` | a finite-state machine: call latching, direction rules, timed states |
| `median3x3` | `benchmark/course/tasks/c9_median3x3` | a streaming datapath with a fixed one-clock latency, a window sorted in pure logic, gaps between windows |
| `pattern_sequencer` | `benchmark/tasks/t1_pattern_sequencer` | a programmable sequence of timed steps, loop or one shot, a pause button, live changes |

Each is a development task: never a held-out task (a test checks the split files) and never wavelet material. Each task is a plain-language request (`spec.md`), a hidden acceptance
bench that scores the result (the agent never sees it), and the test shell on the board's USB-UART. There is **no AXI-Stream example**: no development task in the benchmark asks for
one, and the held-out sets are off limits. A follow-up (below) would add one.

## The pinned setup

`agent/repro/examples.yaml` holds it; `python -m agent example run <name> --dry-run` runs the pre-flight and prints the exact command. Every item is recorded in the result.

| Pin | Value | Checked by the pre-flight |
|---|---|---|
| Model (design, tests, clarify) | `claude-sonnet-5-5`, effort `medium`, on Claude Code | the id is on the command line; Fable, Opus and an Anthropic model through OpenRouter are refused |
| Interview oracle | `claude-haiku-5-5` on Claude Code | likewise |
| Claude Code CLI | 2.1.321, a **pinned copy** (a real file, not a symlink) put first on `PATH`; SHA-256 `426c33815ca6...` | version and hash of `~/.local/share/fpga_design_agent/repro_pins/claude-2.1.321/bin/claude`; a wrong version is a hard stop |
| Harness | the agent's Claude Code arm, harness arm `H1`, profile `single`, verification level `V2`, docs off | on the command line (`agent/repro/registry.py: argv`) and checked against the run's own `config.json` by `example finish` |
| Stop | after stage 6 (timing closure): a post-route build exists, so resources and slack exist; no power, DRC or board stage | on the command line |
| Vivado | 2026.1 | the install path |
| Knowledge bank and prompts | the private knowledge repository at the commit the prompt pin names (`agent/core/prompts_pin.json`), and the prompt manifest's SHA-256 | `git rev-parse HEAD` of the checkout; to pin: `git -C <knowledge repo> worktree add --detach <dir> <commit>` and `export FDA_KNOWLEDGE=<dir>` |
| Agent code | the commit is recorded, not pinned (it moves with the repository) | recorded as `agent_commit` |
| Seeds | none: Claude Code takes no seed and no temperature (checked: `claude --help` of 2.1.321 lists no such option; `docs/deterministic_mode.md` explains the three levels and why a subscription run has none) | |
| Cost cap | $6 per run, the plan's estimate | `--max-usd`; a lower value can be passed, a higher one cannot |
| Tools | Icarus Verilog and cocotb for the hidden bench (seed 1), recorded by the bench | no `apt`, `pip` or container pulls during a run |

The CLI is pinned the way `_handoff/eval_run_checklist.md` asks: auto-updates off (`DISABLE_AUTOUPDATER=1` in `~/.claude/settings.json`), a copy in a pin directory (the updater prunes old versions, so
a symlink can vanish mid-run), the version checked before every launch. A pin that does not hold stops the run **before any model call or heavy slot**, with the check named.

## What should match and what should not

The comparison has three groups. They promise different things, which is why they are kept apart.

| Group | What | Compared against | A difference means |
|---|---|---|---|
| **Deterministic given the same inputs** | the hidden bench's verdict per test (against a reference with the same **RTL hash**); the Vivado build's LUT, FF, DSP and block RAM counts, worst setup and hold slack (only against a reference with the same RTL hash **and the same build stamp**, see below) | a match is shown with the hash | a mismatch with the same RTL is a finding about the tools or the setup, never about the model |
| **Varies with the model** | the RTL itself, lines of RTL, repair loops, agent turns, tokens, cost, wall time | the reference minimum, median and maximum, the new value marked inside or outside | "outside" means "not seen in the references", with few references it is weak evidence |
| **Outcome** | do the hidden tests pass; do the agent's own gates pass; resources and slack against the spread of all references, whatever their RTL | all references | a hidden-test failure is the result that matters most |

The RTL hash is SHA-256 over the sorted (file name, bytes) pairs of `rtl/` with line endings normalised. When no reference wrote the same RTL, the deterministic group says so and
judges nothing, because different RTL builds to different numbers and that is not a failure. To see the tools repeat without a model, `example tools` re-runs the hidden bench on a
stored reference RTL and compares the per-test verdicts with the record; with `--vivado` it also rebuilds the RTL.

**The Vivado numbers depend on the path.** The build stamp hashes the source file *paths* and is compiled into the design as a constant, so the same RTL in another run directory is a slightly different netlist: measured, LUT 431 to 425 and setup slack 3.275 to 3.835 ns for one design. Rebuilt at its original relative path the same RTL gave identical stamp, resources and slack in 4 of 4 rebuilds. A re-run always has a new run directory, so for a re-run only the bench verdicts are judged, and the Vivado numbers are shown against the reference spread. See [the measurements](../results/195_repro_examples/README.md).

**Measured (12 reference runs, 2026-11-23):** the outcome repeated for three of four examples (gray stepper 3/3 pass, elevator 0/3, pattern sequencer 0/3, each failing the same tests every time) and varied for the median filter (1/3); the RTL never repeated (12 runs, 12 hashes); the bench re-scored every stored RTL to the same verdicts (12/12).

## What a user could guess wrong

- **A re-run does not reproduce the RTL.** Claude Code on a subscription takes no temperature and no seed, so two runs of the same request write different RTL. This is the
  expected result, not a bug; reproducibility here means the *outcome* (hidden tests pass, gates pass, resources and slack in a similar range) and the *tools* (same RTL, same numbers).
- **Level-2 replay does not help with Claude Code.** The model-call tape of `docs/deterministic_mode.md` replays exactly for endpoints the agent calls itself, but a Claude Code
  sub-agent's tool loop runs inside the CLI and is refused at level 2. There is no way to replay these examples without the model.
- **The model name is pinned, the model is not.** The provider can change what `claude-sonnet-5-5` serves; each result records the model ids the calls reported (`models_served`), and a
  reference run made before a provider-side update may no longer be representative.
- **The cost is an estimate.** Claude Code on a subscription reports no bill. The figure is the plan's estimate from the tokens used; a metered account would be billed differently.
- **Wall time includes everything the run did**, from the first to the last trace event, and varies with what else the PC is doing (the shared heavy slots, other Vivado jobs). The
  slot wait before the run starts is not counted.
- **The agent's own gates are not the verdict.** "Hidden tests pass" is the scored result; the agent's own gates passing with the hidden bench failing is an *escape* (`tools/run_record.py`),
  and an example can show one.
- **Two examples fail their hidden tests every time.** The elevator and pattern sequencer requests leave cycle-exact behaviour open and the agent's reading differs from the hidden bench's; they show a reproducible failure, and an escape (own gates pass, hidden bench fails). They are not a capability claim.
- **A first re-run can be refused.** The pinned CLI copy and the knowledge-bank checkout are set up by hand once; the pre-flight says exactly what is missing.
- **Stopping at stage 6 is a choice.** The examples do not run power, DRC or the hardware stage, so they say nothing about those.

## Adding a reference run (the maintainer's step)

1. Take a heavy slot, run `python -m agent example run <name> --no-slot` (or the navigator's button), and wait for it.
2. `python -m agent example record <name> <run dir>` copies `example_result.json` to `results/195_repro_examples/<name>/ref_<n>.json` and the RTL to `ref_<n>_rtl/`. It refuses a
   run that did not use the pinned setup, a record that holds long text or an absolute path, and a waived pin.
3. Before pushing, run the leak gate on the committed records:
   `FDA_PROMPTS_DIR=<pinned prompts> FDA_PROMPTS_UNPINNED=1 python -m pytest -q agent/tests/test_99_prompts.py agent/tests/test_195_repro_examples.py`.
   No prompt text, no source text outside `ref_<n>_rtl/` and no path is committed: the records hold numbers, names and hashes.
