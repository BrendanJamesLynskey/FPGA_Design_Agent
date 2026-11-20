| job | task | AW | bit | verdict | seconds | failing assertions |
|---|---|---|---|---|---|---|
| safety_prove_aw4_kb0 | safety_prove | 4 | 0 | PASS | 6.9 |  |
| safety_prove_aw4_kb7 | safety_prove | 4 | 7 | PASS | 11.2 |  |
| safety_prove_aw4_kb39 | safety_prove | 4 | 39 | PASS | 9.5 |  |
| safety_prove_aw4_kb63 | safety_prove | 4 | 63 | PASS | 10.7 |  |
| safety_prove_aw4_kb64 | safety_prove | 4 | 64 | PASS | 10.4 |  |
| safety_prove_aw4_kb71 | safety_prove | 4 | 71 | PASS | 10.9 |  |
| safety_prove_aw4_kb72 | safety_prove | 4 | 72 | PASS | 10.2 |  |
| safety_prove_aw4_kb73 | safety_prove | 4 | 73 | PASS | 9.1 |  |
| safety_prove_aw2_kb0 | safety_prove | 2 | 0 | PASS | 32.0 |  |
| safety_prove_aw1_kb0 | safety_prove | 1 | 0 | PASS | 10.8 |  |
| safety_bmc_aw2_kb0 | safety_bmc | 2 | 0 | PASS | 80.6 |  |
| progress_bmc_aw2 | progress_bmc | 2 | 0 | PASS | 164.8 |  |
| cover_aw2 | cover | 2 | 0 | PASS | 12.2 |  |
| mut_overflow | safety_prove | 2 | 0 | CAUGHT | 3.4 | p1_no_overflow, p1b_bound, p2_wview |
| mut_underflow | safety_prove | 2 | 0 | CAUGHT | 1.0 | p4_no_underflow |
| mut_gray_step | safety_prove | 2 | 0 | CAUGHT | 0.9 | h5a_wp_chain_order, p5_gray_w |
| mut_binary_pointer | safety_prove | 2 | 0 | CAUGHT | 1.8 | h5a_wp_chain_order |
| mut_unsynced_pointer | safety_prove | 2 | 0 | CAUGHT | 1.2 | h5a_wp_chain_order, p3_rview |
| mut_wrong_entry | safety_prove | 2 | 0 | CAUGHT | 4.1 | p8a_pop_is_written_bit, p8b_output_is_written_bit |
| mut_insert_in_frame | safety_prove | 2 | 0 | CAUGHT | 6.9 | p6a_insert_idle_only_between_frames |
| mut_delete_in_frame | safety_prove | 2 | 0 | CAUGHT | 7.9 | p6b_delete_only_between_frames |
| mut_delete_any | safety_prove | 2 | 73 | CAUGHT | 7.3 | p7b_delete_only_flagged |
| mut_no_pop | progress_bmc | 2 | 0 | CAUGHT | 4.1 | r2_rank_decreases |
