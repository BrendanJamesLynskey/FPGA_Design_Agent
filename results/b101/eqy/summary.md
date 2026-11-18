# eqy results (brief 101, part 2)

Written by `python3 -m flow.oss_compare.eqy_run --table` from the per-proof records in this directory.

## RTL against the Yosys netlists (every block x family x script)

| block | netlist | status | strategy | seconds | note |
|---|---|---|---|---|---|
| adder_tree8 | xc7__abc9 | PASS | name | 93.2 | 1 partition(s) proved; 1 gold and 1 gate public names have no partner (they sit inside a partition, not at a cut point: ['a_q', 'u_blk.a']) |
| adder_tree8 | xc7__abc9_dff | PASS | name | 125.7 | 2 partition(s) proved |
| adder_tree8 | xc7__abc_d | PASS | name | 116.6 | 2 partition(s) proved |
| adder_tree8 | xcup__abc9 | PASS | name | 92.5 | 1 partition(s) proved; 1 gold and 1 gate public names have no partner (they sit inside a partition, not at a cut point: ['a_q', 'u_blk.a']) |
| adder_tree8 | xcup__abc9_dff | PASS | name | 122.7 | 2 partition(s) proved |
| adder_tree8 | xcup__abc_d | PASS | name | 108.7 | 2 partition(s) proved |
| crc64_rx | xc7__abc9 | PASS | name | 31.0 | 3 partition(s) proved |
| crc64_rx | xc7__abc9_dff | PASS | name | 31.7 | 3 partition(s) proved |
| crc64_rx | xc7__abc_d | PASS | name | 30.3 | 3 partition(s) proved |
| crc64_rx | xcup__abc9 | PASS | name | 30.7 | 3 partition(s) proved |
| crc64_rx | xcup__abc9_dff | PASS | name | 30.6 | 3 partition(s) proved |
| crc64_rx | xcup__abc_d | PASS | name | 29.9 | 3 partition(s) proved |
| lg_small_comb | xc7__abc9 | PASS | name | 275.8 | 4 partition(s) proved |
| lg_small_comb | xc7__abc9_dff | PASS | name | 274.2 | 4 partition(s) proved |
| lg_small_comb | xc7__abc_d | PASS | name | 328.0 | 4 partition(s) proved |
| lg_small_comb | xcup__abc9 | PASS | name | 270.5 | 4 partition(s) proved |
| lg_small_comb | xcup__abc9_dff | PASS | name | 275.8 | 4 partition(s) proved |
| lg_small_comb | xcup__abc_d | PASS | name | 328.0 | 4 partition(s) proved |
| pcs_tx | xc7__abc9 | PASS | group | 406.3 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | xc7__abc9_dff | PASS | group | 472.0 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | xc7__abc_d | PASS | group | 433.7 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | xcup__abc9 | PASS | group | 403.6 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | xcup__abc9_dff | PASS | group | 414.9 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | xcup__abc_d | PASS | group | 429.2 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |

## RTL against Vivado post-synthesis funcsim netlists

| block | netlist | status | strategy | seconds | note |
|---|---|---|---|---|---|
| adder_tree8 | a7__viv_default | ERROR | name | 900.1038239002228 | eqy timed out after 900 s |
| adder_tree8 | k26__viv_default | ERROR | name | 900.0858957767487 | eqy timed out after 900 s |
| crc64_rx | a7__viv_default | ERROR | name | 900.1077139377594 | eqy timed out after 900 s |
| crc64_rx | k26__viv_default | ERROR | name | 900.1083652973175 | eqy timed out after 900 s |
| lg_small_comb | a7__viv_default | PASS | name | 385.3 | 3 partition(s) proved; 1 gold and 1 gate public names have no partner (they sit inside a partition, not at a cut point: ['u_blk.in_v', 'v_q']) |
| lg_small_comb | k26__viv_default | ERROR | name | 900.1091361045837 | eqy timed out after 900 s |
| pcs_tx | a7__viv_default | ERROR | group | 2720.1 | name strategy: FAIL (2 of 4 partition(s) not proved); group strategy: eqy timed out after 1500 s |
| pcs_tx | k26__viv_default | ERROR | group | 3032.8 | name strategy: FAIL (2 of 4 partition(s) not proved); group strategy: eqy timed out after 1500 s |

## Planted faults on the Yosys abc9 UltraScale+ netlists

