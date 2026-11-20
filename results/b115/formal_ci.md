| job | task | AW | bit | verdict | seconds | failing assertions |
|---|---|---|---|---|---|---|
| safety_prove_aw4_kb0 | safety_prove | 4 | 0 | PASS | 4.5 |  |
| safety_prove_aw4_kb7 | safety_prove | 4 | 7 | PASS | 6.9 |  |
| safety_prove_aw4_kb39 | safety_prove | 4 | 39 | PASS | 6.1 |  |
| safety_prove_aw4_kb63 | safety_prove | 4 | 63 | PASS | 7.1 |  |
| safety_prove_aw4_kb64 | safety_prove | 4 | 64 | PASS | 6.6 |  |
| safety_prove_aw4_kb71 | safety_prove | 4 | 71 | PASS | 7.3 |  |
| safety_prove_aw4_kb72 | safety_prove | 4 | 72 | PASS | 6.4 |  |
| safety_prove_aw4_kb73 | safety_prove | 4 | 73 | PASS | 6.0 |  |
| safety_prove_aw2_kb0 | safety_prove | 2 | 0 | PASS | 20.5 |  |
| safety_prove_aw1_kb0 | safety_prove | 1 | 0 | PASS | 7.5 |  |
| safety_bmc_aw2_kb0 | safety_bmc | 2 | 0 | PASS | 68.0 |  |
| progress_bmc_aw2 | progress_bmc | 2 | 0 | PASS | 143.0 |  |
| cover_aw2 | cover | 2 | 0 | PASS | 9.6 |  |
| mut_overflow | safety_prove | 2 | 0 | CAUGHT | 3.2 | p1_no_overflow, p1b_bound, p2_wview |
| mut_underflow | safety_prove | 2 | 0 | CAUGHT | 1.0 | p4_no_underflow |
| mut_gray_step | safety_prove | 2 | 0 | CAUGHT | 1.1 | h5a_wp_chain_order, p5_gray_w |
| mut_binary_pointer | safety_prove | 2 | 0 | CAUGHT | 1.8 | h5a_wp_chain_order |
| mut_unsynced_pointer | safety_prove | 2 | 0 | CAUGHT | 1.7 | h5a_wp_chain_order, p3_rview |
| mut_wrong_entry | safety_prove | 2 | 0 | CAUGHT | 4.6 | p8a_pop_is_written_bit, p8b_output_is_written_bit |
| mut_insert_in_frame | safety_prove | 2 | 0 | CAUGHT | 5.6 | p6a_insert_idle_only_between_frames |
| mut_delete_in_frame | safety_prove | 2 | 0 | CAUGHT | 5.1 | p6b_delete_only_between_frames |
| mut_delete_any | safety_prove | 2 | 73 | CAUGHT | 5.2 | p7b_delete_only_flagged |
| mut_no_pop | progress_bmc | 2 | 0 | CAUGHT | 2.7 | r2_rank_decreases |
