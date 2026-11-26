# Brief 218: coverage-directed stimulus and assertions written from requirements

This folder holds the pre-registration and the records of brief 218, which adds two opt-in steps to the V3 verification flow (`--coverage-loop on`: rounds of coverage-directed
stimulus inside the stage-2 gate; `--req-sva on`: an SVA property written from each checkable requirement, read back in English by a second model, compared in code and
proved with a reachable trigger) and measures the second on the three 209 pilot designs that reached V2. The mechanism is in [docs/coverage_sva.md](../../docs/coverage_sva.md).
**The coverage loop was not measured in a live agent run** (Part B below): the launcher is here, pre-registered and ready, and the reason it did not run is stated.

## Records

- `preregistration.md`: written before any scored run (power line, arms, designs, outcomes, stop rules, run order) with two dated amendments, both made before any counted
  Part A run and both about the formal tool, not the question.
- `partA/`: Part A (requirement to assertion), six pipeline runs, two per pilot design.
  - `runs.csv`: one row per design and run: candidates, skipped, the count of each outcome, the primary column `with_evidence` and `before_formal_jobs`.
  - `rows.csv`: one row per candidate requirement and run: its status, the property, the model's English reading of it, and the reason.
  - `summary.md`, `stats.txt`, `unusable_reasons.md`: the table, run b against run a through `tools/run_stats/graded.py` (the stability of the step, 3 designs), and the count of why rows were unusable.
  - `as_run/`: each run's `evidence.json` as the pipeline wrote it, the stdout, and the run order and times.
  - `post_hoc_rejudge/`: the same six runs after a fix to the comparison (below), judged again on the recorded replies with no new model call. **Post hoc, not part of the
    pre-registered result.**
  - `traces/`: two WaveDrom documents drawn from cover traces.
  - `aborted_first_start/`: the first, stopped start (Yosys 0.33's reader); its numbers are not used.
- `partA_collect.py`: turns the six scratch folders into the files above.
- `run_partB.sh`: the Part B launcher (not run).

## Measured

Part A: three pilot designs (the first run of each that reached stage 9: p1_clkmeter run 1, p2_bram_rom run 1, p3_crc_engine run 2), the pipeline twice on each, Sonnet 5.5 writing
the property, Haiku 5.5 reading it back, `sby` on the pinned OSS CAD Suite (Yosys 0.70+385, slang front end, yices), bmc depth 24, k-induction depth 12, cover depth 24.

| design | candidates | skipped (not a cycle-level property) | with evidence, run a | with evidence, run b |
|---|---|---|---|---|
| p1_clkmeter | 14 | 15 | 2 (1 proved, 1 bounded) | 2 (1 proved, 1 bounded) |
| p2_bram_rom | 15 | 18 | 0 | 0 |
| p3_crc_engine | 9 | 16 | 1 (1 proved) | 1 (1 proved) |

- **Before:** none of the three designs has a formal job (`before_formal_jobs` is 0 in `runs.csv`), so the number of requirements with a proved property was 0 in each.
  **After:** 3 requirement rows with a proved or bounded property in each run set (2 + 0 + 1 in run a and in run b), out of 38 candidate rows, each with its trigger shown reachable.
  The primary column is small and, on 2 of the 3 designs, the same in the two runs; it is not a rate: 3 designs cannot tell a gain from a chance difference (power line in `preregistration.md`).
- **What the other candidates became** (the six runs together, 76 candidate rows): 60 `unusable` rows, where the generator said the requirement cannot be stated on the ports (`unusable_reasons.md`:
  38 because it gives no register address or bit encoding, 11 because the contents it describes are internal state, 11 for another reason); the `mismatch`, `failed` and `vacuous` rows are in `rows.csv`.
  The pilots' requirements are written about registers ("PUSH4 accepts four bytes"), not about ports, and the pipeline can only state what the requirement and the port list give.
- **Failed properties are findings, and here they were the property's fault.** On p2_bram_rom the property "h_rdata holds its value until the next h_re" fails in both runs; its
  counterexample (`as_run/` and the work folder it names) shows a ROM or RAM read that returns data two clocks after `h_re`, while `h_re` is low again. The requirement does not say that
  the value may still arrive after the read strobe, so the property was stronger than the requirement; on p1_clkmeter and p3_crc_engine the same wording was proved because their
  read data are not pending. The first is the useful kind of failure: it shows an ambiguity in the requirement, which the requirements-readiness brief's two-reader test is for.

## Post-hoc re-judge (not pre-registered)

The comparison in `flow/sva_req.py` called two of the six `mismatch` rows by a rule that was wrong, not the model: a back-translation that quoted the expression `!h_re` counted as a
negation, and `h_addr < 1024` was called a number the requirement does not give when the requirement says "0 to 1023". Both were fixed and the six runs judged again from their recorded
replies (`post_hoc_rejudge/`): p3_crc_engine run a gains one proved property (REQ-22), and p2_bram_rom run a's RAM-word property now goes to the formal tool and fails. Counts differ from
`as_run/` only there; nothing in the pre-registered table above is changed by it.

## Part B: the coverage loop (not run)

`run_partB.sh` runs one agent run of one pilot design in one arm (`--coverage-loop off` or `on`), exactly as `preregistration.md` fixes: 3 designs, 2 arms, 1 run each, in the order
p2 A1, p3 A0, p3 A1, p1 A0, p1 A1, p2 A0, `--verif-level V3 --stop-after 2 --harness claude_code`. It was not run because an agent run starts the agent, whose access gate needs the
owner's key file copied into the worktree (house rules: `cp .../.env <worktree>/.env`, never printed, deleted afterwards), and the instruction this session ran under said never to touch
`.env` or any key. Nothing was run in place of it, and no number below measures the loop. What exists is the tested mechanism: 16 tests of the holes, the plateau rule and the driver
(`flow/tests/test_218_coverage_loop.py`, on a real Verilator coverage file as well as fakes), the passive per-evaluation hole record, and the launcher.

## Part C: why V3 stalled on the mutation score in 209a (read from earlier records, no run)

Sources: `results/209a_pilot_ready/README.md` and its run files, `flow/mutate.py`, `flow/verif_gates.py`, `flow/verif_floors.yaml`, `pilots/209/`.

- **The 209 pilot has no V3 stall to analyse.** Every one of its 18 runs used `--verif-level V2` because of the 209a stall (`pilots/209/p1_clkmeter/preregistration.md`). Its stage-2 stops (p4 to p6, 9 of 9
  runs) are V2 stops ("no seeded results", lint, simulation), brief 224's subject.
- **209a recorded four V3 stalls on the toy and one on the deep-chain spec.** The toy's were: a score of 30 % where the mutants were of the supplied `jtag_bus` module (not the agent's code); a
  coverage step that waited on a heavy-slot lock the run itself held; 15 of 15 mutants "do not compile" because the mutation copy left out `data/jtag_bus.sv`; and the agent's own top-level bench failing.
  All four are infrastructure, fixed in 209a or in PR #344 (brief 219: supplied `data/` files are not mutation targets, the slot deadlock). None is a stimulus problem.
