# ddr2_sched and ddr2_addrmap: ports, timing contract and what a user could guess wrong (brief 141)

Plan and study: [docs/memory_controller_plan.md](../../../docs/memory_controller_plan.md). RTL: `rtl/ddr2_sched.sv`, `rtl/ddr2_addrmap.sv`.

## ddr2_sched ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | the scheduler clock: one command a clock, so the memory clock period in phase 0 |
| `rst` | in | 1 | synchronous, active high; apply once before `en`; never again while the part is in use |
| `en` | in | 1 | the part is initialised and precharged (AMD's `init_calib_complete`); rises once and stays high |
| `req_v`, `req_rdy` | in, out | 1 | request handshake; `req_rdy` is high while a queue entry is free and `en` is high, and does not depend on `req_v` |
| `req_wr` | in | 1 | 1 write, 0 read; one request is one BL8 burst |
| `req_addr` | in | RW+BW+CB | burst address, decoded by `ddr2_addrmap` (parameter `MAP`) |
| `req_tag` | in | TW | returned with the READ or WRITE; **must be unique among requests in the queue** (the user's duty) |
| `ref_defer` | in | 1 | a latency-critical window: refresh is postponed within the allowance `REF_POST`, never beyond |
| `cmd_v`, `cmd_op`, `cmd_bank`, `cmd_row`, `cmd_col`, `cmd_tag` | out | 1, 3, BW, RW, CB, TW | the registered command; `cmd_op` 1 ACTIVATE, 2 READ, 3 WRITE, 4 PRECHARGE, 5 PRECHARGE ALL, 6 REFRESH; `cmd_row` on ACTIVATE, `cmd_col` and `cmd_tag` on READ and WRITE |

Defaults describe the MT47H64M16 (BW 3, RW 13, CB 7: 2**23 bursts of 16 bytes = 128 MiB).

## Parameters

| Parameter | Default | Legal | Meaning |
|---|---|---|---|
| `POLICY` | 0 | 0, 1 | 0 latency-first, 1 bandwidth-first |
| `QD` | 8 | 2 to 40 | queue entries (verified in simulation to 33) |
| `MAP` | 0 | 0, 1, 2 | address map (ddr2_addrmap.sv header) |
| `T_RCD` ... `T_REFI`, `RL`, `WL`, `BL2` | MT47H64M16-25 at tCK 2.5 ns | whole clocks; counters are 8 bits; `RL = WL + 1`; `T_REFI >= 4 x (T_RAS + T_RPA + T_RFC)` | `tests/m141_timing.py` derives them from the data sheet for a clock period (profiles `ddr2_800`, `nexys_650`) |
| `AGE_LIM` | 1024 | above the wait of a request in a full queue | an oldest request this old is served alone |
| `WR_HI`, `WR_LO` | 6, 1 | POLICY 0 | start and stop draining writes at these queued-write counts |
| `RUN_MAX` | 16 | POLICY 1, below 32 | column commands in one direction before the other gets its turn |
| `REF_POST` | 4 | 0 to 6 | refreshes that may be postponed (JEDEC allows up to 8) |

Elaboration errors name a violated range (timing out of range, `REF_POST`, `RL != WL + 1`).

## Timing contract

- A request accepted in clock t (`req_v && req_rdy`) can be decided in clock t+1 and is on `cmd_*` in clock t+2 at the earliest (a hit on an open row). A closed bank costs ACTIVATE then `T_RCD` clocks.
- Every rule of `tests/m141_timing.py` holds between commands **on the output**; the formal monitor and the bench check them there.
- READ data is on the data bus `RL` clocks after the READ command for `BL2` clocks; WRITE data `WL` clocks after the WRITE command.
- One REFRESH falls due every `T_REFI` clocks counted from `en`; at most `REF_POST + 2` are outstanding (proved).
- A request is served within `AGE_LIM + QD x R_MAX + refresh cost` clocks (`verif/formal/run_formal.py:bound`), proved at small parameters and measured at the real ones.

## What a user could guess wrong

1. The block has **no data path**: write data and read data move through the PHY at the fixed latencies; there is no completion signal, the column command is the completion of scheduling.
2. Spacings are those of the **registered output**, not of the internal decision.
3. **No store-to-load forwarding**: a read of an address with an older queued write waits for the write's column command.
4. Out-of-order completion is normal; only same-address order (with a write in the pair) is kept.
5. `ref_defer` is a request: when the allowance is used up the refresh is forced and blocks new commands until its REFRESH.
6. **Tags must be unique among queued requests**; the block does not check.
7. A reset during operation is unsupported (it would forget the open banks of a real part; the proofs assume reset only at the start).
8. `AGE_LIM` set below the wait of a request in a full queue turns the queue into first-come first-served (measured in `results/b141/sim_summary.json`, the `age_sweep` runs).
9. tRC does not appear as an independent constraint at the data sheet's values (tRAS + tRP already equals it); it is still enforced.
10. Latency figures count from the handshake clock, not from when the user raised `req_v`.
