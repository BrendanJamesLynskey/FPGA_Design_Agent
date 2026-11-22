# Brief 152: mutation score of the b96 rate matcher's bench (`rate_match_gp.sv`), the full bench, 2026-11-21 to 2026-11-22

Records in the schema of [brief 143b](../143b_mutation/README.md) (`fpga-design-agent/mutation-score/v1`). Method and verdicts: [docs/mutation_score.md](../../docs/mutation_score.md).
RTL: `designs/b96_kr260_10g/rtl/rate_match_gp.sv`, unchanged (sha256 09ba7301...). Tools: Yosys 0.70+385, SBY 0.70-9, Icarus 14.0 (OSS CAD Suite 2026-11-12).

## Records

| Record | Seed | Evaluated | Killed | Equivalent | Real survivors | Undecided | Score | Worst case | Before the filter |
|---|---|---|---|---|---|---|---|---|---|
| [b96_rate_match_gp_seed1.json](b96_rate_match_gp_seed1.json) | 1 | 30 | 25 | 5 | 0 | 0 | 100 % | 100 % | 83.33 % |
| [b96_rate_match_gp_seed2.json](b96_rate_match_gp_seed2.json) | 2 | 30 | 29 | 1 | 0 | 0 | 100 % | 100 % | 96.67 % |

Bench: all nine cases of `test_rate_match_gp_cocotb` (cocotb + Icarus, output for output against the Python twin): the seven of brief 143b's file (five run for every mutant; the two long ones,
`partner_slower` and `minimum_gap_partner_faster`, for the mutants that survive those five, about 25 minutes a run) and the two added by this brief (below). A mutant is killed when any case fails,
so running the long cases only on the survivors gives the verdict of one run of all nine. Each row's `bench_stage` says which stage decided it (`reduced`, `directed`, `long+directed` = both
stages fail it, `none` = survived every case). The `*_first_pass.json` files are the records as the run wrote them (the survivors that the first limits could not decide are `undecided` there;
seed 1's was made with one added case, the second was added afterwards and run on the survivors only, `bench.rebenched`); the plain files are after `redecide` (the five undecided survivors
of seed 1 and the one of seed 2 proved equivalent with a 900 s BMC and 600 s proof limit) and, for seed 1, `rebench`. Wall time of the runs: 16,664 s (seed 1, with a 3,040 s baseline under load)
and 14,847 s (seed 2), two jobs at once.

## The L107 survivor of brief 143b

`head_frame` (rate_match_gp.sv line 107) decides whether the block the reader has just output starts or continues a frame: Start (0xFB) in lane 0 (control mask 0x01) or in lane 4 (mask 0x1F), or a pure
data block (mask 0x00). `in_frame` is set from it when a block is output, and an idle is inserted only when the buffer is empty and `in_frame` is 0; inside a frame the reader must stall instead.
The mutant `8'hFB` to `8'hFA` on the lane-4 comparison makes a lane-4 start block not count as a frame start, so after it is output `in_frame` is 0. If the buffer is then empty, the reader inserts an
idle block between the start block and the rest of the frame (the twin stalls). The formal miter's counterexample (within 30 clocks) is exactly that, and the SymbiYosys bench fails
`p6c_spec_matches_rtl` (`in_frame == spec_in`) at step 10, in 2 s; on the real RTL the same job passes (194 s to depth 40).

Why no simulation case saw it: the buffer has to be empty right after a lane-4 start block is output. With the stream written one block a clock the fill sits at 1 or more; it falls to 0 only
when the partner is slow, and then the empty slot must follow a lane-4 start. In `partner_slower` (700 frames at -400 ppm) the RTL inserted 108 idles and stalled 13 times, and none was
after a lane-4 start (the lane-0 variant of the mutant, `8'hFB` to `8'hFA` on the other comparison, is killed by the long cases; they were not run one by one on it); `minimum_gap_partner_faster` (5000 frames at +300 ppm) never stalls (`n_stall` 0).
**The two long cases do not kill it** (run alone on the mutant: both pass, 155 s and 1,409 s), so the reduced bench was not the cause. The kill is the added case `pause_right_after_a_frame_start`
(the write side offers nothing for 40 clocks after every frame-start block): it fails the mutant at the first idle inserted (output block 146, 497 output blocks differ from the twin, 618 inserted
idles against 121) and passes the real RTL (0 mismatches, `n_stall` 1553). The formal bench already caught the mutant: it was not new coverage there, and brief 143b's statement that it did not is
corrected (see below).

## What the added cases are

