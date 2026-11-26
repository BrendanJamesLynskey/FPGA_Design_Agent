# Coverage-directed stimulus and assertions written from requirements (brief 218)

Two steps of the verification flow, both **off by default** (`--coverage-loop on`, `--req-sva on`), so a run without the flags is the run it was before.
Code: [flow/coverage_loop.py](../flow/coverage_loop.py), [flow/sva_req.py](../flow/sva_req.py), [agent/graph/covsva.py](../agent/graph/covsva.py). Tests:
[flow/tests/test_218_coverage_loop.py](../flow/tests/test_218_coverage_loop.py), [flow/tests/test_218_sva_req.py](../flow/tests/test_218_sva_req.py),
[tools/run_stats/test_graded.py](../tools/run_stats/test_graded.py). Pre-registration, measurements and the V3 stall analysis:
[results/218_coverage_sva](../results/218_coverage_sva/README.md).

## 1. The coverage loop (`--coverage-loop on`)

**What V3 does without it.** When a V3 check fails, the gate's text names the unhit bins, cover properties and lines, and the next stage-2 visit (which also
repeats lint, the simulation, the standards check and the first synthesis build) gives them to the tests role with everything else that failed. A visit is
expensive and there are six of them.

**What the loop does.** Inside one gate evaluation, when V2 has passed and every failed V3 check is one the tests can change (functional bins, cover
properties, line, toggle, mutation survivors; not the seed count, a failing seed, a waiver without a reason or the CDC checks), it runs rounds of:

1. read the open holes (`holes_of`: unhit bins, unreached cover properties, lines and signal bits never exercised, mutants that survived or timed out);
2. one tests-role repair call whose only failures are those holes (`brief`: what each kind of hole asks for, what earlier rounds closed);
3. rerun the V3 evidence (the Verilator coverage run, then the mutation run); a coverage run that now fails, or a V2 that no longer holds, **halts** the loop
   at once: the ordinary repair visit owns that;
4. read the holes again; the round is one line of `build/verif/coverage_loop.jsonl` (holes before and after, the keys closed, the keys opened, tokens spent).

It stops on **convergence** (no hole left), on a **plateau** (no hole closed in two rounds in a row), on the **round limit** (3) or when the stage or run budget
refuses the next call. After the last round, if the tests changed, the stage-2 simulation gate (Verilator, then Icarus) runs again, so new stimulus is held to
the same standard as the old.

**What the tests role sees.** The holes, as file, line and signal for a line or toggle hole, never the RTL text: the Verifier never reads the RTL
([agent/graph/roles.py](../agent/graph/roles.py)), and a test written from the RTL shares the RTL's misreading. It is told not to change assertions, the model
or the testplan thresholds to make a hole go away. The text is code in `flow/coverage_loop.py`, not a private prompt, and the role is the stage-2 tests role in
repair mode, so no prompt, request golden or prompt pin changes.

**What it does not do.** It cannot close a hole that stimulus cannot reach: an **equivalent mutant** (a change that cannot alter an output), a mutant that
**times out** (counted as not killed), or a cover property that can never be true. The V3 mutation score of `flow/mutate.py --generic` counts all three as
survivors (the formal equivalent-mutant filter of brief 143b, `flow/mutation_equiv.py`, is not in the gate). The plateau rule stops spending on such a hole;
it does not remove it. See the stall analysis in the results folder.

**The passive record.** In either arm, every stage-2 gate evaluation that has V3 evidence appends a line to `build/verif/coverage_visits.jsonl` (holes
open, run tokens, mutation score). It is how the control arm is measured the same way as the loop: holes closed per million tokens between two evaluations.

## 2. Assertions written from requirements (`--req-sva on`)

For each requirement row that states a cycle-level property of the module's ports:

1. **Generate** (one model call, the `assertgen` purpose: Sonnet 5.5, effort low). The model sees the requirement text (and the structured L2 fields of
   brief 227 when the requirement has them), the port list, and **never the RTL**. It answers with one JSON object: `kind` (`same`: when `ante` then `cons` in
   the same cycle; `next`: when `ante` was true last cycle then `cons` now; `reset`: right after reset `cons`), `ante`, `cons`. Names must be ports or `rst`;
   `$past(x, N)` (N up to 16), `$rose`, `$fell`, `$stable` are allowed; `##`, `|->`, `always`, `;` are refused.
2. **Read back** (the `assertback` purpose: Haiku 5.5, a different model from the writer). It sees only the property and the ports and says in one sentence
   what it requires.
