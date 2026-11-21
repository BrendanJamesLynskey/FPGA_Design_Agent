# Results for the formal proofs of the gray-pointer rate matcher (brief 115)

Brief 115's records: the SymbiYosys runs of the properties bound to `designs/b96_kr260_10g/rtl/rate_match_gp.sv` (the own elastic buffer of brief 96E), covering safety proofs by k-induction, a bounded-response progress check, covers, and one seeded bug per key property that a named assertion must catch. The properties, the model of the two clocks and the study notes that tie each property to LTL, CTL, BMC, k-induction, fairness and abstraction are in [docs/formal_study_notes.md](../../docs/formal_study_notes.md).

## Records

| File | What |
|---|---|
| `formal_ci.json`, `formal_ci.md` | the jobs CI runs (`run_formal.py --set ci`): safety proved by k-induction at AW = 4 (the shipped 16 entries) for one bit of each class of the 74-bit entry, and at AW = 2 and 1; bounded model check of the safety properties and of the progress ranking function at AW = 2; covers; ten mutants, each caught by a named assertion. One verdict, run time and failing assertions per job. |
| `formal_full.json`, `formal_full.md` | the same plus all 74 bits of the entry at AW = 2, a deeper progress check, and the deletion cover (`run_formal.py --set full`; local, not in CI) |

`verdict` is `PASS` (the proof or check holds), or for a mutant `CAUGHT` (a named assertion failed on the seeded bug) or `MISSED`. The tool is Yosys 0.70 with the slang front end from the OSS CAD Suite 20261112, the release the repo's CI pins.

## Reproduce

```
python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set ci   --json results/b115/formal_ci.json   --md results/b115/formal_ci.md
python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set full --json results/b115/formal_full.json --md results/b115/formal_full.md
python3 -m pytest -q designs/b96_kr260_10g/tests/test_b115_formal.py       # the ci set as a test; skipped without sby, fails under FDA_REQUIRE_FORMAL=1
```

Run times are in the records. The runs are small (a few hundred MB each); no heavy slot is taken.

## Known gaps and limits

- The properties are Boolean forms compiled by hand; the SVA text beside each one was not read by any tool (the free front end rejects implication and `s_eventually`).
- Progress is a bounded model check of a ranking function to a stated depth, not an unbounded proof; the induction step for it has open counterexamples (docs/formal_study_notes.md, section 7).
- Instances: AW = 1, 2, 4, `ENT_SYNC` = 1, `HI` = 1, `MIN_KEEP` = 0. The clock ratio is assumed within 3:1; skew beyond one source clock is not modelled.
- A mutant that shortens the write pointer's chain from three flops to two was not refuted at depth 32 of the base case (the model's skew bound makes it safe); it is not in the records as a catch.
- The ITCH/MoldUDP64 parser of brief 110 was not covered: its pull request was not merged when this work started.
