# Mutation score as the headline bench metric (brief 143b)

A bench is good when it fails on a design that is wrong. Mutation testing makes wrong designs on purpose (one small change to the RTL) and counts how many
the bench catches. The number is easy to inflate, so this page fixes how it is made and reported. It follows YosysHQ MCY (AppNote 400) for the formal
filtering of equivalent mutants and the reporting rules of GateTruth (arXiv 2608.12635, a single-author preprint; its lessons are concrete, its numbers are
not relied on here). It adds to `flow/mutate.py` (brief 04f and 05k: sampled generic mode, equivalents stay as survivors) and does not replace it.

## The three rules

1. **Blind mutants.** `flow/mutation_blind.py` makes mutants from RTL text and an integer seed only: `generate(files, seed, count, operators)` has no
   argument through which a test, model or bench could reach it, and a unit test pins that signature. Same files and seed give the same mutants. The
   operators are 23 classes: comparison (`==`/`!=`, `<`/`<=`, `>`/`>=`, `>=`->`<`, `>`->`<=`), logic (`&&`/`||`, `&`/`|`, `^`->`|`, `!` and `~` removed),
   arithmetic (`+`/`-`, `<<`/`>>`), constants (a one-bit constant flipped; a sized `N'dV`/`N'hV` changed by +1 and by -1) and the swap of the two arms of a
   one-line `c ? a : b`. Comment, declaration, parameter and assertion lines are skipped. Optional: `llm_prompt` builds the prompt for a model asked to
   propose realistic bugs from the RTL alone (no test text goes in) and `load_llm_proposals` validates what comes back; no live model was used for the
   records below.
2. **Equivalent mutants are decided by a formal miter, not by hand.** Each surviving mutant is checked against the original (`flow/mutation_equiv.py`):
   BMC from the reset state first (a counterexample is a real difference); then a register-matched induction proof (Yosys `equiv_make`/`equiv_induct`, the
   flow eqy automates); then an unbounded proof (`sby`, `abc pdr`, or k-induction for two-clock blocks). Verdicts: `equivalent` (dropped from the
   denominator and listed), `not_equivalent` (a real survivor), `undecided` (limit reached; reported apart, never a kill, never equivalent), `error`.
3. **Report it GateTruth-style.** Every record states the operator set, the mutant count, kills by simulation and by formal property bench separately, the
   timeout policy, the seed, the RTL hashes, the bench and the tool versions, and lists every survivor with its verdict.

```
mutation score          = killed / (killed + real survivors)                      the headline
score, worst case       = killed / (killed + real survivors + undecided + bench timeouts)
score before the filter = killed / (killed + every survivor + bench timeouts)     what flow/mutate.py reports
```

A bench run cut by its time limit is `timed_out`: in no numerator, in the worst case's denominator. An invalid mutant (the copy does not build) is excluded and
listed. Mutants run one after another by default (GateTruth: parallel sweeps can silently inflate kill rates through timeouts).

## What the formal verdict means and does not mean

* The miter starts both versions from the same power-up state (registers without an initial value start at 0) and, where the target says so, holds the
  reset for a few clocks. A mutant that differs only from a start-up state the design can never reach would show as `not_equivalent`; a mutant that differs
  only under inputs the target's `assume` lines forbid (for example `in_valid` while `in_ready` is low) is `equivalent` *under those assumptions*.
* The decision is of the configurations the target lists (parameters and widths, the same ones the bench runs), not of every parameter value.
* Outputs are compared as the target says: every output always, or a data output only while its valid is high (a stream interface's contract).
* The register-matched proof does not see which clock a register runs on, so for two-clock blocks it is skipped when the changed line mentions a clock edge.
* `equivalent` is a proof about the miter's model of the RTL (Yosys with the slang front end), not about the bench.
* Kills by the design's own property bench (`formal_bench`) are counted apart; a target without one reports 0 and `formal_bench_bound: false`.

## Running it and reading it

```
python3 -m flow.mutation_score targets
python3 -m flow.mutation_score run b119_tcp_fast --seed 1 --count 30       # results/143b_mutation/b119_tcp_fast.json
python3 -m flow.mutation_score show results/143b_mutation/b119_tcp_fast.json
python3 -m flow.mutation_score run b119_tcp_fast --no-filter                # simulation only: a trace_v1 floor refuses such a record
```

Needs the OSS CAD Suite pinned by CI (sby, yosys with slang) for the filter, and the repo's venv (cocotb) for the cocotb benches. Sim-only; no heavy slot.

## A requirement binds a floor

`flow/trace_v1.py` has a `mutation` evidence reader. The item uses an existing method (`coverage_bin`: adequacy evidence of the bench, not a test) and the
floor sits on the item or on one of its requirements:

```yaml
requirements:
  - id: B119-V-BENCH
    kind: functional
    title: the bench catches seeded bugs
    mutation_floor: {score_pct: 90, min_mutants: 20, max_undecided: 0}      # max_timed_out defaults to 0; worst_case_pct: N (brief 152) also floors the worst case
verification:
  - id: V-B119-MUT
    requirements: [B119-V-BENCH]
    method: coverage_bin
    evidence: {file: results/143b_mutation/b119_tcp_fast.json, reader: mutation}
```

The item passes when the record was filtered, has at least `min_mutants` evaluated, a headline score at or above `score_pct`, no more than `max_undecided`
undecided and `max_timed_out` timed-out mutants (and, when the floor has `worst_case_pct`, a worst-case score at or above it), and its recorded RTL hashes match the RTL now. The detail line names the counts, the worst-case score and
the seed. No real testplan binds a floor yet: which requirement carries one, and at what number, is the planner's and the human's decision (a floor is a
specification of how thorough verification must be).

## Records

See [results/143b_mutation/README.md](../results/143b_mutation/README.md) for the four records (b96 `rate_match_gp`, b119 `tcp_fast`, two arith
functions), the scores before and after the filter, and the survivors.
