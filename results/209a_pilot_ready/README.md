# Brief 209a: the agent made ready for the KR260 pilot

Two specs for the live checks of brief 209a: a toy design for a board with no UART (two registers and an LED blink on the KR260, reached over the JTAG register
bus) and a design that is deliberately too deep for its clock (the report gates of brief 204a send it back to the Designer). The runs were made with the subscription
harness (`--harness claude_code`, Sonnet 5.5); no OpenRouter or Anthropic API call was made.

## Records

- `toy_jtag_leds/spec.md` and `toy_jtag_leds/data/jtag_bus.sv`: the request of the JTAG-route toy run (the bus is `designs/b58a_trigger/rtl/jtag_bus.sv`, unchanged).
- `deep_for_clock/spec.md`: the request of the report-gate run (24 dependent multiplies in one 40 ns clock).
- `toy_jtag_leds/jtag_bus_utilization_hier.rpt`: the hierarchical utilisation (Vivado 2026.1, xck26) of the first toy run that built: `jtag_bus` is 90 LUTs and 413 flip-flops (u_bus 200, u_cmd 90, u_resp 120 flip-flops); the Designer's note quotes these.
- `toy_jtag_leds/run/`: the record of the toy run that reached a bitstream (run 20261125-003327-c4f4, `--verif-level V2`): `run_summary.json` (tokens, turns, wall time and the plan cost estimate per stage, from the run's `role_usage.jsonl`), the agent's own `hw_checks.py` and `BRINGUP.md`, `mock_run.json` (every check of that `hw_checks.py` against its own mock bus, run by `python -m flow.host_transport`), `bringup_ready.json` (the bring-up artefact gate) and `routing_events.jsonl` (the report-gate decision at each visit).
- `deep_for_clock/run/`: the record of the report-gate run 20261124-230657-f934 (default verification level V3, `--stop-after 4`): `run_summary.json` and `designer_message_visit4.txt`, the Designer's own reply on the visit after the gate fired.

## The report-gate run

The request chains 24 dependent 32-bit multiplies in one 40 ns clock with no register inside. The first synthesis build of stage 2 went to the report gate; the Designer's reply of visit 4 says it split the chain into four pipeline stages "because the report gate requires pipelining" and that the worst path was 253 logic levels, about 60 ns of logic and about 18 ns of net delay, so the gate fired, the finding reached the Designer, and the Designer changed the RTL. It also says that this breaks the request's own requirement REQ-08 (no register between `a` and `y`); the Designer left that to the owner or the verifier to judge. The run then stopped at the stage-2 visit limit, on the V3 mutation score (50 %, need 70 %), not on the gate. The gate's own text is not in the run files (the repair prompt is private and was not logged then); the routing-event record of the gate decision (`report_gates_checked` in `routing_events.jsonl`) was added after this run. A second run (20261125-005310-2449, `--verif-level V2`) was stopped by me after 26 minutes in one simulation of the 24-multiply chain and made no record.

## Runs of the toy spec (all on the subscription harness, Sonnet 5.5, no board)

| Run | Change since the run before | Where it stopped | Tokens | Wall (s) |
|---|---|---|---|---|
| 20261124-213035-3a4c | first JTAG note: copy `jtag_bus.sv` into rtl/ | stopped by me at stage 2, visit 4: V3 mutation score 30 % (mutants of the supplied bus) and the CDC-injection check | 3,014,757 | 829 |
| 20261124-215935-0c23 | bus kept in data/ | stopped by me at stage 2: the run held both heavy slots and its own V3 coverage step waited on the lock | 3,148,231 | 729 |
| 20261124-223426-42f2 | V3 lock moved to a private file | stage 2 visit limit: 15 of 15 mutants "do not compile" (the mutation compile left out data/jtag_bus.sv) | 4,095,433 | 911 |
| 20261124-231314-3a61 | `flow/mutate.py` compiles with the build's other sources | stage 2 visit limit: the agent's own top-level bench failed | 4,096,519 | 1,027 |
| 20261124-235800-8fea | `--verif-level V2`, note says one simulated toplevel | stage 1 visit limit after stage 4: the architecture's flip-flop range (150 to 260) left out `jtag_bus` (552 used) | 3,050,600 | 1,456 |
| 20261125-003327-c4f4 | the note gives `jtag_bus`'s measured cost | **stage 9: bitstream built, all five flow stages pass, `bringup_ready` ok, `hw_checks.py` passes against its mock; paused for the owner's approval to program** | 3,980,720 | 1,717 |

Tokens and wall time are sums over the run's role calls (`role_usage.jsonl`); a run stopped at a limit has a `summary.json`, the two I stopped have none.

## Reproduce

`python -m agent run results/209a_pilot_ready/toy_jtag_leds/spec.md --board kr260 --harness claude_code --cc-model claude-sonnet-5-5 --review off --interview off`
and the same for `deep_for_clock` with `--stop-after 4`. Both need the pinned private prompts and Vivado 2025.2 (a heavy-job slot on the shared PC).

## Known gaps and limits

The runs depend on the model and are not repeatable to the byte; they are single runs, not a measurement of the agent's rate.
