# results/244_redpitaya: timing closed on the Red Pitaya image (frequency counter span path), the rebuilt image, the owner kit (brief 244)

What this folder holds: the records of brief 244, which follows brief 243 ([results/243_redpitaya](../243_redpitaya/README.md)). **Nothing here touched the board**: no board command, ping, ssh or owner script was run; every step was offline (simulation, a build, a dry run of the scripts).
Date: 2026-11-27 (GMT). Tools: Vivado 2026.1 for the build, Vivado 2025.2 xsim for the bus simulation, iverilog for the block tests.
Vendor shell: RedPitaya-FPGA at the pinned commit 728a4f37e9 (project v0.94, Z10 build, `xc7z010clg400-1`), unchanged. Build `d2f617ca` (brief 243) and its owner scripts and pack are replaced by this folder's.

## Files

- `shell_timing/I_freqcount_two_clock_span_explore/`: the new image's `build.json` (id, pins, hashes of every block and of the adapter, timing, utilisation, power), the head of the routed timing summary (to the first path), power, DRC and utilisation reports, `vivado_time_v.log` (`/usr/bin/time -v` of the build).
- `sim/`: the bus-path simulation on the rebuilt sources (`bus_path_17e913f1_rebuilt_sources.txt`, and the same at a 4 ns clock offset, `..._phase4.txt`).
- `owner_scripts/` and `dry_run/`: the owner's load-and-check scripts for build `17e913f1` and `load_fda.sh`; each script's own `DRY_RUN=1` output (every board command printed, none run) and the board-side checks against the models (mock, not evidence).
- [owner_pack.md](owner_pack.md): the one page for the next board visit.
- The repaired block: [pilots/225/rp_freqcount/agent_244_rtl/](../../pilots/225/rp_freqcount/agent_244_rtl/README.md) (RTL, README with the latency statement, lock-step testbench); tests [hil/tests/test_244_redpitaya_freqcount.py](../../hil/tests/test_244_redpitaya_freqcount.py).

## 1. The failing path (build d2f617ca)

From brief 243's routed timing summary of `d2f617ca` (`~/Claude_sandbox/_worktrees/243-scratch/w_H/pkg/`, head kept in [results/243_redpitaya/shell_timing/H1_adapter_explore_default_directives](../243_redpitaya/shell_timing/H1_adapter_explore_default_directives/red_pitaya_top_timing_summary_routed.rpt)): the worst path, slack -0.084 ns, runs from `i_user_block/cur_edges_reg[27]/C` to `i_user_block/span_reg[5]/R` (`pll_adc_clk`, 8 ns), 7.424 ns of data path, 16 logic levels (CARRY4 x8, LUT4 x4, LUT5, LUT6 x3). `i_user_block` is `rp_freqcount`.

The logic: `span` was written at the end of a gate from `span_n = (cur_edges_n >= 2) ? (last_n - first_n) : 0`, where `cur_edges_n` is the edge counter after this clock's increment (a 32-bit increment with saturation, behind the Schmitt edge detector's `edge_o`), `last_n` and `first_n` come from `idx + 1` through muxes, and the subtraction is 32 bits. The synthesiser folded the `: 0` into the register's reset pin, so the counter's carry chain, the `>= 2` compare and the enable all feed one reset/enable path in one 8 ns clock.

## 2. The repair

[agent_244_rtl/rp_freqcount.sv](../../pilots/225/rp_freqcount/agent_244_rtl/rp_freqcount.sv): the end-of-gate update is split over two clocks. In the clock where the gate's last cycle is seen the block only captures the results (`cur_edges_n`, `first_n`, `last_n`, the gate length, CONT); in the next clock it computes `span` from those registers (`>= 2` and the subtraction on registers only) and writes EDGES, GATE_ACTUAL, SPAN, FEW_EDGES, MEAS_DONE, DONE and the final BUSY together. Register map and behaviour are kept; the documented difference is **one adc_clk (8 ns) of extra latency in the publishing of a gate's result**, all registers together, and BUSY stays 1 for that clock when CONT was 0 (a START in it is ignored, where it was accepted before). Stated in the RTL header, in [agent_244_rtl/README.md](../../pilots/225/rp_freqcount/agent_244_rtl/README.md) and in the owner pack. The register behaviour a user could guess wrong (spec.md) is otherwise unchanged; the pilot's spec.md is the agent's input and is left as written.

