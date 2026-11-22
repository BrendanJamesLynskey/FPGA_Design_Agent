# results/158_cov_closure: closing the open coverage points of the b96 PCS/MAC pyuvm bench (brief 158)

Follows brief 146 (`results/146_verilator_cov/`). Three things: the transmit underrun of `mac64_tx` driven under a fault-injection mode of the protocol checker (new test `t_underrun`), the two `mac64_tx` interframe-gap conditions that 146 classified as unreachable checked by SymbiYosys, and the 17-mutant set run on Verilator as a second engine's kill record. No RTL file was changed.

## Reproduce
```
source ~/.local/opt/verilator-5048/env.sh
export PYTHONPATH=. SIM=verilator PYUVM_COV=1
PY=~/.local/opt/verif-venv/bin/python
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/v158 --record results/158_cov_closure     # 44 runs; build about 17 s, 162 s of simulator time
verilator_coverage --write /tmp/v158/merged.dat /tmp/v158/runs/*/coverage.dat
verilator_coverage --write-info results/158_cov_closure/coverage_lcov.info /tmp/v158/merged.dat
$PY designs/b96_kr260_10g/verif/pyuvm/scripts/cov_report.py /tmp/v158/merged.dat results/158_cov_closure designs/b96_kr260_10g
# mutants on Verilator (build per mutant; coverage off):
SIM=verilator PYTHONPATH=. $PY designs/b96_kr260_10g/verif/pyuvm/scripts/run_regress.py --out /tmp/v158m --mutants-only --record /tmp/v158m_rec    # 418 s
bash designs/b96_kr260_10g/verif/formal/run_ifg_formal.sh /tmp/ifg                                                                                  # a few seconds (OSS CAD Suite 2026-11-12)
```
The Verilator build and the mutant builds are heavy jobs on the shared machine (heavy slot, `systemd-run --scope -p MemoryMax=8G`).

## Records
- `summary.txt`, `results.tsv`, `scoreboard_totals.tsv`, `protocol_cover.tsv` (with `underrun_injected`), `coverage_report.md`, `coverage_merged.tsv`: the 44-run regression and its functional coverage, in the format of `results/146_verilator_cov/`.
- `coverage_summary.json`, `coverage_by_module.md`, `uncovered.tsv`, `coverage_lcov.info`, `verilator_coverage_summary.txt`: code coverage (the testplan item `V-COV-CODE` reads the JSON).
- `mutants_verilator.tsv`, `summary_mutants_verilator.txt`: the 17 seeded bugs on Verilator; compare `results/123_pyuvm_pcs_mac/mutants.tsv` (Icarus).
- `formal/`: the SymbiYosys logs (`unreach_cover.log`, `unreach_prove.log`, `reach_cover.log`, and the planted control `control_n_plus_2_*.log`).

## 1. The underrun (`t_underrun`)
**What the RTL does** (`mac64_tx.sv`, the `!s_valid` arm of `S_DATA`, read before any test was written): the start word has gone out, the whole data words the MAC had taken have gone out; on the first clock with `adv` high at which `s_valid` is low and no word is offered, it puts out **one word of eight error characters (0xFE, control mask 0xFF)**, raises `underrun` for one clock, and goes to the gap state: one idle word, then idle, where a new `s_valid` starts the next frame. There is no FCS, no terminate, and `eop` stays low. This is a sensible abort (a frame with error characters and no terminate is what a receiver discards), not a frame sent as if good, so no RTL question arises and nothing was changed; the latency figures are unaffected.

**What was added.**
- Checker: `ProtocolChecker.inject_underruns(n)` is the explicit fault-injection mode. Outside it `no_underrun` is unchanged. Inside it an underrun is allowed while the budget lasts (`underrun_only_when_injected`) and all injected ones must have been seen at the end (`injected_underruns_seen`).
- Scoreboard rule (`TXMAC`): a frame the source abandoned after k whole words must appear as start word, the k words, the error word (`refmodels.abort_words`), and then the gap: the error word counts as 8 byte times and one idle word follows, 16 in all, so the rule that a gap is at least 12 byte times still applies to the next start (`TXMAC_IFG`). `RXMAC`: the receiver aborts exactly the injected frames (a new exact count) and the reference receiver and `mac64_rx` agree on every other frame.
- Stimulus (`t_underrun`, 2 seeds, 12 underruns each): stalls 1, 2, 3, 1, 8, 4, 2, 5, 1, 12 words into a frame, then a good or poisoned frame offered at once, two stalls in a row, a 1514-byte and a 61-byte frame, and random frames. The source drops `s_valid` for exactly one clock at which `adv` is high, then raises it for the next frame at once, which tests the gap after an underrun at its minimum.

**Result.** 44 runs (the 42 of 146 and the two `t_underrun` runs): 0 failed, 0 scoreboard mismatches, 0 protocol-checker failures, 217 of 217 functional bins, 24 injected underruns seen (`protocol_cover.tsv`, `underrun_injected`). The 42 earlier runs are identical to 146's (same verdict and the same simulated time in every one). Icarus gives the same simulated time for both `t_underrun` seeds (6640.42 and 6677.66 ns) and the same scoreboard comparison totals (checked for seed 2).

