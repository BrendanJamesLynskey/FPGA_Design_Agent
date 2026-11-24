# AGENT b64b_zedboard (fda-handover/1)
source: designs/b64b_zedboard/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b64b_zedboard

## identity
kind=demonstration produced_by=session part=xc7z020clg484-1 board=ZedBoard top=zb_hwsw_wrapper tool=Vivado 2026.1

## summary
Measures what a Cortex-A9 and the fabric of a Zynq-7000 cost each other, bare metal, on the ZedBoard. A PS7 with GP0, HP0 and ACP ports drives two AXI DMA to accelerator chains (CRC-32 or a 16-tap FIR) and a register plane with a latency probe and three bus-error blocks. Software against the HP path with cache maintenance against the coherent ACP path is swept over buffer sizes, and the A9's reaction to AXI SLVERR and DECERR responses is recorded for each memory mapping.
not: Linux, UIO, device-tree or kernel-driver measurements; bare metal only; the KR260 and the Cortex-A53; this folder is Zynq-7000 only; a power or energy measurement; the only power figure is the tool's estimate

## state
stage=board-verified vivado=2026.1 kb_pin=5e2eab8 build_id=None
gates: build_2026_1=pass board_run=pass

## interface
clk clk_fpga_0 100MHz
rst FCLK_RESET0_N active-low: from the PS, through a processor system reset block to every fabric block as aresetn (synchronous, active low)
if GP0 register plane AXI3 from the PS through a protocol converter to AXI4-Lite, our axil_xbar, generated register blocks: latency probe, error blocks and the accelerator control registers at the window base 0x40000000; accesses outside every block get DECERR from the crossbar, holes inside a block follow its unmapped setting doc=designs/b64b_zedboard/gen/regs/zb_lat_regs.md
if Bus-error blocks three generated register blocks, one per unmapped setting (okay, slverr, split): each has an error-capture register pair at offsets 0xFF8 and 0xFFC; the other two blocks have the same layout doc=designs/b64b_zedboard/gen/regs/zb_hole_split_regs.md
if DMA and accelerator chains AXI DMA simple mode, 32-bit AXI4-Stream into zb_accel, chain 0 on HP0 and chain 1 on the ACP: the ACP chain drives AxUSER 1 and AxCACHE 0011 so its accesses are coherent; the HP chain needs software cache maintenance doc=designs/b64b_zedboard/gen/regs/zb_accel_regs.md
if Console and logs PS UART1 at 115200 baud, 8N1 on the board's USB-UART; a copy of the console text is kept in DDR and read over JTAG: the DDR copy is the record because the UART has one reader at a time
param accelerator mode=CRC-32 or 16-tap FIR legal=register ACC_CTRL 0 or 1 (designs/b64b_zedboard/gen/regs/zb_accel_regs.md)
param stream width=32 bit legal=fixed

## files
designs/b64b_zedboard/vivado/build_full.tcl cd7fc70cec: block design and implementation script
designs/b64b_zedboard/vivado/ps7_zedboard.tcl 2dc453be73: PS7 configuration for the ZedBoard
designs/b64b_zedboard/rtl/zb_ctrl.sv 16dce53dab: register plane
designs/b64b_zedboard/rtl/zb_accel.sv aab15b8e30: CRC-32 or FIR accelerator on a stream
designs/b64b_zedboard/sw/rt.c 3455d06e38: bare-metal runtime (MMU, caches, UART, interrupts, abort handlers)
designs/b64b_zedboard/sw/t_err.c f401cda3f1: bus-error experiment
designs/b64b_zedboard/sw/acc_bench.h c8e0a77b0e: shared CRC and FIR offload benchmark
designs/b64b_zedboard/tcl/zb.tcl 3726c0c7ca: xsdb helpers (first load, light reload, DDR log read)
designs/b64b_zedboard/make_summary.py 9e0e2e8002: reads the committed reports and logs into results/64b_zedboard/summary.json

## commands
[heavy] build the bitstream and the XSA (~16min): vivado -mode batch -source designs/b64b_zedboard/vivado/build_full.tcl -tclargs <out dir> <repo root>
build the bare-metal programs (~1min): make -C designs/b64b_zedboard/sw t_crc.elf t_fir.elf hello.elf && bash designs/b64b_zedboard/sw/build_err.sh
run one program on the board (first load after a power cycle, then ZB_LIGHT=1) (~1min): ZB_SERIAL=<cable serial> XSA_DIR=<unzipped XSA> ZB_FIRST=1 designs/b64b_zedboard/run_elf.sh designs/b64b_zedboard/sw/hello.elf out.log 60
rebuild the summary record and the sweep tables (~1min): python3 designs/b64b_zedboard/make_summary.py && python3 designs/b64b_zedboard/summarise_sweeps.py results/64b_zedboard/sweeps/crc32_sweep.log results/64b_zedboard/sweeps/fir16_sweep.log

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b64b_zedboard/tb/zb_accel_tb.sv 12e8e58d33
R2 results/64b_zedboard/builds/full/timing.rpt 669c4f0579
R3 results/64b_zedboard/sweeps/crc32_sweep.log 7af7eb5977
R4 results/64b_zedboard/bus_errors/README.md 1ddc931ef1
R5 results/64b_zedboard/summary.json de263e4aea

