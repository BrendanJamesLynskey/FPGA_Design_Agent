## Simulator comparison under cocotb

Versions: `ghdl-4.1.0-mcode` = GHDL 4.1.0 (Ubuntu 4.1.0+dfsg-0ubuntu2.1) [Dunoon edition] (static elaboration, mcode JIT code generator); `ghdl-7.0.0dev-llvm` = GHDL 7.0.0-dev (6.0.0.r729.g8e642a9a5.dirty) [Dunoon edition] (llvm 21.1.8 code generator); `nvc-1.23.1-jit` = nvc 1.23.1 (1.23.1.r0.gfab54a9) (Using LLVM 18.1.3); `nvc-1.23.1-aot` = nvc 1.23.1 (1.23.1.r0.gfab54a9) (Using LLVM 18.1.3)

Median of 3 runs, seconds, run 2026-11-22 01:55:38 GMT. build = analysis + elaboration command; start = BENCH_OPS=0 (simulator start, elaboration for the mcode and JIT flows, cocotb start, reset); sim = workload run minus start; tests = cocotb tests passed.

| Design | ops | ghdl-4.1.0-mcode build / start / sim | ghdl-7.0.0dev-llvm build / start / sim | nvc-1.23.1-jit build / start / sim | nvc-1.23.1-aot build / start / sim | pass/fail | trace digests |
|---|---:|---|---|---|---|---|---|
| sync_fifo_regs | 40000 | 0.03 / 0.43 / 17.87 | 0.25 / 0.38 / 16.18 | 0.03 / 0.41 / 15.53 | 0.05 / 0.44 / 15.88 | PPP | same |
| gray_stepper | 1500 | 0.04 / 0.45 / 3.96 | 0.39 / 0.42 / 3.56 | 0.03 / 0.42 / 3.65 | 0.05 / 0.42 / 3.58 | PPP | same |
| debounce_bank | 4000 | 0.04 / 0.43 / 6.10 | 0.42 / 0.39 / 5.52 | 0.02 / 0.43 / 5.40 | 0.06 / 0.42 / 5.40 | PPP | same |
| elevator_fsm | 300 | 0.03 / 0.43 / 4.33 | 0.39 / 0.40 / 3.88 | 0.03 / 0.41 / 3.97 | 0.05 / 0.43 / 3.88 | PPP | same |
| axil_regs | 8000 | 0.03 / 0.45 / 6.86 | 0.31 / 0.39 / 6.60 | 0.02 / 0.44 / 6.69 | 0.05 / 0.42 / 6.68 | PPP | same |
| fir16 | 6000 | 0.04 / 0.48 / 10.49 | 0.45 / 0.47 / 7.66 | 0.03 / 0.51 / 2.89 | 0.06 / 0.53 / 2.88 | PPP | same |

## Faults caught

| Design (one fault) | ghdl-4.1.0-mcode | ghdl-7.0.0dev-llvm | nvc-1.23.1-jit | nvc-1.23.1-aot |
|---|---|---|---|---|
| sync_fifo_regs | caught | caught | caught | caught |
| gray_stepper | caught | caught | caught | caught |
| debounce_bank | caught | caught | caught | caught |
| elevator_fsm | caught | caught | caught | caught |
| axil_regs | caught | caught | caught | caught |
| fir16 | caught | caught | caught | caught |

## Kernel speed without cocotb

fir16 pure-VHDL testbench, 300000 clocks, median of 3 runs (2026-11-22 02:05:31 GMT).

| Simulator | build s | run s | clocks per s | result line |
|---|---:|---:|---:|---|
| ghdl-4.1.0-mcode | 0.05 | 237.34 | 1264 | CHECKSUM=555711018 OUTPUTS=262272 SAT='1' |
| ghdl-7.0.0dev-llvm | 0.47 | 134.55 | 2230 | CHECKSUM=555711018 OUTPUTS=262272 SAT='1' |
| nvc-1.23.1-jit | 0.03 | 2.49 | 120606 | CHECKSUM=555711018 OUTPUTS=262272 SAT='1' |
| nvc-1.23.1-aot | 0.06 | 2.53 | 118528 | CHECKSUM=555711018 OUTPUTS=262272 SAT='1' |

