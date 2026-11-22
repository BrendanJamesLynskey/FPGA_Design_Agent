# Brief 167: end-to-end VHDL agent re-run (arm A before brief 153, arm B with it)

Pre-registration: [prereg.md](prereg.md) (committed before the first run; amendments at its end). Table: [table.md](table.md), made by
[summarise.py](summarise.py) from [records/](records/). Driver: [run_one.sh.txt](run_one.sh.txt). Date of the runs: 2026-11-22.
Model: Claude Haiku 5.5 through Claude Code 2.1.321 (every role, plan-billed, no provider-reported cost; the agent's own estimate is in each `summary.json`).

## Result, nulls first

- **Nothing passed.** 0 of 6 runs passed a hidden bench. Only 1 of 6 reached stage 2 at all.
- **5 of 6 runs (both arms) stopped at stage 1** ("stage 1 visited more than 4 times"): the VHDL `build.yaml` the agent writes lists
  `runs/<id>/<design>/rtl/*.vhd`, and the build-yaml check in `agent/core/tools.py` (code unchanged by brief 153) refuses a glob that matches no file; at stage 1 no RTL exists yet.
  All five audit logs show the refusal (6 to 8 times each). The one run that reached stage 2 wrote its `build.yaml` after the RTL existed.
  This is a second, earlier failure that brief 153's fix does not touch, and it hid the effect of the fix.
- **H1 (repair against rewrite): inconclusive.** The only run with stage-2 revisits is in arm A (`r1_G_A`): 0 repairs and 5 fresh writes on visits 2 to 6, as the pre-153 code predicts
  from reading it. No arm-B run reached stage 2, so the other half of H1 (B repairs) is **untested**.
- **H2 (B passes more than A): inconclusive** (0 against 0; the pre-registered rule needs at least 2 complete runs per arm: A has 1, B has 0).
- Brief 55's 0 of 4 is therefore **not explained or ruled out**: this re-run did not reach the stage where 153's fix acts.

## What was run

6 runs, one at a time: round 1 (gray stepper A, B, sync fifo A, B) and round 2 (gray stepper A, B). Round 2 sync fifo A and B were not run (prereg amendment 4).
Tasks, arms, flags: prereg.md.

## Known gaps

- The short stage-1 stops (about 7 minutes each) mean the stage-2 comparison has n = 1 (A) and n = 0 (B).
- `r1_G_A` was cut by the 90 minute wall cap at stage-2 visit 6, with every visit a fresh write; it was scored on the RTL it had (0 of 9 tests; the register map fails like brief 55's runs).
- Model differs from brief 55 (Haiku 5.5 here, luna there): the runs are not comparable in rate.

## Next step the data points to

Make stage 1 accept a VHDL `build.yaml` whose RTL does not exist yet (or tell the agent in the stage-1 prompt not to write `build.yaml` until stage 2), then repeat this brief.
