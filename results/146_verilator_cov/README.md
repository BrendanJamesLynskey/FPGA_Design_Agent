# results/146_verilator_cov: RTL code coverage of the b96 PCS and MAC pyuvm bench with Verilator (brief 146)

The brief-123 pyuvm bench (`designs/b96_kr260_10g/verif/pyuvm`) run on **Verilator 5.048** (cocotb 2.0.1, pyuvm 5.0.0) with `--coverage`: line, branch, expression and toggle coverage of `pcs_tx`, `pcs_rx`, `mac64_tx`, `mac64_rx` and `b96_pkg`, merged over the full 42-run regression (eleven directed tests over 2 seeds, `t_rand` and `t_rand_line` over 10 seeds each). The xsim UVM bench of brief 112 has no code coverage (`xcrg` is refused on the Basic licence tier). No RTL file was changed.

## Reproduce
```
source ~/.local/opt/verilator-5048/env.sh            # Verilator 5.048; cocotb 2.0.1 needs 5.036 or newer, Ubuntu's 5.020 is refused
export PYTHONPATH=. SIM=verilator PYUVM_COV=1
PY=~/.local/opt/verif-venv/bin/python                # cocotb 2.0.1, pyuvm 5.0.0, cocotb-coverage 2.0
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/v146 --record results/146_verilator_cov     # build 17.6 s; 42 runs in 186 s of simulator time
verilator_coverage --write /tmp/v146/merged.dat /tmp/v146/runs/*/coverage.dat
verilator_coverage --write-info results/146_verilator_cov/coverage_lcov.info /tmp/v146/merged.dat
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/cov_report.py /tmp/v146/merged.dat results/146_verilator_cov designs/b96_kr260_10g
```
The Verilator build is a heavy job on the shared machine (heavy slot, `systemd-run --scope -p MemoryMax=8G`); the runs themselves are sim-only.

## Records
- `summary.txt`, `results.tsv`, `scoreboard_totals.tsv`, `protocol_cover.tsv`, `coverage_report.md`, `coverage_merged.tsv`: the regression and its functional coverage, in the format of `results/123_pyuvm_pcs_mac/`.
- `coverage_summary.json`: per module and kind, covered, total, percent, plus `design` (all modules but the bench top); the testplan item `V-COV-CODE` reads it. `coverage_by_module.md`: the same as a table. `verilator_coverage_summary.txt`: Verilator's own summary (it counts the bench top too).
- `uncovered.tsv`: every uncovered line, branch and expression point with its source text, and each toggle bit never seen to move. `coverage_lcov.info`: the merged line coverage as lcov.
- `before_added_stimulus/`: the same records for the regression as brief 123 left it (before the stimulus added here), and its `results.tsv` and `coverage_merged.tsv`, which are identical to Icarus's.
- `return_arm_artifact/`: two small SystemVerilog files with their outputs, showing a Verilator reporting artefact (see below).
- `icarus_vs_verilator.txt`: the engine comparison on the final stimulus.

## Measured (design-wide: the four modules and the package; the bench top is reported apart)
| | before the added stimulus | after | open points after |
|---|---|---|---|
| line | 81.25 % (65/80) | 81.25 % (65/80) | 15, all explained below |
| branch | 81.90 % (95/116) | 85.34 % (99/116) | 17 |
| expression | 88.17 % (82/93) | 92.47 % (86/93) | 7 |
| toggle | 96.06 % (5523/5750) | 96.33 % (5539/5750) | 211 bit points |
| functional bins (cocotb-coverage) | 217 of 217 | 217 of 217 | 0 |

The line count is small because Verilator makes one line point per basic block, and 37 of the 80 points sit in `b96_pkg`'s functions. Per module: `pcs_tx` 100 % line, 99.8 % toggle; `pcs_rx` 100 % line, branch and expression, 99.7 % toggle; `mac64_rx` 90.9 % line, 100 % branch and expression, 89.2 % toggle; `mac64_tx` 80 % line, 85.7 % branch, 75 % expression, 96.3 % toggle (`coverage_by_module.md`).

