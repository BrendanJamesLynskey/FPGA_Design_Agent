# Brief 159: typed goals in spec.yaml and `agent revise` (review item F5)

`python -m agent revise <design> --goal "lut<=700" [--retarget <part|board>]` plans from goals as data
(`agent/graph/goals.py`, `agent/graph/revise.py`) instead of from the words of a change request. Files here:
`PREREGISTRATION.md` (written before any goal code, with the null result), `labelled_changes.json` (ten changes, labels fixed
beforehand), `measure.py`, `measure.json`. No model call, no Vivado, no simulation, nothing for the spend ledger.

## Result (ten scripted changes on `t1_dimmer_counter` 5, `b58a_trigger` 3, `b96_kr260_10g` 2)

| Arm | stages re-run (of 100) | builds (of 10) | plans that keep stale evidence | plans equal to the label |
|---|---|---|---|---|
| full re-run (stage 0) | 100 | 10 | 0 | 0 |
| F1: brief 149's `classify_change` on the goal text | 84 | 10 | 0 | 6 |
| F5: `agent revise` | 57 | 7 | 0 | 10 |

- The null result (F5 within 5 percent of F1, or any unsound plan) is rejected: F5 re-runs 32.1 percent fewer stages than F1 and
  43.0 percent fewer than a full re-run, with no unsound plan; the pre-registered pass (0 unsound, at least 15 percent below F1, every plan
  equal to its label) holds.
- The whole gain is three changes (C01, C06, C09) where the committed, fresh measurement already meets the bound (LUT 487 against 700,
  8 clocks against 10, 1.087 W against 1.5 W): F5 re-runs nothing, F1 and the full re-run have no way to say so. The other seven are
  the same stage in F1 and F5 except C05 (same-family retarget, stage 3 against F1's stage 1).

## What this does not show
- **The hidden-bench pass rate of the resulting designs is not measured.** The brief's "same pass rate" needs model runs and Vivado. The
  stand-in is soundness against labels, and it is weak: the "met" labels were written from the same committed measurement lists the planner
  reads (a label for an unmet change is the stage table of brief 149), so 10 of 10 exact is partly by construction. What the table does
  establish is that the planner never skips a stage the labels say must run, and that it does not trust a stale measurement (unit test).
- The stage numbers per class (area and latency 1, fmax and power 3, retarget in-family 3) are judgement, as in brief 149. A same-family
  retarget at stage 3 has been planned in dry runs only; nothing ran to confirm that the RTL survives a package change.
- "Met by evidence" takes one committed build as proof of a bound. A different seed or tool version can move a LUT count; power is the
  vectorless estimate; a latency measured in simulation is a simulation figure.
- The three designs are those with a handover and measurements. A library entry (`ip_lib/*`) has no handover, so `resume` and `revise`
  refuse it: `b58a_trigger` replaces the library entry the brief named.
- On these worktree checkouts the handover reports added files (`__init__.py`, test files) that pull the real `revise` entry to stage 2 for any
  change, goal or not (`entry_stage_with_worktree_noise` in `measure.json`). The arms are compared on the stage the goal change itself needs.
- Typed-goal readers: the closure loop and latency loop are tested with fakes (the closure vector and the loop's baseline stop), not run live.