## NVC coverage

Lines with at least one hit / lines with coverage items. NVC counts a line when any of its statement, branch, toggle or expression bins exists; GHDL's file has statement lines only. short = a few operations per run (seed 1, seed 2), merged_short = the two short runs merged (NVC: `--cover-merge`; GHDL: our union script, because `ghdl coverage` fails on two inputs), full = the whole workload (seed 1).

| Design | tool | short seed 1 | short seed 2 | merged short | full |
|---|---|---:|---:|---:|---:|
| sync_fifo_regs | NVC 1.23.1 | 48/81 | 48/81 | 54/81 | 55/81 |
| sync_fifo_regs | GHDL 4.1.0 | 48/55 | 48/55 | 54/55 | 55/55 |
| gray_stepper | NVC 1.23.1 | 69/134 | 62/134 | 69/134 | 76/134 |
| gray_stepper | GHDL 4.1.0 | 68/78 | 61/78 | 68/78 | 75/78 |
| debounce_bank | NVC 1.23.1 | 54/108 | 54/108 | 57/108 | 61/108 |
| debounce_bank | GHDL 4.1.0 | 54/64 | 54/64 | 57/64 | 61/64 |
| elevator_fsm | NVC 1.23.1 | 74/120 | 74/120 | 74/120 | 74/120 |
| elevator_fsm | GHDL 4.1.0 | 74/77 | 74/77 | 74/77 | 74/77 |
| axil_regs | NVC 1.23.1 | 49/92 | 52/92 | 53/92 | 53/92 |
| axil_regs | GHDL 4.1.0 | 49/56 | 52/56 | 53/56 | 53/56 |
| fir16 | NVC 1.23.1 | 48/69 | 48/69 | 48/69 | 48/69 |
| fir16 | GHDL 4.1.0 | 56/56 | 56/56 | 56/56 | 56/56 |

NVC bins per kind, full run (bins hit / bins; excluded bins are the clock and reset toggles NVC leaves out):

| Design | statement | branch | toggle | expression | fsm-state |
|---|---:|---:|---:|---:|---:|
| sync_fifo_regs | 67/67 | 53/54 | 118/162 | 45/49 | - |
| gray_stepper | 93/96 | 67/70 | 172/294 | 73/83 | - |
| debounce_bank | 451/484 | 284/317 | 600/608 | 152/188 | - |
| elevator_fsm | 80/83 | 51/54 | 141/290 | 59/68 | - |
| axil_regs | 53/56 | 31/34 | 418/434 | 37/41 | - |
| fir16 | 63/63 | 26/26 | 270/272 | 16/17 | - |

## PSL constructs