3. **Compare, in code** (`compare`: no model produces the verdict). A property whose back-translation disagrees is **discarded with its reason**:
   a number the property chooses (a `$past` depth, a constant) that the requirement does not give; a number the back-translation states that neither gives;
   a negation that appears on one side only; signals the requirement neither names nor describes (a register requirement names a register, not its port, so the
   words must support the link); a back-translation about something else (under 25 % word overlap either way); a signal the L2 fields name that the property
   leaves out. A back-translation that covers under 60 % of a long requirement's words is accepted and marked **partial**: evidence of part of the row.
4. **Prove** (`sby`: bmc depth 24, k-induction depth 12, cover depth 24; the OSS CAD Suite the repository pins when present, else the user-local Yosys 0.33).
   The property is the house form of `flow/v_macros.svh` (`V_SAME`, `V_NEXT`, `V_RST`), each with its **trigger cover** (`<name>__ante`).

**What counts as evidence** (research/228, accepted): `proved` (k-induction closes) or `bounded` (holds to depth 24, induction does not close), **and** the
trigger cover passes. A property whose trigger is never reached is `vacuous` and is never evidence (the saturation example of 228 proves vacuously at
N = 100,000). A property that fails is `failed`: the property is wrong or the design is; the counterexample stays in `build/verif/sva/<id>/`, nothing is
installed. Other outcomes: `mismatch` (discarded by the comparison), `unusable` (the reply was not a property of the form, or the generator said it cannot be
stated on the ports), `sim_only` (its signals are in two clock domains and the spec states no clock relation), `error` (a tool error or timeout), `not_run`.

**Where the evidence goes.** Only an evidenced property is installed, as `verif/formal/sva_<id>.sby` (+ `.sv`), tagged `# req: <id>`: the traceability matrix reads
it as a formal artefact of that requirement (a bounded one without the `prove` task, so the matrix reads it as the bounded evidence it is), and `flow/formal.sh`
runs it again like any formal job (it puts the pinned suite first on PATH for a job that loads the slang plugin). `build/verif/sva/evidence.json` holds every
row's outcome; `REQUIREMENTS_REPORT.md` gets a section "Assertions written from the requirements" with the property and its English reading beside each
requirement. A changed design withdraws an installed proof: the property is re-earned against the new RTL, never kept on trust.

**The cover trace as a diagram.** For each evidenced property `build/verif/sva/<id>/cover_trace.wavedrom.json` is a WaveDrom document drawn from the cover
task's trace (`wavedrom`), the picture for brief 227's show-back packet: the trigger firing in the last cycle, the signals of the property, reset.

### Which module the properties are about

The spec's `top` when the RTL has it and open-source Yosys can elaborate it. A register core behind a bus module (the JTAG register port designs: a top with a
clock primitive and `jtag_bus`, and the register map in a core whose ports `h_we`, `h_re`, `h_addr`, `h_wdata`, `h_rdata` the spec lists as internal nets) is not
elaborable at the top, so the module whose ports match the most spec port names and which instantiates no undefined cell is used (`effective_spec`); the
evidence file says which and why. Only module headers are read to choose it; the generator sees the port list, not the bodies.

### Limits (stated, not hidden)

* The property is written without the RTL. A requirement about a register's contents ("MEM_ADDR auto-increments") that the ports do not carry, or that gives
  no address, is `unusable`: the generator says so. Requirements that name a register and its address are the ones that become properties.
* One clock domain per property. A reference clock input is a free input of the wrapper.
* Reset is asserted in the first cycle only (a reset requirement: free after the third), so a mid-run reset is not explored for the other kinds.
* A vendor primitive is the design's own simulation stub (`SYNTHESIS` is left undefined), not the primitive. A property that rests on it is a property of the stub.
* Bounded results hold to the depth shown. A long timing (a 10 ms debounce at 100 MHz) is out of reach of a depth-24 cover and ends `vacuous`.
* The comparison is a word-and-number check, not understanding. It catches a changed latency, a dropped negation and a signal that is not in the requirement; it
  does not catch every misreading. The English the user confirms stays the requirement's own words: the property is a check, shown beside it, never a
  replacement (research/228 section 8).
* FVEval NL2SVA-Human (79 items) was not run: its licence and form were not checked in this brief.

## 3. Reading results: `tools/run_stats`

`ablate.py` and `table.py` are the CVDP project's paired-comparison tools (MIT, standard library; copied unchanged, see [NOTICE](../tools/run_stats/NOTICE.md)).
`graded.py` adds the adapter from run records and a paired bootstrap of any numeric column, so a graded outcome (holes closed per million tokens, requirements
evidenced, tokens, stage reached) is compared the way a pass rate is: paired on the item, repeats kept together, a 95 % interval from a bootstrap over items, an
exact sign test, and "no detectable effect" (never "no effect") when the interval includes zero. A run stopped by the plan, a rate limit or a refused slot is
left out and re-run, never scored as a failure.
