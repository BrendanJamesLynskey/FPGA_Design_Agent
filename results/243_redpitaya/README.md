# results/243_redpitaya: why the Red Pitaya user slots did not answer the bus, the fix, the rebuilt image, the loader fixes (brief 243)

What this folder holds: the records of brief 243, which follows brief 235 ([results/235_redpitaya](../235_redpitaya/README.md)). **Nothing here touched the board**: the Red Pitaya was powered off, no board command, ping or owner script was run; every step was offline (simulation, a Vivado checkpoint, a build).
Date: 2026-11-27 (GMT). Tools: Vivado 2026.1 for the builds and the checkpoint (the checkpoint of build `170300fd` was written by 2026.1 and 2025.2 will not open it), Vivado 2025.2 xsim for the bus simulation, iverilog for the CI test.
Vendor shell: RedPitaya-FPGA at the pinned commit 728a4f37e9 (project v0.94, Z10 build, `xc7z010clg400-1`), unchanged.

## What happened at the board (from the brief)

Build `170300fd` loaded (fpga_manager `operating`, md5 matched, fclk0 125 MHz). The vendor's own slots answered (housekeeping 0x40000000 reads 1, PID 0x40300000 reads 0xf). Our two blocks, slot 6 `rp_patgen` (0x40600000) and slot 7 `rp_freqcount` (0x40700000), read 0 at the ID register, and a scratch write read back 0.

## 1. Root cause

**The blocks do answer, but their answer is gone by the time the PS reads it.** Between the PS and every slot the vendor's `sys_bus_interconnect` puts a clock-crossing bridge (`sys_bus_cdc`). It (a) holds `wen` or `ren` high from the first cycle until the slot's `ack` has been carried back across the crossing, so a block with a one-cycle ack sees the request for two cycles, and
(b) hands the slot's `rdata` to the PS-side AXI slave combinationally, two to three clocks after the ack was raised. A block that follows the convention of `shell.yaml` and `rp_user_block` (rdata valid in the ack cycle only, cleared the next cycle) has cleared `rdata` by then, so every read returned 0. The vendor's own slots hold `rdata` until the next access, which is why they answered.
The planner's hypothesis (no ack, or no wen/ren) was disproved: the ack comes back, the AXI slave does not time out, and `err` is 0; the data is what is missing.

Evidence:

| What | Result | File |
|---|---|---|
| Simulation of the patched top's bus path (vendor interconnect, bridge and stubs from the pinned files; the blocks of `170300fd` wired exactly as `rp_shell.py` wired them; a master that drives the bus the way the vendor's AXI slave does: held address and data, a one-cycle wen/ren, wait for ack up to 32 clocks) | both ID reads return `00000000` with `timeout=0 err=0`; scratch write then read returns `00000000`; 6 mismatches of 6 reads | [sim/bus_path_170300fd_no_adapter.txt](sim/bus_path_170300fd_no_adapter.txt) |
| Waveform excerpt of slot 6, the first read (one line per adc clock in which the slot or the PS side is active; values sampled just before the clock edge) | the slot sees `ren=1` for two clocks; its block raises `ack` with `rdata=fda10201` in the second of them and the one after; the bridge's ack reaches the PS side one clock after the block's ack has ended, and by then the slot's `rdata` is `00000000` again | [sim/waveform_slot6_first_read_170300fd.txt](sim/waveform_slot6_first_read_170300fd.txt) (monitor [sim/mon_slot6.sv](sim/mon_slot6.sv)) |
| The routed checkpoint of `170300fd` (Vivado 2026.1, `open_checkpoint` on `red_pitaya_top_routed.dcp`) | nothing is constant or removed: both blocks present (`i_user_block` 819 leaf cells, `i_user6_block` 1581), each block's `sys_ack` register drives the bridge's `reg_read`, `reg_write` and `reg_done` logic of its own slot, each `sys_rdata` bit reaches the PS AXI slave's `RDATA` mux (`ps/axi_slave_gp0/axi.RDATA[n]`), `wen` and `ren` come from the bridge's `reg_write`/`reg_read` registers of the same slot, all eight bridges exist, no unrouted nets under the blocks | [evidence/checkpoint_170300fd_inspect.out](evidence/checkpoint_170300fd_inspect.out), [inspect2.out](evidence/checkpoint_170300fd_inspect2.out), the Tcl beside them |
| Same simulation with the adapter of section 2 in front of the blocks (blocks of `170300fd`; PS/adc clock offset 0.5, 1, 4 and 7.5 ns) | every ID and scratch read correct, 0 mismatches | [sim/bus_path_170300fd_with_adapter_phase*.txt](sim/) |

