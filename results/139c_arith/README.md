# Arithmetic library, brief 139c: measured results

Five more functions of the library in [arith/](../../arith/README.md). **No Vivado run was made**: nothing here is an Fmax, area or power figure. Every number is a count from a simulation, a proof job or a Lean build, taken on 2026-11-21 on this PC (Icarus Verilog, Verilator, Yosys with yosys-slang and SymbiYosys from the OSS CAD Suite installed here, Lean 4.36.0), with the machine loaded by other sessions (jobs ran niced, one at a time).

| Function | Variants | Simulation | Mutants killed / total | SymbiYosys | Faults caught by the proof |
|---|---|---|---|---|---|
| sqrt_r4 | 2 | 42 runs, 342,432 vectors | 18 / 18 (+0 equivalent) | reference 11 unbounded, pairs 3 | 6 / 6 |
| divider_hr | 3 | 54 runs, 663,036 vectors | 32 / 32 (+2 equivalent) | reference 3 unbounded + 3 bounded, pairs 1, lemmas 6 | 8 / 8 |
| div_nr | 2 | 54 runs, 702,592 vectors | 16 / 16 (+0 equivalent) | reference 6 unbounded | 7 / 7 |
| recip | 3 | 96 runs, 195,912 vectors | 13 / 13 (+2 equivalent) | reference 8 unbounded | 7 / 7 |
| rsqrt | 3 | 90 runs, 269,640 vectors | 15 / 15 (+1 equivalent) | reference 8 unbounded | 7 / 7 |

Proof kinds: `pdr` and k-induction are for all input sequences at the stated width; lemma jobs are combinational (complete for all inputs at that width); bounded jobs claim nothing past their depth. The approximate functions (recip, rsqrt, div_nr) are proved against an error characterisation, not for bit-exactness, and only at the small widths listed in each `tests/*_formal_rtl.py`.

## Findings

* divider_hr: abc pdr proves the whole divider only at K = 1; the step lemmas (all inputs, W up to 16) carry the argument for larger K. The initial Q-1 register value is irrelevant (equivalent mutant, argument tested).
* recip, rsqrt: the residual's high bits are discarded by its narrow word, so two mutants of them are equivalent; the word width is a checked claim.
* div_nr: both variants hit a truncation floor near 1.2 ulp; Goldschmidt can exceed the exact quotient by up to about 0.5 ulp, Newton cannot.
* rsqrt Newton can end slightly above the exact value (about 0.23 ulp), unlike the reciprocal.

## Known gaps and limits

Vivado runs (descriptions prepared), the digit-selection table's containment in Lean, truncation error in Lean, formal proofs at larger widths for the approximate functions, any human approval.

## Records

`<function>_junit.xml`, `<function>_sim_record.json`, `<function>_formal_record.json`.

## Reproduce

`ARITH_RECORD_DIR=results/139c_arith python -m pytest -q arith/<function>/tests --junitxml=results/139c_arith/<function>_junit.xml`, then `python -m flow.trace_v1 pin arith/<function>` and `write`; Lean record by `python -m flow.trace_v1 lean-record`.
