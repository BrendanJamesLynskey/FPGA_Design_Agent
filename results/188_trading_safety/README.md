# results/188_trading_safety: trading-path safety fixes (brief 188)

Records of brief 188: level sizes saturate, risk limits are staged and committed together, the price-band reference can come from software, a notional check as a multiply or a software table, a per-instrument hold-off, and a measured answer on the b58a token bucket. Ideas from Edwards 2026 (ch 8, 9, 13), written from scratch.

## Records
- `uvm/`: the full UVM regression of brief 170/176 on the new RTL (`summary.json` is what the b110 testplan reads; `results.tsv` every run; `coverage_report.md`).
- `pytest_junit.xml`: the b110 model, cocotb bench (27 tests, new ones `level_size_saturates`, `soft_reference`, `soft_reference_age`, `holdoff`, `price_wrap`, `notional`), notional builds, notional latency, lint and the SymbiYosys proof.
- `staged_limits_sim.json`: whole core in xsim 2026.1: a limit lowered but not committed stays out of force, COMMIT applies it.
- `mutation_new.json`, `mutation_rerun.json`: the 14 new or changed seeded faults; 13 killed first time, the survivor (`risk_nt_tbl_idx`) was killed after a test was added (rerun file).
- `nt0/`, `nt1/`, `nt2/`: `latency_sim.json` of the builds with NOTIONAL_MODE 0, 1, 2.
- `ooc/`: out-of-context Vivado 2026.1 builds of itch_ouch_top for NOTIONAL_MODE 0, 1, 2, with the check computed in the verdict clock (`same_clock_nt*.json`) and pipelined (`pipelined_nt*.json`); `notional_measurement.md` reads them.
- `build_rm_gp_itch/`: the rebuild of rm_gp_itch with the new registers (`build_one.sh` runs it).

## Measured
UVM: 40 runs, 0 failed, 0 SVA failures, SEQ 538 comparisons 0 mismatches, 97 of 97 bins. Latency in clocks from the last byte of the message, equal in all three NOTIONAL_MODE builds and equal to brief 110's record: book update 7, first order word 8 (3 when speculative). BMC from reset to depth 12 of properties Q1-Q6, 86 s, and the cover that a saturation is reachable (step 9).

## Illustrative or not measured
All data are synthetic. Hold-off and software-reference age are clock based, so the untimed Python model does not cover them; the bench tests them with exact clock margins. No board run: board steps are pre-registered rows in `next_board_visit_plan.md`.

## Known gaps and limits
No k-induction (the invariant over the ladder memories needs a strengthening). The register window of rm_gp_itch has no room for the notional table, so the board build has NOTIONAL_MODE 0. The mutation sweep of brief 170 (60 % worst case) was not repeated. b119's own evidence is older than the RTL it reads (its matrix says so).

## Reproduce
`python3 -m pytest -q designs/b110_itch_ouch/tests`; `python3 designs/b110_itch_ouch/tests/run_mutants.py --only <names>`; `B188_RECORD=$PWD/results/188_trading_safety python3 -m pytest -q designs/b96_kr260_10g/rm_gp_itch/tests/test_b188_staged_limits_sim.py` (xsim); `designs/b96_kr260_10g/rm_gp_itch/verif/uvm/scripts/run_regress.sh --out <dir> --record results/188_trading_safety/uvm`; `python3 -m designs.b110_itch_ouch.ooc.ooc --clocks 6.2061 5.0 --tag <t> --param NOTIONAL_MODE=<0|1|2>`.
