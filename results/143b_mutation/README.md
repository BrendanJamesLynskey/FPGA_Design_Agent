# Brief 143b: mutation score records

**Correction (brief 152, 2026-11-22).** The b96 row below is replaced by [results/152_b96_mutation](../152_b96_mutation/README.md). Two statements on this page about it are wrong: the design's SymbiYosys bench
*did* catch the L107 survivor (it fails `p6c_spec_matches_rtl` at step 10 in 2 s; the 143b run never started it, because the filter deleted each survivor's copy before the formal bench looked for it,
so `killed_by_formal_bench` 0 meant not run), and the left-out 5000-frame cases do not catch it either. The record itself is kept as it was made.

Recorded 2026-11-21, seed 1, blind mutants (`flow/mutation_blind.py`, 23 operator classes), survivors decided by a formal miter (`flow/mutation_equiv.py`).
Method, rules and the meaning of each verdict: [docs/mutation_score.md](../../docs/mutation_score.md). Re-run: `python3 -m flow.mutation_score run TARGET --seed 1`.
Each record is a JSON file (`fpga-design-agent/mutation-score/v1`) that lists every mutant, its change, its bench status and its formal verdict.

## Records

| Record | Bench | Mutants evaluated (invalid) | Killed | Survived the bench | Equivalent | Real survivors | Undecided | Score before the filter | Score (headline) | Worst case |
|---|---|---|---|---|---|---|---|---|---|---|
| [b96_rate_match_gp.json](b96_rate_match_gp.json) | cocotb vs Python twin, Icarus (trimmed, see below) | 10 (0) | 7 | 3 | 0 | 1 | 2 | 70.0 % | 87.5 % | 70.0 % |
| [b119_tcp_fast.json](b119_tcp_fast.json) | the design's cocotb bench | 30 (0) | 29 | 1 | 0 | 0 | 1 | 96.67 % | 100 % | 96.67 % |
| [arith_isqrt.json](arith_isqrt.json) | the library's exhaustive stream test, three variants | 35 (5) | 29 | 6 | 6 | 0 | 0 | 82.86 % | 100 % | 100 % |
| [arith_lzc_norm.json](arith_lzc_norm.json) | the library's exhaustive stream test, four variants | 39 (1) | 35 | 4 | 4 | 0 | 0 | 89.74 % | 100 % | 100 % |

Score = killed / (killed + real survivors); worst case counts every undecided mutant as a survivor; before the filter counts every survivor. No bench timed out in any run.

## What the filter did

* The arith survivors (10 of 10) are all proved equivalent by the miter, so the filter lifts those two scores from 82.86 % and 89.74 % to 100 %: the
  bench was not weak there, the raw score was understating it.
* b119 has one survivor the proof could not decide (BMC clean to 30 clocks, the unbounded proof timed out at 240 s). It is reported as undecided, so the
  headline is 100 % and the worst case 96.67 %; the two are not merged.
* b96 has one real survivor, L107 (`head_frame`: the `8'hFB` start-of-frame byte compared in the lane-4 start case changed to `8'hFA`). The miter finds a
  counterexample in 30 clocks, so it is a behaviour difference, and the bench did not catch it. The design's own SymbiYosys safety bench (`rm_gp.sby`, 
  bound to the target) did not catch it either (`killed_by_formal_bench` is 0). Two more (L130 `<` to `<=` on the fill minimum, L139 idle run counter +2)
  are undecided: no counterexample to 30 clocks, no unbounded proof.

## Reproduce

```
python3 -m flow.mutation_score run b96_rate_match_gp --seed 1 --count 10 --jobs 2 --mutant-timeout-s 2400 --prove-s 240
python3 -m flow.mutation_score run b119_tcp_fast --seed 1 --count 30
python3 -m flow.mutation_score show results/143b_mutation/b96_rate_match_gp.json
```

Needs the OSS CAD Suite pinned by CI and the repo's venv (cocotb). The arith runs use `arith_b139b`, a `git archive` of the arith tree of PR 263's branch.

## Known gaps and limits

* The b96 bench is not the full `test_rate_match_gp_cocotb`: its two longest cases (5000 frames at 400 ppm) are left out so that a mutant costs about
  8 minutes (baseline 495 s). A mutant the full bench catches could survive here; the L107 survivor in particular might be caught by a left-out case.
  Not checked.
* b96 has 10 mutants out of 135 candidates and b119 30 out of 451: small samples of the operator space, one seed each. The b96 score has a wide interval
  (7 of 8 decided).
* The arith RTL comes from branch `b139b-arith-previvado` (PR 263, not on main at the time); the record names the commit and the RTL hashes.
* The formal verdicts are of the listed configuration (for b96: `AW=4 HI=1`) with Yosys and the slang front end, from the reset state; see the docs page.
* No LLM-proposed bugs were used (`llm_proposals_valid` is 0 in every record): the optional LLM path exists and is tested with canned proposals only.
* No requirement in a real testplan binds a mutation floor yet (the reader is tested on synthetic records); that is the planner's decision.