## 3. Results

| Item | Result | Record |
|---|---|---|
| Independent cross-check from briefs 225 and 235 (`pilots/225/rp_freqcount/crosscheck_tb.sv`, iverilog) on the repaired block | `XCHECK PASS`, access latency 1 | `hil/tests/test_244_redpitaya_freqcount.py` (runs it) |
| Lock-step comparison with `agent_235_r2_rtl` (same bus and input; every result register one clock later) | 29,831 clocks, 19 gates, 0 mismatches, `DIFF PASS`; three mutants of the new block each make it fail | same test file |
| Existing tests: `hil/tests/test_243_redpitaya_bus.py`, `test_225_redpitaya.py`, `test_235_redpitaya_followups.py`, `agent/tests/test_235_block_for_shell.py`, and the new file | 111 passed, 3 skipped (the xsim bus-path test, gated on `RP_SHELL_WORK`), 1 failed: `test_225_redpitaya.py::test_the_checks_import_from_a_bare_directory`, which also fails on `main` (known from 243, untouched) | (command in Reproduce) |
| The vendor bus path in xsim on the rebuilt sources (`hil/rp_bus_sim/run_xsim.py`): both IDs and the scratch registers | `ERRORS=0`, `BUS PATH PASS`: slot 6 ID `fda10201`, slot 7 ID `fda10101`, scratch writes read back, every access `timeout=0 err=0`; also at a 4 ns clock offset | [sim/](sim/) |

### The image

One image holds both instruments (`rp_freqcount` r2 repaired, slot 7; `rp_patgen` r1 unchanged, slot 6), each behind its adapter. Vivado 2026.1, our constraints overlay, the vendor script with the Explore directives (place, physopt, route), `MemoryMax=8G`, one heavy slot (declared `peak 4G`), 17 min 22 s of wall time, largest process 2.77 GB resident.

| | `d2f617ca` (brief 243) | `17e913f1` (this build) |
|---|---|---|
| WNS (ns) | -0.084 | **+0.172** (a vendor PS-side path, `clk_fpga_3`: `axi_protocol_converter_0` to `xadc`) |
| TNS (ns) | -0.302 | 0.000 |
| Failing setup endpoints | 4 of 13,612 | **0 of 13,831** |
| `adc_clk` group (`pll_adc_clk`, where our blocks are): setup / hold (ns) | -0.084 / +0.056 | +0.196 / +0.011 |
| WHS (ns), failing hold endpoints | +0.056, 0 | +0.011, 0 |
| Build id | d2f617ca | **17e913f1** |
| md5 of `fpga.bit.bin` | 4b74fa654ad90b26fb81509e9eac786d | **a8ee76f4336d99f7bf500c3bb2d02bed** |
| sha-256 of `fpga.bit.bin`, size | d2f617ca...c71fcc45 (993,360 bytes) | 17e913f171edb00e35f187522a751255b4d798b24ac5b626bc8274d7b803c757 (996,948 bytes) |

