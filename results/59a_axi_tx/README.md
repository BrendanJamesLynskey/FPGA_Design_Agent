# Brief 59A: the on-chip AXI transactor, protocol checker and scoreboard

Design and method: [docs/axi_tx.md](../../docs/axi_tx.md). Every number below is read from a JSON file in this folder by
[axi_tx/report.py](../../axi_tx/report.py); the showcase page (site/showcase/axi_transactor.yaml) reads [summary.json](summary.json) and [hero.json](hero.json).

## On the board (Nexys A7-100T, xc7a100tcsg324-1, Vivado 2026.1)

17 of 17 pre-registered runs passed ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml), [board_run.json](board_run.json)); build ID `05236f86`, build stamp `c3ed8fb8`.
Operating conditions: inside the recommended operating conditions at every sample (JTAG XADC before and after, fabric XADC with its min/max and latched alarms after every run).

| Run | Pass | Transactions | Rules fired (episodes) | Scoreboard checked / mismatched | AMD checker | Same digest as simulation |
|---|---|---|---|---|---|---|
| bram_random_rw #0 | yes | 432 | none | 107 / 0 | quiet | not compared (AMD core on the board) |
| bram_random_rw #1 | yes | 432 | none | 107 / 0 | quiet | not compared (AMD core on the board) |
| bram_random_rw #2 | yes | 432 | none | 107 / 0 | quiet | not compared (AMD core on the board) |
| bram_strobes #0 | yes | 48 | none | 16 / 0 | quiet | not compared (AMD core on the board) |
| periph_regs #0 | yes | 105 | none | 32 / 0 | quiet | yes |
| periph_regs #1 | yes | 105 | none | 32 / 0 | quiet | yes |
| periph_regs #2 | yes | 105 | none | 32 / 0 | quiet | yes |
| periph_regs_b_early #0 | yes | 105 | B_EARLY 8 | 32 / 0 | asserted | yes |
| periph_regs_r_live #0 | yes | 105 | R_HOLD 4 | 32 / 0 | asserted | yes |
| periph_regs_r_glitch #0 | yes | 105 | R_HOLD 31 | 32 / 0 | asserted | yes |
| periph_regs_exokay #0 | yes | 105 | EXOKAY 8 | 24 / 0 | asserted | yes |
| periph_regs_no_strb #0 | yes | 105 | none | 32 / 8 | quiet | yes |
| master_inject #0 | yes | 48 | AW_HOLD 2, W_HOLD 2, AR_HOLD 2 | 0 / 0 | asserted | yes |
| stream_packets #0 | yes | 12 | none | 0 / 0 | quiet | yes |
| stream_packets #1 | yes | 12 | none | 0 / 0 | quiet | yes |
| stream_packets_lose_last #0 | yes | 12 | none | 0 / 0 | quiet | yes |
| stream_packets_keep_wire #0 | yes | 12 | HOLD 22 | 0 / 0 | quiet | yes |

The digest is a CRC-32 over every transaction including its latency in cycles. Runs on target `periph` use the same RTL in simulation and on the board, so their digests must be equal; runs on target `bram` use AMD's AXI BRAM Controller on the board and a memory model in simulation, so only their transactions and verdicts are compared (with the model), not their timing.

## Formal proof of the checker (SymbiYosys, bounded, depth 20)

| Unit | Proofs passed | Checker mutants killed |
|---|---|---|
| axil_rules | 19 of 19 | 23 of 23 |
| axis_rules | 11 of 11 | 11 of 11 |

Records: [formal.json](formal.json).

## Resource cost (out-of-context synthesis, xc7a100tcsg324-1, Vivado 2026.1)

| Configuration | Top | Generics | LUT | FF | BRAM tiles |
|---|---|---|---|---|---|
| core_full_s32 | axi_tx_core | LCHK=1 SCHK=1 MON=1 SDATA_W=32 | 5291 | 5934 | 3 |
| core_chk_nomon | axi_tx_core | LCHK=1 SCHK=1 MON=0 SDATA_W=32 | 3021 | 2629 | 3 |
| core_bare | axi_tx_core | LCHK=0 SCHK=0 MON=0 SDATA_W=32 | 2520 | 1873 | 3 |
| axil_checker_d32 | axil_checker | DATA_W=32 | 297 | 478 | 0 |
| axil_checker_d64 | axil_checker | DATA_W=64 | 317 | 546 | 0 |
| axis_checker_d32 | axis_checker | DATA_W=32 | 183 | 287 | 0 |
| axis_checker_d64 | axis_checker | DATA_W=64 | 215 | 327 | 0 |
| axis_checker_d128 | axis_checker | DATA_W=128 | 246 | 407 | 0 |
| axil_mon_d32 | axil_mon | DATA_W=32 | 1870 | 2587 | 0 |
| axis_mon_d32 | axis_mon | DATA_W=32 | 427 | 709 | 0 |
| axil_demo_periph | axil_demo_periph | - | 275 | 295 | 0 |
| axis_demo_fifo | axis_demo_fifo | DATA_W=32 | 58 | 13 | 0 |

Not in the table: `core_full_s64` (synthesis trimmed the sequencer at SDATA_W = 64 (not root-caused); 59A's core is 32-bit only; it synthesised to 1253 LUT, which is not a cost).
The stand-alone stream checker is measured at 32, 64 and 128 bits.

Records: [resources.json](resources.json).

## AMD IP on Vivado 2026.1 (BASIC tier)

| Core | Catalogue entry | Licence needed | Builds (create_ip, synth_ip) | LUT | FF | BRAM tiles |
|---|---|---|---|---|---|---|
| amd_axi_pc | xilinx.com:ip:axi_protocol_checker:2.0 | no | PASS | 545 | 691 | 0.0 |
| amd_axis_pc | xilinx.com:ip:axis_protocol_checker:2.0 | no | PASS | 74 | 148 | 0.0 |
| amd_atg | xilinx.com:ip:axi_traffic_gen:3.0 | no | PASS | 4929 | 4245 | 7.0 |
| amd_bram_ctrl | xilinx.com:ip:axi_bram_ctrl:4.1 | no | PASS | 30 | 12 | 0.0 |
| amd_bram | xilinx.com:ip:blk_mem_gen:8.4 | no | PASS | 4 | 6 | 2.0 |

Records: [amd_ip_probe.json](amd_ip_probe.json) from [amd_ip_probe.tcl](../../axi_tx/vivado/amd_ip_probe.tcl).