| Case | What it does | Kills (seed 1, 2) |
|---|---|---|
| `pause_right_after_a_frame_start` | 40 clocks of nothing to write after every frame-start block, so the reader finds the buffer empty inside a frame | the L107 lane-4 mutants (`!=` form, 0xFB to 0xFA, 0x1F to 0x20 in the mask compare) |
| `writer_outruns_a_reader_held_in_reset` | the read side held in reset for 400 clocks while the write side offers a stream: the buffer fills and `n_ovf` counts the refused blocks (329 in the real RTL, equal to the twin) | L60 (full flag never true: the mask `{CW{1'b1}}` tied to 0), L70 (`n_ovf` counting, two forms) |

Both pass the real RTL in all variants of the bench (xpm macro `rate_match`, `rate_match_gp`, `ENT_SYNC = 0`).

## What every survivor was

| Mutant | Seed | Verdict | Why |
|---|---|---|---|
| L130 `<` to `<=` (`fill_min`), L131 `>` to `>=` (`fill_max`) | 1 | equivalent | assigns the value the register already holds |
| L135 `+` to `-`, `+1` to `+0`; L139 `+1` to `+2` (`idle_run`) | 1 (L135 also 2) | equivalent at the shipped configuration | `idle_run` is read only through `keep_ok`, which is tied to 1 when `MIN_KEEP` is 0, and the one instance in the b96 RTL (`rx_path.sv`) does not override it |
| L60 `{CW{1'b1}}` to `{CW{1'b0}}` (full flag) | 1 | real; killed by the SymbiYosys bench (`p1_no_overflow`) and, after the second added case, by simulation | no case of the seven fills the buffer (`fill_max` 6 of 16 in the longest) |
| L107 `!=` on the lane-4 start byte | 1, 2 | real; killed by `pause_right_after_a_frame_start` and by the SymbiYosys bench | as above |

## Floor

The planner's floor (worst case at least 90 %, at least 30 evaluated mutants) is bound in `designs/b96_kr260_10g/verif/testplan.yaml`: requirement `B96-V-RM-BENCH` with
`mutation_floor: {score_pct: 90, worst_case_pct: 90, min_mutants: 30, max_undecided: 3}`, checked by item `V-RM-MUTATION` against the seed 2 record (the `worst_case_pct` key is new in
`flow/mutation_score.py`, brief 152). It passes: 29 killed, 1 equivalent dropped, worst case 100 %.

## Known gaps and limits

* Seed 1's two added cases were written after seeing seed 1's survivors, so seed 1's 100 % is in-sample for them. Seed 2 was run on the final bench; it still has 4 mutants that only the added cases
  kill (L70 twice, L107 twice), so the additions are not specific to seed 1's survivors, but 8 of seed 2's 30 mutants are also in seed 1's (the pool has 135 candidates). Together the two seeds
  cover 52 distinct mutants of 135.
* The bench before this brief (seven cases): seed 1 kills 23 of 25 non-equivalent mutants by simulation (92.0 %; 24 of 25 with the SymbiYosys bench's kill of L60, 96 %); seed 2 kills 25 of 29 (86.2 %, simulation only: the SymbiYosys bench was not run on seed 2's survivors of the seven), below the floor.
* Samples of 30 mutants from a pool of 135: a 100 % score is not an interval. The formal verdicts are for AW 4 / HI 1 (shipped) and AW 2 / HI 1, `MIN_KEEP` 0, depth-30 BMC plus an inductive proof; with
  `MIN_KEEP` 1 to 3 (a documented parameter that nothing instantiates) `rate_match_gp` has no simulation bench at all: the existing MIN_KEEP = 1 case runs the xpm macro `rate_match`.
* The bench's independent frame check (`frames_equal`) did not notice the idle block inserted inside a frame (it passed on the lane-4 mutant while 497 output blocks differed from the twin); the twin comparison
  catches it. Whether the real MAC drops such a frame was not run.
* Brief 143b's record of this target (`../143b_mutation/b96_rate_match_gp.json`) is kept as made; its README carries a correction.

## Reproduce

```
python3 -m flow.mutation_score run b96_rate_match_gp --seed 2 --count 30 --jobs 2 --mutant-timeout-s 5400 --bmc-s 60 --prove-s 240 --json results/152_b96_mutation/b96_rate_match_gp_seed2.json
python3 -m flow.mutation_score redecide b96_rate_match_gp results/152_b96_mutation/b96_rate_match_gp_seed2.json --bmc-s 900 --prove-s 600
python3 -m flow.mutation_score rebench b96_rate_match_gp results/152_b96_mutation/b96_rate_match_gp_seed1.json --stage directed
FDA_B96_CASES=long python3 -m flow.mutation_targets b96-bench      # one stage on the real RTL (FDA_MUTANT_DIR set to the rtl directory)
```

Needs the OSS CAD Suite pinned by CI and the repo's venv. Simulation only; no heavy slot.
