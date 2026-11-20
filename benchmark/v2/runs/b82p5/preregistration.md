# b82p5: one planted live run of the derived-constants exit gate (pre-registration)

Written 2026-11-20 on branch `b82p5-mismatch-gate`, committed before the run. Development measurement on the L2 UDP endpoint task
(`v2_e_udp_endpoint`, development split); nothing here reads, lists or copies a held-out task. The hidden bench used for scoring is the
task's own, unchanged.

## Why

82P4 wired the derived-constants check (HDL-ORC-01, `flow/derived_constants.py`) into the stage-2 and stage-3 exit gates. In the six
live runs the model never bound a wrong constant, so the gate never fired live (its effect is shown only on planted tests and recorded
82P3 RTL). Owner decision 19 puts one planted live run before the 4 h measured run (82P6). This brief asks only: when a live run binds a
wrong derived constant, does the gate block it, name both values, and does the run recover?

## The plant (`planted/spec.md`, the only change to the task)

The 82P3 spec with two sentences changed (diff against `../../tasks/v2_e_udp_endpoint/spec.md`):

1. **Design ID.** The register list now says register 0's identification word `0x55445031` "is also the word the shell's design-ID
   register must show". The spec still says, in its last paragraph, `The design ID is "UEP1"` (= 0x55455031 as four ASCII characters,
   most significant first, `shell/PROTOCOL.md` register 0x00). The prose therefore points at the wrong hex value; the quoted ASCII
   string is the derivation the gate uses. **Right value: 0x55455031.** The endpoint's own register 0 keeps 0x55445031.
2. **Board clock.** The first paragraph now says everything runs on "the single 125 MHz system clock (an 8 ns period in the clock
   constraint)". The Nexys A7-100T's oscillator is 100 MHz (`boards/nexys_a7_100t/board.yaml`, 10 ns). **Right value: `create_clock
   -period 10.000` on `CLK100MHZ`.**

Dry check, before the run (not the live run, `posthoc/gate_dry_check.txt`): `python3 -m flow.derived_constants` on the 82P4 B r3 RTL with
the shell DESIGN_ID set to 0x55445031 and the clock period set to 8 gives `CONST-ID-01` and `CONST-CLK-01`, both blocking; with the right
values it gives none.

## What the gate should do (the expectation being tested)

- At every stage-2 visit the `constants` gate runs on the design as it stands (`agent/graph/run.py: constants_gate`), writes
  `build/derived_constants.json`, and a blocking finding fails the stage, skips the spec-test bench and the Vivado build on that visit and
  hands the RTL role a `[derived constants]` finding (`agent/graph/repair.py: stage2_owners`). `CONST-ID-01` and `CONST-CLK-01` are
  the two blocking codes for the two plants. Both route to the RTL role in stage 2 (it may write `rtl/*` and `design.xdc`). Stage 3 is
  not reached (`--stop-after 2`).
- The RTL role is expected to change the bound value to the right one on the next visit.

## Command and configuration (one run; arm A of 82P3/82P4: `spec_tests` off)

`python -m agent run benchmark/v2/runs/b82p5/planted/spec.md --name v2_e_udp_endpoint --board nexys_a7_100t --interview oracle
--hidden-spec <task>/hidden/spec.yaml --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --oracle claude_code
--oracle-cc-model claude-haiku-5-5 --review off --stop-after 2 --verif-level V2 --docs off`. L2, Sonnet `claude-sonnet-5-5` for every
role through `claude_code` via the 108 model table (the resolved table and its hash are in the run's `config.json`), Haiku oracle,
never Fable or Opus. Pinned CLI copy 2.1.321 (SHA-256 in `environment.txt`), `DISABLE_AUTOUPDATER=1`, version checked before launch
(mismatch: PREFLIGHT_FAIL, no run). **Hard wall limit 4 h** (owner decision 19). Heavy slot through `take_heavy_slot.sh` with text
starting "82P5:" (stage 2 has a Vivado synthesis gate), `systemd-run --user --scope -p MemoryMax=8G`, `nice 10`, `FDA_VIVADO_MAX=1`.
No launch at 88% weekly usage or more. The agent, knowledge, prompts and benchmark are not changed between this commit and the run.
Scoring: `benchmark/tools/run_task.py` on the run's `rtl/` against the unplanted hidden bench, Icarus, unchanged; no LLM scores anything.

## Outcomes, fixed before the run

Per plant (ID, clock) and for the run:

| Outcome | Condition (from `build/audit.jsonl`, the stage snapshots in `snap.git`, `summary.json` `constants`) | Reading |
|---|---|---|
| **Gate test passed, recovered** | a snapshot binds the wrong value, the next stage-2 gate evaluation lists the blocking code, the RTL role then binds the right value | gate works and the hand-off recovers |
| **Gate test passed, run failed elsewhere** | as above for the block, but the run then fails or is killed for a reason unrelated to the constant (visit limit on other failures, 4 h limit) | gate works; the run's other outcome is reported as it is |
| **Gate test passed, not recovered** | the gate fires and the constant is still wrong at the end | gate works, the repair hand-off fails: a finding about the hand-off |
| **GATE FAILURE** | any snapshot that a stage-2 gate evaluation saw binds a wrong value of a planted constant and `constants.findings` shows no blocking finding at that evaluation | the gate does not fire on a wrong binding |
| **Not exercised** | no snapshot at any visit binds a wrong value (the model read through the plant, or the clarify stage resolved it) | inconclusive for the gate; reported plainly, not counted as a pass |

A blocking finding on a value that is in fact right would be a false positive and is reported as one. The run's hidden-bench score is
reported but is not the test; pass or fail on the hidden bench says nothing about the gate. No run is repeated for a better result; an
infrastructure failure (no model turn recorded) is evidenced and re-launched once, labelled.

## What is recorded

The record under `records/`, the run's `summary.json` (`constants`, `stop`, stages), per-visit constants findings and the bound value of
each planted constant in every stage snapshot (`posthoc/`), the exact gate events from the audit log, the hidden score, wall time, tokens
and plan-equivalent cost. Private material (the run directory archive with rendered prompts) goes to the private knowledge bank
(`results_private/benchmark/v2/runs/b82p5/`) with a pointer in `artifacts/`; `tools/prompts/leak_allow.txt` is not edited.
