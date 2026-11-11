# Brief 36 retrieval (written by measure.py)

12 labelled development tasks; catalogue 157 skills (Nexys A7-100T, xc7a100tcsg324-1); index hybrid (BAAI/bge-small-en-v1.5); stale vectors: 0. R2 classifier openai/gpt-6-luna, provider-reported cost $0.0032.

Arms marked * were added after the pre-registered arms were read (post hoc, on the same 12 tasks).

| Arm | recall@3 | recall@6 | recall@10 | MRR |
|---|---|---|---|---|
| T0 | 0.269 | 0.394 | 0.394 | 0.792 |
| T1 | 0.269 | 0.344 | 0.439 | 0.760 |
| R1 | 0.083 | 0.100 | 0.220 | 0.342 |
| R2 | 0.083 | 0.100 | 0.206 | 0.338 |
| I-bm25 | 0.208 | 0.305 | 0.347 | 0.660 |
| I-vec | 0.194 | 0.228 | 0.292 | 0.688 |
| I-hybrid | 0.242 | 0.306 | 0.350 | 0.726 |
| R3* | 0.253 | 0.361 | 0.406 | 0.553 |
| R4* | 0.192 | 0.303 | 0.406 | 0.476 |
| I-hybrid-clean* | 0.242 | 0.289 | 0.364 | 0.711 |

Per task, recall@6 (and first labelled rank):

| Task | T0 | T1 | R1 | R2 | I-bm25 | I-vec | I-hybrid | R3* | R4* | I-hybrid-clean* |
|---|---|---|---|---|---|---|---|---|---|---|
| t1_elevator_fsm | 0.20 (1) | 0.20 (3) | 0.00 (-) | 0.00 (-) | 0.40 (1) | 0.20 (1) | 0.40 (1) | 0.40 (3) | 0.20 (6) | 0.40 (1) |
| t1_sync_fifo_regs | 0.40 (2) | 0.40 (1) | 0.20 (1) | 0.20 (1) | 0.40 (3) | 0.20 (1) | 0.20 (1) | 0.40 (2) | 0.40 (2) | 0.20 (1) |
| t1_debounce_bank | 0.40 (1) | 0.20 (1) | 0.00 (8) | 0.00 (8) | 0.20 (1) | 0.40 (1) | 0.40 (1) | 0.20 (2) | 0.20 (3) | 0.40 (1) |
| t2_i2c_cmd_master | 0.60 (2) | 0.60 (1) | 0.20 (1) | 0.20 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) |
| t2_spi_master_modes | 0.80 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) | 0.60 (1) | 0.40 (1) | 0.60 (1) | 0.80 (1) | 0.80 (1) | 0.60 (1) |
| t2_vga_sprite | 0.60 (1) | 0.60 (1) | 0.20 (3) | 0.20 (3) | 0.40 (1) | 0.40 (1) | 0.40 (1) | 0.40 (1) | 0.40 (1) | 0.40 (1) |
| t2_pdm_vu | 0.20 (4) | 0.20 (1) | 0.00 (9) | 0.00 (9) | 0.40 (1) | 0.20 (1) | 0.40 (1) | 0.20 (2) | 0.20 (2) | 0.20 (1) |
| c10_dds_sine | 0.20 (1) | 0.00 (8) | 0.00 (-) | 0.00 (-) | 0.00 (-) | 0.00 (14) | 0.00 (-) | 0.00 (19) | 0.00 (15) | 0.00 (-) |
| c11_nco_mixer | 0.50 (1) | 0.33 (1) | 0.00 (7) | 0.00 (8) | 0.33 (3) | 0.00 (18) | 0.17 (6) | 0.33 (2) | 0.33 (3) | 0.00 (7) |
| c14_systolic_matmul | 0.50 (1) | 0.67 (2) | 0.00 (7) | 0.00 (7) | 0.00 (7) | 0.00 (8) | 0.17 (2) | 0.50 (2) | 0.17 (5) | 0.33 (3) |
| c16_ntt_engine | 0.17 (1) | 0.17 (6) | 0.00 (8) | 0.00 (9) | 0.00 (9) | 0.00 (-) | 0.00 (20) | 0.17 (4) | 0.00 (9) | 0.00 (18) |
| c9_nexys_vga_720p | 0.17 (4) | 0.17 (1) | 0.00 (8) | 0.00 (9) | 0.33 (1) | 0.33 (1) | 0.33 (1) | 0.33 (2) | 0.33 (2) | 0.33 (1) |

Context per stage-2 role from the knowledge tools (characters):

T0 is what one `load_skill(sections)` call returns after the registry's 20,000-character clip (MAX_OUTPUT); unclipped is the six bodies' full length. The router block is the v2 shortlist (k = 8); the last column adds the bodies of the labelled skills in it (what a role that loads only those would read).

| Task | T0: one load_skill (clipped) | T0 unclipped | router block | block + labelled shortlisted bodies |
|---|---|---|---|---|
| t1_elevator_fsm | 20035 | 28839 | 1772 | 9234 |
| t1_sync_fifo_regs | 20035 | 24107 | 1795 | 10403 |
| t1_debounce_bank | 20035 | 23658 | 1889 | 6214 |
| t2_i2c_cmd_master | 20035 | 21068 | 1813 | 12805 |
| t2_spi_master_modes | 20035 | 23329 | 1867 | 17886 |
| t2_vga_sprite | 20035 | 23541 | 1665 | 13512 |
| t2_pdm_vu | 20035 | 20853 | 1733 | 4206 |
| c10_dds_sine | 20035 | 24517 | 1886 | 1886 |
| c11_nco_mixer | 20035 | 25245 | 1586 | 14207 |
| c14_systolic_matmul | 20035 | 25320 | 1629 | 19464 |
| c16_ntt_engine | 20035 | 23113 | 1586 | 5746 |
| c9_nexys_vga_720p | 20035 | 23329 | 1836 | 9878 |
| **mean** | 20035 | 23909 | 1754 | 10453 |
