# Brief 227: pre-registration of the requirements-readiness arms on our own designs (written before any arm run)

Stamped 2026-11-26 14:57 GMT (`date`), executor Sonnet 5.5. Owner decision 2026-11-25: no CVDP pass rates as an evaluation; the arms run on **our own designs**, the six 209 pilot designs, with a hidden full spec for the oracle.

## Question (the owner's headline, 2026-11-25)

"Can the agent reliably build from a very clear requirement?" Arm C starts from a complete requirement document (stage 0 bypassed). Arms A and B show how much of today's failure is requirements (A against C) and how close the readiness gate with an oracle gets to the given requirements (B against C).

## Designs, arms, repeats

- Designs: **p1_clkmeter, p2_bram_rom, p3_crc_engine** (the three that reached a bitstream in brief 209; p4 to p6 failed there for the output-length limit that brief 224 fixed, and are used for the stage-0 gate runs only).
- **A**: the request as the user wrote it (`pilots/209/<design>/spec.md`), nobody to ask: `--interview off --requirements loose` (the agent's defaults are taken and listed).
- **B**: `--interview oracle --readiness on --requirements loose`: the oracle answers only with a verbatim quote from the hidden spec; the build follows only if the gate froze the set. A stop at stage 0 is the result `stopped at stage 0` with its open questions.
- **C**: given requirements: the request followed by the further answers (`pilot_hidden_specs/<design>.md`) as one document, `--interview off`, `--readiness off`. These hidden specs were written for this brief by the executor as the user's answers (**not owner-sourced**): reset values, out-of-range and simultaneous behaviour, side effects. They carry no test values.
- **k = 3 runs per design per arm** (repeats are the point: "a design that passes 1 run in 3 is not reliable"). 27 runs if all three arms are built; arm B is built only for designs whose gate froze.
- Every run: Claude Code 2.1.321 pinned (SHA-256 `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`), Sonnet 5.5 effort medium for every role and the oracle, `--stop-after 2 --no-shell --verif-level V2 --board kr260`, simulation only (no Vivado, no slot; load under 6 and more than 12 GB free), plan-billed, no OpenRouter (the oracle runs on `--oracle claude_code`).

## What counts as a pass, and what cannot be said

- **There is no independent check of the built behaviour in this brief.** The independent checks of the pilots are the host scripts (`pilots/209/host/check_p*.py`) that talk to a loaded board over JTAG; no board command is allowed here, and the designs' top modules and port names differ from run to run, so a simulation harness for those scripts was not built. The hardware column is **pending**.
- A run "passes" here if it reaches the end of stage 2 at V2 (its own lint, simulation, standards and verification checks) **and** the stage-2 independent spec-only bench (`spectest`, written by a separate role from the spec and never the RTL; it shares the model family) does not fail. This is the project's gate set, not ground truth: the 215 cross-table (own check against independent) shows the own check is not a reliable proxy (agreement 23 of 49). Results are labelled "gates", never "correct".
- Per design and arm: pass rate over 3, pass on all 3 (pass^3), pass on any (pass@3) with Wilson intervals; paired by design across arms; plus per run the failure class from {interface, timing, reset, handshake, functional, testbench wrong, tool, cut-off reply, budget} by a code rule over the stop reason and the failing gates, and a hand check of every failure; plus tokens, the plan-cost estimate, wall time and, for B, rounds, questions, agreement per round.
- **Power**: 3 designs x 3 runs per arm cannot detect a difference below about 35 points; the comparison between arms is descriptive and no significance is claimed. Stated before the runs.
- The gate is also run on the arm C documents (stage 0 only, `--readiness on`, nobody to answer): the open questions it raises on a document written to be complete show how complete it was.

## Stage-0 runs on all six pilots (the gate on real FPGA designs)

`--interview oracle --oracle claude_code --readiness on --requirements loose --stop-after 0`, one run per design, no build: rounds, questions asked and answered by the oracle, questions the hidden spec could not answer, reader agreement per round, repairs, and what the gate would have stopped on.

## Stop rules

Weekly usage 92 % (owner plan 2026-11-26): read before each launch (`run_arm.sh` refuses at 90 % and writes the STOP flag); a run stopped by the plan limit is recorded `rate_limited` and re-run, never scored. A run that hits the harness's own limits is a result (a failure of its class), never re-run.