Slot index, address decode, reset polarity, clock: all as the planner read them (slot 6 and 7 at `addr[22:20]`, one `adc_clk` and `adc_rstn` for every block and bridge); none of them is the fault. The overlay's two `set_false_path` constraints name only `i_asg/*`, `i_scope/*`, `ps/axi_master_2/*` and `ps/axi_master_3/*`; they do not touch our blocks or the bridge.
A scratch write was also correct in the simulation (the write lands; only the read-back is lost), so the 2026-11-27 write-then-read test read 0 for the same reason, not because writes were dropped.

Why the earlier tests missed it: brief 225's testbench (`tb_rp_user_block.sv`) and the agent's cross-checks read `rdata` in the cycle after the pulse, which is what the convention says; they never put the vendor's bridge in the path. The fault is in what `shell.yaml` and the shell-patch tool promised ("the block answers in the next cycle"), not in either block's RTL.

Waveform of slot 6, the first read, from the monitor (times in ps; left of the bar the slot's side of the bridge, right of it the PS side): `293000 ren=1 ack=0 rdata=0 | PS ack=0`, `301000 ren=1 ack=1 rdata=fda10201 | PS ack=0`, `309000 ren=0 ack=1 rdata=fda10201 | PS ack=0`, `317000 ren=0 ack=0 rdata=0 | PS ack=1 rdata=0`: the block's reply is two clocks long and gone when the PS acts on the bridge's ack.

## 2. The fix

[boards/redpitaya_stemlab_125_14/shell/rp_bus_adapt.sv](../../boards/redpitaya_stemlab_125_14/shell/rp_bus_adapt.sv), our own file, put by `tools/rp_shell.py` between each slot and its block (the patch now carries `slot_instance(...)`; the vendor's files are not edited). The block keeps its one-cycle convention unchanged (so the agent's blocks, `shell.yaml` and the models need no change). The adapter:

- passes the block exactly one `wen` or `ren` per shell access (the bridge's held request is not repeated into the block);
- captures the block's `rdata` and `err` in its ack cycle and holds them until the next access, raising `ack` one cycle later and holding it until the shell drops its request;
- answers a block that has not acked after 16 clocks with `ack` and `err` high and `rdata` 0, so one silent block cannot hold the shell's bus;
- adds one clock of latency; reset is synchronous, active low. Everything a user could guess wrong is written at the top of the file.

Tests (a test that fails on `170300fd`):

- [hil/tests/test_243_redpitaya_bus.py](../../hil/tests/test_243_redpitaya_bus.py) (CI): the adapter against a behavioural model of the bridge with 4 combinations of crossing delay, a silent block, and the same model with the block wired straight on (`DIRECT`), which **fails** (every read 0), so the model has teeth ([tb_rp_bus_adapt.sv](../../boards/redpitaya_stemlab_125_14/shell/tb_rp_bus_adapt.sv), iverilog). The model is written from measured behaviour, not from the vendor's text.
- The same test file, when `RP_SHELL_WORK` names a `tools/rp_shell.py` work directory and xsim is installed (not in CI: needs the vendor checkout and Vivado): the whole bus path against the pinned vendor files, three clock offsets, with the adapter (must pass) and `--no-adapter` (must fail with reads of 0) ([hil/rp_bus_sim/](../../hil/rp_bus_sim/); the slot text comes from `rp_shell.slot_instance`, so it cannot drift from the patch).
- The xsim run on the rebuilt sources (both builds): [sim/bus_path_H1_rebuilt_sources.txt](sim/bus_path_H1_rebuilt_sources.txt), [H2](sim/bus_path_H2_rebuilt_sources.txt): `BUS PATH PASS`.

What this does not prove: the board. The simulation uses the vendor's bridge and a model of the PS master; a clock offset between fclk0 and the ADC clock is covered at four values, not every phase; the real AXI master's timing is as read from the vendor's source. Whether the rebuilt image answers is a board result and is pending.

## 3. The rebuilt image

One image holds both instruments (`rp_freqcount` in slot 7, `rp_patgen` in slot 6; the blocks' RTL is the same as `170300fd`'s: freqcount r2 and patgen r1, files byte-identical), each behind its adapter. Vivado 2026.1, our constraints overlay, the vendor script with our directives, `MemoryMax=8G`, about 24 minutes per build, one heavy slot each.

| Build | Directives (place, physopt, route) | WNS (ns) | Failing endpoints | WHS (ns) | Build id | md5 of `fpga.bit.bin` |
|---|---|---|---|---|---|---|
| `170300fd` (brief 235, no adapter; reads 0 on the board) | Explore, Explore, Explore | +0.016 | 0 | +0.038 | 170300fd | ce6ccca2dc4e15515f939d6fa4cceccb |
| **H1: this image, the one to load** | Explore, Explore, Explore | **-0.084** | **4** | +0.056 | **d2f617ca** | **4b74fa654ad90b26fb81509e9eac786d** |
| H2: second directive set | ExtraTimingOpt, AggressiveExplore, Explore | -0.166 | 26 | +0.009 | cd83a18f | 940e3f72c91bac2cc10f5bd6d51836ed |

**Timing is not met, and was not made to be.** H1 misses setup by 84 ps on the slow corner at 125 MHz, 4 endpoints, TNS -0.302 ns; hold is met. All four are the same place: the frequency counter's own `span` register (`i_user_block/span_reg[n]/R`, a reset/enable path of 15 to 16 logic levels through the edge-detect and span arithmetic, 7.4 ns of data path against 8 ns). That is the path brief 235 named for builds E and F (`rp_freqcount`'s span register, -0.101 and -0.049 ns); build G met it by 16 ps with the second freqcount RTL.
The adapter is not on any failing path: it only changed placement, as any change to the netlist does, and the margin was 16 ps to begin with. A second directive set (H2) did worse; no new exclusion, no constraint change and no RTL change was made to hide it. The repair is routine and belongs to the freqcount RTL (register `span_n`'s comparison and subtraction across two cycles, then re-run the independent cross-check and the build): a follow-up for the planner, not done here (it changes a cross-checked block).
What the miss means for the visit: at 84 ps short, timing-driven failures at 125 MHz would show as rare wrong frequency readings, not as a bus that does not answer; the ID, scratch and `rp_patgen` checks do not depend on that path. Treat any `rp_freqcount` result as provisional until the path is repaired, and say so.
Power 1.906 W, junction 47.0 C, 10684 LUTs, 13514 registers, 36 block RAM tiles, 28 DSPs (placed): within 0.1 percent of `170300fd`, the adapters cost a few hundred LUTs and registers at most. The methodology report still carries the vendor's TIMING-6, -7 and -17 critical warnings (as in 235).
The overlay's exclusions are unchanged and still apply: the vendor's generator, oscilloscope and the two AXI bridges to the deep-memory ports are left out of the timing analysis and are not claimed to work.
Memory: the largest Vivado process of each build peaked at 2.76 GB resident (`/usr/bin/time -v`); the scope's total was sampled once during synthesis at 3.09 GB, not at its final peak. I declared `peak 6G` for the slot (no measured figure existed for this design; an honest estimate) and ran under `MemoryMax=8G`. A later declaration for this design can be `peak 4G`, a measured lower bound plus margin.

Files: [shell_timing/H1_adapter_explore_default_directives/](shell_timing/H1_adapter_explore_default_directives/) and [H2_adapter_extratimingopt_aggressive/](shell_timing/H2_adapter_extratimingopt_aggressive/): `build.json` (id, pins, hashes of every block and of the adapter, timing, utilisation, power), the head of the routed timing summary (to the first path), power, DRC and utilisation.
The package itself (`fpga.bit.bin`, `fpga.bit`, all reports) is in `~/Claude_sandbox/_bench/rp_visit_d2f617ca/package_build_d2f617ca/` and is not committed (as in 235).

## 4. The loader generator (`hil/redpitaya_load.py`)

From what the board visit taught; tests in [hil/tests/test_243_redpitaya_bus.py](../../hil/tests/test_243_redpitaya_bus.py) (a fake `ssh` that plays the board) and the updated brief 225 tests.
- (a) `rp()` now runs every board command after `. /etc/profile` with `/opt/redpitaya/sbin:/opt/redpitaya/bin` prepended to PATH (a non-interactive ssh has neither).
- (b) Shell builds load with a generated `load_fda.sh` ([owner_scripts/load_fda.sh](owner_scripts/load_fda.sh); copied to `/tmp/fda_load/` with the bitstream) that mirrors `overlay.sh`'s volatile steps: it reads the board model with `profiles -f`, copies the bitstream to `/tmp/fda_load/fpga.bin` (the v0.94 device tree asks the kernel for firmware named `fpga.bin`), removes the previous overlay from configfs, runs `fpgautil -b ... -o <dtbo> -n Full`, checks `operating` and no `fail` in the log, writes the `/tmp` markers. OS 3.00's `overlay.sh <name> <path>` ignores the path and loads `/opt/<name>/fpga.bin`, which is why it was not used. It passes `agent.core.permissions.check_script`; nothing is written to the SD card.
- (c) After the load the script checks `fpga_manager` is `operating` and the log has no `fail`, then reads the ID register of **every user block in the image** (`redpitaya_checks.py <block> --base <slot> --id-only`, exit 0 ok, 3 reads 0, 1 another value) and **stops, naming the slot**, if one reads 0 or the wrong value. This is the check that would have found the 2026-11-27 fault in one step. Nothing is written to the block and no check or OUT1 move runs after a stop.
- RESTORE keeps `overlay.sh v0.94`. A dry run (`DRY_RUN=1`) now prints every command; before, its record check line was redirected into the captured file and truncated the log (the 235 dry-run texts show only the tail).

Regenerated for build `d2f617ca`: [owner_scripts/rp_patgen/load_d2f617ca.sh](owner_scripts/rp_patgen/load_d2f617ca.sh), [owner_scripts/rp_freqcount/load_d2f617ca.sh](owner_scripts/rp_freqcount/load_d2f617ca.sh), their dry runs in [dry_run/](dry_run/) (the script's own `DRY_RUN=1` output, every board command printed, none run; and the board-side checks against the models, mock, not evidence). **The scripts in [results/235_redpitaya/owner_scripts](../235_redpitaya/owner_scripts/) and [results/225_redpitaya/owner_scripts](../225_redpitaya/owner_scripts/) are superseded**: they load `170300fd` or `3a50020d`, use `overlay.sh` with a path, and have no ID stop.
Ready-to-use copies (bitstream, scripts, `load_fda.sh`, check files) are in `~/Claude_sandbox/_bench/rp_visit_d2f617ca/rp_patgen/` and `.../rp_freqcount/`. The owner pack is [owner_pack.md](owner_pack.md).

## Known gaps and limits

- No hardware result. The adapter and the loader checks are proven in simulation and against a fake board only.
- Build `d2f617ca` misses setup by 84 ps in the frequency counter's span register (section 3); `rp_freqcount` frequency results from it are provisional.
- The xsim bus-path test is not in CI (needs Vivado and the vendor checkout). The iverilog adapter test is.
- The simulation covers the vendor bridge at the pinned commit; the real PS master and its clock phase are modelled, not measured.
- `hil/tests/test_225_redpitaya.py::test_the_checks_import_from_a_bare_directory` fails on this machine on `main` as well as on this branch (it truncates `sys.path` and then cannot import `__future__`); not touched here (follow-up).

## Reproduce

```
R=pilots/225
python3 tools/rp_shell.py prepare <dir> --block $R/rp_freqcount/agent_235_r2_rtl/rp_freqcount.sv --block $R/rp_freqcount/agent_235_r2_rtl/schmitt_edge.sv \
    $(for f in $R/rp_patgen/agent_235_r1_rtl/*.sv; do echo --block $f; done) --slot7 rp_freqcount --slot6 rp_patgen \
    --overlay boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc --explore                       # H1; H2 adds --directives ExtraTimingOpt,AggressiveExplore,Explore
python3 tools/rp_shell.py build <dir> ; python3 tools/rp_shell.py package <dir> <out>                 # heavy slot, about 24 minutes, peak 4G
python3 hil/rp_bus_sim/run_xsim.py <dir> [--no-adapter] [--phase 4]                                   # the bus path in xsim: BUS PATH PASS (FAIL with --no-adapter)
python3 -m hil.redpitaya_load script <out> --block rp_patgen --slot 6 --also rp_freqcount:7 -o <script>   # the owner's script (never run by the agent)
python3 -m pytest hil/tests/test_243_redpitaya_bus.py hil/tests/test_225_redpitaya.py hil/tests/test_235_redpitaya_followups.py
```
