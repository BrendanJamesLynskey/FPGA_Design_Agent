# benchmark/: the F3 benchmark (v1, tiers T1-T2)

Natural-language FPGA design tasks for the Nexys A7-100T, each with an independent golden model and acceptance
tests that the agent never sees, and a reference design that shows the task is achievable on this board and
toolchain. The benchmark measures the agent, so it was written **before** any agent tuning on it, by a session that
did not read the agent's prompts or run records (brief 06a). Frozen: see [FROZEN.md](FROZEN.md).

The course projects of Parts 9-16 are ported to this layout as a separate tier with its own split and freeze: [course/README.md](course/README.md).

Development tasks can be amended after the freeze, only through a dated entry in [AMENDMENTS.md](AMENDMENTS.md) (spec clarifications where a hidden test
checks something the spec left open, mutants, tests); held-out tasks are never amended.

## Layout of one task

```
tasks/<id>/
  spec.md              what the agent is given: natural language, as a user would write it (some details left out
                       on purpose: the interview has to ask; the spec oracle answers from hidden/spec.yaml)
  hidden/              never shown to the agent
    spec.yaml          the full spec, in the schema the clarify gate validates (requirements with proof methods)
    model.py           the golden model, written from spec.yaml alone
    acceptance.py      cocotb tests: the RTL under test against model.py, through the board pins and the test shell
    bench.yaml         toplevel, cocotb module, the shrunk parameters the bench uses, optional wrapper / sim stubs
    tb_*.sv            optional wrapper (open-drain buses, device pins) around the design's top
    mutants.yaml       deliberate bugs in copies of the reference RTL (each must fail the tests) and the trap
    selfcheck.py       on-board check over the shell (board_check.py convention); pass rule in its docstring
  ref/rtl/*.sv         the reference RTL (written for the benchmark, not by the agent)
```

Held-out tasks keep **all** of this in the private repository (`FPGA_Design_Agent_Knowledge/benchmark_private/`);
the public repo lists them by id and hash only, and publishes their `spec.md` only after scoring.

## Conventions every task follows

- The design is a board top named `<id>_top`, with the port names of Digilent's master XDC
  (`boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc`). Pmod and indexed pins are scalar ports: `JA1`, `QSPI_DQ0`,
  `ACL_INT1` (`tools/board_xdc.py` maps them).
- Every design embeds the test shell (`shell/`, PROTOCOL.md 1.1 since 2026-11-12, see AMENDMENTS.md; 1.0 before) on the USB-UART, with the task's DESIGN_ID, and
  puts its registers in the shell window (offsets = shell address - 0x80). Exception: a task whose subject is the
  USB-UART itself says so.
- Time constants are integer clock counts exposed as top-level parameters with the names `spec.md` gives under
  "Test hooks"; the bench shrinks them (bench.yaml). The 100 MHz board clock is the only clock unless a task says
  otherwise.
- The reference XDC is generated from `hidden/spec.yaml` (`tools/board_xdc.py xdc`).

## Tools

| Tool | What |
|---|---|
| `tools/run_task.py <task> [--rtl DIR] [--sim icarus\|verilator]` | the acceptance bench against an RTL directory (the reference by default); per-test pass/fail from cocotb's results.xml. Scoring uses exactly this |
| `tools/check_task.py <task>` | reference passes; every mutant killed; the trap variant fails its trap test. Writes `results/reference/<id>__<sim>.json` |
| `tools/board_xdc.py expand\|xdc` | pins from the master XDC into a spec's ports; the reference XDC from a spec |
| `tools/ref_build.py <task>` | stages the reference into `build/bench/<id>/` and runs `flow/run_vivado.sh` (memory-guarded) and the gates |
| `tools/freeze.py make\|verify\|refreeze` | the manifest (SHA-256 of every file per task, the split, tool versions); `verify` also checks the shell fingerprint; `refreeze UNIT...` re-records named public units for a dated amendment |
| `tools/shell_freeze.py show\|make\|verify` | the shell fingerprint: one hash over what graders import from `shell/` (`GRADER_DEPS.json`); how a scored run uses the frozen shell is in [FROZEN.md](FROZEN.md) |
| `tools/split.py` | the seeded held-out draw (v1); v2: per-task draw at creation into an append-only ledger, see [v2/README.md](v2/README.md) |
| `tools/bank_grep.py` | the knowledge bank must not contain any spec's distinctive phrases |
| `tools/task_leak.py`, `tools/leak_norm.py` | pre-freeze leak guard between tasks: comment-, string- and identifier-insensitive (see "Leak guard" below) |
| `tools/similarity.py` | pool/benchmark spec similarity; RTL similarity to a local clone of the textbook repos (contamination probe) |
| `tools/pin_scan.py` | grader-validity scan (08a2): which hidden benches read a pulled-up or tri-state pin and would fail a legal `1'bz` driver; prints only ids and yes/no flags (`--private` adds the held-out tasks) |

