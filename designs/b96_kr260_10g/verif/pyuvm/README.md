# pyuvm bench for the b96 PCS and MAC (brief 123)

The same verification job as brief 112's SystemVerilog UVM bench (`../uvm/`), done with **pyuvm on cocotb**: same scope (`pcs_tx`, `pcs_rx`, `mac64_tx`, `mac64_rx` on one clock, a bit-level channel in place of the GT), the same thirteen tests' intents, the same seventeen seeded bugs, the same coverage bins, a scoreboard with the same five checks. It runs on Icarus, which the repo already uses for every cocotb bench, so it needs no Vivado licence tier and no xsim; a build takes a fraction of a second. It exists to answer one question with measurements instead of opinion: where does pyuvm fit this project and where does SystemVerilog UVM stay? The answer, the comparison table and a short section for the verification course are in [COMPARISON.md](COMPARISON.md); this file says how the bench is built, how to run it and what it does not do. The numbers are in `results/123_pyuvm_pcs_mac/`.

No RTL file was changed. pyuvm and cocotb-coverage are not dependencies of the repo (`pip install pyuvm==5.0.0 cocotb-coverage`, see Reproduce); CI installs them for one small job (see Reproduce).

## Structure

```
 usr_agent ----> mac64_tx --xm--> [mux <- xg_agent (direct XGMII words)] --p--> pcs_tx --gt_tx_d--+
 (frames)                                                                                           |
 line_agent: Python LineChannel (bit FIFO: offset, slips, bit flips, bad headers)  <-----------------+
 line_agent (line mode: its own 66B stream, own scrambler) ----> LineChannel --gt_rx_d--> pcs_rx ---> mac64_rx
 monitors ---> Scoreboard (RefTxPcs, RefRxPcs, RefMacRx) + cocotb-coverage + ProtocolChecker
```