- **The 50 % (need 70 %) on the 24-multiply chain cannot be explained from what was kept.** The run kept `run_summary.json` and the Designer's message, not `mutation.json` or `v3_evidence.json`.
  What the code says can be stated: the V3 score is `killed / (killed + survived + timed out)` over at most 20 sampled mutants (`flow/mutate.py --generic`); **an equivalent mutant counts as a survivor, a
  timeout counts as not killed, and "nothing in the tests can raise the number evaluated"** (`mutation_why`). The formal equivalent-mutant filter of brief 143b (`flow/mutation_equiv.py`) is not in the
  gate. A second run of the same spec at V2 was stopped after 26 minutes in one simulation, so mutants of that design probably time out; that is a likely contributor, not a shown one.
- **Do the two steps fix it?** The loop helps the survivors that are real gaps in the tests (its holes include them, and the role is shown each), and stops spending on a plateau. It cannot touch an equivalent
  mutant, a timeout, a mutant of supplied code or an infrastructure fault, which is every recorded cause above. The assertion step does not affect the mutation score (the generic V3 run counts no formal
  kills). So **neither fixes the recorded stalls**; the gap they leave is the gate's treatment of equivalent mutants and timeouts, a follow-up (below), and a rerun of the deep-chain spec at V3 keeping `mutation.json`.

## Reproduce

- Tests: `python -m pytest -q flow/tests/test_218_coverage_loop.py flow/tests/test_218_sva_req.py agent/tests/test_218_covsva.py tools/run_stats/test_graded.py` (the formal cases need `sby` and z3: the
  pinned OSS CAD Suite at `$FDA_OSS_CAD` or `~/.local/opt/oss-cad-suite`, else the user-local Yosys 0.33 install; CI's `formal-rate-matcher` job runs them).
- Part A: copy each design (`pilots/209/<d>/<run>/design`) to a scratch folder twice, then `python -m flow.sva_req <folder>` (needs the `claude` CLI on the plan; takes a heavy slot only through
  `take_heavy_slot.sh` and a memory cap: the proofs here are small, about 35 to 65 s a run); then `python3 results/218_coverage_sva/partA_collect.py <scratch root>`. The model replies vary run to run; the
  recorded replies are in `as_run/`, and `python -m flow.sva_req <folder> --from-file replies.json` re-judges recorded replies without a model call.
- Part B: copy the owner's key file into the worktree (never print it), then `results/218_coverage_sva/run_partB.sh <design> <A0|A1>` for each pair in the pre-registered order; it takes a heavy slot (about 90 minutes
  each, Vivado synthesis at stage 2) and cannot be regenerated without a paid-plan agent run.

## Known gaps and limits

- Part A is 3 designs and 2 runs each: a description, not a test. The primary column's interval over 3 designs is wide (`stats.txt`).
- The pilots' requirements rarely carry what a property needs (addresses, encodings, a reset to check against), so most rows are `unusable`; brief 227's structured fields are what would change that, and the
  pipeline takes them when a requirement has an `l2` mapping (the field names are 227's: scope, condition, component, timing, response; 227 had not merged, so this was exercised on a fixture, not a real row).
- A property is written without the RTL, so it can be wrong where the design is right (the p2 case above), and the comparison is a word-and-number check that can call a faithful property a mismatch (the two cases fixed
  post hoc) or pass an unfaithful one; both directions are possible and neither is measured here beyond these rows.
- One clock domain per property; reset in the first cycle only; vendor primitives are the design's own simulation stubs; bounded results hold to depth 24; a 180 s limit per task makes a slow proof an `error`.
- FVEval NL2SVA-Human (79 items) was not run (licence and form not checked).
- The pilots' V3 evidence does not exist (they ran at V2), so "today's V3" is not measured here either.
- Heavy slots: Part A's formal runs were small and ran inside a held slot (`218: sva ...`), released by the script; the unit tests also run `sby` (a few seconds each), as `test_24_fsm_formal.py` does.