| block | netlist | status | strategy | seconds | note |
|---|---|---|---|---|---|
| adder_tree8 | clean | PASS | name | 87.8 | 1 partition(s) proved; 1 gold and 1 gate public names have no partner (they sit inside a partition, not at a cut point: ['a_q', 'u_blk.a']) |
| adder_tree8 | lut_init_0 | FAIL | bmc | 2.2 | flipped INIT bit 7 of LUT _066_: 96 -> 16 |
| adder_tree8 | lut_init_1 | FAIL | bmc | 2.2 | flipped INIT bit 42 of LUT _071_: 965aa59669a55a69 -> 965aa19669a55a69 |
| adder_tree8 | reset_drop_0 | N/A | name | 0.0 | no register to plant a reset_drop fault in |
| adder_tree8 | reset_value_0 | N/A | name | 0.0 | no register to plant a reset_value fault in |
| adder_tree8 | swap_regs_0 | FAIL | bmc | 2.1 | swapped the D inputs of registers _147_ and _146_ |
| adder_tree8 | swap_regs_1 | FAIL | bmc | 2.2 | swapped the D inputs of registers _152_ and _146_ |
| crc64_rx | clean | PASS | name | 30.6 | 3 partition(s) proved |
| crc64_rx | lut_init_0 | FAIL | bmc | 9.8 | flipped INIT bit 7 of LUT _168_: 69 -> e9 |
| crc64_rx | lut_init_1 | FAIL | bmc | 12.5 | flipped INIT bit 42 of LUT _173_: 6996966996696996 -> 6996926996696996 |
| crc64_rx | reset_drop_0 | FAIL | bmc | 6.8 | register _476_: reset pin S tied low |
| crc64_rx | reset_drop_1 | FAIL | bmc | 6.8 | register _481_: reset pin S tied low |
| crc64_rx | reset_value_0 | FAIL | bmc | 7.1 | register _476_: set-by-reset (FDSE) became clear-by-reset (FDRE) |
| crc64_rx | reset_value_1 | FAIL | bmc | 6.8 | register _481_: set-by-reset (FDSE) became clear-by-reset (FDRE) |
| crc64_rx | swap_regs_0 | FAIL | bmc | 9.3 | swapped the D inputs of registers _476_ and _475_ |
| crc64_rx | swap_regs_1 | FAIL | bmc | 10.1 | swapped the D inputs of registers _481_ and _475_ |
| lg_small_comb | clean | PASS | name | 274.6 | 4 partition(s) proved |
| lg_small_comb | lut_init_0 | FAIL | bmc | 16.1 | flipped INIT bit 7 of LUT _328_: 4d -> cd |
| lg_small_comb | lut_init_1 | FAIL | bmc | 10.6 | flipped INIT bit 10 of LUT _333_: bf2f -> bb2f |
| lg_small_comb | reset_drop_0 | FAIL | bmc | 10.7 | register _826_: reset pin R tied low |
| lg_small_comb | reset_drop_1 | FAIL | bmc | 277.3 | register _825_: reset pin R tied low |
| lg_small_comb | reset_value_0 | FAIL | bmc | 10.5 | register _827_: set-by-reset (FDSE) became clear-by-reset (FDRE) |
| lg_small_comb | reset_value_1 | FAIL | bmc | 10.4 | register _827_: set-by-reset (FDSE) became clear-by-reset (FDRE) |
| lg_small_comb | swap_regs_0 | FAIL | bmc | 282.0 | swapped the D inputs of registers _787_ and _786_ |
| lg_small_comb | swap_regs_1 | FAIL | bmc | 276.8 | swapped the D inputs of registers _792_ and _786_ |
| pcs_tx | clean | PASS | group | 415.2 | name strategy: FAIL (2 of 7 partition(s) not proved); group strategy: one partition (all state), abc pdr: proved from the post-reset state |
| pcs_tx | lut_init_0 | PASS | group | 402.9 | flipped INIT bit 7 of LUT _0512_: 3003184896 -> 3003185024 |
| pcs_tx | lut_init_1 | FAIL | bmc | 233.4 | flipped INIT bit 10 of LUT _0517_: 64371 -> 65395 |
| pcs_tx | reset_drop_0 | FAIL | bmc | 17.2 | register _1279_: reset pin R tied low |
| pcs_tx | reset_drop_1 | FAIL | bmc | 17.5 | register _1284_: reset pin R tied low |
| pcs_tx | reset_value_0 | N/A | name | 0.0 | no register to plant a reset_value fault in |
| pcs_tx | swap_regs_0 | FAIL | bmc | 20.3 | swapped the D inputs of registers _1279_ and _1278_ |
| pcs_tx | swap_regs_1 | FAIL | bmc | 20.7 | swapped the D inputs of registers _1284_ and _1278_ |
