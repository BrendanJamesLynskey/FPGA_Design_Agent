# Results: the on-chip AXI transactor and protocol checker

Measured results for the on-chip AXI transactor, protocol checker and scoreboard: board runs on a Nexys A7-100T, a
bounded formal check of the checker, its resource cost, and a build test of the AMD AXI IP cores it was compared with.
Method and terms: [docs/axi_tx.md](../../docs/axi_tx.md).

Reproduce the simulation and formal parts (no board): `python -m pytest -q axi_tx/tests/test_59a_rtl.py && python axi_tx/formal/run_formal.py`.

Rule names used below: B_EARLY = a write response sent before its write data arrived; R_HOLD = read data changed while
the master was not ready; EXOKAY = an exclusive-access response, which AXI4-Lite does not allow; AW_HOLD, W_HOLD,
AR_HOLD = a request dropped or changed before it was accepted; IN_RESET = a VALID high while reset is held; HOLD
(stream) = stream data changed while the receiver was not ready.

## On the board (Nexys A7-100T, xc7a100tcsg324-1, Vivado 2026.1)

17 of 17 runs passed. The runs and what each must show were written in a plan before the board was used ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml)); a run passes when its verdict is the one the plan expects ([board_run.json](board_run.json)). Build ID `44b780c9` (read back over JTAG before the runs: matched), build stamp `19a86593`, built from commit `e562dd3`. A build of this pull request (checked at commit `ad99917`) gives build ID `94eca24c`, because build inputs changed after the board run, though no logic did ([board_build.json](board_build.json), [earlier attempts](board_run_attempts.md)).
Operating conditions: inside the recommended operating conditions at every sample (JTAG XADC before and after, fabric XADC with its min/max and latched alarms after every run).

Earlier attempts, before this plan's final run, are listed in [board_run_attempts.md](board_run_attempts.md): the model and the RTL were changed after them, and the whole plan was then run again on the final build.

| Run | Pass | Transactions | Rules fired (episodes) | Scoreboard checked / mismatched | Stream receiver: packets, TLAST mismatches | AMD checker (AXI4-Lite) | Same digest and cycle count as simulation |
|---|---|---|---|---|---|---|---|
| bram_random_rw #0 | yes | 432 | none | 107 / 0 | 0, 0 | quiet | not compared (vendor IP on the board) |
| bram_random_rw #1 | yes | 432 | none | 107 / 0 | 0, 0 | quiet | not compared (vendor IP on the board) |
| bram_random_rw #2 | yes | 432 | none | 107 / 0 | 0, 0 | quiet | not compared (vendor IP on the board) |
| bram_strobes #0 | yes | 48 | none | 16 / 0 | 0, 0 | quiet | not compared (vendor IP on the board) |
| periph_regs #0 | yes | 105 | none | 32 / 0 | 0, 0 | quiet | yes |
| periph_regs #1 | yes | 105 | none | 32 / 0 | 0, 0 | quiet | yes |
| periph_regs #2 | yes | 105 | none | 32 / 0 | 0, 0 | quiet | yes |
| periph_regs_b_early #0 | yes | 105 | B_EARLY 8 | 32 / 0 | 0, 0 | asserted | yes |
| periph_regs_r_live #0 | yes | 105 | R_HOLD 4 | 32 / 0 | 0, 0 | asserted | yes |
| periph_regs_r_glitch #0 | yes | 105 | R_HOLD 31 | 32 / 0 | 0, 0 | asserted | yes |
| periph_regs_exokay #0 | yes | 105 | EXOKAY 8 | 24 / 0 | 0, 0 | asserted | yes |
| periph_regs_no_strb #0 | yes | 105 | none | 32 / 8 | 0, 0 | quiet | yes |
| master_inject #0 | yes | 48 | AW_HOLD 2, W_HOLD 2, AR_HOLD 2 | 0 / 0 | 0, 0 | asserted | yes |
| stream_packets #0 | yes | 12 | none | 0 / 0 | 30, 0 | quiet | yes |
| stream_packets #1 | yes | 12 | none | 0 / 0 | 30, 0 | quiet | yes |
| stream_packets_lose_last #0 | yes | 12 | none | 0 / 0 | 18, 12 | quiet | yes |
| stream_packets_keep_wire #0 | yes | 12 | HOLD 22 | 0 / 0 | 30, 0 | quiet | yes |

