# ps_axi_lat: Cortex-A53 to programmable-logic AXI latency probe (brief 191, board row B-R8): datasheet and pre-registration

An idea from Edwards 2026 (ch 12: the host's access to the fabric is a few hundred nanoseconds, many times a whole fabric path, so what software may be asked to do must be fixed by measuring it).
On the KR260 the relevant cost is the processor system's (PS) Arm Cortex-A53 reading and writing registers in the programmable logic (PL) over AXI. Nothing in the repository measures it. This design is
a small PL image and a host program that do. **Nothing here has run on a board**: there are no runnable commands in this page on purpose (owner rule: commands only when it is time); the planner gives each step at
the board from `board/ps_axi_lat_session.sh`. Status: the probe RTL is simulated (all tests pass, seeded faults caught); the host program is built for the board's processor and its arithmetic is tested against a software
stand-in; the PL image's recipe (`build.yaml`, `ip/amd_ip_lat.tcl`) is written and **was not built** (see "Status").

## 1. What is measured

Two AXI masters of the PS reach the PL: `M_AXI_HPM0_FPD` (full-power domain; the one used for fast control registers) and `M_AXI_HPM0_LPD` (low-power domain; the one the debug bridge of build `dbg_xvc` uses). Each gets
one `axi_lat_probe` ([rtl/axi_lat_probe.sv](../rtl/axi_lat_probe.sv)) on `pl_clk0` (100 MHz, a fabric clock of 10 ns), 32-bit data, so a 32-bit access is a single AXI beat. The program
([host/ps_axi_lat.c](../host/ps_axi_lat.c)) maps a probe's 4 KiB window as Device memory and times accesses with two clocks that do not share an error: the Arm generic timer (`CNTVCT_EL0`, its tick read from `CNTFRQ_EL0` at run time; the
timer's tick is the resolution of every CPU-side figure) and the probe's own fabric counter (10 ns resolution). Figures, each over 200,000 observations per run, 5 runs per program start, 3 starts per port:

| Figure | What it is | Start and end events |
|---|---|---|
| `read_cpu` | one 32-bit load of CNT | timer read, `ldr` of the probe's CNT register, use of the data, timer read: from the first timer read to the clock the data is in a register |
| `read_fab` | the difference of two consecutive CNT values | the fabric clock in which each of two read requests was accepted at the probe's port (`arvalid && arready`), loop overhead included; fabric clocks of 10 ns |
| `write_cpu` | one 32-bit store of SCRATCH followed by `dsb sy` | timer read, `str`, `dsb sy` (it completes when the write response has come back), timer read |
| `rw_cpu` | a store of SCRATCH then a load of SCRATCH | timer read, `str`, `ldr`, use, timer read (Device memory is ordered: the load waits for the store) |
| `write_fab` | differences of the logged clocks of back-to-back TRIG writes with a `dsb sy` after each | the fabric clock in which each write was accepted at the probe's port; fabric clocks |
| `write_burst` | the same with no barrier between the stores | how fast the processor issues posted writes, seen by the fabric |

The probe's block itself answers a read request in the clock after it is accepted and a write response in the clock after both AW and W are in: its own contribution is 1 fabric clock and is in every figure.
The interval between two read requests at the port can be no smaller than 2 fabric clocks even for a perfect master (request, response, next request; simulated: [results/191_trading_variants/sim/probe_sim.json](../../../results/191_trading_variants/sim/probe_sim.json)).

## 2. Register map of the probe (what a user could guess wrong)

32-bit registers, 4 KiB window (the low 12 address bits are decoded). AXI4, single beat, 32-bit only (`AxLEN = 0`, `AxSIZE = 2`); anything else is answered SLVERR and counted in BAD (the processor never issues it for 32-bit
Device accesses). Reads of unmapped addresses return 0 with SLVERR; writes to unmapped or read-only addresses are ignored with SLVERR; a partial write strobe is refused (SLVERR). The counter is 32 bits and wraps (42.9 s at 100 MHz): software
uses differences modulo 2^32. Reset (the PS's `pl_resetn0`, synchronised) clears the counter and the registers; the log memory is not cleared, and `LOG_N` says how much of it is valid.

| Offset | Name | Access | Meaning |
|---|---|---|---|
| 0x000 | ID | RO | 0x50534C54 ("PSLT") |
| 0x004 | BUILD | RO | the build stamp: the first 8 hex digits of the hash of the image's sources, which the flow passes as `BUILD_STAMP` (0xB1910F01 when simulated or built outside the flow) |
| 0x008 | CLK_HZ | RO | the fabric clock in Hz (100,000,000) |
| 0x00C | SCRATCH | RW | data path check |
| 0x010 | CNT | RO | the counter in the clock this read request was accepted |
| 0x014 | WR_TS | RO | the counter in the clock the last write (any address) was accepted (AW and W both in) |
| 0x018 | WR_N | RO | writes accepted since reset or CLEAR |
| 0x01C | LOG_N | RO | TRIG writes logged (saturates at 256) |
| 0x020 | TRIG | WO | a write logs its acceptance clock into LOG; nothing is logged once the log is full |
| 0x024 | CTRL | WO | bit 0: clear LOG_N, WR_N and BAD (the log contents stay) |
| 0x028 | BAD | RO | accesses that were not single-beat 32-bit, were unmapped, or wrote a read-only register |
| 0x400 + 4 i | LOG[i] | RO | the acceptance clock of the i-th logged TRIG write |

## 3. Pre-registration (written before any board time, 2026-11-23)

**What would be measured and how it is judged.** There is no prior measurement of this system, so **no value is pre-registered as pass or fail**. The pass criteria are on the validity of the measurement (verdict script
[scripts/ps_axi_lat_verdict.py](../scripts/ps_axi_lat_verdict.py)): the ID and the build stamp match; no data mismatch in 20,000 random SCRATCH round trips per run and no bad access; every figure has at least 200,000 observations per run,
5 runs per start and 3 starts per port; operating conditions (CPU temperature and frequency, governor, kernel log) were read before and after and show no error. Each figure is quoted as the median of the run medians with the range of
the run medians (the spread over runs); the p99 and p99.9 only where the sample holds 100 observations beyond the percentile (p99 from 10,000 observations, p99.9 from 100,000), as the tail rule of `next_board_visit_plan.md` states.

**Hypotheses recorded in advance (reported as confirmed or not confirmed, not as pass or fail):**
- H1: the FPD port's `read_cpu` median is not larger than the LPD port's (the full-power domain's master is the fast one).
- H2: `write_cpu` (store plus `dsb sy`, which waits for the write response) is not smaller than `read_cpu` for the same port.
- H3: `write_burst` (stores with no barrier) is faster per write than `write_fab` (a barrier after each).

**Conditions the result depends on and the program does not change:** the CPU frequency and governor of the board's Ubuntu (recorded before and after), the PL clock (fixed in the image), the memory type (Device-nGnRnE, from `/dev/mem` with `O_SYNC`
or a UIO mapping), other load on the board (the program pins itself to CPU 2 and the board is otherwise idle), and the cable and supplies of the board (operating conditions are evidence: the CPU temperature and the kernel log are read at the start and the end; a run with an
error in the kernel log or a thermal event is void and repeated).

**Unconfirmed (to check at the board, in this order):** that `/dev/mem` accepts a mapping at 0xA0000000 and 0x80000000 on the board's Ubuntu kernel (the `CONFIG_STRICT_DEVMEM` setting may refuse it; the fallback is the overlay of
[board/pl-ps-axi-lat.dtsi](../board/pl-ps-axi-lat.dtsi) with `generic-uio`); that the PS addresses are the ones of the Zynq UltraScale+ address map (UG1085; confirm in the build's address report); that `CNTFRQ_EL0` is 100 MHz (the program
reads it and prints the tick); that `xmutil loadapp` accepts the app made by the session script.

## 4. Status, limits and next steps

- **Simulated, not built, not run on a board.** `tests/b191_cocotb.py`: identity and scratch, read and write timestamps against an edge-counting master (every timestamp checked), the log, bad accesses, a random mix against a model.
  Seeded faults in the RTL: `tests/run_mutants.py`. The host program is tested without a board (`tests/test_b191_host.py`: a software stand-in for the registers, the JSON, the verdict script, the aarch64 build).
- **The PL image was not built.** The recipe is written (`build.yaml`, `ip/amd_ip_lat.tcl` with the allow-list entry in `flow/ip_tcl_allow.yaml`, `design.xdc`); the image instantiates the Zynq UltraScale+ PS IP (`zynq_ultra_ps_e` 3.5, M_AXI_HPM0_FPD and
  M_AXI_HPM0_LPD at 32 bits, `pl_clk0` 100 MHz) and the two probes. The properties it names exist in Vivado 2026.1's IP definition; no run was made, so the clock constraint the PS IP supplies, the address assignment and the flow's gates are unchecked. A
  build is the first thing to do before the board visit (about 15 minutes, small).
- **Limits.** The figures are for 32-bit Device accesses by one core to a 100 MHz fabric slave; they are not the latency of the ACP, the HP ports or DMA, of cached accesses, of wider accesses, or of a faster PL clock (the PS-to-PL crossing's
  cost depends on the PL clock: a 250 MHz variant is a one-line change in `ip/amd_ip_lat.tcl`, not built). The fabric counter's 10 ns resolution quantises the fabric-side figures.
- **Next steps.** Build the image; run row B-R8; use the result to fix what a fast/slow loop split may ask of software (Edwards 2026, ch 12: the fast path never waits for the host); a second PL clock row.