**Does the check bite?** Three planted bugs in a throw-away copy of the RTL, each killed by `t_underrun` seed 1 on Icarus (these are not in the 17-mutant set): the error word replaced by idle characters, `underrun` never raised, and the abort going straight to the idle state (which makes the next frame start one word early, which only the minimum-gap stimulus above can show; with a source that waits for the underrun pulse before offering the next frame, that bug survived, so the driver was changed).

**Coverage** (`coverage_by_module.md`, `coverage_summary.json`):

| design-wide | 146 | 158 |
|---|---|---|
| line | 81.25 % (65/80) | **82.50 % (66/80)** |
| branch | 85.34 % (99/116) | 85.34 % (99/116) |
| expression | 92.47 % (86/93) | 92.47 % (86/93) |
| toggle | 96.33 % (5539/5750) | **96.37 % (5541/5750)** |

`mac64_tx.sv` line 67 (the underrun arm) is closed (mac64_tx line 80 % to 90 %), and the `underrun` register's two toggle points in `mac64_tx` (and two more in the bench top, which is reported apart and was already complete for the other signals). The brief expected 4 toggle points: 2 are in the design, 2 in the bench top's copy of the signal. Open now: 14 line, 17 branch, 7 expression, 209 toggle points, all classified in `results/146_verilator_cov/README.md` (the underrun row there is now closed). **Floors** in the testplan (`V-COV-CODE`): line 81 to 82; branch 85, expression 92 and toggle 96 unchanged (measured values rounded down to whole numbers; none lowered). `V-COV-FUNC` and `V-COV-CODE` read this record now; 146's record is kept as it was.

## 2. The two ifg conditions (SymbiYosys)
`verif/formal/mac64_tx_ifg.sby` with `mac64_tx_ifg_props.sv` (bound, RTL untouched) and `mac64_tx_fv_top.sv`; `formal/*.log` here. OSS CAD Suite 2026-11-12 (the version CI pins): yosys 0.70+385, yosys-slang, boolector.
- `unreach_cover` (cover, depth 12): the true arm of `n + 4 - 8 > 4` at line 76 and the false arm of `n + 4 > 4` at line 79, each together with the state and handshake that lead to the assignment: **both unreached** (`UNREACH_A`, `UNREACH_B`), so no trace exists.
- `unreach_prove` (k-induction): the same two conditions as assertions, and `1 <= n <= 8`: **PASS**. This is the unbounded statement; the covers are bounded to 12 steps, but the conditions depend on `s_nb1` and the state only, so the proof is what carries the claim.
- `reach_cover` (control): the true arm of line 79 and the false arm of line 76, and `n` = 1, 4, 5, 8 at a last word, are reached at step 3: **PASS**, so S_DATA with a last word is reachable and the unreached ones are not unreached for a wrong reason.
- Planted control (`formal/control_n_plus_2_*.log`, also `test_b158_ifg_formal.py`): with `n = s_nb1 + 2` in a copy of the RTL, `UNREACH_A` is reached at step 3 and the proof fails on the range assertion. So the harness can see the condition when it is reachable.
Result: the two conditions are **unreachable by design** (`n` is 1 to 8), not a stimulus gap; the 146 classification stands and is now proved. Brief 112's mutant M03 (the equivalent mutant that replaces the line-76 ternary) is therefore equivalent for the same reason, and survives every run in both engines.

## 3. The 17 mutants on Verilator (second engine)
`mutants_verilator.tsv`, `summary_mutants_verilator.txt`. 16 of 17 killed, M03 survives (equivalent, above), the same as Icarus's record in `results/123_pyuvm_pcs_mac/mutants.tsv`. **All 17 rows agree with Icarus's on the verdict, the first killing test and seed, and the set of checks that fired.** The test order is brief 123's, with `t_underrun` seed 1 appended last (it only changes M03's run count, 15 to 16; no earlier kill moved). Wall time: 173 s of simulator time for the 17 mutants against 427 s on Icarus (2.5 times); 17 Verilator builds took the rest of the 418 s. The blind variant (without 112's two hindsight patterns) was not repeated on Verilator.

## What is illustrative / not measured
Code coverage shows the code ran, not that it was checked; the underrun is checked by the scoreboard rule and the three planted bugs above. The proofs cover `mac64_tx` as an isolated module with free inputs (any source and pause behaviour), not the rest of the design. The 158 coverage run is by hand (Verilator 5.036 or newer is not in CI); the formal check is in CI (job `formal-rate-matcher`, `test_b158_ifg_formal.py`).

## Known gaps and limits
- 14 line, 17 branch, 7 expression and 209 toggle points remain open: unreachable by design, or Verilator reporting artefacts (146's README).
- What a real source does with the remainder of an abandoned frame is outside the MAC; the bench drops it.
- The waveform path and the concurrent SVAs were not repeated on Verilator.
