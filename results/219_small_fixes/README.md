# results/219_small_fixes: records behind brief 219 (eight small fixes)

Brief 219 fixes eight small defects found by briefs 207, 208, 209a and the 209 pilot. The code and its tests are in the pull request; this folder holds
the measured records that two of the fixes stand on.

## Records

| File | What it is |
|---|---|
| `raw/cdc207_sim_before.txt` | the 207 fixture (`flow/tests/fixtures/cdc_margin_207`, Icarus) before fix 3: good design (BAD=0), binary-pointer fault (BAD=1), one-stage fault (BAD=2), plain and with five injection seeds |
| `raw/cdc207_sim_after.txt` | the same runs after fix 3 |
| `raw/gt_buf_sites.txt` | Vivado 2026.1 `link_design -part xck26-sfvc784-2LV-c`: every `BUFG_GT` and `BUFG_GT_SYNC` site, and the part has no site of type `IBUFDS_GTE4` (probe `designs/b56a_gth_serdes/probe/gt_bufs.tcl`) |
| `raw/gt_ref_bels.txt` | the same part: each `GTHE4_COMMON` site and its two IBUFDS bels, and the package pins of the four `MGTREFCLK` functions (probe `designs/b56a_gth_serdes/probe/gt_ref_bels.tcl`) |

## The eight fixes

| # | Fix | Where | Test |
|---|---|---|---|
| 1 | a run that holds a heavy slot (`FDA_HEAVY_SLOT` names its lock file) runs its V3 coverage and mutation steps inside it | `flow/mutate.py` `held_slot`, `take_lock` | `flow/tests/test_219_small_fixes.py` |
| 2 | `report_clock_networks` runs last in the build's synthesis reports and in the check session, and alone in its own session; a crash is recorded as `report unavailable`, never a pass | `flow/build.tcl`, `flow/checks/vivado_checks.tcl`, `flow/checks/__init__.py` `run_sessions`, `flow/standards_check.py` | the recorded 208 crash log, `flow/tests/data/219/clock_networks_segfault.txt` |
| 3 | `cdc_inject` holds a Gray bus as a whole while its input moves by at most two bits between two destination edges | `flow/cdc_inject.py` `gray_signals`, `flow/cdc_models/cdc_inj_pkg.sv` `bus_steps` | the 207 fixture, seeds 1 to 5, good and faulty |
| 4 | the site test compares the family matrix with the bank at the commit `knowledge/PACKS.md` pins | `site/tests/test_site.py` | itself |
| 5 | LOC site names are checked against the part before synthesis; the link planner names the reference-clock site and bel from the board's package pins | `flow/xdc_sites.py`, `flow/prepare.py`, `flow/gt_plan.py`, `flow/gt_parts/xck26.json` | the pilot's two recorded XDC files |
| 6 | the Designer's `lint` tool applies the design's `lint/waivers.yaml` | `agent/core/tools.py`, `flow/lint_ruleset.py` `waive_verilator_text` | `agent/tests/test_219_agent_fixes.py` |
| 7 | a run paused at the programming approval writes `summary.json` and the DOC step, marked `paused` | `agent/graph/run.py` `write_paused_record`, `agent/__main__.py`, `agent/graph/requests.py` | `agent/tests/test_219_agent_fixes.py` |
| 8 | supplied `data/` bus files, and copies of them in `rtl/`, are not mutation targets; the result lists them as `excluded_supplied` | `flow/mutate.py` `supplied_copies` | `flow/tests/test_219_small_fixes.py` |


## Measured

- **Fix 3, good design:** before the fix the read pointer was seen ahead of its source on seeds 1 and 3 (and, in the one-stage arm, the same two seeds); after it, no seed flags it
  (`raw/cdc207_sim_before.txt`, `raw/cdc207_sim_after.txt`).
- **Fix 3, real fault:** the binary-pointer fault (BAD=1) still fails on all five seeds after the fix (a pointer seen ahead, or unknown data from the torn bus), as it did before.
- **Fix 5, the pilot's failure:** the XDC of p1_clkmeter run 3 (`LOC IBUFDS_GTE4_X1Y6`) is refused at line 13 before synthesis, and the message names the board's own answer: package pins Y6 and Y5 belong to
  `GTHE4_COMMON_X0Y1`, bel `IBUFDS0_GTHE4`. The XDC of run 1 of the same spec, which passed in the pilot, is accepted.
- **Fix 5, why no site list for the buffer:** the xck26 has no site of type `IBUFDS_GTE4`; the reference-clock buffer is a bel of the `GTHE4_COMMON` site (`raw/gt_buf_sites.txt`, `raw/gt_ref_bels.txt`).
- **Fix 9 withdrawn** by the planner (owner: a `.sv` file where the task names `.v` is acceptable); its code and tests were removed.
- **Fix 4, cause:** the site data was right. `site/data/family_diffs.json` was regenerated from the bank at the commit `knowledge/PACKS.md` pins (the knowledge-bank re-pin), and matches the matrix tool at that commit. The test ran the tool from the
  owner's working copy of the bank, which sits on another branch, so it failed whenever that copy was not at the pin. The test was wrong; the data was not changed.

## What is illustrative

- The Gray rule is static text plus a runtime step limit: a bus counts as Gray when its driver cone has a Gray-named signal or a Gray conversion, and it is held whole only while its input moves by at most two bits between two
  destination edges. A source more than twice as fast as the destination clock, or a Gray bus that moves by more steps than that, is torn per bit again: the injection then reports a value the source never held, which is the
  pessimism fix 3 removes only up to that ratio.
- The binary-pointer fault is still caught only where a step changes more than two bits at once; a binary count that changes one or two bits at a time is not torn by this model.

## Reproduce

No Vivado is needed to rerun the tests; the two Vivado queries are small `link_design` runs (about 10 seconds each, under a heavy slot).

```
python3 -m pytest flow/tests/test_219_small_fixes.py agent/tests/test_219_agent_fixes.py site/tests/test_site.py
bash flow/tests/fixtures/cdc_margin_207/run_sim.sh /tmp/cdc207   # Icarus; the two sim files in raw/
vivado -mode batch -source designs/b56a_gth_serdes/probe/gt_bufs.tcl
vivado -mode batch -source designs/b56a_gth_serdes/probe/gt_ref_bels.tcl
```

## Known gaps and limits

- The XPM stand-in `xpm_cdc_gray` (`flow/cdc_models/xpm_cdc_models.sv`) keeps the per-bit hold: its lines are transcribed in a Lean record (`V-LEAN-GRAY-STEP`), so editing them makes that evidence stale. The fast-to-slow pessimism is therefore removed only for ASYNC_REG registers in the design's own RTL, not for the XPM macro model.

- The LOC check covers the transceiver site types the part's data lists (`GTHE4_CHANNEL`, `GTHE4_COMMON`, `BUFG_GT`, `BUFG_GT_SYNC`) and the `IBUFDS_GTE4_*` names; other site types, and parts with no data file, are not checked and say so.
- Only the xck26 has site data. A Zynq-7000 or Artix-7 design is not checked for LOC names.
- Fix 7 writes the DOC step at the pause with the same document call as at the end of a run, so with docs on it costs model calls at the pause; no run was made here (no model calls in this brief), so the pause path is
  tested with a stub writer, not on a live run.
- Fix 8: no V3 run was made on a design with a supplied bus (the pilot ran V2). The test is on the candidate list.
