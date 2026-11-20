# 82P5 Part A: why the B arm's stage-2 simulation disagreed with its model (82P4 runs B r2 and B r3)

Diagnosis from records only; the agent was not changed. Sources: the two run directories (private archives, KB
`results_private/benchmark/v2/runs/b82p4/artifacts/<run>/run_dir.tar.gz`: audit log, per-role Claude Code transcripts, `summary.json`
turn trace, the final model, bench and RTL), the task's visible spec (`benchmark/v2/tasks/v2_e_udp_endpoint/spec.md`), and the repair routing
code (`agent/graph/repair.py`). The rendered prompts are archived as hashes only, so what each role was told is reconstructed from the code
(replayed, `posthoc/replay_stage2_owners.txt`) and from the roles' own statements; that part is labelled where it matters.

## The one cause

All three artefact writers (model, bench, RTL) took the same length table from the spec (read 2, write 6, telemetry start 2) but
**the bench built packets with a 1-byte register number** (read payload 1 byte, write payload 5), while the model and RTL kept the length table.
The bench therefore sent packets the RTL and the model both judged "wrong length" (status 2, a 9-byte reply) where the bench expected status 0
(a 13-byte reply). It also expected status 2 for the very same packet in its wrong-length test, so the bench contradicted itself.

The spec line (visible spec, "Commands"): *"The payload a type needs: read 2 bytes (a register number), write 6 (a register number, then a
32-bit value, high byte first), telemetry start 2 (the period in ticks), status and stop none."* The width of the register number is not stated as a
number, but the write payload is a register number plus a 4-byte value in 6 bytes, so the register number is **2 bytes, high byte first**
(and the read payload of 2 bytes is just that number). The spec is derivable here, not open: no reading of it makes a write 5 bytes long.
Sure: high (the arithmetic is in the text; the scored hidden bench of 82P4 gives these two runs 1 of 10 each, the passing arm-A runs all
decode two bytes).

## Classification of every mismatch seen

| # | Mismatch (where seen) | Class | Spec line each side relies on | Sure? |
|---|---|---|---|---|
| 1 | Bench read/write helpers send 1-byte register number: `status 2 expected 0`, `9 == 13` (B r2 visits 1 to 6, B r3 visits 2 to 6; B r3 final sim: `read offset 2: dut 0xd model 0x9`) | **Test-bench fault** (bench contradicts spec and its own wrong-length test) | Bench: "read 2 bytes (a register number)" read as 1 byte, and "write 6" ignored (it sums to 5). RTL and model: "read 2 ... write 6", the length table | high |
| 2 | `dut 0xd model 0x9`: reply-length word 13 (a 4-byte read reply, 9+4) against 9 (a status-2 reply) | **Not a separate defect**: it appears only in the visits where the RTL role tried accepting the bench's 1-byte read and 5-byte write; the DUT then answered status 0, the model status 2 | same lines; the experiment left the RTL wrong against the length table, the model right | high |
| 3 | B r3 `read offset 4: dut 0x820044e4 model 0x820244e4` (status byte 0 against 2) | same as 2 (RTL tolerance experiment, visit 4) | same | high |
| 4 | Model and RTL both take the register number from payload byte 0 (B r2: value from bytes 1 to 4 / RTL wval pbuf[5..8]; B r3: model and RTL read the number from the first payload byte and the value from bytes 2 to 5) | **Model and RTL wrong against the spec, latent**: both decode a 1-byte register number while keeping the 2/6 length table; they agree with each other, so no simulation can show it (hidden bench 1 of 10 each) | "a register number, then a 32-bit value" inside a 6-byte payload | high |
| 5 | V2 gate `constrained_random_test_ran` ("no passing test with 'random' in its name") and `planned_tests_missing` | **Consequence of 1**, listed as a Verifier failure | none (gate rule) | high |
| 6 | B r3 only: the first three simulations of visit 1 timed out at 1800 s each (a 65,536-packet counter-wrap test, about 4e7 clocks) | **Harness / bench size fault**, found at visit 2 and fixed by running the short wrap test | "counters wrap at 65536" | high |

Nothing here is a disagreement the spec leaves open. The B r1 run (afd9, not the subject of this brief) shows the same field mis-read differently:
its spec.yaml says "register number (1 byte) ... giving 6 bytes" (1+4=5), its bench writes `[reg, value x4, 0]` (a spare byte), reads `[0, reg]`.

## Why six repair visits did not converge

The loop never gave the one role that could fix the fault the evidence that it was its fault. Per visit (B r2: `summary.json` turn trace; B r3 likewise):

