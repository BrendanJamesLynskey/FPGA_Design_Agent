# Formal rigour: is a SymbiYosys proof worth what it says? (brief 143c)

A green `sby` task says only that no assertion failed. Three things it does not say, and that this page's tool, `flow/formal_rigour.py`, checks for every shipped proof:

1. **The assertion had something to check.** `if (req) assert (ack)` passes for ever if `req` can never be true (a vacuous pass). Each assertion is paired with a *cover of its own antecedent*; a cover task must reach it.
2. **The assumptions left the design able to do something.** An over-constrained harness proves everything. Each job lists *sanity covers* (the main states: a frame leaves, a grant is made, an item is popped) that the cover task must reach under every assumption.
3. **Why a bounded depth N is enough**, or an explicit statement that it is not. Every `bmc` task carries a written justification, `enough: true` with the argument (pipeline depth, counter period, the step at which the deepest cover is reached) or `enough: false` with what the depth does not reach.

Code: [flow/formal_rigour.py](../flow/formal_rigour.py) (tests `flow/tests/test_143c_formal_rigour.py`); mutation score: [flow/formal_mutation.py](../flow/formal_mutation.py); records: [results/143c](../results/143c/README.md).

## What the tool reports per assertion

| Status | Meaning | Counts as `pass` in trace_v1? |
|---|---|---|
| `proved` | holds in a passing `prove` task (k-induction: every depth) and its antecedent cover is reached | yes |
| `bounded` | holds to depth N in `bmc` tasks only; `justified` says whether a written argument for N exists (`enough: true` or `false`) | no: the item is `bounded` if justified, `fail` if not |
| `vacuous` | no antecedent cover is paired with it, or it contains a constant-true term (`\|\| 1'b1`). *Not shown to be non-vacuous*: the burden of proof is on the harness | no: `fail` |
| `unreachable-cover` | the antecedent cover exists but no cover task reaches it: within the cover depth the assertion never fires | no: `fail` |
| `failed`, `not-run` | a task reports it failing; no passing proof task contains it | no: `fail` |

A job also fails when a task does not pass, there is no cover task, no sanity cover is listed, a sanity cover is unreachable, a `bmc` task has no written justification, or the record is **stale** (the hash of the `.sby`, or of any file in its `[files]`, changed since the record was made).

`pass` needs every assertion `proved`. A bounded result with a good justification is still `bounded` in the matrix: a prose argument for N is not a proof, and the matrix says so.

## Writing a proof that passes

1. **Label every assertion** (`a_name: assert (...)`). An unlabelled assertion cannot be paired and is `vacuous`.
2. **Pair it.** The cover is `a_name__ante: cover (<the guard>)`, in the same clock and guard as the assertion. For `if (A) assert (B)` the cover is `cover (A)`; for an implication, the left side; for an invariant, the state in which it could be broken (a counter above 0, a buffer full), not `1'b1`. One cover can serve a group: map them in the sidecar (`antecedents: {"a_grant_*": a_grant__ante}`). The T1 checkers get this for free: `designs/t1_dimmer_counter/verif/formal/v_macros_paired.svh` (read after the flow-owned `v_macros.svh`, which stays unchanged because the tests role sees it) redefines `V_SAME`, `V_NEXT` and `V_RST` in the Yosys (`-DFORMAL`) branch to add `NAME__ante`; rm_gp has `FV_ANTE`.
3. **Add a cover task** to the `.sby`, deep enough to reach every antecedent. A cover that needs more steps than the others (rm_gp's idle deletion needs about 70) goes in its own task (`cover_del`).
4. **Write the sidecar** `<job>.rigour.yaml` beside the `.sby` (schema in the module docstring): `scope` (what instance is proven), `antecedents` (only where the default `NAME__ante` does not apply), `sanity` (covers that show the assumptions are not over-constraining), `depth` (one entry per `bmc` task), and `unclaimed` (a task that is kept but does not pass and is not relied on, with the reason).
5. `python -m flow.formal_rigour run <job>.sby` (needs `sby`; FDA_OSS_CAD or `~/.local/opt/oss-cad-suite`), commit the record in `results/143c/formal_rigour/`, then `python -m flow.formal_rigour check <job>.sby` and `audit`.

If a bounded job can be made a proof, do that instead of writing a justification: T1's debounce and scan jobs were bounded, and a `prove` task (k-induction, depth 12) closed both.

## In the traceability matrix

A `formal` item in `testplan.yaml` may carry `rigour: [path/to/job.sby, ...]` (schema in [traceability_v1.md](traceability_v1.md)). `flow/trace_v1.py` then reads each job's committed record and the live sidecar: an item whose junit or text evidence passes becomes `fail` ("formal rigour: ...") if any job has a vacuous, unreachable-cover, failed or unjustified-bounded assertion or a stale record, `bounded` if every assertion is proved or justified-bounded and some are bounded, and keeps `pass` only when every assertion is proved. An item without the field is untouched. b96's `V-FORMAL-SVA-PLANNED` carries it.

## Limits

- The check is only as good as the antecedent: a cover of `1'b1` pairs an assertion and shows nothing. The sidecar is read by a person, not proved; the report below lists where an antecedent is weak.
- "Reached" means reached in some cover task of the job in which the cover exists, within that task's depth; it does not tie the cover task to the proof task's assumptions beyond both being the same harness.
- A constant-true term is found by a text match on the assertion's source (`|| 1'b1`, `assert (1)`), not by logic; a tautology written another way is not found.
- The tool judges a committed record against the files' hashes; it does not re-run `sby`. CI runs `flow/formal.sh` (T1) and the proofs' own tests, and the record is re-made by a person with the OSS CAD Suite.
- Mutation: see `flow/formal_mutation.py`. A survivor is a bug the properties did not notice at that depth *or* an equivalent mutant; the tool cannot tell them apart.