| Construct | expected | GHDL 4.1.0 sim | GHDL 7.0.0-dev sim | NVC 1.23.1 sim | Yosys 0.33 + plugin 4.1.0 | Yosys 0.70 + plugin 7.0.0-dev |
|---|---|---|---|---|---|---|
| `always_next_impl` | true | pass | pass | pass | pass | pass |
| `always_next_impl_bad` | false | fail | fail | fail | fail | fail |
| `prev` | true | rejected | rejected | pass | pass | pass |
| `rose` | true | rejected | rejected | rejected | pass | pass |
| `fell` | true | rejected | rejected | rejected | pass | pass |
| `stable` | true | rejected | rejected | pass | pass | pass |
| `onehot0_bad` | false | rejected | rejected | fail | fail | fail |
| `onehot` | true | rejected | rejected | pass | pass | pass |
| `sere_suffix_nonoverlap` | true | pass | pass | pass | pass | pass |
| `sere_suffix_overlap` | true | pass | pass | pass | rejected | rejected |
| `sere_repeat_overlap` | true | pass | pass | rejected | pass | pass |
| `sere_repeat_nonoverlap_bad` | false | fail | fail | rejected | fail | fail |
| `never_sere` | true | pass | pass | pass | pass | pass |
| `until` | true | pass | pass | fail (differs from the formal tools and the other simulators) | pass | pass |
| `eventually` | true | pass | pass | pass | pass | pass |
| `next_e_range` | true | pass | pass | pass | pass | pass |
| `next_a_range` | true | pass | pass | fail (differs from the formal tools and the other simulators) | pass | pass |
| `next_n` | true | pass | pass | pass | pass | pass |
| `before` | true | pass | pass | pass | pass | pass |
| `abort` | true | pass | pass | pass | pass | pass |
| `sync_abort` | true | pass | pass | pass | pass | pass |
| `within` | true | rejected | rejected | rejected | rejected | rejected |
| `assume_then_assert` | true | pass | pass | rejected | pass | pass |
| `named_property_stmt_part` | true | pass | pass | rejected | rejected | rejected |
| `named_property_decl_part` | true | rejected | rejected | rejected | rejected | rejected |
| `assert_report` | false | fail | fail | rejected | fail | fail |
| `cover_sequence` | cover | accepted (no cover report read) | accepted (no cover report read) | accepted (no cover report read) | pass | pass |
| `cover_bad_unreachable` | cover-unreachable | accepted (no cover report read) | accepted (no cover report read) | accepted (no cover report read) | fail | fail |
| `restrict` | true | rejected | pass | rejected | pass | pass |
| `fairness` | true | rejected | rejected | rejected | rejected | rejected |
| `strong_next` | true | rejected | rejected | pass | rejected | rejected |

Why a construct was rejected (first error line of the tool, paths removed):