1. **The RTL role was told every time, and was right every time.** The failing simulation is routed by `classify_sim` to the RTL role as a
   "mismatch" (first suspect: the RTL). In all 5 repair visits of B r2 and in 3 of 5 of B r3 (visits 2, 3, 5) the RTL role changed no file (`files_changed` empty; at B r3 visits 4 and 6 it
   wrote the RTL as an experiment, accepting the bench's lengths, and reverted it) and said in every final message that the bench contradicts itself and the spec ("the fix belongs to the Verifier"). That message is shown to nobody:
   the graph builds each role's input from evidence only, never from another role's words.
2. **The Verifier (the bench's owner) was handed a different failure.** `stage2_owners` adds the "same failure survived a repair of the RTL: check that
   the bench drives the ports as the spec says" hint to the Verifier at repeat 1 only `if ... "tests" not in owners`. But the Verifier
   already owned a failure at every visit: the V2 gate `constrained_random_test_ran`, a consequence of the failing simulation that the
   routing does not treat as covered (it drops only `failing_tests` and `planned_tests_missing`). So the hint was never sent. Replay on evidence
   of the recorded shape: `posthoc/replay_stage2_owners.txt` (the Verifier gets the gate note at every repeat; with the consequence check
   treated as covered it gets the hint at repeat 1). The Verifier's own words confirm it: "I couldn't see the gate output ... I don't know why
   the gate saw no passing random test" (B r2 visits 2, 3, 5, 6; B r3 visits 3 to 6); it spent them on test-module lists, the wrap test length, and the
   testplan, never on the packet length.
3. **When the Verifier did notice, its brief told it to stay small.** B r3 visit 3: it listed the bench/model length disagreement and wrote "I left this
   alone because you asked for the smallest fix". It had not been shown the simulation output either (it could not read `build/`).
4. **The Modeller was told only a test name, from repeat 2** (it is kept blind to the RTL and bench by design) and guessed: reset width, busy bit,
   refused-counter width. Its decode of the register number was itself the same 1-byte reading.
5. The visit limit (6) then ended the run with the stop reason "stage 2 visited more than 6 times": the true cause, written correctly five times by
   the RTL role, appears nowhere in `summary.json`.

So the repair loop lacked two things: the **evidence-only fact** that the RTL role declined to change anything while the failure stayed
unchanged (available in the turn trace), and a **hand-off that carries the failing assertion to the bench's owner**.

## Arm A against arm B

Up to the end of stage-2 simulation the two arms run identical code: `--spec-tests` acts only after the simulation passes
(`agent/graph/run.py`, the spec-test gate at the simulation-ok test; `purposes_in_use` adds one role purpose). A had no mechanism that B lacked.
The difference is how the first roles read the register-number field. Decoding of the register number in the final artefacts
(`posthoc/register_width_by_run.json`, from the archives):

| Run | Model | RTL | Bench helpers | Result |
|---|---|---|---|---|
| A r1 (448e) | 2 bytes `(pl[0]<<8)\|pl[1]` | 2 bytes `{pbuf[4],pbuf[5]}` | 2 bytes | own stage 2 passed; hidden 10/10, killed at 3 h |
| A r2 (a5da) | 2 bytes | not extracted; hidden 10/10 | 2 bytes | hidden 10/10, killed at 3 h |
| A r3 (97ce) | 2 bytes | not extracted; hidden 10/10 | 2 bytes | hidden 10/10 |
| B r1 (afd9) | read 2 bytes, write 1 byte plus spare | read 2 bytes, write 1 byte | read `[0,reg]`, write `[reg, v x4, 0]` | stage 2 visit limit, hidden 4/10 |
| B r2 (553a) | 1 byte | 1 byte | 1 byte | 1/10, visit limit after 27 min |
| B r3 (68eb) | 1 byte | 1 byte | 1 byte | 1/10, visit limit |

In the model and bench helpers, all three A runs and none of the three B runs decoded two bytes (A's RTL is evidenced by the hidden 10/10 and, for A r1, the extracted line). The clarify output (spec.yaml) says the same words in every run
("read needs length 2 (register number)"), so it is a per-run reading. n = 3 per arm: this is a chance difference in one field reading, not an
effect of the spec-test bench, and no rate is claimed.

## Smallest change that would converge or stop with the right diagnosis (proposal; not made)

Ordered by size; the first two together are the proposed content of 82P6's pre-registration.

- **P1 (hand-off, about 10 lines in `agent/graph/repair.py` plus the prompt text).** (a) Treat the V2 consequence checks
  (`constrained_random_test_ran`, `assertions_bound_zero_failures`: both already say "see failing_tests") as covered whenever the simulation
  failure is a mismatch, as `failing_tests` already is; (b) append the repeat-1 hint to the Verifier even when it owns other failures, and put in
  the failing assertion and its source line, the bench and model lengths question ("does the bench send the lengths the spec table needs?").
  Replay: with (a) alone the Verifier receives the hint at repeat 1 (`replay_stage2_owners.txt`). Evidence it is enough: the Verifier role
  reported the contradiction unprompted at B r3 visit 3 and only stopped for want of a mandate.
- **P2 (an evidence-only escalation).** When the RTL repair visit changes no file and the simulation signature is unchanged, call it "RTL declined"
  and at that visit give the Verifier the failing assertion text and the Modeller the test name, instead of waiting for repeats 1 and 2. The signal
  is in the turn trace (`files_changed == []`): present at visit 2 in B r2 and B r3. This respects "from the evidence only".
- **P3 (stop with the diagnosis).** If, after P1 and P2, two consecutive visits end "RTL declined" with the same signature, stop with a stop reason that
  names it ("stage 2: RTL unchanged for two visits, simulation unchanged: the bench or the model disagrees with the spec table") and write the RTL
  role's last message into `summary.json`, so the run record carries the right diagnosis instead of "visited more than 6 times".
- **Not proposed as smallest:** a model-in-the-loop run of the bench against the Python model before any RTL exists (it would have caught this at visit 1,
  but needs a bench-to-model adapter); a spec-layout check in the clarify stage (field widths by arithmetic against the length table), in the style of
  HDL-ORC-01; an oracle question at repair time. Worth a brief of their own if P1 to P3 do not move the stage-2 failure rate.

Not tested: the proposals are not run; whether the Verifier fixes the bench once given the hint is a prediction from its own earlier statement.

## Other findings (for the planner; outside this brief)

- Model and Verifier roles cannot read `@shell/PROTOCOL.md` in stage 2 ("no read-only shell view in this session"); the Verifier guessed `CLKS_PER_BIT`
  and could not read `build/verif/sim/seed1/results.xml` or `flow/cocotb_run.py`. Each of these shows up as guesswork in their final messages.
- B r3 visit 1 spent about 46 minutes in three 1800 s simulation time-outs (full counter wrap in the bench) before the loop reached a failing test.
