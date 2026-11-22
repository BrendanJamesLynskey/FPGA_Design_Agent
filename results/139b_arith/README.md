# Arithmetic library, everything before Vivado (brief 139b): measured results

Four functions of the FPGA arithmetic library, in [arith/](../../arith/README.md). **No Vivado run was made**: nothing here is an Fmax, an area or a power figure. Every number below is a count from a simulation, a proof job or a build of the Lean project, taken on 2026-11-21 with Icarus Verilog 14 (devel), Verilator 5.055, Yosys 0.70 with yosys-slang and SymbiYosys from the OSS CAD Suite build 20261031 installed on this PC (CI pins build 20261112; not re-run on that build here), Lean 4.36.0.

| Function | Variants | Simulation: configurations, vectors | Seeded mutants killed / total | SymbiYosys: reference, pairs (all unbounded, `abc pdr`) | Faults caught by the proof | Lean (all widths, proved; statements not approved) |
|---|---|---|---|---|---|---|
| divider | 4 | 60 runs, 659,648 vectors | 16 / 16 (+1 equivalent, reasoned) | 14 / 14, 3 / 3 | 6 / 6 | 3 theorems |
| fxp_round | 3 | 1029 runs, 383,808 vectors | 14 / 14 | 24 / 24, 8 / 8 | 6 / 6 | 6 theorems |
| isqrt | 3 | 70 runs, 464,816 vectors | 16 / 16 | 12 / 12, 3 / 3 | 6 / 6 | 1 theorem |
| lzc_norm | 4 | 94 runs, 926,512 vectors | 16 / 16 (+1 equivalent by construction) | 13 / 13, 5 / 5 | 6 / 6 | 1 theorem |

The proofs are at small widths (W = 4 to 12): each is for all input sequences from reset at that width, not for all widths. The all-widths claims are the Lean theorems, and those are about transcriptions of the recurrences (cross-checked against the Python models for small widths), not about the RTL itself; the matrix says so per item. The "faults caught" column is bounded model checking finding a counterexample on a mutated copy of the RTL (it shows the proof harness is not vacuous).

## Findings

* The restoring divider's shifted partial remainder never needs its top bit (it is a prefix of the dividend); the first surviving mutant showed it, the RTL was narrowed by one carry-chain bit, and the model asserts the bound.
* One equivalent mutant of the non-restoring divider (the correction applied in every stage is an identity) and one of the normaliser (loop variant wired to the tree: simulation cannot tell them apart) were found and are listed with reasons in each `verif/mutants.yaml`, not counted as kills.
* Tree and priority-loop leading-zero variants are proved equal by SymbiYosys, a question simulation cannot answer. Whether Vivado builds them as the same logic is open.
* A saturating rounding output exactly W_IN - S bits wide still saturates for the largest input (the rounded value needs one more bit).

## Records

`<function>_junit.xml` (pytest, the sim_test evidence), `<function>_sim_record.json` (every configuration run, mutant rows), `<function>_formal_record.json` (every proof job with engine, depth, seconds, claim).

## Reproduce

`ARITH_RECORD_DIR=results/139b_arith python -m pytest -q arith/<function>/tests --junitxml=results/139b_arith/<function>_junit.xml`, then `python -m flow.trace_v1 pin arith/<function>` and `write`. Lean: `formal/lean/Arith/`, record `formal/lean/records/build_record.json` (`python -m flow.trace_v1 lean-record`).

## Known gaps and limits

Vivado out-of-context runs (the descriptions are prepared in `arith/<function>/build/`), post-implementation simulation, structural netlists, Lean for the non-restoring square root and the stagewise normaliser, and every human approval (specifications and Lean statements are drafts). The format is the brief's own layout; brief 137's library format (`docs/arithmetic_pareto_plan.md`, branch `b137-arith-pareto`, uncommitted when this was written) was not on main and the two are to be aligned when it merges.