Which paths are now the worst: in the `adc_clk` group, `rp_patgen`'s `u_reg/period_reg` to `u_reg/width_reg` at +0.196 ns; `rp_freqcount`'s worst listed path is `adc_dat_reg[0][0]` to `i_user_block/cur_edges_reg[29]` at +0.427 ns. The failing path of section 1 no longer appears among the worst paths. The hold slack of +0.011 ns is met but is thin; it is what the router left, with no hold constraint added.
Utilisation (placed): 10,672 LUTs, 13,644 registers, 36 block RAM tiles, 28 DSPs (d2f617ca: 10,684, 13,514, 36, 28: the repair adds about 130 registers and saves a few LUTs). Power 1.904 W, junction 47.0 C (d2f617ca: 1.906 W, 47.0 C).
**No new exclusion, constraint or directive was added to reach this.** The overlay (`fda_overlay.xdc`) and its two `set_false_path` exclusions are the ones of 235 and 243: the vendor's generator, oscilloscope and the two AXI bridges to the deep-memory ports are left out of the timing analysis and are not claimed to work. The methodology report still carries the vendor's TIMING-6, -7 and -17 critical warnings (as in 235 and 243).
Single build, default Explore directives: no second directive set was run, so the margin is one placement's. A different seed would move it by tenths of a nanosecond.

## 4. The owner kit for the next board visit

Regenerated by `python3 -m hil.redpitaya_load script` for build `17e913f1` (the generator reads the build's timing and writes the confirmation text from it): [owner_scripts/rp_patgen/load_17e913f1.sh](owner_scripts/rp_patgen/load_17e913f1.sh), [owner_scripts/rp_freqcount/load_17e913f1.sh](owner_scripts/rp_freqcount/load_17e913f1.sh), [owner_scripts/load_fda.sh](owner_scripts/load_fda.sh); dry runs in [dry_run/](dry_run/). They are unchanged from 243's except the build id, the md5 and size, and the timing sentence in the confirmation question. **The scripts and pack in [results/243_redpitaya](../243_redpitaya/README.md) (build `d2f617ca`) are replaced**, as are 235's and 225's. The owner pack is [owner_pack.md](owner_pack.md).
Ready-to-use copies (bitstream, scripts, `load_fda.sh`, check files) are in `~/Claude_sandbox/_bench/rp_visit_17e913f1/rp_patgen/` and `.../rp_freqcount/`, the whole package in `.../package_build_17e913f1/` (not committed, as in 235 and 243); the 243 folder carries a `REPLACED.txt`.

## Known gaps and limits

- No hardware result. The bus fix and the timing repair are proven in simulation and in the build only; the board has not seen build `17e913f1`.
- The one-clock extra latency changes what a poller sees in the single clock after a gate ends (section 2); a host that waits for DONE or MEAS_DONE is not affected.
- Timing margin is from one build; hold slack +0.011 ns is thin.
- The lock-step stimulus is one 1 MHz-class sine generator re-tuned between gates, not a random one; 19 gates.
- The xsim bus-path test is not in CI (needs Vivado and the vendor checkout).
- `hil/tests/test_225_redpitaya.py::test_the_checks_import_from_a_bare_directory` fails here and on `main` (sys.path truncation); not touched.

## Reproduce

The build needs a heavy slot and the network (the vendor repository at the pin); the simulation needs Vivado 2025.2 xsim; the block tests need only Python and iverilog. Each command below reproduces one family of results in this folder.

```
R=pilots/225
python3 tools/rp_shell.py prepare <dir> --block $R/rp_freqcount/agent_244_rtl/rp_freqcount.sv --block $R/rp_freqcount/agent_244_rtl/schmitt_edge.sv \
    $(for f in $R/rp_patgen/agent_235_r1_rtl/*.sv; do echo --block $f; done) --slot7 rp_freqcount --slot6 rp_patgen \
    --overlay boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc --explore
python3 tools/rp_shell.py build <dir> ; python3 tools/rp_shell.py package <dir> <out>                 # heavy slot, about 17 minutes, peak 4G
python3 hil/rp_bus_sim/run_xsim.py <dir> [--phase 4]                                                   # BUS PATH PASS
python3 -m hil.redpitaya_load script <out> --block rp_patgen --slot 6 --also rp_freqcount:7 -o <script>   # the owner's script (never run by the agent)
python3 -m pytest hil/tests/test_244_redpitaya_freqcount.py hil/tests/test_243_redpitaya_bus.py hil/tests/test_225_redpitaya.py hil/tests/test_235_redpitaya_followups.py agent/tests/test_235_block_for_shell.py
```
