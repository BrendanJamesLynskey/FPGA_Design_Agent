# Lessons from building the agent

Measured claims only, each with the file that holds its numbers. The story, with the experiment cards and a timeline, is on
the site's "How it was built" page (`site/story/story.yaml` is its source; every number there is read from the files named
here). Each lesson says what it does not show. Everything is development work: the agent has no held-out score, because
the first held-out evaluation (`eval-1`) was stopped before analysis.

## Where the errors come from

1. **The agent's own checks are not a pass.** 6 of 21 development runs were escapes: the agent's own checks passed and the
   hidden tests failed, each from reading the spec differently from the tests (`site/data/dev.json`, from
   `results/course/*/run_*.json`). *Does not show:* a rate for new tasks. The agent was changed between runs.
2. **A test bench that looks complete can miss a class of fault.** The first full mutation run of T1's bench killed 90.48 %
   of 21 mutants; the two survivors were reset-state faults no test looked at. With a test for them, 21 of 21
   (`results/04f/mutation_t1.json`). *Does not show:* the score on other designs. One design, hand-written mutants.
3. **The measuring instrument has bugs, and they matter more than the model.** Examples with recorded fixes: a hidden bench
   that read a high-impedance value from a legal design (PR 72); a closure run that accepted a design whose core synthesis
   had removed, which is not counted and is why a synthesis guard exists (`results/62a_closure/README.md`); a gate that
   failed every build with a debug core (PR 120); a regular-expression scan of HDL source defeated by three adversarial
   reviews, replaced by elaboration (PR 164). *Does not show:* how many such bugs remain.

## What paid off

4. **Where the standard tool is silent, a deterministic gate can see the fault.** The tool's own CDC report alone flagged 5 of
   10 faulty fixture designs; the gate flagged 10 of 10, with 0 false alarms on 12 correct designs, on Vivado 2026.1
   (`results/16_cdc_gate_2026_1/mutant_table.json`). *Does not show:* a detection rate on real designs. The fixtures are
   small and hand-written, and the simulation injection is cycle-level.
5. **Timing-exception checks match the expected verdict on the drills.** 14 of 14 drills with an expected verdict matched, 10
   of them expected to be flagged (`results/20_timing_exceptions_2026_1/exceptions_table.json`). *Does not show:* how often
   real designs carry such exceptions.
6. **A build cache saves most of an agent run's build time with identical results.** 76 % less on c10 and 80 % less on c13
   for one run's build sequence, with the same placement and routing hashes and slack
   (`results/33_vivado_speed_2026_1/README.md`). *Does not show:* the saving on other runs; the no-cache time is modelled
   from measured fresh-build stages.

## What did nothing, or could not be measured

7. **A cheaper model is not evidence of equal quality.** Paired over 86 problems against the base model, one cheaper model
   differed by -4.1 points (97.5 % interval -13.4 to 5.8), no detectable difference, and the other by -12.4 points
   (interval -21.7 to -3.5), worse (`results/f1b/paired_eval86.md`). *Does not show:* a ranking of the models for this
   agent; the problems are CVDP's, not the FPGA tasks.
8. **A tool the roles do not use cannot be measured.** With skill routing on, end-to-end hidden-test passes were 0 and with it
   off 0, on three runs per arm; retrieval recall at six skills was 0.394 for the plain index, 0.306 for the hybrid index and
   0.1 for the classifier router; the roles hardly called the new tools (`results/36_skill_routing/e2e.md`,
   `retrieval.md`). *Does not show:* that routing cannot help; three runs per arm cannot show a difference.
9. **With few blocks only large effects are visible, and an adopt rule needs one reading.** Over 12 blocks (4 tasks, 3
   repeats) context management (H1) lowered cost by 32.8 % (interval -53.3 to -4.3) and tokens by 65.6 % (interval -79.6 to
   0.9); the pre-registered rule gave two answers, depending on how "tokens per run (and cost)" was read. Hang protection
   (H2) showed no difference (cost -1.5 %, interval -31.4 to 12.6). H1 was made the default after the data, a decision
   recorded as made after the data (`results/42_workflows/README.md`, `analysis.md`). *Does not show:* the saving on more
   tasks; re-measure before quoting it.
10. **One run per case is an illustration, not a rate.** Of 3 seeded timing misses, 1 closed; none of 6 attempts to write RTL
    with the design-time plan passed its hidden bench (`results/62a_closure/README.md`). *Does not show:* a closure rate.
11. **A screen with too tight a spend guard is noise.** Every run of the open-weight base screen was stopped by the guard on
    42 to 65 of 86 problems, so it recommended nothing (`results/p0/REPORT.md`).

## About measuring

12. **Pin every tool that is not under test.** 9 of the 57 `eval-1` run slots ended as not run after the Claude Code CLI
    updated itself between two launches and the agent refused the untested version. 14 slots had been launched and 2 runs
    scored when the owner stopped it; nothing is reported (`docs/eval/eval1_preregistration.md`, section 10). Later
    evaluations pin the binary and turn auto-update off.
13. **A passing simulation is not a passing build.** Two blocks driving the same registers passed in Icarus and were tied to
    ground by Vivado (`results/62a_closure/c13_orig_plan_unguarded/INVALID.json`).

## Open

- The fine-tuning experiment on closure-strategy choice has not been run. A "no" will be recorded as one.
- The baseline held-out evaluation, with a new tag and pre-registration, has not been run.
