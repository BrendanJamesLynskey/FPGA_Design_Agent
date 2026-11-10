# Amendments to frozen benchmark content

Dated entries. Each follows the eval-1 pre-registration style: "Amended <date> (planner, before any scored run)": the task, the reason (a quoted review
finding), the change and the new hash. Only **development** tasks are amended; no held-out unit, draw or split file is touched, and the v2 draw is not redone.
v1 and course units are re-recorded with `freeze.py refreeze`; v2 development tasks through a hash-chained `amend` entry in `v2/ledger.jsonl`.
Reviews: `reports/12_quality_review_area2.md` (planner repository), items R2, R5-R9, B2, Q2.

## 2026-11-10: shell fingerprint, spec gaps, mutants (brief 15)

**Amended 2026-11-10 (planner, before any scored run), shell freeze.** Reason (R2): "the shell is a scoring dependency that can [change]": `shell/rtl/*.sv`,
`shell/host/protocol.py` and `shell/tests/uart_bfm.py` were outside every freeze. Change: `GRADER_DEPS.json` (v1), `course/GRADER_DEPS.json`, and a
`shell_freeze` ledger entry (v2), all recording shell fingerprint **`80ef214ea18ffbc307d844fde59e2ae50fa835dfcb0d16f3262571278e941555`** over these 11 files:

```
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  shell/__init__.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  shell/host/__init__.py
e279ed19af201294ba75ab3e3c3c28e2c3809d0b93d9244075451765286f7e6f  shell/host/protocol.py
c1a5d9551c5c173b5dc65a1cc3c01a00b184d9d187e2a22e8c80b3a616b8bbb1  shell/rtl/fpga_shell.sv
1beca829ea724f3a4eb1e7cf3688d8e0f26706c8f89810730672306ba66e0815  shell/rtl/reset_sync.sv
4956b6380ebf052984d598942bea4e70c6c379b9683cae40f78076dd60093d39  shell/rtl/shell_core.sv
9103308bbb71cd224d958c434bddd7b3bd2647d49cc8e718df0c6acba49509ba  shell/rtl/sync2.sv
df36889737e1714453c29b4efb1134e3bed54be50be3f31b18d51e929711df49  shell/rtl/uart_rx.sv
ccc19a6bd09120d11b9258452eb93a9a0f8fd5852fd4badacce549ef6e38b358  shell/rtl/uart_tx.sv
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  shell/tests/__init__.py
ce027cf2652e5aa710bec9c43e3d112e79660279b9b8005b980a86ce9cc8faab  shell/tests/uart_bfm.py
```

`freeze.py verify` and `split.py verify` fail on a different shell unless `--grader-shell DIR` names a frozen copy; usage in [FROZEN.md](FROZEN.md). `run_task.sources()` now
raises on an agent file whose name equals a shell file. The shell hash is newest-changed in commit `1bb13681d6a89d77ce1451c0964bb42e96a239fd`.

**Amended 2026-11-10 (planner, before any scored run), spec clarifications.** Where a hidden test checks something the spec left open, the requirement is added to spec.md and the test stays.

| Task | Review finding | Added to spec.md |
|---|---|---|
| `v2_a_tick_gen` | R6: "hidden test requires reset DIV = 8 and a generator that runs from reset; spec.md never says so"; R7: LED[1] "flips on the same clock edge" | "CPU_RESETN resets everything: N goes back to 8 and the ticks run from then on ... and the tick count goes to zero"; LED[1] "changes on the same clock edge on which LED[0] goes high, not a clock earlier or later" |
| `v2_a_seq_detect` | R7: "requires LED[0] exactly two clocks behind the input ... no latency or synchroniser depth is stated" | "I expect it through two flip-flops first, and LED[0] to light two clocks after the edge that takes in the pattern's last bit" |
| `t1_gray_stepper` | R8: "enforces that a button press does not move the automatic step grid ... spec.md says only 'Buttons still work in automatic mode'" | "a press gives one step of its own and does not disturb the automatic ones, which carry on exactly the set rate apart" |
| `t1_bcd_updown` | Q2: WRAPS width "never tested" | "a single byte is plenty, so after 255 that count can go round to zero", with a test and a mutant |

**R9 (gray stepper "proved"), decision: the spec wording changed, no formal check was added.** The grader has no formal stage, and SymbiYosys/Yosys are not installed on the
planner machine, so a formal result could not be checked here. The simulation test `test_every_transition_one_bit` already drives all 1024 steps in each direction, so spec.md now asks for
exactly that ("checked on every step of the whole count, in both directions, not just on a few"); REQ-01/02 are `proof: [simulation]`. The reference's `ifdef FORMAL` assertions stay. A separate
formal result in CI is a possible follow-up.

**Not done, and why.** Q2 "clear wins over a match on the same clock" (`v2_a_seq_detect`): spec.md does not say it, and a test would need a UART write landing on a given clock of a
one-clock match, which the shell's timing does not let a bench aim; a mutant without a killing test would break the rule that every mutant is killed. Left as a deliberate gap.

