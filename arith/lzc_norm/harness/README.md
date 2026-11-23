# Verification harness for `lzc_norm` (rerun it after integration)

Brief 139b, owner decision 24: the library entry is the RTL variants **and** this harness, so a user who changes, wraps or re-instantiates a variant can check it again without knowing the library's internals.

## What is in the harness

| Part | Where |
|---|---|
| Model (the specification in code, bit-exact) | `../model.py` |
| Bench: drives vectors with random input gaps, checks every value, the order, and the **measured latency of every result** | `../../common/tb_stream.sv` (generic) driven by `run.py` |
| Vectors | exhaustive when the width is small, otherwise edge values plus random (count with `--vectors N`) |
| Coverage targets | `coverage.yaml`: named bins over the input vectors; the run fails if a bin is not hit |
| Assertions / formal properties | `../formal/lzc_norm_fv.sv`: timing (out_valid exactly LAT cycles after an accepted input) and value against an independent reference; run with SymbiYosys (see `../tests/test_lzc_norm_formal_rtl.py` for the exact job; it needs a module with the library's selector interface) |
| Seeded-fault check (proves the bench can fail) | `../verif/mutants.yaml`, run by `../tests/test_lzc_norm_rtl.py` |

## Run it against your instance

Your instance needs the library's packed stream ports (as `../rtl/*_sel.sv`): `clk, rst, in_valid, in_ready, in_data, out_valid, out_data` with the packing in `../spec.md`. Parameter names are yours; pass each one as `--param NAME=VALUE`, including the function parameters the model needs (see `run.py`: `W (and PIPE)`).

```
python3 arith/lzc_norm/harness/run.py --dut my_norm --rtl my_norm.sv --param W=24 --param PIPE=2 --variant stagewise_pipe
```

`--variant` takes the library variant id so the expected latency is taken from the model; if your instance has a different latency (for example after adding an input register) give it with `--latency N` and the run checks that instead. Needs Icarus Verilog (the OSS CAD Suite one is found automatically, or put `iverilog` and `vvp` on PATH). Exit status 0 only if the result, order and latency checks pass and every coverage bin is hit; the output is JSON.

## What a pass does and does not show

It shows that, for the parameters you gave, the instance computes the model's value in the model's order at the stated latency on the vectors run (all of them at small widths). It does not show timing (Fmax, area and power are not measured for this entry yet), behaviour under reset in the middle of a stream, or widths you did not run.