## Tests

| Test file | What |
|---|---|
| `tests/test_bench_static.py`, `tests/test_bench_rtl.py` | v1 tasks well formed, split and manifest verify; the reference passes (Icarus or Verilator) |
| `tests/test_split_v2.py` | the v2 ledger tool: blocks, draws, tamper evidence, the five moves |
| `tests/test_task_quality.py` | every v1, course and v2 task: mutant and trap edits well formed, no new mutant killed only by a build failure; v2 tasks well formed, still equal to their manifests and the ledger, ledger only grows against the base commit |
| `tests/test_task_leak.py` | a held-out snippet copied with comments added and identifiers renamed is caught; unrelated tasks pass |
| `tests/test_tool_guards.py` | `bank_grep`, `similarity` and `split` fail loudly on missing input |
| `tests/test_shell_freeze.py` | the shell fingerprint (v1, course, v2 ledger) matches `shell/`, a changed file is noticed, a frozen copy is accepted; v2 `amend` entries are chained; `run_task` refuses a file named like a shell file |

## Leak guard (brief 83)

Nothing the agent can see (a development task's spec, reference RTL, tests) may give away a held-out task. Two tools:

- `tools/task_leak.py --pairwise <task roots> [--corpus <roots>]` (pre-freeze: each task in turn is the secret, every other
  task a target; `--secret/--target` for a held-out set against public tasks). Every text file of a task is compared.
  Comments and string literals are removed, whitespace collapsed, VHDL lower-cased (`tools/leak_norm.py`; SystemVerilog,
  Verilog, VHDL, Python through the real tokenizer, `#` comment files). Then (1) 80-byte windows of the stripped text and
  (2) winnowing on a token stream with identifiers and numbers normalised (k 12, w 4; code and prose scored apart): the
  share of a secret file or task found in the target, and the reverse. Windows and fingerprints present in three or more
  tasks of the corpus are stock idioms (board tops, test skeletons) and do not count.
- `site/leak_guard.py` (80-byte windows against everything to be published) now also matches on comment- and
  string-stripped text.

**Thresholds** (`task_leak.py --baseline` over all 62 existing tasks, public and private, v1, v2 and course; 3 782 ordered
pairs, idiom filter on): winnowing score median 0.00, 95th percentile 0.07, 99th 0.25; windows median 0. A pair fails at a
score of 0.30 or more (the file-level maximum counts) or more than 100 shared windows (a copied ten-line block gives about
400). The 2 % of existing pairs above that are real sibling tasks that share a module on purpose (the two VGA tasks,
RMSNorm and softmax, the AES and SHA UART tasks, the I2C master and ADT7420, sat_add and mini_alu); they are frozen and not
reopened. A new task is held to the thresholds.

**Rule.** The guard fails to see cosmetic changes only if it does not normalise them, so it normalises them. Comments,
renamed identifiers, different indentation, number radix and key order are never an acceptable way to clear a hit: rework
the visible files so that the structure differs, and re-freeze through the dated amendment log. A guard allowance for
shared scaffolding is a planner decision, written down. Stock scaffolding is exempt only by appearing in three or more
tasks, never by editing it.