## evidence
E1 simulation pass R1: accelerator testbench against independent references for the CRC and the FIR; run once by the first executor, not in CI
E2 build pass R2: whole design implemented on Vivado 2026.1; setup and hold slack positive at the PS clock
E3 board pass R3: CRC-32 and FIR sweeps; every output checked against the software result on every repetition, no mismatch in any size | cond: ZedBoard on its 12 V supply, junction temperature in the high thirties C, VCCINT 0.99 V, VCCAUX 1.80 V, VCCBRAM 0.99 V, no latched alarm (printed in the log)
E4 board pass R4: 30 bus-error runs of 200 accesses each, five targets, read and write, three memory mappings; the board stayed healthy | cond: as E3, the readings are in each run's log

## measured
M1 resources lut=17,335 LUT R5#build.lut: LUTs | routed, Vivado 2026.1, xc7z020clg484-1, includes the DMA, interconnect and both accelerators
M2 resources ff=15,935 FF R5#build.ff: flip-flops | as M1
M3 resources bram_tile=6 tiles R5#build.bram_tile: block RAM tiles | ditto
M4 resources dsp=0 DSP R5#build.dsp: DSP slices | as M1; the FIR is built from LUTs
M5 timing wns_ns=0.856 ns R5#build.wns_ns: worst setup slack | routed, 100 MHz PS clock
M6 timing whs_ns=0.012 ns R5#build.whs_ns: worst hold slack | as M5
M7 power power_w=1.765 W R5#build.power_w: total on-chip power estimate | report_power after routing, confidence Medium; the PS is included
M8 latency gp_read_ns=207 ns R5#gp.gp_read_id.p50_ns: uncached GP-port read of a PL register, median per timed pair | strongly ordered mapping, 4096 reads, includes a timer overhead of 39 ns, A9 global timer ticks of 3 ns
M9 latency irq_ns=250 ns R5#irq.caches_on_busy_loop.p50_ns: PL interrupt to bare-metal handler, median | MMU and caches on, busy loop, 2000 events timed by a PL counter on the 100 MHz clock
M10 latency irq_nocache_ns=1670 ns R5#irq.caches_off.p50_ns: PL interrupt to handler with MMU and caches off, median | as M9 but MMU and caches off
M11 throughput crc_sw_ns=350943 ns R5#crc32.sw_crc_slice8.65536.p50_ns: CRC-32 of 64 KB, software slice-by-8, median | 96 repetitions, input left dirty in the caches before each call
M12 throughput crc_hp_ns=351588 ns R5#crc32.hp_crc.65536.p50_ns: CRC-32 of 64 KB, HP path with cache maintenance, median | as M11; clean of the input and the DMA job and the result read are in the timed region
M13 throughput crc_acp_ns=166791 ns R5#crc32.acp_crc.65536.p50_ns: CRC-32 of 64 KB, coherent ACP path, median | as M12 without cache maintenance
M14 throughput fir_sw_ns=1.78393e+06 ns R5#fir16.sw_fir16.65536.p50_ns: 16-tap FIR of 64 KB, software, median | 96 repetitions, input left dirty in the caches before each call
M15 throughput fir_hp_ns=681765 ns R5#fir16.hp_fir16.65536.p50_ns: 16-tap FIR of 64 KB, HP path with cache maintenance, median | as M14; the whole output is read back
M16 throughput fir_acp_ns=294456 ns R5#fir16.acp_fir16.65536.p50_ns: 16-tap FIR of 64 KB, coherent ACP path, median | as M15 without cache maintenance

## gaps
[board_run] Linux was not run. UIO interrupt-to-user latency, access through devmem or UIO mmap and a kernel driver reacting to an error response are unmeasured, and SD-card writes need the owner's yes.
[E1] The accelerator testbench is not run by CI, and its result is the first executor's report, not a committed log.
[power] Power is the tool's estimate (confidence Medium) and no board power measurement was made; energy per result is not given.
[behaviour] With the normal non-cacheable mapping the error-capture count read 255 (it saturates) for 200 accesses, so more accesses reached the slave than the core issued; the cause is not known. DFAR is not reliable for an imprecise abort (stale in six of eight read runs). A write error with a device or non-cacheable mapping produced no abort in any run, so its only trace is the slave's capture register.
[statistics] Each timing is a median with min, 95th percentile and max over the repetitions in the log (hundreds at small sizes, a dozen at 1 MB); no confidence interval is computed, and one board, one bitstream and one power-up were used.
[wedges] The PS wedged three times on 2026-11-14 on full reloads. None occurred on 2026-11-15 with one full load after the power cycle and light reloads only, but the cause is not proven, so the first load and light-reload procedure in tcl/zb.tcl is a precaution.

## next_actions
1. Run the same three-way comparison on Linux (UIO latency, devmem and driver behaviour on an error response).
2. Find why the normal non-cacheable mapping shows more accesses at the slave than the core issued.
3. Put the same bus-error test on the KR260 Cortex-A53 and compare SError against the A9's abort.

## open_questions
- Is the posted-write error lost in the PS interconnect for every non-strongly-ordered mapping, or only for these buffering settings?

## history
2026-11-13 64B pr=-: design, first bring-up and latency measurements
2026-11-14 64B pr=-: PS wedges during full reloads; abort-path bugs fixed in the runtime
2026-11-15 64B pr=-: bus-error matrix, CRC and FIR sweeps, cost-model update and handover