**Against the functional bins.** All 217 functional bins were hit before and after, yet 15 line, 17 branch, 7 expression and 211 toggle points were open at the start of the work: functional coverage counted what the bench asked for, code coverage showed three things it never reached (below). It also showed that most open points are not stimulus gaps.

## What the stimulus added, and what it raised
Three additions to the sequences (`seqs.py`), each from a hole in the first merge; the regression still passes, 0 protocol-checker failures, 0 scoreboard mismatches:
1. `t_lens`: frames of 32800, 16400 and 61 bytes. Bits 14 and 15 of `mac64_rx`'s `len`, `len_pend`, `t_len` and `m_len` had never moved (the longest frame was 9000 bytes); 16 toggle points.
2. `t_line_blocks`: a lane-4 start block followed at once by a terminate block of each lane, in line mode (`mac64_rx` line 86, a frame with no data; the same pattern existed only in direct XGMII mode, where `pcs_tx` turns a lane-4 start into an error block so it never reached the receiver). Closed 1 branch and 1 expression point.
3. `t_xg`: all-control words with an error character in each lane and all error characters, and a terminate followed by an error character or another control character in a higher lane (`enc66` in `b96_pkg`). Closed 3 branch and 3 expression points of the package (`enc66`'s control-word and trailing-character checks).

## Every open point, explained
| Where | Points | Class | Why |
|---|---|---|---|
| `mac64_tx.sv` 67 (underrun branch), toggle `underrun` | 1 line, 2 toggle (+2 in the bench top) | **deliberately not driven** | The source must not stall inside a frame; the bench's protocol checker asserts `no_underrun`. Driving it would need a scoreboard rule for the error word and the gap that follow, which is a new check, not stimulus. A short test that stalls the source and expects the error word is the way to close it (follow-up). |
| `mac64_tx.sv` 76 (`n + 4 - 8 > 4` true arm) | 1 branch, 1 expression | **unreachable by design** | `n` is 1 to 8 (`s_nb1` is 3 bits), so `n - 4` is at most 4. A formal `cover` of the condition would confirm it. |
| `mac64_tx.sv` 79 (`n + 4 > 4` false arm) | 1 branch, 1 expression | **unreachable by design** | `n >= 1`. Same formal cover. |
| `mac64_tx.sv` 91, `mac64_rx.sv` 106 (`default:` of the state case) | 2 line | **unreachable by design** | The states are enumerated and the case lists them all. |
| `mac64_tx` `cv[4:0]`, `tail_c[7:4]`, `tail_d` bytes 5-7 and most of byte 4 | 14 + 4 + 41 toggle points | **unreachable by design** | The frame-end word holds `n` data bytes (n at least 1), 4 FCS bytes, the terminate and idles: lanes 0 to 4 of the first word are always data, and lanes 4 to 7 of the tail word are always idle (a frame needs at most 13 of the 16 bytes). |
| `mac64_rx` `fl_d[63:32]`, `t2_aw[63:32]` | 128 toggle points | **unreachable by design** | `fl_d <= {32'd0, x_d[63:32]}`: the upper half is wired to zero. |
| `mac64_rx` `fl_nb[3:2]`, `t2_nb[3:2]` | 8 toggle points | **unreachable by design** | `fl_nb = tk - 4` with `4 < tk <= 7`, so 1 to 3. |
| `mac64_rx` `len[2:0]` | 6 toggle points | **unreachable by design** | `len` grows by 8 per data word; the odd byte counts are added in `t_len` and `len_pend`. |
| `pcs_rx` `cnt[7]`, `sh_cnt[6]`, `inv_cnt[4]`; `pcs_tx` `n[0]` | 8 toggle points | **unreachable by design** | The window counters stop at 63 and 15 (`sh_cnt == 63` resets, 16 bad headers lose lock), the gearbox fill `cnt` is always below 66 (it is reduced by 66 as soon as it reaches 66, so bit 7 never sets), and `n` is always even. |
| `b96_pkg.sv` 18-25 (`rxv_pos`, `rxv_count`) | 4 line, 4 branch | **not in this bench's hierarchy** | These are used by `rx_path.sv` and `b96_core.sv` (and, as constants, at elaboration), not by the PCS or MAC. They are covered by whichever bench runs the core, not here. |
| `b96_pkg.sv` 34-35 (`t_term` case arms), 79, 83, 89, 95, 113, 114, 118, 122, 123, 142, 143 (the `if (...) return ...;` arms of `enc66` and `dec66`) | 8 line, 11 branch | **Verilator reporting artefact** | The arm of an `if` that ends in `return` is counted 0 although it runs. `return_arm_artifact/t.sv` shows it in 15 lines: `a == 1` returns 1 (printed) and the `if` arm's count is 0. The bench proves these arms run: `dec66`'s `sh == 2'b01` arm is every data block, 198 thousand of which the scoreboard compared with no mismatch. |
| `b96_pkg.sv` 82, 119, 124 (expression points in loops) | 5 expression | **Verilator reporting artefact, probable** | `return_arm_artifact/t2.sv`: a ternary in a loop in a function reports both expression outcomes 0 while the branch counter of the same ternary counts 5 and 3. `code == 7'h00` on line 119 and 124 certainly has both outcomes (idle blocks and error blocks are both decoded). Line 82 is the same construct; I have not shown independently that its error-character outcome occurs, so it stays listed as open. |

So of the points open at the end, none is a plain stimulus gap that the bench could close without a new check (underrun), and the lines that look uncovered in `b96_pkg` are mostly an engine artefact. **The floors** in the testplan item `V-COV-CODE` are the measured design-wide percentages rounded down (81, 85, 92, 96): a regression gate that fails if a change to the bench or RTL makes coverage drop, not a claim that the remaining percentages are the target.

## Verilator against Icarus (the second engine)
Same bench, same 42 (test, seed) runs. Measured by `icarus_vs_verilator.txt` and the records in `before_added_stimulus/`:
- **Same results.** The simulated time of every run is identical to the nanosecond, the scoreboard comparison totals are identical, and the merged functional-coverage hit counts (`coverage_merged.tsv`) are byte-identical (before the added stimulus, against `results/123_pyuvm_pcs_mac/`).
- **Faster to run, slower to build.** The 42 runs took 186 s of simulator wall time on Verilator against 538 s on Icarus (2.9 times, `icarus_vs_verilator.txt`, same final stimulus); the build took 15.6 to 17.6 s (two builds) against 0.1 s.
- **Verilator needs flags Icarus does not.** `--timing` (the bench awaits `RisingEdge`; the top has `timescale` delays) and `-Wno-fatal`: the RTL has no `timescale` and the bench top does, which is a fatal TIMESCALEMOD warning. With `-Wall` there are 5 TIMESCALEMOD, 3 UNUSEDPARAM and 2 UNUSEDSIGNAL warnings and no others.
- **Version.** cocotb 2.0.1 supports Verilator 5.036 or newer; Ubuntu's package is 5.020, so CI (apt) cannot run this; the repo's machine has 5.048 under `~/.local/opt`. The Verilator coverage run is therefore by hand, not in CI.
- **Two-state.** Verilator has no X or Z. The bench already avoids reading unresolved values (it skips the first edge); nothing differed. The one place a difference would show is reset-time X propagation, which this bench does not test.
- **Coverage reporting quirks** (above): early-`return` arms report 0, and expression points in loops inside functions report 0.
- **Not repeated on Verilator:** the 17-mutant run (brief 123's 16 of 17 stands for Icarus), the `PYUVM_WAVES` waveform path, concurrent SVA.

## Illustrative or not measured
Code coverage describes this bench's stimulus against these four modules and the package, not the design in the larger core: `b96_core`, `trade64`, `rate_match*` are not in scope. A high percentage shows the code ran, not that it was checked; the checking is the scoreboard and the mutants. Toggle coverage here counts a bit as covered when it has moved in both directions, so it is a measure of datapath activity, not of correctness. Nothing ran on a board.
