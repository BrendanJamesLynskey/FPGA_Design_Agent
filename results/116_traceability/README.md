# results/116_traceability: recorded runs that the specification-to-evidence matrices read (brief 116)

Evidence files that exist so that a requirement can point at them. The matrices and the rules are in [docs/traceability_v1.md](../../docs/traceability_v1.md).

## Records

| File | What | Made by |
|---|---|---|
| `b96_kr260_10g/pytest_junit.xml` | JUnit record of every pytest test under `designs/b96_kr260_10g/tests`: the cocotb benches run through their pytest entry points (Icarus Verilog, cocotb 2.0.1) and the board-driver tests on a fake board | simulation only, no board, no Vivado, 2026-11-20 |

## Reproduce

```
python -m pytest -q designs/b96_kr260_10g/tests --junitxml=results/116_traceability/b96_kr260_10g/pytest_junit.xml
python -m flow.trace_v1 pin designs/b96_kr260_10g     # after committing the record
python -m flow.trace_v1 write designs/b96_kr260_10g
```

The cocotb benches take well over half an hour on a loaded machine (the rate-match benches are the slow ones), so run it under `systemd-run --user --scope -p MemoryMax=3G`.

## Known gaps and limits

The simulation tests are not otherwise recorded in the repository (CI runs them and keeps no file), so this record is what the `sim_test` items of the b96 testplan read.
It is one run on one machine on one day; re-record it after a change to the design or its tests, or the matrix will mark the evidence stale.
