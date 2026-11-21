# results/116_traceability: recorded runs that the specification-to-evidence matrices read (brief 116)

Evidence files that exist so that a requirement can point at them. The matrices and the rules are in [docs/traceability_v1.md](../../docs/traceability_v1.md).

## Records

| File | What | Made by |
|---|---|---|
| `b96_kr260_10g/pytest_junit.xml` | JUnit record of every pytest test under `designs/b96_kr260_10g/tests`: the cocotb benches run through their pytest entry points (Icarus Verilog, cocotb 2.0.1) and the board-driver tests on a fake board | simulation only, no board, no Vivado, 2026-11-20 |
| `b119_tcp_fast/pytest_junit.xml` | JUnit record of every pytest test under `designs/b119_tcp_fast/tests`: the Python-side model tests, the cocotb bench and the bench behind brief 110's risk logic (Icarus Verilog, cocotb 2.0.1), and the Verilator lint | simulation only, no board, no Vivado, 2026-11-21 (brief 133) |

## Reproduce

```
python -m pytest -q designs/b96_kr260_10g/tests --junitxml=results/116_traceability/b96_kr260_10g/pytest_junit.xml
python -m flow.trace_v1 pin designs/b96_kr260_10g     # after committing the record
python -m flow.trace_v1 write designs/b96_kr260_10g
```

For b119 (about 15 seconds):

```
python -m pytest -q designs/b119_tcp_fast/tests --junitxml=results/116_traceability/b119_tcp_fast/pytest_junit.xml
python -m flow.trace_v1 pin designs/b119_tcp_fast
python -m flow.trace_v1 write designs/b119_tcp_fast
```

The cocotb benches take well over half an hour on a loaded machine (the rate-match benches are the slow ones), so run it under `systemd-run --user --scope -p MemoryMax=3G`.

## Fresh runs

`python -m flow.fresh_evidence run b119-tests --out DIR` and the nightly workflow re-make these JUnit records (and `results/b119/*.json`) from the current tree into DIR and compare them with the committed ones
(brief 143d, [docs/traceability_v1.md](../../docs/traceability_v1.md#fresh-evidence-brief-143d)); a difference is a stale or wrong committed record.

## Known gaps and limits

The simulation tests are not otherwise recorded in the repository (CI runs them and keeps no file), so this record is what the `sim_test` items of the b96 testplan read.
It is one run on one machine on one day; re-record it after a change to the design or its tests, or the matrix will mark the evidence stale.
