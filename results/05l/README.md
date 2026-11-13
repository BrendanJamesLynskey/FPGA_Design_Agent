# 05l: V3 evidence produced by the harness on T1

This folder holds the records from brief 05l, which made the graph run the Verilator coverage run and the mutation run
itself before the verification gate, instead of leaving them to an agent's tool choice. The records are from a run on
the reference `designs/t1_dimmer_counter` bench with no agent, run on the host (Verilator, no container).

## Records

| File | What |
|---|---|
| `mutation_t1_harness.json` | generic mutation run: 21 candidates, 20 sampled (cap 20, seed 1), 20 killed, 0 survived; score 100.0 %; baseline 138.8 s, wall 656.4 s |
| `v3_evidence_t1_harness.json` | the evidence status the gate reads: coverage ok, mutation ok and not busy, plus the hash of the sources it applies to |
| `verif_gates_t1_harness.json` | `flow/verif_gates.py` on that evidence: code coverage line 36/36, toggle 760/870 (87.36 %), branch 28/28; V0 and V1 pass, V2 fails |

## Reproduce

The evidence step is run by the graph (`v3_evidence` in `agent/graph/run.py`) at stage 2, level V3, after lint and
Icarus simulation pass; it takes the heavy lock itself (do not hold it around the call). It needs a heavy slot and a
host Verilator, about 20 minutes on T1, and no Vivado, board or paid agent run. The mutation part alone:

    python3 flow/mutate.py --generic designs/t1_dimmer_counter --json results/05l/mutation_t1_harness.json

The exact harness invocation used for the committed files is not recorded in the folder.

## Known gaps and limits

- The gate result stops at V2: the four SymbiYosys tasks (`debounce_bmc`, `debounce_cover`, `scan_bmc`, `scan_cover`)
  were absent from this run, so `formal_tasks_not_passing` fails; V3 shows 0/0 functional bins because the reference bench
  does not export them (`FDA_COV_OUT`). V-HW and sign-off are also not passed here. The coverage and mutation numbers
  are therefore evidence made by the harness, not a V3 pass.
- Only 20 of 21 mutants were sampled (cap 20).
- With the simulation container image present, the graph uses the container runner (Icarus only), so a real graph run
  would record "coverage not made"; this was found and fixed by brief 05m (see `results/05m`).
- One design, no live agent run.