| Construct | tool | message |
|---|---|---|
| `prev` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_PREV (p.vhd:21:43) |
| `prev` | ghdl-llvm | p.vhd:21:43:error: PSL builtin function not supported in simulation |
| `rose` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_ROSE (p.vhd:21:39) |
| `rose` | ghdl-llvm | p.vhd:21:39:error: PSL builtin function not supported in simulation |
| `rose` | nvc | ** Fatal: (init): argument to not is not boolean |
| `fell` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_FELL (p.vhd:21:39) |
| `fell` | ghdl-llvm | p.vhd:21:39:error: PSL builtin function not supported in simulation |
| `fell` | nvc | ** Fatal: (init): argument to not is not boolean |
| `stable` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_STABLE (p.vhd:21:39) |
| `stable` | ghdl-llvm | p.vhd:21:39:error: PSL builtin function not supported in simulation |
| `onehot0_bad` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_ONEHOT0 (p.vhd:21:20) |
| `onehot0_bad` | ghdl-llvm | p.vhd:21:20:error: PSL builtin function not supported in simulation |
| `onehot` | ghdl-mcode | translate_expression: cannot handle IIR_KIND_PSL_ONEHOT (p.vhd:21:20) |
| `onehot` | ghdl-llvm | p.vhd:21:20:error: PSL builtin function not supported in simulation |
| `sere_suffix_overlap` | formal-debgh, formal-oss | base: Please report this bug on https://github.com/ghdl/ghdl/issues |
| `sere_repeat_overlap` | nvc | ** Error: left hand side of suffix implication operator must be a Sequence |
| `sere_repeat_nonoverlap_bad` | nvc | ** Error: left hand side of suffix implication operator must be a Sequence |
| `within` | ghdl-mcode, ghdl-llvm | p.vhd:21:46:error: missing matching ')' for '(' at line 21:35 |
| `within` | nvc | ** Error: unexpected within while parsing FL property, expecting ) |
| `within` | formal-debgh, formal-oss | base: p.vhd:21:46:error: missing matching ')' for '(' at line 21:35 |
| `assume_then_assert` | nvc | ** Error: unexpected identifier while parsing concurrent procedure call statement, expecting one of ( or ; |
| `named_property_stmt_part` | nvc | ** Error: unexpected identifier while parsing concurrent procedure call statement, expecting one of ( or ; |
| `named_property_stmt_part` | formal-debgh, formal-oss | base: Please report this bug on https://github.com/ghdl/ghdl/issues |
| `named_property_decl_part` | ghdl-mcode, ghdl-llvm | p.vhd:12:5:error: 'begin' is expected instead of 'sequence' |
| `named_property_decl_part` | nvc | ** Error: unexpected identifier while parsing block declarative item, expecting one of signal, type, subtype, file, constant, function, impure, pure, procedure, alias, at |
| `named_property_decl_part` | formal-debgh, formal-oss | base: p.vhd:12:5:error: 'begin' is expected instead of 'sequence' |
| `assert_report` | nvc | ** Error: unexpected severity while parsing PSL or concurrent assertion statement, expecting one of ** or ; |
| `restrict` | ghdl-mcode | gather_processes_stmt: cannot handle IIR_KIND_PSL_RESTRICT_DIRECTIVE (p.vhd:21:5) |
| `restrict` | nvc | ** Error: unexpected { while parsing concurrent procedure call statement, expecting one of ( or ; |
| `fairness` | ghdl-mcode, ghdl-llvm | p.vhd:21:14:error: '<=' is expected instead of "req" |
| `fairness` | nvc | ** Error: unexpected identifier while parsing concurrent procedure call statement, expecting one of ( or ; |
| `fairness` | formal-debgh, formal-oss | base: p.vhd:21:14:error: '<=' is expected instead of "req" |
| `strong_next` | ghdl-mcode, ghdl-llvm | p.vhd:21:33:error: unexpected token 'next!' in a primary |
| `strong_next` | formal-debgh, formal-oss | base: p.vhd:21:33:error: unexpected token 'next!' in a primary |

## PSL properties on the Gray stepper

Run 2026-11-22 03:11:19 GMT. Formal: SymbiYosys `bmc` (depth 20, z3) and `cover`; sim: the cocotb bench of brief 55's gray_stepper with the PSL properties compiled in.

| Language | design | flow | bmc | cover |
|---|---|---|---|---|
| SystemVerilog | clean | SV twin, `ifdef FORMAL`, Yosys front end; Yosys 0.33 (Ubuntu) | PASS (5.78 s) | PASS (1.12 s) |
| SystemVerilog | clean | SV twin, `ifdef FORMAL`, Yosys front end; Yosys 0.70 (OSS CAD Suite) | PASS (4.21 s) | PASS (0.4 s) |
| SystemVerilog | fault | SV twin, `ifdef FORMAL`, Yosys front end; Yosys 0.33 (Ubuntu) | FAIL at step 6 (2.46 s) | PASS (1.31 s) |
| SystemVerilog | fault | SV twin, `ifdef FORMAL`, Yosys front end; Yosys 0.70 (OSS CAD Suite) | FAIL at step 6 (0.98 s) | PASS (0.41 s) |
| VHDL | clean | VHDL, PSL, GHDL plugin 4.1.0; Yosys 0.33 (Ubuntu) | TIMEOUT at 60 s (60.23 s) | TIMEOUT at 60 s (60.25 s) |
| VHDL | clean | VHDL, PSL, GHDL plugin 7.0.0-dev; Yosys 0.70 (OSS CAD Suite) | PASS (4.31 s) | PASS (0.48 s) |
| VHDL | fault | VHDL, PSL, GHDL plugin 4.1.0; Yosys 0.33 (Ubuntu) | TIMEOUT at 60 s (60.21 s) | TIMEOUT at 60 s (60.24 s) |
| VHDL | fault | VHDL, PSL, GHDL plugin 7.0.0-dev; Yosys 0.70 (OSS CAD Suite) | FAIL at step 5 (0.75 s) | FAIL (0.49 s) |

| Simulation | design | cocotb bench | PSL messages | first message |
|---|---|---|---:|---|
| ghdl-4.1.0-mcode | clean | pass | 0 |  |
| nvc-1.23.1-aot | clean | pass | 0 |  |
| ghdl-4.1.0-mcode | fault | fail | 1 | build/156_psl_gray/vhdl/fault/gray_stepper.vhd:214:12:@1680ns:(psl assertion error): Asser |
| nvc-1.23.1-aot | fault | fail | 1 | ** Error: 1680ns+1: PSL assertion failed |
