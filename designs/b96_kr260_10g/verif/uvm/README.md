# UVM 1.2 bench for the b96 PCS and MAC (brief 112)

The project's first UVM environment: agents, reference models, a scoreboard, directed and constrained-random sequences, functional coverage, SVAs bound
into the RTL, a one-command regression with a coverage merge across seeds, and a set of seeded bugs the bench must catch. It verifies the 64B/66B PCS
(`pcs_tx.sv`, `pcs_rx.sv`) and the 64-bit MAC (`mac64_tx.sv`, `mac64_rx.sv`) of `designs/b96_kr260_10g`, as the RTL is on main, in the **xsim of Vivado
2026.1 (the version the repo pins), which ships UVM 1.2**. There is no GT model in it: the GTHE4 simulation model is refused by the Basic simulator
(`results/56a_serdes/xsim_refusal.txt`), so a small bit-level channel stands in for the transceiver. Before this the design was verified with cocotb
(Python) against a Python model and with formal equivalence; this bench adds a second, independent reference written in SystemVerilog and the UVM
machinery an interviewer or a team lead will recognise. The numbers are in `results/112_uvm_pcs_mac/`.

## Structure

```
 usr_agent ----> mac64_tx --xm--> [mux <- xg_agent (direct XGMII words)] --p--> pcs_tx --TXDATA--+
 (frames)                                                                                          |
 line_agent (loopback: faults)  ---------------- line_channel <-------------------------------------+
 line_agent (line mode: its own 66B stream) ----> (bit FIFO: slips, bit flips, bad headers)
                                                        |  RXDATA
                                          rx_agent <--- pcs_rx ---> mac64_rx ---> frames (rx_agent monitor)
 monitors ---> scoreboard (ref_tx_pcs, ref_rx_pcs, ref_mac_rx) + coverage;   SVAs bound into the four RTL modules
```

| Part | File | What it does and why |
|---|---|---|
| top | `tb/tb_uvm_top.sv` | the DUT chain on one 161.13 MHz clock, the XGMII injection mux, the interfaces; no GT model |
| interfaces | `tb/pcs_mac_ifs.sv` | `sys_if` (clock, resets, mode, initial bit offset), `usr_if`, `xg_if`, `line_if`, `rx_if`, each with a clocking block |
| channel | `tb/line_channel.sv` | the stand-in for the GT link: a bit FIFO with single-bit insert and delete (a slipped alignment), an initial bit offset, a word XOR mask (bit errors) and a sync-header corruptor |
| usr agent | `env/pcs_mac_agents.sv` | driver offers a frame word by word to `mac64_tx` (stable until `s_ready`, back to back or with a gap, a poisoned FCS, noise on `s_poison`); monitor rebuilds the frames the MAC took |
| xg agent | same | driver injects XGMII words straight into `pcs_tx` (lane-4 starts, error characters, ordered sets, malformed words, a frame cut short); monitors tap the MAC output and the PCS input |
| line agent | same | the GT-side agent. In loopback mode it injects faults (bit flips, header bursts, slips, receive resets, a bit-error rate). In line mode it drives **its own 66B stream** from raw blocks (any block type, any sync header, scrambled by its own scrambler), so receive paths the real transmitter never produces are reachable |
| rx agent | same | passive: `pcs_rx` outputs every clock; `mac64_rx` frames (words to a frame, verdict at `m_end`, abort at `m_err`) |
| reference models | `ref/pcs_ref_pkg.sv` | `ref_tx_pcs`, `ref_rx_pcs`, `ref_mac_rx`, block encode and decode, CRC-32, XGMII frame builders; see below |
| scoreboard | `env/pcs_mac_scoreboard.sv` | five checks (TXMAC, TXPCS, RXPCS, RXMAC, E2E), paired by clock number |
| coverage | `env/pcs_mac_cov.sv` | six covergroups and a mirror that makes them mergeable; see below |
| sequences | `env/pcs_mac_seqs.sv` | `vseq_base` helpers and eleven directed scenarios plus a constrained-random mix, run on the virtual sequencer `pcs_mac_vsqr` |
| tests | `tests/pcs_mac_tests.sv` | thirteen tests (`+UVM_TESTNAME=t_...`), each = a mode, an initial offset and one virtual sequence |
| assertions | `sva/pcs_mac_sva.sv` | SVAs on the interface of each RTL module, attached with `bind` (the RTL is not edited) |
| mutants | `mutants/mutants.tsv`, `scripts/mutate.py` | the seeded bugs, applied to a copy of the RTL |
| regression | `scripts/run_regress.sh`, `uvm_build.sh`, `cov_merge.py` | build, run, merge, summary |

