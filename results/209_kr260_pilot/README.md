# 209: KR260 pilot (agent-generated designs, tested on hardware)

Question: can the agent take a short written spec to a design that passes on the owner's KR260 first time, with no human or Claude hand-fixes?
Headline (to be filled after the board visit): N of 6 passed on hardware first time. State: **prep complete, agent runs on hold** (planner, 2026-11-24; waits for brief 209a).

## Records

Specs, draft pre-registrations, host checks and mock-bus tests are in `pilots/209/` (`<id>/spec.md`, `<id>/preregistration.md`, `host/`, `tests/`). No agent run has been made yet.
Per run (3 runs per design, `anthropic_api`, claude-sonnet-5-5): all columns below stay empty until the runs; hardware columns stay "pending board visit" until the owner's run.

| Design | Run | Gates passed | Fmax / timing | LUT / FF / BRAM / DSP | Tokens | USD | Wall time | Interventions | Reached hardware | Hardware result |
|---|---|---|---|---|---|---|---|---|---|---|
| p1_clkmeter | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |
| p2_bram_rom | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |
| p3_crc_engine | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |
| p4_fir_dsp | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |
| p5_async_fifo | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |
| p6_glitchfree_mux | 1-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending board visit |

Then per design: mean and spread (min, max) over the three runs of gates passed, Fmax, resources, tokens, USD and wall time.

## Reproduce

Host-check dry runs (no board): `python -m pytest pilots/209/tests`. Interventions: `pilots/209/interventions.yaml`. Board stages (owner, with the planner's command): `pilots/209/run_pilot_board.sh <stage> YES`.

## Known gaps and limits

- The register map is part of each spec, so the host checks were written before any design exists; bus and bring-up details may change with brief 209a.
- C3 frequency (P1) is measured relative to the GT reference clock, which has not itself been measured.
- Mock buses model the spec, not a real design; they test the check logic only.
- Visit-plan section (`next_board_visit_plan.md`, "Added <date>: brief 209 pilot") is not written yet; it needs the stamps.