| Part | File | What it does |
|---|---|---|
| hardware top | `tb/tb_pyuvm_top.sv` | `mac64_tx -> pcs_tx` and `pcs_rx -> mac64_rx` on one clock, the XGMII injection mux, `x_os` exposed; the channel is **not** in the hardware: `gt_rx_d` and the receive reset are inputs driven from Python. Plain Verilog-2012 with no UVM, so Icarus (or Verilator) builds it |
| channel | `pcs_mac_pyuvm/channel.py` | a line-for-line port of 112's `line_channel.sv`: bit FIFO with single-bit insert and delete, start-up bit offset, word XOR mask, header corruptor |
| agents | `pcs_mac_pyuvm/agents.py` | `UsrAgent` (frames into the MAC), `XgAgent` (XGMII words straight into `pcs_tx`), `LineAgent` (faults in loopback, or its own raw 66-bit block stream in line mode), `RxAgent` (passive); drivers, monitors and sequencers are pyuvm's `uvm_driver`, `uvm_monitor`, `uvm_sequencer` |
| items | `pcs_mac_pyuvm/items.py` | `FrameItem`, `XgItem`, `LineItem` (`uvm_sequence_item`) |
| reference models | `pcs_mac_pyuvm/refmodels.py` | see "Which reference" below |
| scoreboard | `pcs_mac_pyuvm/scoreboard.py` | the five checks of 112: TXMAC (+ interframe gap), TXPCS, RXPCS, RXMAC, E2E; one `uvm_subscriber` per stream |
| coverage | `pcs_mac_pyuvm/cov.py` | `CoverPoint` and `CoverCross` decorators of cocotb-coverage, 112's 213 bins plus 4 helper bins |
| protocol checker | `pcs_mac_pyuvm/checker.py` | 18 of 112's SVA implications, hand-translated (Icarus does not run concurrent SVA) |
| sequences | `pcs_mac_pyuvm/seqs.py` | eleven directed virtual sequences and one constrained-random mix |
| env, tests | `pcs_mac_pyuvm/env.py`, `tests/pcs_mac_pyuvm_cocotb.py` | the environment and the thirteen tests (same names as 112's); one cocotb test per UVM test |
| scripts | `scripts/pyuvm_run.py`, `run_regress.py`, `loc_count.py`, `crv_probe.py`, `time_xsim.sh`, `compare_timing.py` | build and run one test; the one-command regression with coverage merge and mutants; the line counts, the probe of cocotb-coverage's constraint solver, the xsim timing of 112's bench over the same runs and the comparison of the two (the comparison's measurements) |
| mutants | `../uvm/mutants/mutants.tsv`, `../uvm/scripts/mutate.py` | **shared with 112, not copied**: the same 17 bugs applied the same way |

### Which reference model, and why

`model/pcs.py` (brief 96), not a second rewrite. 112's SystemVerilog models were themselves a port of that file ("its receive reference shares `model/pcs.py`'s reading of clause 49"), so reusing it here adds no independence from 112 and no new independence from the Python bench of brief 96 either: the reading of clause 49 is still one author's. What `refmodels.py` adds on top of it is what 112 added: `encode_rtl` (`pcs_tx` encodes neither a lane-4 start nor an ordered set, both become the all-error block, `model/pcs.py` encodes S4), `RefRxPcs` (clock by clock, with the six event pulses and `x_os`, which `pcs.RxPcs` keeps only as counters) and `RefMacRx` (frames and aborts with the pipeline delay and the lane-4 flush state, a port of 112's `ref_mac_rx`). The scrambler, the block tables and the decoder are the repo's bit-serial ones, nothing shared with `b96_pkg`'s parallel expressions, so the symmetric bugs M07 and M08 are still seen by the models and not by the loopback.

### Timing idiom

Every component waits for `RisingEdge(clk)` and reads then: cocotb returns the values from just before the edge (what a clocking block's `input #1step` gives in SystemVerilog); drivers write after the edge and the DUT sees the value at the next edge. A DUT output sampled at clock n+1 is the result of the inputs sampled at clock n, as in 112. The first edge is skipped (nothing is driven yet; unresolved values read as 0).

## Tests

Thirteen, same names and intents as 112 (table in `../uvm/README.md`): `t_smoke`, `t_lens`, `t_gaps`, `t_badfcs`, `t_xg`, `t_line_blocks`, `t_hdr`, `t_slip`, `t_ber`, `t_rxreset`, `t_offsets`, `t_rand`, `t_rand_line`. A run is one UVM test with one seed: `SEED` seeds a `random.Random` shared through the ConfigDB (and cocotb's own seed, `COCOTB_RANDOM_SEED`); a (test, seed) pair repeats exactly. The regression is the 112 shape: 11 directed tests over 2 seeds, 2 random tests over 10 seeds = 42 runs.

Random stimulus is plain `random` with weights (frame lengths and gaps, patterns 8:1:1:1:1, poison 10 %, fault mix): pyuvm has no `randomize()` and no constraint solver. `scripts/crv_probe.py` measures cocotb-coverage's `Randomized` (python-constraint) as a stand-in: with one constraint across two fields and the full length domain it takes tens of seconds per call, so the sequences do not use it (numbers in `results/123_pyuvm_pcs_mac/crv_probe.txt`).

## Coverage

`cov.py` expresses 112's points and bins with cocotb-coverage decorators on small sampling functions (`@CoverPoint("frame.len", xf=..., bins=[...])`, `@CoverCross(...)`); bin names are the same strings as 112's, so the two reports line up. Four helper bins are extra: a cocotb-coverage cross can only combine points sampled by one function, so `rxf.slane x tlane` needs `rxf.slane (non-aborted)` and `block.kind x lock` needs `block.lock`. Each simulator process exports its coverage to YAML (`coverage_db.export_to_yaml`); `run_regress.py` merges the 42 files with cocotb-coverage's own `merge_coverage` and writes `coverage_report.md`. Unlike 112 nothing has to be mirrored by hand: the library's database is the one merged. There is **no code coverage** (statement, branch, toggle): Icarus has none and Verilator, which has, is not installed here (see Known gaps).

## Seeded bugs

The 17 bugs of 112 (`../uvm/mutants/mutants.tsv`), each applied to a copy of the RTL and run through the tests in 112's fixed order until one fails; the table is in COMPARISON.md and `results/123_pyuvm_pcs_mac/mutants.tsv`. `PYUVM_BLIND=1` (`run_regress.py --blind`) leaves out the two patterns 112 added after seeing M13 and M15 survive.

## Reproduce

```
# once: a venv that sees the system cocotb 2.0.1 (the repo's version) and adds pyuvm and cocotb-coverage
python3 -m venv --system-site-packages /tmp/v123 && /tmp/v123/bin/pip install pyuvm==5.0.0 cocotb-coverage
cd <repo root>; export PYTHONPATH=.
PY=/tmp/v123/bin/python
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/pyuvm123 --mutants --record results/123_pyuvm_pcs_mac    # the regression and the mutants, about 15 minutes
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/pyuvm123 --mutants-only --blind                       # the mutants without 112's hindsight patterns, about 12 minutes
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/pyuvm123 --quick                                      # one seed per directed test, 3 random seeds
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/pyuvm_run.py build /tmp/b && $PY designs/b96_kr260_10g/verif/pyuvm/scripts/pyuvm_run.py run /tmp/b t_rand 7   # one test, one seed
PYUVM_WAVES=1 ...pyuvm_run.py build / run                                                                                     # a waveform: /tmp/b/tb_pyuvm_top.fst (GTKWave)
python -m pytest -q designs/b96_kr260_10g/tests/test_b96_pyuvm.py                                                              # the CI checks
designs/b96_kr260_10g/verif/pyuvm/scripts/time_xsim.sh /tmp/xsim123                                                         # 112's bench timed in xsim (needs Vivado 2026.1), then scripts/compare_timing.py <results dir>
```

A run takes 3 to 31 seconds of wall time (Python dominates); a build takes 0.1 second. The machine rule for simulation-only runs applies (the regression waits while the 1-minute load is 6 or more or less than 12 GB is free). `pip install` into the system Python is refused by Debian's PEP 668 guard: use the venv.

**CI** (job `rtl-sim`, step "pyuvm bench of the 10G PCS and MAC"): `tests/test_b96_pyuvm.py` installs `pyuvm==5.0.0`, checks the files, that every one of 112's mutants still applies to the RTL, that the reference models agree with `model/pcs.py` and that the channel makes the reference receiver lock and lose lock; builds the bench in Icarus, runs `t_smoke` (every check non-trivial) and requires mutant M01 to be killed. About 8 seconds. The full regression is not in CI: it is 8 minutes for the 42 runs (27 with the two mutant runs) and CI's job here is a gate, not a soak.

## Records

`results/123_pyuvm_pcs_mac/`: `results.tsv` (every run with its seed, wall time and simulated time), `summary.txt`, `scoreboard_totals.tsv`, `coverage_report.md`, `coverage_merged.tsv`, `protocol_cover.tsv`, `mutants.tsv`, `mutants_blind.tsv`, `loc.tsv`, `crv_probe.txt`, `xsim_timing.tsv` and `timing_compare.txt` (112's bench timed in xsim over the same 42-run shape, and the comparison), `first_run/` (the first merge, 215 of 217 bins), `example_run_t_smoke_seed1.log`, `example_kill_M01_t_smoke_seed1.log`, `README.md`.

## Known gaps and limits

- **Same reading of the standard.** The reference receiver is `model/pcs.py`'s, as 112's was; only a network card closes interoperability.
- **Same scope as 112**: four modules, one clock, no GT, no elastic buffer, no ppm offset. Not `b96_core`, `trade64`, `rate_match*`, `es_ctrl`.
- **Icarus only.** Verilator is not installed here (the repo's convention is CI or a local install into `~/.local`) and was not tried; the top is plain Verilog so nothing in the bench should need more than Icarus. Verilator would add line and toggle coverage and real concurrent assertions; that is the obvious next step (see COMPARISON.md).
- **No code coverage and no bound SVAs.** The protocol checker is Python, sampled each clock; it cannot see a glitch between clock edges or an X, and a property written by hand can be wrong in a way a tool would catch (my first version of `adv_rhythm` fired on a mid-run reset, which an SVA's `disable iff` handles for free).
- **Coverage is functional only**, 217 bins (112's 213 plus 4 helpers); the real holes listed in `../uvm/README.md` are real here too (gearbox phase at frame start, position of an ordered set inside a frame, header spacing beyond runs and strides, anything that needs two clocks).
- **The mutant result is not blind.** I wrote these tests having read 112's tests, its mutant list and which ones survived. Both the full-test and the "before hindsight" mutant runs are reported; neither says how an author who had not seen the mutants would have fared.
- **Speed.** About 2.7 ms of wall time per simulated clock at the margin (xsim: 0.29 ms plus a 6.4 s start-up per run; `results/123_pyuvm_pcs_mac/timing_compare.txt`), because every signal read and write goes through the VPI and the models are Python. Fine for this bench (the 42-run regression is 8 minutes), not for a soak of millions of clocks.
- **Line agent timing** is 112's: a fault takes effect after the queued blocks have gone out (a few blocks of slack).
- **pyuvm 5.0.0 subset.** Only what the bench uses was exercised; the register layer (`uvm_reg*`), callbacks and the factory's override calls are present in the package and were **not** exercised.

## pyuvm and cocotb notes for the next engineer

- `pyuvm.uvm_sequence.start_item` needs the sequence to run on one sequencer; a virtual sequence has none (`UVMSequenceError`). Send items to the agents' sequencers directly: `await sqr.start_item(item); await sqr.finish_item(item)` (`seqs.py::VseqBase._send`).
- `run_test` clears the ConfigDB and the factory each call; set configuration in the test's `build_phase` (the cocotb handles go through a module-level `CTX`).
- A class created in a loop needs `__qualname__` set as well as `__name__` for cocotb's test filter (`tests/pcs_mac_pyuvm_cocotb.py`).
- cocotb 2.0.1's runner object keeps build state in memory: in a new process call `build(..., always=False)` before `test(...)` (`pyuvm_run.py::_built`).
- A cocotb-coverage `CoverCross` must be listed **below** the `CoverPoint`s it combines (decorator expressions evaluate top to bottom); constraint lambdas of `Randomized` must name their arguments in alphabetical order.
- Reading a signal that is X raises `ValueError` in cocotb 2: `agents.rd()` reads it as 0 (only before the first reset).
- Coverage in cocotb-coverage is a process-global: run one UVM test per simulator process and merge the YAML files, as `run_regress.py` does.
- The simulator's stdout is the log: every message is `<sim time> <level> <file(line)> [<component path>] <text>`; a failing check prints the first 8 mismatches of that check.