### The scoreboard's five checks

A DUT output sampled at clock n+1 is paired with the model's result for the inputs sampled at clock n.

| Check | Compares | Against |
|---|---|---|
| TXMAC | the MAC's output words, from the start character to the terminate, word for word; the interframe gap in bytes | the words `ref` builds from each frame the user offered (preamble, SFD, data, FCS or a deliberately bad FCS, terminate, idles) |
| TXPCS | `TXDATA`, clock for clock, and the pause strobe `adv` | `ref_tx_pcs` fed the XGMII words `pcs_tx` was offered |
| RXPCS | `lock`, `x_v`, `x_d`, `x_c`, `x_os` and the six event pulses, clock for clock | `ref_rx_pcs` fed the words `pcs_rx` captured |
| RXMAC | the frames `mac64_rx` reports (bytes, length, FCS verdict), in order, and the number of aborted frames | `ref_mac_rx` fed the *reference* PCS's outputs |
| E2E | on a clean channel only: the frames received are the frames sent, FCS verdict equal to "not poisoned" | the sequence's own list |

The first four are model checks that hold under any fault; E2E is the loopback self-consistency a PCS talking to itself would pass even with a
symmetric mistake. Seeded bugs M07 and M08 below are exactly that kind, and E2E does not see them.

### Why the reference is independent of the RTL

`ref/pcs_ref_pkg.sv` imports nothing from `b96_pkg`. The scrambler is bit by bit (the RTL's is a 64-bit parallel expression), the CRC is bit by bit
(reflected, 0xEDB88320), the block tables and the decoder are written again from the block formats, and the frame builders and the frame parser work on
bytes. The receive PCS and MAC models are cycle models, ports of `model/pcs.py` (the earlier Python reference) to SystemVerilog, so they carry that
model's reading of the clause 49 block-lock diagram (64 valid headers to lock, 16 invalid in 64 to lose it, one bit slip on failure, the block formed
before the slip takes effect ignored). It is the same author's reading, not the standard's text, which was not available: only a network card closes
that (see the design README). Two places where the RTL is deliberately narrower than the Python model are followed as the RTL states them:
`pcs_tx` encodes neither a lane-4 start nor an ordered set (both become the all-error block), so lane-4 frames reach the receiver only through the line agent.

## Tests

| Test | Mode | What it does |
|---|---|---|
| `t_smoke` | loopback | minimum, maximum, back-to-back and poisoned frames; end to end |
| `t_lens` | loopback | lengths 60 to 99 and every residue mod 8, 127 to 9000 bytes |
| `t_gaps` | loopback | gaps from 0 to 520 idle clocks, random lengths, a long gap after a minimum frame and after a jumbo |
| `t_badfcs` | loopback | poisoned frames, random patterns, noise on `s_poison` for non-last words |
| `t_xg` | loopback | XGMII injection: lane-0 and lane-4 frames, every terminate lane, error characters, a cut frame, a second start, a lone terminate, start then terminate, ordered sets, malformed control vectors, and 32 frames whose FCS error moves the CRC residue in exactly one bit position each (kills a receiver whose FCS compare ignores a residue bit) |
| `t_line_blocks` | line | raw blocks: frames in both start lanes, the four ordered-set types, all-error and unknown-type blocks, single bad sync headers, terminate-only blocks, a second start, and a lock loss **while a frame is in progress** |
| `t_hdr` | loopback | isolated and bursts of corrupted sync headers (15 is the limit, 16 and more lose lock), sparse corruption, recovery |
| `t_slip` | loopback | single-bit slips mid-stream, hunting until the receiver finds the alignment again |
| `t_ber` | loopback | random bit errors at 20 to 30000 ppm, then recovery |
| `t_rxreset` | loopback | receive reset in the middle of frames |
| `t_offsets` | loopback | 15 start-up bit offsets: lock acquisition from every alignment class |
| `t_rand` | loopback | constrained-random mix (frames of all sizes, gaps, flips, header bursts, slips, XGMII injection, resets, error rates), random start-up offset |
| `t_rand_line` | line | the same mix on the line agent's own block stream |

Seeds are recorded: every run's `+SEED` and xsim's `-sv_seed` are in `results/112_uvm_pcs_mac/results.tsv`; rerunning a (test, seed) pair repeats it.

## Coverage