**Amended 2026-11-10 (planner, before any scored run), mutants.** B2: `c16_ntt_engine` `forward_scaled` "does not compile" (dangling `else`); replaced by an edit of both lines, killed by
`test_forward_random` and `test_forward_edge_polynomials`; `KNOWN_BUILD_KILLS` is now empty. R5: every development task whose reset/ID test killed no mutant (21 tasks) gained one "this register is not reset" mutant
(listed below); each is killed by `test_identity_and_reset` (the `t1_bcd_updown` ones by the new `test_reset_after_activity`). Q2: `v2_a_sat_add` `led_wrapped_sum` (LED shows the wrapped sum). In Icarus an unreset
register starts as X and the test's read of it fails; the `t1_bcd_updown` mutants hold the old value, so they need the new reset-after-activity test.

## New hashes

v1 and course units (SHA-256 of the unit's sorted file lines, as in MANIFEST.json):

| Tier | Unit | Old digest | New digest | Change |
|---|---|---|---|---|
| v1 | `t1_bcd_updown` | `fa39506fb33cd5b0f0a89382760e58d9ca769d84b4bc34f6ff5af69028528238` | `826ae6443a7a0647936f53ca04a2ebd57429994ca846c5ad720be7505ac84dab` | spec.md: the wrap count is a single byte (goes round after 255); tests `test_wrap_count_is_a_byte`, `test_reset_after_activity`; mutants `wraps_nine_bits`, `count_survives_reset`, `wraps_survive_reset`; NOTES.md |
| v1 | `t1_elevator_fsm` | `c4a5e57dbcfb23f8c98b7b93547cfd6104677d8ade67365b7e1408b17446c204` | `944a56ad22c0d171083e561b722e3042129d51574c6033d5517c2496c5ed5382` | mutant `pend_not_reset` |
| v1 | `t1_gray_stepper` | `b496053e45b566c714bf895b229da7d0703cd33ba6eca40f5b15c7249ba06128` | `195a637fc30b76a940d830234ef860c380dc37c881c6087ae22da7578cf36038` | spec.md: press during automatic mode (R8) and `proved` replaced by `checked on every step of the whole count, in both directions` (R9); bench.yaml phrase; spec.yaml REQ-01/02 proof [simulation]; NOTES.md. Tests and mutants unchanged |
| v1 | `t1_pattern_sequencer` | `266152b0d23234f12a6e347ce5cbb4a79f1520dfd10893cac48902dc5b9eb540` | `b3429f905b7c4d3c866766738be48ded8542980304288615a1015db9f7aa62ea` | mutant `run_not_reset` |
| v1 | `t1_press_classifier` | `01c15aa8a917608a3e2f07da239b2a126495a609afbe7c271f120dc13d8fd8c0` | `dc297e5a0b6d1da2085876be45975122ae9ab537890526085eb65bb3ba5653d6` | mutant `short_cnt_not_reset` |
| v1 | `t2_i2c_cmd_master` | `f3cc809a068ff1e5b27210353a894d0e20c5a8e21b0dd9613789a59aaa0dd575` | `c8e112682bfe8ab33ad6e56c12ba8685d8459ef9fcade24137156f201de64a31` | mutant `scl_oe_not_reset` |
| v1 | `t2_pdm_vu` | `1d2521124ec66ae1bdfd1d9f6dcb9b9c12a7c0189933373bae5cfae7c4dc7f09` | `66177476f88de6c6b0c44b7e89d50003b1a373c4f427f7a1bf907a87705c41ca` | mutant `hold_set_not_reset` |
| v1 | `t2_spi_master_modes` | `909059ec82635e94860c72048d132b94d2ad891c52823a0455600a9151bf7c3c` | `b9c80d3e5c92b0906aba1c97ced96cd8fadb31fbf1bbd69711ec3ed47b4bd6d4` | mutant `rxd_not_reset` |
| v1 | `shared:tools/run_task.py` | `8872d7a1012ea2c225b296aa39f6fb914589fd6b9d148a7f755c84d64b7a438d` | `5647e625d764329530fc6a13acdd4619e9c5ad69b8aeaff2e9945fb32181cd9c` | a file named like a shell file is an error; `FDA_GRADER_SHELL` |
| course | `c10_dds_sine` | `047f07096adb3b38a3bc1e55fa34c2912549dec19d947c8ccb8b4e5440a2d6e4` | `cd7402ad4742d4a34d1637f42b6c9598d085987b006d904319a561f06566e927` | mutant `fw_r_not_reset` |
| course | `c11_nco_mixer` | `14b7d251f59af283f2f57fa252a49f88feeb246ef95c9dd39c497d6ecf63bf7a` | `e459be870952870d564b1fa392b5bbcaa2e4c3ac0a052ebbafefa594dfd47b4c` | mutant `fw_r_not_reset` |
| course | `c12_adsr_envelope` | `045da56b53f3aa8b7cd3ff500deb8c53a2406730153aad61259dc727e87306b8` | `c322652dd81000b67f79c6ee9cec3eae409ead148a221a85a4020e74edd12ab0` | mutant `level_not_reset` |
| course | `c12_nexys_pwm_audio` | `f30a4c50c2e8f5d696fd04aa5c70f4d5be6b47fbdb0c99e63d2a82bb9d2c1843` | `66a4f7731d4f491c29b9e768ced4bdd41ba86795818a1358b77f6fbd2fe3388a` | mutant `gain_not_reset` |
| course | `c13_hough_lines` | `1b132803ce98e1815cdd921498f9320d742cbaa24fc3d6be05a9b5f77c7b8dd4` | `df6e2378f80d9415173e487a342292367ade3d78d1ca87e2d6b0403c2c17ee93` | mutant `k_not_reset` |
| course | `c14_int8_dot_requant` | `1941c51ddb180c73d7966bb8f8402038402da5eb711820216359d42b8f7cff30` | `57b168bee67f3dfdf173530bd3aecfddbd0934189c2d48cac1ac44aaa9b435fc` | mutant `a_r_not_reset` |
| course | `c14_systolic_matmul` | `9444968e56183cfd5f2be2269273a7bb20fd3e77350f80cf49356e8c335e8b2c` | `18f54fc01a2d15f8e6faad5f7b38f0fe0d1e46c91de6afab2f8252250a658ff7` | mutant `lat_not_reset` |
| course | `c15_rmsnorm_unit` | `c5384267f803bd988f4dad00cb665be9159f600ca9e234155e28a4ab9370c167` | `4d7d93b80cab39bcb5eacf283f63e12b9bec763517e2c5cd43cc532084a8af46` | mutant `x_r_not_reset` |
| course | `c15_softmax_unit` | `d72376b25ea19c8f90c8cbd69acd922d146a457639889121d430c2240e199a6d` | `207c7f6e81a5ab06fb7b99592af6c7e79ed8e2ac5cf7119cbbe0eeac98a42835` | mutant `x_r_not_reset` |
| course | `c16_ntt_engine` | `ee8795e12b436d27602e1db7fce9b3abc6a4edb1597c4bfa02886cc2c3a513f3` | `5c0b0350f0a7ebfcbd6ccbc9e277dbbae7c6dd76076d65c112e78a2f8579045b` | mutant `forward_scaled` replaced by an edit that compiles (B2); mutant `ld_ptr_q_not_reset` |
| course | `c9_median3x3` | `b4182f3bc1adc1817db3315e2cc9dd027173aa55140259ee8e2ac7ba0bc8ab90` | `6bf70dd99fe8c637303f98348948e0eca6ae494d36200caff99d6cdbb4485adc` | mutant `vmask_not_reset` |
| course | `shared:benchmark/tools/run_task.py` | `8872d7a1012ea2c225b296aa39f6fb914589fd6b9d148a7f755c84d64b7a438d` | `5647e625d764329530fc6a13acdd4619e9c5ad69b8aeaff2e9945fb32181cd9c` | same file as the v1 shared unit |

v2 development tasks (ledger `amend` entries; manifest = SHA-256 of `v2/manifests/<task>.json`):

| Task | Old manifest hash | New manifest hash | New unit digest |
|---|---|---|---|
| `v2_a_tick_gen` | `9942a4c8ed284156205f5b653773af34c367676e1fa1f1b88eca13e0aa082d54` | `9d20c4feb21fc84bda37b03d0e1b97d5af5c43181428801fbbfffa46dc759f92` | `3efc7a3469d5b2cacb8141441ec52df95b749f6df680db26ae430c2e616cb225` |
| `v2_a_seq_detect` | `5fb1771f0e88f088691e0d8e5a9b20954bac61415e6faf518c97197c7b10264d` | `98ebd30e2d7fe15a8ab406fc01792754136535106948df66a0f70a73bdad833a` | `27f3f0778654c37ff4c977a5184e7145ed347648084d1df5044830c1ceb67527` |
| `v2_a_sat_add` | `10360507494f8105cdf6d904577843d2b826af33fd4c25764d8694226d3b9a53` | `db99b9f6a2485fc00fe9827bc0d354d86e59a3005bc934877b9e1678d12dcbec` | `7e60ad69f761aaf151ad5d16f4114bc0d72d79cebebe0f4d04ccca03f5925ec0` |
| `v2_a_shifter` | `8de2ba88d8fb4b49089a468caad661b8bbc8bca093acafce3a68c7f01462c6a4` | `504601c074e837109e73d6a77d57f920b5711bd5cbd6554b5247c525aebdc6f7` | `a5ec8ae71fe077e6c9c29e47a24945ce908f6095b4438289c02fe73063899f98` |
| `v2_a_prio_enc` | `49b64b1a00bcb95d3bc7ad56ab8444ba14b1db3130d3e11d1e252495be1f6890` | `16fedde3269cc3412e3862838a157a6ae64d6caa0be48532cfb9dd48491d3235` | `d7f00e8fcc2ac91787552d4ef8c2622e903fdd8c9e57e24977ac84459e4c30c0` |

The private manifests (`benchmark_private/MANIFEST_full.json`, `course/MANIFEST_full.json`) list the same public units and the two shared `run_task.py` units; their entries are for the owner to re-record
(no private file was read or written here).