- Data bugs are caught by the data checks, not by a rule: `periph_regs_no_strb` by the scoreboard, `stream_packets_lose_last` by the stream receiver's TLAST check.
- The digest covers the AXI4-Lite transactions, latency included. Runs against our own peripheral and FIFO use the same RTL in simulation and on the board, so their digests must be equal; the stream runs are also compared counter by counter. Runs on target `bram` use a vendor block-RAM controller IP core on the board and a memory model in simulation, so only their transactions and verdicts are compared (with the model), not their timing.
- AMD's AXI Protocol Checker watches only the AXI4-Lite bus; on stream runs it can only stay quiet.
- The latency figures on the showcase page come from one run (bram_random_rw #0).

## Formal check of the checker (SymbiYosys, bounded to 20 clock cycles)

A proof passes when no violation of its property is reachable within the depth; it says nothing about longer runs. A mutant (a copy of the checker with one deliberate fault) is killed when at least one proof fails on it.

| Unit | Proofs passed | Mutants killed (structural and semantic) | Of which semantic |
|---|---|---|---|
| axil_rules | 21 of 21 | 37 of 37 | 12 of 12 |
| axis_rules | 11 of 11 | 16 of 16 | 5 of 5 |

Records: [formal.json](formal.json).

## Resource cost (out-of-context synthesis, xc7a100tcsg324-1, Vivado 2026.1)

| Configuration | Top | Generics | LUT | FF | BRAM tiles |
|---|---|---|---|---|---|
| core_full_s32 | axi_tx_core | LCHK=1 SCHK=1 MON=1 SDATA_W=32 | 5307 | 5953 | 3 |
| core_chk_nomon | axi_tx_core | LCHK=1 SCHK=1 MON=0 SDATA_W=32 | 3038 | 2648 | 3 |
| core_bare | axi_tx_core | LCHK=0 SCHK=0 MON=0 SDATA_W=32 | 2513 | 1874 | 3 |
| axil_checker_d32 | axil_checker | DATA_W=32 | 320 | 496 | 0 |
| axil_checker_d64 | axil_checker | DATA_W=64 | 343 | 564 | 0 |
| axis_checker_d32 | axis_checker | DATA_W=32 | 183 | 287 | 0 |
| axis_checker_d64 | axis_checker | DATA_W=64 | 215 | 327 | 0 |
| axis_checker_d128 | axis_checker | DATA_W=128 | 246 | 407 | 0 |
| axil_mon_d32 | axil_mon | DATA_W=32 | 1870 | 2587 | 0 |
| axis_mon_d32 | axis_mon | DATA_W=32 | 427 | 709 | 0 |
| axil_demo_periph | axil_demo_periph | - | 275 | 295 | 0 |
| axis_demo_fifo | axis_demo_fifo | DATA_W=32 | 58 | 13 | 0 |

The full core is 5307 LUTs here; the whole board design used 7043 after implementation, because it adds the demo peripheral, the stream FIFO, the UART shell, the logic analyser, the XADC readout and the vendor IP cores.

A 64-bit stream version is not in the table: synthesis removed part of the sequencer at that width (cause not investigated), so its 1253 LUTs would understate the cost. The core is 32-bit only, and refuses other widths at elaboration. The stand-alone stream checker is measured at 32, 64 and 128 bits.

Records: [resources.json](resources.json).

## AMD AXI IP cores on Vivado 2026.1 (the free licence tier)

| Core | Catalogue entry | Licence needed | Builds (create_ip, synth_ip) | LUT | FF | BRAM tiles |
|---|---|---|---|---|---|---|
| amd_axi_pc | xilinx.com:ip:axi_protocol_checker:2.0 | no | PASS | 545 | 691 | 0 |
| amd_axis_pc | xilinx.com:ip:axis_protocol_checker:2.0 | no | PASS | 74 | 148 | 0 |
| amd_atg | xilinx.com:ip:axi_traffic_gen:3.0 | no | PASS | 4929 | 4245 | 7 |
| amd_bram_ctrl | xilinx.com:ip:axi_bram_ctrl:4.1 | no | PASS | 30 | 12 | 0 |
| amd_bram | xilinx.com:ip:blk_mem_gen:8.4 | no | PASS | 4 | 6 | 2 |

Records: [amd_ip_probe.json](amd_ip_probe.json) from [amd_ip_probe.tcl](../../axi_tx/vivado/amd_ip_probe.tcl).

Every number above is read from a JSON file in this folder by [axi_tx/report.py](../../axi_tx/report.py); the showcase page reads [summary.json](summary.json) and [hero.json](hero.json).


## Records

| File | What |
|---|---|
| `board_run.json` | The final 17-run board plan on the Nexys A7-100T: verdicts, rules fired, scoreboard and stream counters, operating conditions |
| `board_run_build3.json`, `board_run_build2_attempt.log`, `board_run_attempts.md` | The earlier attempts, kept and explained |
| `board_build.json` | The Vivado 2026.1 build record of the board design |
| `sim/` | The simulation record of each program (one JSON per program, including a memory mutant) the board runs are compared with |
| `formal.json` | SymbiYosys proofs and mutant kills for the two checker units |
| `resources.json` | Out-of-context synthesis of the transactor, checkers, monitors and demo blocks |
| `amd_ip_probe.json` | Build test of the AMD AXI IP cores |
| `false_fire.json` | Legal-but-unusual traffic scenarios the checker must stay quiet on (none fired) |
| `e2e_showcase.json` | Browser checks of the showcase page (layout, overlaps, animation start) |
| `summary.json`, `hero.json`, `page_data.json` | The numbers the showcase page reads, derived by `axi_tx/report.py` |

## Reproduce

- Simulation and formal (no board): `python -m pytest -q axi_tx/tests/test_59a_rtl.py && python axi_tx/formal/run_formal.py`.
- Board run (needs the Nexys A7-100T, the board lock and a built bitstream, SRAM only):
  `python3 axi_tx/host/run_board.py --plan axi_tx/programs/board_plan.yaml --json results/59a_axi_tx/board_run.json`.
- The Vivado builds and the AMD IP probe (`axi_tx/vivado/amd_ip_probe.tcl`) need a heavy slot; the page numbers are derived from these records by `axi_tx/report.py`.

## Known gaps and limits

- One board, one build per plan run; the plan was written before the board was used, but earlier attempts led to model and RTL changes and the whole plan was re-run.
- The board design has the build ID `44b780c9`; a rebuild at the commit of this folder gives another ID because build inputs changed, not logic.
- Digests and cycle counts are compared with simulation only where the RTL is the same on both sides; `bram` runs use vendor IP on the board and a memory model in simulation.
- AMD's checker watches only AXI4-Lite; which of its status bits fired was not recorded.
- The formal checks are bounded to 20 cycles. The 64-bit stream core is not in the resource table (cause of the removed sequencer not investigated); the core is 32-bit only.
- The latency figures on the showcase page come from one run.
