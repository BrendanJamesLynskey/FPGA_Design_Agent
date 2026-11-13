# 05m: the V3 evidence step run inside the simulation container

This folder holds the records from brief 05m, which added Verilator 5.048 to the `fda-sim:2` container image so the
coverage run and the mutation run work under the same sandbox as the agent's other runs. The records are for the
reference `designs/t1_dimmer_counter` bench, no agent, run in the container, and were made to be compared with
`results/05l` (the same steps on the host).

## Records

| File | What |
|---|---|
| `mutation_t1_container.json` | generic mutation run with `sandbox: container`: 21 candidates, 20 sampled (cap 20, seed 1), 20 killed, 0 survived; score 100.0 %; baseline 142.2 s, wall 938.2 s |
| `v3_evidence_t1_container.json` | evidence status: coverage ok, mutation ok, same source hash as `results/05l` |
| `verif_gates_t1_container.json` | gate output: line 36/36, toggle 760/870 (87.36 %), branch 28/28, identical to `results/05l`; V0 and V1 pass, V2 fails |

## Reproduce

Needs the `fda-sim:2` image (built from `container/Dockerfile`; the Verilator build took about 15 minutes) and a heavy
slot; no Vivado, board or paid agent run. The mutation part alone, in the container:

    python3 flow/mutate.py --generic designs/t1_dimmer_counter --sandbox container --json results/05m/mutation_t1_container.json

The graph's own evidence step (`v3_evidence` in `agent/graph/run.py`) produces the other two files; the exact invocation
used for the committed files is not recorded in the folder. Do not wrap a V3 run in your own heavy lock: the
mutation subprocess does not inherit it and would report busy.

## Known gaps and limits

- The gate stops at V2 exactly as in `results/05l`: the formal tasks are absent from this run and the reference bench does
  not export functional bins, so the result shows code coverage and mutation, not a V3 pass.
- Compared with `results/04f`, toggle coverage is 760/870 here and 759/870 there: these are different runs and the
  difference of one point was not investigated.
- Only 20 of 21 mutants sampled; one design; no live agent run.
- A session using the local runner while the image exists still sees the image's Verilator in `available_sims()`;
  this affects direct and MCP use only.
