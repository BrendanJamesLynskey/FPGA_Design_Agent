# Results for the formal rigour pack (brief 143c)

Brief 143c's records: for each shipped SymbiYosys proof, whether its assertions had something to check (antecedent covers), whether its assumptions left the design able to work (sanity covers), why each bounded depth is enough or that it is not, and a mutation score for one proof. The tool is [flow/formal_rigour.py](../../flow/formal_rigour.py) and the page that explains it is [docs/formal_rigour.md](../../docs/formal_rigour.md).

## Records

| File | What |
|---|---|
| `formal_rigour/<job>.json` | one per `.sby` job (path with `/` as `__`): every task's status, run time, the assertions, assumptions and covers of its elaborated model, and which covers were reached at which step; the SHA-256 of the `.sby` and of every source file, so that a changed file makes the record stale. Judged by `python -m flow.formal_rigour check <job>.sby` together with the sidecar `<job>.rigour.yaml` beside the `.sby` |
| `mutation/rm_gp_safety_bmc.json`, `mutation/rm_gp_progress_bmc.json` | the mutation runs on the rate matcher's `safety_bmc` (60 mutants, depth 24) and `progress_bmc` (40 mutants, depth 20) tasks: each mutation, its verdict, the assertions that caught it, the RTL line and the wires of the mutated cell, and (for survivors) the class `designs/b96_kr260_10g/verif/formal/classify_mutants.py` gave it |

The tool is Yosys 0.70 (OSS CAD Suite 20261112, the release the repo's CI pins) with `sby`, boolector, z3 and yices.

## Reproduce

```
python3 -m flow.formal_rigour run designs/b58a_trigger/verif/formal/interlocks.sby     # one job; writes its record here
python3 -m flow.formal_rigour check designs/b58a_trigger/verif/formal/interlocks.sby   # judge the record and the sidecar
python3 -m flow.formal_rigour audit                                                    # every tracked .sby
python3 -m flow.formal_mutation designs/b96_kr260_10g/verif/formal/rm_gp.sby --task safety_bmc --depth 24 --n 60 --seed 1 --select 'a:src=*rate_match_gp.sv* a:src=*xpm_formal.sv* %u' --json results/143c/mutation/rm_gp_safety_bmc.json
python3 -m flow.formal_mutation designs/b96_kr260_10g/verif/formal/rm_gp.sby --task progress_bmc --depth 20 --n 40 --seed 1 --select 'a:src=*rate_match_gp.sv* a:src=*xpm_formal.sv* %u' --json results/143c/mutation/rm_gp_progress_bmc.json
python3 designs/b96_kr260_10g/verif/formal/classify_mutants.py results/143c/mutation/rm_gp_safety_bmc.json    # and the progress file: the survivor classes
python3 -m pytest -q flow/tests/test_143c_formal_rigour.py
```

The runs are single-threaded and small (each under 6 GB). The slowest records are `order_ctl` (its `bmc` task took 2757 s) and `icmp` (its `cover` task about 17 minutes); the two mutation runs took about 27 and 18 minutes. No heavy slot is taken (single-threaded formal runs under `systemd-run -p MemoryMax=6G`, one or two at a time while the machine's load was above 6).

## Known gaps and limits

- A record is judged against file hashes; it does not show that `sby` was re-run. Re-make a record after any change to a harness, its RTL or the `.sby`.
- Antecedent covers show that a guard is reachable, not that the guarded assertion is a strong one; the sidecars and `docs/formal_rigour.md` list where an antecedent is weak.
- Bounded jobs stay bounded: `mac_rx`, `mac_tx`, `order_ctl` and the network blocks have no k-induction proof (attempted on `mac_rx`, `mac_tx`, `order_ctl` and `arp`: each fails its induction step), and rm_gp's progress check is bounded with an open induction step.
- The mutation score is for one task at one depth with one seed, and the mutants sample the netlist evenly, most of them in the 74-bit entry's storage and synchroniser copies, of which the proof follows one bit; a survivor is an unnoticed bug, an equivalent mutant or a bug outside the slice, and the tool cannot tell which. The survivor classes are rules on the mutated cell's wires, not proofs.
- `flow/tests/fixtures` and `runs/` hold test fixtures and old agent runs, not shipped proofs; they are not judged.