Six covergroups (`frame`: length class, length mod 8, FCS good or bad, payload pattern, gap class, length by FCS; `ifg`: interframe gap class and
terminate lane; `rxf`: start lane, terminate lane, outcome, start lane by terminate lane; `block`: the 16 block kinds; `error`: 11 error kinds from sync
errors to aborted frames to injected faults; `lock`: acquire, loss with the line idle, loss with a frame in progress, hunting slip, re-lock, hunting slips
before the first lock, the three lock transitions). They are standard SystemVerilog covergroups over enum-typed sample variables.

**Vivado 2026.1 Basic refuses `xcrg`**, the coverage report and merge tool (`results/112_uvm_pcs_mac/xcrg_refusal.txt`: "The Vivado Simulator license tier,
BASIC, does not meet the requirement to run xcrg"). xsim itself writes its database and `get_inst_coverage()` works at run time, but the bins cannot be read
back or merged. So every sample also increments a mirror counter keyed by point and bin name; each run writes them to a text file, and
`scripts/cov_merge.py` merges the files of all seeds and writes the report with the holes. xsim's own percentages are printed per run as a cross-check
(they track the mirror's, but are not mergeable). The interframe gap by terminate lane cross was dropped: the MAC's gap is `8(m+1) - k` bytes for terminate
lane k and m idle words, so most of that cross cannot happen.

Merged over the 42 runs of the final regression (`results/112_uvm_pcs_mac/coverage_report.md`): **213 of 213 bins hit, no open holes, nothing waived**.

| coverage point | bins | hit | waived | hit of all | hit of reachable |
|---|---|---|---|---|---|
| block.kind x lock | 32 | 32 | 0 | 100.0 % | 100.0 % |
| block.kind | 16 | 16 | 0 | 100.0 % | 100.0 % |
| error.kind | 11 | 11 | 0 | 100.0 % | 100.0 % |
| frame.fcs | 2 | 2 | 0 | 100.0 % | 100.0 % |
| frame.gap | 6 | 6 | 0 | 100.0 % | 100.0 % |
| frame.len x fcs | 16 | 16 | 0 | 100.0 % | 100.0 % |
| frame.len x gap | 48 | 48 | 0 | 100.0 % | 100.0 % |
| frame.len | 8 | 8 | 0 | 100.0 % | 100.0 % |
| frame.mod8 | 8 | 8 | 0 | 100.0 % | 100.0 % |
| frame.pat | 5 | 5 | 0 | 100.0 % | 100.0 % |
| ifg.bytes | 6 | 6 | 0 | 100.0 % | 100.0 % |
| ifg.tlane | 8 | 8 | 0 | 100.0 % | 100.0 % |
| lock.event | 5 | 5 | 0 | 100.0 % | 100.0 % |
| lock.hunt_slips_before_first_lock | 4 | 4 | 0 | 100.0 % | 100.0 % |
| lock.transition | 3 | 3 | 0 | 100.0 % | 100.0 % |
| rxf.outcome x slane | 6 | 6 | 0 | 100.0 % | 100.0 % |
| rxf.outcome | 3 | 3 | 0 | 100.0 % | 100.0 % |
| rxf.slane x tlane | 16 | 16 | 0 | 100.0 % | 100.0 % |
| rxf.slane | 2 | 2 | 0 | 100.0 % | 100.0 % |
| rxf.tlane | 8 | 8 | 0 | 100.0 % | 100.0 % |

This says every bin I defined was reached, not that the design is fully verified: the bins are my choice and were refined while the bench was built (the first
merge, over 15 runs, had 7 open holes among 127 bins; the final set has 213 bins). Things the bins do not measure, which are the real holes: statement, branch and
toggle coverage of the RTL (needs `xcrg`, refused); the gearbox phase (0 to 32) at which a frame starts; the position of an ordered set or an error character
inside a frame; the spacing of corrupted sync headers other than consecutive runs and a few regular strides; a lock loss in the flush state of `mac64_rx` (reached
by one directed pattern that is probabilistic over the lock window's phase); and any case that needs two clocks (a ppm offset, an elastic buffer).

## Assertions

`sva/pcs_mac_sva.sv`, bound with `bind pcs_tx`, `bind mac64_tx`, `bind pcs_rx`, `bind mac64_rx`: the pause is one clock in 33 and exactly 32 clocks
apart; `s_ready` only while `adv`; the source holds a word stable until `s_ready`; no underrun; `sop` comes with a start character in lane 0, `eop` with a
terminate; `x_v` only with lock one clock earlier; `ev_lock` with lock, `ev_loss` with no lock and a slip, a rising lock with `ev_lock`, a falling lock with
`ev_loss` or a reset; `m_nb` in 1 to 8; `m_sof` with `m_v`. A failure is a `UVM_ERROR`, so the test fails. Two of the first versions were wrong and the bench caught
them (a frame's `m_end` and the next frame's `m_err` legitimately share a clock; the lock also falls on a reset): they are kept as comments in the file. xsim does
not run the action of a `cover property`, so covers are written as `assert property (not (...)) else count++` and printed at the end ("SVA_COV" lines).

## Seeded bugs

`mutants/mutants.tsv` lists sixteen bugs, applied to a copy of the RTL (never the design's own files) by `scripts/mutate.py`; each edit must match exactly once, so
an RTL change that moves a target breaks the mutant loudly. `run_regress.sh --mutants` builds each and runs the tests in a fixed order until one fails.

| Id | What the bug does | Result | Killed by | Checks that fired |
|---|---|---|---|---|
| M01 | poison polarity inverted: good frames get a bad FCS | killed | t_smoke seed 1 | E2E TXMAC |
| M02 | start-of-frame delimiter 0xD4 instead of 0xD5 | killed | t_smoke seed 1 | TXMAC |
| M03 | EQUIVALENT: the dead branch of the gap after a two-word frame end replaced by its live value (cannot be detected) | survived | - | - |
| M04 | interframe gap one word short when the frame ends in the first of its two words | killed | t_lens seed 1 | TXMAC_IFG |
| M05 | frame end with 4 data bytes in the last word is not split over two words | killed | t_smoke seed 1 | E2E SVA TXMAC |
| M06 | gearbox remainder not cleared on the pause clock | killed | t_smoke seed 1 | E2E TXPCS |
| M07 | scrambler tap 38 instead of 39 in the scrambler and the descrambler alike (symmetric: the loopback cannot see it) | killed | t_smoke seed 1 | RXMAC RXPCS TXPCS |
| M08 | terminate-in-lane-3 block type 0xB5 instead of 0xB4, in encoder and decoder alike (symmetric) | killed | t_lens seed 1 | RXMAC RXPCS TXPCS |
| M09 | block lock after 63 valid headers instead of 64 | killed | t_smoke seed 1 | RXPCS |
| M10 | lock lost at the 17th invalid header instead of the 16th | killed | t_line_blocks seed 1 | RXMAC RXPCS |
| M11 | ordered-set event counts unknown block types | killed | t_line_blocks seed 1 | RXPCS |
| M12 | ordered-set type 0x4B not decoded as an ordered set (symmetric table, line-side only) | killed | t_line_blocks seed 1 | RXPCS |
| M13 | a frame is not aborted when block lock drops | killed | t_line_blocks seed 1 | RXMAC |
| M14 | lane-4 frame flush word one byte too long | killed | t_line_blocks seed 1 | RXMAC |
| M15 | FCS check ignores the top residue bit (a subtle one) | killed | t_xg seed 1 | RXMAC |
| M16 | lane-4 start detected with the wrong control vector (line side only) | killed | t_line_blocks seed 1 | RXMAC |
| M17 | mac64_tx ignores the PCS pause: its state advances on the clock the gearbox takes no word | killed | t_smoke seed 1 | E2E TXMAC |

**16 of 17 killed.** M03 is an equivalent mutant: in `mac64_tx.sv` the expression `(n + 4 - 8 > 4)` cannot be true (n is at most 8), so the branch it guards is dead
RTL and replacing it by its live value changes nothing; it is listed to show the bench does not claim kills it cannot make. Two kills were earned by improving the
bench after the first full mutant run: M13 (no abort on lock loss) survived until a directed pattern put the lock loss in the one clock where that RTL branch is not
made redundant by the error word the bad header delivers (the flush state of a lane-4 frame ending in lane 5, 6 or 7: the branch is otherwise dead), and M15 (the
FCS check ignoring the top residue bit) survived until a test produced FCS errors that move the residue in exactly one bit position. M07 and M08 are *symmetric*
errors (the same wrong table or tap in the transmit and the receive half): the loopback end-to-end check does not fire for them, the reference models do. The first lines
of the errors that killed each mutant are in `results/112_uvm_pcs_mac/mutant_kills.txt`.

## Reproduce

```
cd <repo root>
designs/b96_kr260_10g/verif/uvm/scripts/run_regress.sh --out /tmp/uvm112 --mutants --record results/112_uvm_pcs_mac     # everything, 45 to 60 minutes (the last full run took 56)
designs/b96_kr260_10g/verif/uvm/scripts/run_regress.sh --quick                                                          # one seed per directed test, 3 random seeds
designs/b96_kr260_10g/verif/uvm/scripts/uvm_build.sh /tmp/b && cd /tmp/b && \
  xsim pcs_uvm -runall -sv_seed 7 -testplusarg UVM_TESTNAME=t_rand -testplusarg SEED=7                                    # one test, one seed
python -m pytest -q designs/b96_kr260_10g/tests/test_b96_uvm.py                                                           # CI-safe checks (+ a smoke run if xsim exists)
```

Needs Vivado 2026.1 (`$HOME/Xilinx/2026.1/Vivado/settings64.sh` or `$XSIM_SETTINGS`); the Basic tier is enough. CI has no Vivado, so CI does not run the bench:
`tests/test_b96_uvm.py` runs there and checks that every mutant still applies to the RTL exactly once, and runs the smoke test only where xsim is present.
A run is a simulation of about 225 MB for 5 to 15 seconds; a build is about 45 seconds. The regression waits while the 1-minute load is 6 or more or less than 12 GB is free
(the owner's rule for simulation-only runs).

## Records

`results/112_uvm_pcs_mac/`: `results.tsv` (every run, with its seed), `summary.txt`, `scoreboard_totals.tsv`, `coverage_report.md`, `coverage_merged.tsv`,
`sva_cover.tsv`, `mutants.tsv`, `mutant_kills.txt` (the first errors of each killing run), `timing.txt`, `example_run_t_smoke_seed1.log`, `xcrg_refusal.txt`.

## Known gaps and limits

- **One reading of the standard.** The reference receiver and its block-lock FSM are a port of `model/pcs.py`, the same author's reading of clause 49 (standard text unavailable). A symmetric misreading shared by the RTL, the Python model and this port would pass; only a network card proves interoperability.
- **Scope.** Four modules: `pcs_tx`, `pcs_rx`, `mac64_tx`, `mac64_rx`. Not covered: `b96_core`, `trade64`, `rate_match*`, `es_ctrl`, the host registers. One clock for both halves: no ppm offset, no clock-domain crossing, no elastic buffer. The GT is a bit-level channel, not the GTH: no real PMA behaviour.
- **Behaviours as the RTL states them.** `pcs_tx` encodes neither a lane-4 start nor an ordered set (both become the error block), so lane-4 frames and ordered sets reach the receiver only through the line agent's own stream, and the transmit side of those is not exercised. `mac64_rx` does not check the preamble, the SFD or runts, and the transmit MAC needs at least 60 bytes from the source: the bench follows that and does not test it.
- **Coverage** is functional only; its bins are mine; xsim's own covergroup database could not be read or merged (Basic refuses `xcrg`), so the merge uses a mirror of the bins whose agreement with xsim's covergroups is shown only by the percentages printed per run, not bin by bin. No code coverage exists. The real holes are listed above.
- **Mutants** are sixteen hand-picked bugs plus one equivalent: a sample, not a mutation score of the design. The tests that killed M13 and M15 were written after seeing them survive, so those two kills are not blind.
- **Line agent timing.** A fault item takes effect after the blocks queued before it have gone out, within a few blocks; a fault cannot be aimed at an exact bit of a given block, except by building the raw block (line mode). The channel's header corruptor assumes the stream's own 66-bit grid, which is right for both modes and wrong after a slip, by design.
- **Random regression** is ten seeds for each of two tests; the numbers in `results.tsv` are what ran, not a closure argument.
- **Not run in CI**: CI has no Vivado. `tests/test_b96_uvm.py` runs there (mutants apply, files present) and runs the smoke test only where xsim exists.
- **xsim limits.** The Basic tier refuses designs of more than 50000 instances (`results/56a_serdes/xsim_refusal.txt`): this bench is far below that, and that is why the real GTHE4 model is not in it.

## xsim and UVM notes for the next engineer

- xsim 2026.1 ships UVM 1.2 (`-L uvm`, `xlnx_uvm_package.sv`); `xvlog -sv -L uvm -i <dir>` finds `uvm_macros.svh`. A build is dominated by compiling the UVM package (about 45 s).
- `-sv_seed N` seeds `$urandom` and randomisation; the plusargs are `-testplusarg NAME=value`.
- Covergroups and `get_inst_coverage()` work in Basic; `xcrg` does not. `cover property` actions are not executed (hits stay 0); `assert property` pass and fail actions are. `final` blocks work.
- Clocking blocks work. A clocking-block `output` signal cannot be read through the block: declare it `inout` when a monitor shares it (`usr_if`).
- SystemVerilog keywords bite in a class: `buf` is one. A `new` cannot be used inside a `?:` expression. A queue return type needs a typedef.
- The log contains non-UTF-8 bytes: use `grep -a`.
- UVM prints `UVM_ERROR : 0` and `UVM_FATAL : 0` summary lines that start with the same word as a real error: count only lines with ` @ ` in them.
