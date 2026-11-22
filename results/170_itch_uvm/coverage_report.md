# Functional coverage closure (brief 170)

97 of 97 bins hit; 0 holes.

| bin | hits |
|---|---|
| msg_S | 119 |
| msg_R | 152 |
| msg_A | 1008 |
| msg_F | 58 |
| msg_E | 124 |
| msg_C | 107 |
| msg_X | 158 |
| msg_D | 759 |
| msg_U | 206 |
| m_skip | 127 |
| m_badlen | 4 |
| m_bad | 6 |
| add_buy | 404 |
| add_sell | 652 |
| mpp_1 | 557 |
| mpp_3 | 230 |
| mpp_6 | 143 |
| mpp_other | 185 |
| gap | 23 |
| overlap | 2 |
| dup | 25 |
| heartbeat | 18 |
| eos | 2 |
| sess | 2 |
| short | 2 |
| trunc | 4 |
| badlen | 86 |
| drop_off | 2 |
| drop_mac | 2 |
| drop_type | 19 |
| drop_frag | 4 |
| drop_proto | 10 |
| drop_dip | 2 |
| drop_port | 12 |
| drop_len | 4 |
| drop_ipck | 10 |
| odup | 2 |
| oovf | 2 |
| lvovf | 6 |
| oover | 2 |
| omiss | 592 |
| unwatch | 6 |
| fire_strict | 433 |
| fire_cut | 55 |
| fire_spec | 108 |
| rej_arm | 21 |
| rej_kill | 4 |
| rej_gap | 30 |
| rej_stale | 6 |
| rej_size | 13 |
| rej_pos | 4 |
| rej_band | 19 |
| rej_nobid | 4 |
| bad_fcs | 31 |
| bad_fcs_with_order | 8 |
| tail_near_strict | 408 |
| tail_far_strict | 14 |
| tail_edge_strict | 11 |
| tail_near_cut | 37 |
| tail_far_cut | 14 |
| tail_edge_cut | 4 |
| burst_3 | 83 |
| cmd_clr_cnt | 5 |
| cmd_clr_flags | 34 |
| cmd_clr_book | 2 |
| cmd_clr_pos | 7 |
| cmd_clr_ref | 5 |
| cmd_tcp_load | 35 |
| reset | 35 |
| in_bubbles | 20 |
| out_pause_in_frame | 22 |
| obs_good | 465 |
| obs_poisoned | 22 |
| obs_must_present | 306 |
| obs_mustnot_absent | 20 |
| obs_may_present | 158 |
| obs_may_absent | 2 |
| align_0_l0 | 397 |
| align_0_l4 | 114 |
| align_1_l0 | 22 |
| align_1_l4 | 25 |
| align_2_l0 | 61 |
| align_2_l4 | 35 |
| align_3_l0 | 81 |
| align_3_l4 | 58 |
| align_4_l0 | 80 |
| align_4_l4 | 37 |
| align_5_l0 | 55 |
| align_5_l4 | 36 |
| align_6_l0 | 48 |
| align_6_l4 | 38 |
| align_7_l0 | 85 |
| align_7_l4 | 57 |
| order_lane0_only | 487 |
| xtalk_strict_bad_none | 3 |
| seq_consumed_by_poison | 11 |
| frame_fwd | 1164 |

## Holes

none

## SVA cover counts

| cover | hits |
|---|---|
| stream_frames | 487 |
| stream_poisoned | 0 |
| stream_unresolved | 0 |
| in_frames_lane0 | 829 |
| input_bubble_after_data | 838 |
| out_pause_inside_frame | 174 |
| out_frame_start | 487 |
