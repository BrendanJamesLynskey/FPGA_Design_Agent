# An application-optimised DRAM scheduler for the Nexys A7's DDR2: study, plan and phase 0 (brief 141)

Owner, 2026-11-21: "Is it possible that we could develop our own versions of memory controllers which are optimised for some application?" The answer after phase 0 is **yes, at two levels, and the
levels differ in what they can change**: a scheduler in front of AMD's MIG can change the order of requests and when refreshes happen; a scheduler that replaces MIG's controller and drives
AMD's PHY directly (a mode AMD documents) can change everything above the pins, including page policy and bank scheduling. Phase 0 builds the second kind in simulation, proves its timing rules,
measures two policies, and prepares (does not run) the hardware build and the board test. The context is the IP-library direction (owner decision 24, `_handoff/fpga_agent/owner_decisions_2026-11-19.md`):
a verified, FPGA-optimised block with a contract, a packaged harness and characterised variants; section 12 gives this block's entry in that form.

This page is the plan. The design is `designs/m141_ddr2_sched/` (README, handover and AGENT.md there say what was built and measured). Third-party documents are cited and linked, never copied: JEDEC,
Micron, AMD and LiteDRAM text is paraphrased, with the table, figure or file named so the reader can check it.

## 1. What phase 0 delivers, and what it does not

| Delivered | Where |
|---|---|
| Study: the part, the JEDEC rules, AMD MIG for 7 series, LiteDRAM, the design space | this page, sections 2 to 6 |
| Scheduler RTL v0: two policies, parameterised, on an abstract command interface | `designs/m141_ddr2_sched/rtl/ddr2_sched.sv`, `ddr2_addrmap.sv`; section 7 |
| Formal proofs of the timing rules and request order (SymbiYosys, k-induction with helper invariants), the refresh debt (property-directed reachability) and a bounded-response property | `designs/m141_ddr2_sched/verif/formal/`; section 9 |
| A behavioural DDR2 timing model (written from the data sheet) and a bench; measured latency, bandwidth and row-hit rate per policy for two access patterns | `tb/tb_ddr2.sv`, `tests/m141_measure.py`, `results/b141/sim_summary.json`; section 10 |
| Seeded faults: 16 deliberate bugs in the RTL the bench catches, 14 mutants the proofs catch | `tests/test_m141_*_rtl.py`, `verif/formal/run_formal.py` |
| Prepared, not run: the Vivado build plan with MIG and the pre-registered board test | sections 11 and 12 |
| Library entry in decision 24's form | section 13 |

Not delivered, on purpose: a bitstream, a board run, a data path (the scheduler issues commands; bursts follow them at fixed latencies and a PHY moves the data), the DDR2 initialisation and
calibration (AMD's PHY does that), power-down and self-refresh, ZQ and on-die termination control, multiple ranks, burst length 4, additive latency. Section 8 lists them as gaps.

## 2. The part and the rules that matter

The board has one Micron **MT47H64M16HR-25** (1 Gb, x16, 8 banks, 8192 rows of 1024 columns, 128 MiB) on a 1.8 V bank (Digilent Nexys A7 reference manual, section 3.1; part and settings in
`boards/nexys_a7_100t/inventory.yaml`, entry `ddr2`). Its data sheet is Micron's "1Gb: x4, x8, x16 DDR2 SDRAM", Rev. AB 09/18 ([link](https://www.micron.com/-/media/client/global/documents/products/data-sheet/dram/ddr2/1gb_ddr2.pdf);
a copy is in `_amd_docs/boards/nexys_a7/MT47H64M16.pdf`, the project's own archive).

**Clock.** The part's fastest grade (-25) runs at 400 MHz (tCK 2.5 ns, DDR2-800). The board cannot: Digilent's MIG settings (reference manual Table 3.1.1) give a maximum clock period of 3000 ps
(667 Mb/s) and recommend 3077 ps (650 Mb/s) because the clock primitives cannot make 400 MHz from the 100 MHz oscillator. Everything in this plan is therefore done for two **profiles**:
`nexys_650` (tCK 3077 ps, CL 5, the board's) and `ddr2_800` (tCK 2500 ps, CL 6, the part's limit, a cross-check). The scheduler's timing parameters are in command clocks and `tests/m141_timing.py` derives them from the
data sheet's picoseconds: each value is rounded up to whole clocks, the refresh interval down.

**Markings.** Digilent's reference manual names the part both "-25:H" (section 3.1 text) and "-25E" (Table 3.1.1, the MIG part). The -25E grade has tRCD = tRP = 12.5 ns, the -25 grade 15 ns (data sheet Table 12). The scheduler uses
the slower of the two for every parameter, so it is safe on either marking and loses at most one clock.

| Rule | Symbol | Data sheet value | Clocks, `nexys_650` | Clocks, `ddr2_800` | Source in the data sheet |
|---|---|---|---|---|---|
| ACTIVATE to READ/WRITE | tRCD | 15 ns | 5 | 6 | Table 12 |
| PRECHARGE period | tRP | 15 ns | 5 | 6 | Table 12 |
| PRECHARGE ALL period | tRPA | 17.5 ns | 6 | 7 | Table 12 (>= 1 Gb row) |
| ACTIVATE to PRECHARGE | tRAS | 40 ns minimum | 13 | 16 | Table 12 |
| ACTIVATE to ACTIVATE, same bank | tRC | 55 ns | 18 | 22 | Table 12 |
| ACTIVATE to ACTIVATE, other bank | tRRD | 10 ns (x16, 2 KB page) | 4 | 4 | Table 12 |
| Four-ACTIVATE window | tFAW | 50 ns (x16, 8-bank devices) | 17 | 20 | Table 12, note 38 |
| Write recovery | tWR | 15 ns | 5 | 6 | Table 12 |
| Write to read, after the data burst | tWTR | 7.5 ns | 3 | 3 | Table 12; Table 40 |
| Read to precharge | tRTP | 7.5 ns | 3 | 3 | Table 12; READ-to-PRECHARGE figures |
| REFRESH to next command | tRFC | 127.5 ns (1 Gb) | 42 | 51 | Table 12 |
| Average refresh interval | tREFI | 7.8 us (3.9 us above 85 C case) | 2534 | 3120 | Table 12; REFRESH section |
| CAS latency, write latency | CL, WL | CL; WL = CL - 1 (AL = 0) | 5, 4 | 6, 5 | Mode register; Figures 39, 40 |
| Burst length | BL | 8 (4 clocks of data) | 4 | 4 | |

Derived rules the RTL enforces (in the RTL as `RTW`, `R2P`, `W2P`, `W2R`; in the proofs under the same names):

- READ to WRITE command spacing `RL + BL/2 + 1 - WL` (= BL/2 + 2): one idle bus clock between the read burst and the write burst (Table 40 "READ with auto precharge to WRITE: BL/2 + 2"; Figure 50 READ-to-WRITE).
- WRITE to READ command spacing `WL + BL/2 + tWTR` (Table 40 gives `(CL - 1) + BL/2 + tWTR`; the same number).
- READ to PRECHARGE `BL/2 - 2 + max(tRTP, 2)` (AL = 0; READ-to-PRECHARGE figure).
- WRITE to PRECHARGE `WL + BL/2 + tWR`.
- Column to column `BL/2` (tCCD of 2 clocks is for BL4; with BL8 the data bus is the limit).
- tRC is **implied** by tRAS + tRP at these values (40 + 15 = 55 ns), so a short tRC alone cannot be seen in the command stream; the rule is still enforced and checked, and no mutant is made of it.
- Refresh: 8192 REFRESH commands per 64 ms; the data sheet allows bursting them (Table 12 note 1) and gives the average interval. The **postponement allowance** (at most 8 postponed, at most 9 x tREFI between
  two REFRESH commands) is JEDEC's (JESD79-2, refresh) and is not in the Micron data sheet text we hold; we do not have the JEDEC standard (it is behind a free registration). The scheduler keeps its own
  allowance `REF_POST` to 6 or fewer, so the debt never reaches 8, and the bench checks that no gap exceeds 9 x tREFI. **Open item:** confirm the allowance against JESD79-2F before a board run.

The temperature rule matters for a board: above 85 C case temperature the refresh interval halves (3.9 us); the scheduler assumes the commercial range and a case below 85 C (an open item for the board test,
which reads the FPGA's XADC temperature as a proxy and does not measure the DRAM case).

## 3. AMD's MIG for the 7 series (UG586 v4.2): what is fixed and what is free

Source: AMD UG586 "7 Series FPGAs Memory Interface Solutions User Guide", v4.2, 2024-11-13 (copy: `_amd_docs/UG586_ug586_7Series_MIS-en-us-4.2.pdf`). Page numbers below are that document's.

**Layers.** The MIG core is four layers: the **user interface** (UI: a flat address space, `app_en`, `app_cmd`, `app_addr`, `app_rdy`, the write-data and read-data FIFO handshakes), the **native interface**
(the front of the memory controller, the same requests without the buffering), the **memory controller** (MC: bank machines, a row/column arbiter, rank machines, refresh and "periodic read" logic;
`user_design/rtl/controller`, Table 6), and the **PHY** (`user_design/rtl/phy`, Table 8: the I/O byte lanes, PHASER_IN and PHASER_OUT, the PHY control block and its FIFOs, initialisation and calibration:
write leveling, read leveling, write calibration). The PHY and its calibration are AMD's; the MC is soft logic AMD generates into the project.

**Fixed by AMD, whatever we do.**

- The PHY: the I/O structure, PHASERs, the FIFOs between the fabric and the I/O, initialisation (MRS, ZQ) and calibration. `init_calib_complete` says the part is ready.
- The clocking: a memory clock that must be derived with the MMCM/PLL, a PHY-to-controller clock ratio of 2:1 or 4:1 (UG586, Controller Options: 2:1 has lower latency and a lower maximum memory frequency;
  4:1 is needed for the highest data rates), and a memory clock no faster than the Nexys A7's 3000 ps. At 3077 ps, 4:1 gives a 81.25 MHz controller clock and 2:1 gives 162.5 MHz.
- The pin-out: fixed by the board (the MIG's pin file; `inventory.yaml` says the master XDC has none).
- A memory controller that, when it is the MIG's own, decides page policy (a bank machine keeps a row open until a conflict or the end of its request queue; the exact rules are in
  `bank_state.v` and `bank_queue.v`, which we have not read in the generated source, an open item), command arbitration (round-robin among bank machines, UG586: "the round-robin arbiter itself is a source
  of reordering"), the placement of refresh and of periodic reads, and the timing counters.

**Free at the native or user interface.**

- **Ordering mode** (UG586, Controller Options; the native-interface ordering modes): STRICT (commands issued in request order, lowest latency, read data in order), NORM (reads may be reordered, writes are
  not, requests within a rank-bank retire in order), RELAXED (reads and writes may be reordered between rank-bank queues). The UI hides the reordering from the user by returning reads in order.
- **Number of bank machines** (a generator option).
- **User-controlled refresh** (UG586, "User Refresh"): set the `USER_REFRESH` parameter to "ON" to disable the controller-managed maintenance, then request each REFRESH with a one-clock pulse of
  `app_ref_req` and wait for `app_ref_ack`. `app_zq_req`/`app_zq_ack` do the same for ZQ calibration. **This is the lever for refresh placement at MIG's level**: the user logic decides when to refresh,
  including postponing within the allowance for a latency-critical window.
- The request stream itself: what is submitted and when.

**What a scheduler in front of MIG cannot do** (level A below): choose page policy, issue ACTIVATE early for a request that has not arrived, precharge eagerly, batch writes at the command level, or see the DRAM state.
It sees only `app_rdy`. The MC below it may reorder its own way within the ordering mode.

**The PHY-only interface** (UG586, "Physical Layer Interface (Non-Memory Controller Design)", pp. 155 to 157, Table 61): AMD documents using the PHY without the MC. The PHY's front end is the PHY control FIFO
and the command and write-data OUT_FIFOs; commands go in through "slots" (one per memory clock within a controller clock: four in 4:1), the CAS slot number depends on CWL (odd CWL: slots 1 or 3; even: 0 or 2),
and the controller must watch the three FIFO full flags (`phy_mc_ctl_full`, `phy_mc_cmd_full`, `phy_mc_data_full`). AMD states what a custom controller must add: **periodic reads** every 1 us when the bus
is idle or only writing (two back-to-back BL8 reads) to keep PHASER_IN's ICLK aligned to DQS ("Customers using the PHY only design must include the periodic read logic within the custom controller"), and
**`tempmon_sample_en`** driven around each REF or ZQ. The MIG controller is the worked example (`mem_intfc.v` instantiates both).

### What phase 1 needs, per level

| Level | What changes | What the user must supply | Reach | Cost |
|---|---|---|---|---|
| **A** a scheduler in front of the native interface, `USER_REFRESH` on | request order and refresh timing | requests and refresh requests; nothing else | refresh placement, request reordering, write batching at the request level | small; limited by what the MC does below |
| **B** our scheduler replaces the MC, on AMD's PHY (PHY-only mode) | page policy, ACTIVATE/PRECHARGE timing, bank scheduling, refresh, direction batching: the whole command stream | the scheduler (this block), the slot packing (up to four commands per controller clock), the data path to the PHY's FIFOs, periodic reads, `tempmon_sample_en`, FIFO-full handling, init_calib_complete handshake | everything above the PHY | medium: the PHY interface is documented but intricate; the first build is the risk |
| **C** our own PHY (LiteDRAM style) | the pins, the calibration | everything | everything, including calibration | large; section 5 |

Phase 0 builds the scheduler for level B and keeps its request side narrow enough that level A can reuse the policies (the request queue, the ordering rule, the refresh knobs). The mapping, concretely:

| Scheduler (this design) | Level B (PHY-only) | Level A (native interface, `USER_REFRESH` on) |
|---|---|---|
| `req_*` (burst address, direction, tag) | the user side of the block | `app_en`, `app_cmd`, `app_addr` with `app_rdy` backpressure; the data goes through the UI's write and read FIFOs |
| `cmd_op` ACT, PRE, PREA | PHY control words in the ACT/PRE slots | not exposed (the MC issues them); the scheduler's bank model is advisory only |
| `cmd_op` RD, WR + `cmd_tag` | CAS slot per CWL parity; the tag follows the data through the read path | `app_cmd` = read or write; data comes back in order at the UI |
| `cmd_op` REF + `ref_defer` | REF in a command slot; refresh debt in the scheduler | `app_ref_req` / `app_ref_ack` with the debt counted in the scheduler |
| `en` | `init_calib_complete` | `init_calib_complete` |
| timing in command clocks (one command a clock) | four command slots per controller clock in 4:1: a wrapper issues up to four decisions per clock or the scheduler is clocked at the memory clock's quarter with a four-wide decision (see section 11) | not needed |

The scheduler's command output is one command per clock of a clock whose period is tCK. At level B the real controller clock is tCK x 4 (or x 2), so the phase-1 work is to make the decision logic produce up to four
commands per controller clock (the timing counters already count in tCK; the arbiter would pick up to four non-conflicting commands). Phase 0 does not do this and its clock closes at the fabric's speed
(section 11), well below 400 MHz; that is the single largest open engineering item and is stated as a gap.

## 4. What the owner's question asks for: where application optimisation lives

A general controller (MIG's) is tuned for average throughput over unknown traffic. A controller optimised for an application wins by exploiting something the general one cannot know:

- **Trading-style random reads** (the project's FPGA expertise direction): few outstanding requests, uniformly random addresses, latency the figure of merit, and above all a **predictable** latency (the tail, not
  the mean). What helps: the bank is already precharged when the read arrives (eager precharge removes tRP from the critical path), reads are not delayed behind writes (read priority, write batching), and refresh
  does not hit the critical window (postpone within the allowance, do it in idle time). What does not help: a deep reorder queue (it adds nothing at one outstanding request).
- **Streaming bandwidth** (DMA, video): long runs of sequential addresses, bandwidth the figure of merit. What helps: an address map that keeps a stream in an open row and rotates banks so row cycles overlap, open-page
  policy (no precharge until a conflict), first-ready first-come-first-served, long same-direction runs (every read/write turnaround costs `WL + BL/2 + tWTR` or `RL + BL/2 + 1 - WL` clocks).

The two are in tension (eager precharge costs row hits; direction batching costs read latency), which is why the scheduler has two policies selected by a parameter, and why each is measured on both patterns (section 10).

## 5. LiteDRAM, the open-source alternative

[LiteDRAM](https://github.com/enjoy-digital/litedram) (Enjoy-Digital, from M-Labs' LASMICON) is an open-source DRAM controller and PHY generator in Migen/LiteX. It supports Xilinx Artix-7 DDR2 and DDR3 with its own
PHY (`s7ddrphy`; 1:2 or 1:4 frequency ratio), and the LiteX board target for the Nexys 4 DDR, the same board family as ours, uses it with an `MT47H64M16` module definition
(`litex-boards`, `targets/digilent_nexys4ddr.py`; `litedram/modules.py` class `MT47H64M16`: tRP, tRCD, tWR 15 ns, tRFC 127.5 ns, tWTR 7.5 ns: the same numbers we use).

**Licence: BSD 2-Clause** (LICENSE in the repository; "Unless otherwise noted, LiteDRAM is Copyright 2012-2024 / EnjoyDigital"; initial development based on M-Labs' LASMICON). Reuse is permitted with the copyright
notice and disclaimer retained in source and binary distributions. **Nothing is copied into this repository in phase 0**; if a later phase reuses LiteDRAM source (for instance its PHY for level C), the notice must be kept
and recorded in `THIRD_PARTY_NOTICES.md`.

**Architecture** (from its README and `litedram/core`): a crossbar of user ports, a controller of one bank machine per bank (page policy and the row-hit logic live there), a multiplexer that arbitrates between bank machines
with read/write time slices ("anti-starvation": the maximum time the multiplexer keeps issuing in one direction), a refresher with a configurable postponing (`refresh_postponing`, default 1), and a DFI interface to the PHY.
Address mapping is selectable (`ROW_BANK_COL` default, `BANK_ROW_COL`, ...).

**What it tells us.** The structure (per-bank state machines + a direction-time-sliced arbiter) is the standard answer; our scheduler centralises the decision (one queue, one pick) because a small queue and one
command per clock make a global pick affordable and make the formal proofs one state machine rather than a network. LiteDRAM is the second comparison arm for the board test if its build is practical
(section 12) and the natural basis for level C.

## 6. The design space for the scheduler

| Axis | Options | Phase 0 choice | Why |
|---|---|---|---|
| Page policy | open; closed (auto-precharge); adaptive | latency-first: **eager precharge** (close a bank as soon as no queued request wants its open row); bandwidth-first: **open page** (close only on a conflict) | eager precharge removes tRP from a random read; open page keeps stream hits |
| Address mapping | row-bank-column; interleaved low bank bits | `ddr2_addrmap` MAP 0, 1, 2 | MAP 0 keeps a stream in a row, MAP 2 maximises bank overlap; measured (section 10) |
| Reordering | none; first-ready first-come-first-served; full | FR-FCFS in bandwidth-first, oldest-ready-first in latency-first; both with a **same-address order rule** (a request never overtakes an older request to the same address when one of the two is a write) | correctness first: read-after-write order is observable |
| Read priority | none; reads first | latency-first: reads first | a read waits behind a write by up to the write-to-read turnaround |
| Write combining | none; batch | **batch**: latency-first drains writes in batches between watermarks (`WR_HI`, `WR_LO`); bandwidth-first stays in a direction for up to `RUN_MAX` column commands | each turnaround costs 7 to 12 clocks |
| Refresh | at due time; postponed; opportunistic in idle time; user-timed | postponed up to `REF_POST` and during a `ref_defer` window, otherwise in idle time; forced when the allowance is used | tail latency; JEDEC allows postponing |
| Fairness | none; aging | **aging**: the oldest request is served alone once it has waited `AGE_LIM` clocks | a bounded wait is a property that can be proved |
| Queue | per-bank queues; one queue | one queue of `QD` entries with an age matrix and a dependency vector | small, formal-friendly |
| Not done | per-rank logic, BL4/BL8 choice, auto-precharge commands, ODT, ZQ, power-down, self-refresh | | scope |

## 7. The scheduler v0

`designs/m141_ddr2_sched/rtl/ddr2_sched.sv` (header comment has the full description). Summary of the **interface contract**, written without knowing the system around it:

- **Clock and reset**: one clock; one synchronous active-high reset, applied once before `en` (a reset in the middle of operation forgets the open banks of a real part and is not supported: the proofs assume it never happens). `en` is "the part is initialised and precharged"; hold it low until `init_calib_complete`; it stays high.
- **Requests** (`req_v`/`req_rdy`, `req_wr`, `req_addr` = `{row, bank, burst column}` through `ddr2_addrmap`, `req_tag`): a handshake; `req_rdy` is high while a queue entry is free and `en` is high; it does not depend on `req_v`. One request is one BL8 burst.
- **Commands** (`cmd_v`, `cmd_op`, `cmd_bank`, `cmd_row`, `cmd_col`, `cmd_tag`): registered; one command a clock; the decision in clock t is on the output in clock t+1. `cmd_tag` accompanies the READ or WRITE. The data burst of a READ is on the data bus RL
  clocks after the command and of a WRITE WL clocks after it.
- **Latency**: from `req_v && req_rdy` to the column command on `cmd_*`: at least 2 clocks to the first command (decision, register) plus the timing rules; with a closed bank, 2 + tRCD, with an open row, 2 (a hit).
- **Ordering**: out of order except that a request never overtakes an older request to the same burst address if either is a write.
- **Refresh**: one REFRESH falls due every tREFI after `en`; the scheduler keeps the debt, postpones while reads are pending (latency-first), while `ref_defer` is high (both), and issues when the allowance `REF_POST` is used or in idle time. A refresh once started runs to its REFRESH command (PREA, REF) and blocks new column and ACTIVATE commands meanwhile.
- **Bounded wait**: a request is served within `AGE_LIM + QD x R_MAX + refresh cost` clocks, with `R_MAX` the worst forced service (formula in `verif/formal/run_formal.py:bound`, proved at small parameters, measured at real ones).
- **What a user could guess wrong**: (1) the READ and WRITE data bursts are not part of this block; (2) the output is registered, so spacings are measured on the output, not on the decision; (3) there is no response channel, the column command *is* the completion
  of scheduling (data follows at the fixed latency); (4) a reset in the middle of operation is unsupported; (5) a write is not forwarded to a later read of the same address: the read waits until the write's column command has issued; (6) `ref_defer` is a request, not an override: the allowance is still enforced;
  (7) the tRC rule is implied by tRAS + tRP at the data sheet's values; (8) latency figures count from the handshake clock.

## 8. Gaps and limits of phase 0 (also in the handover)

- No data path, no PHY, no MIG: the scheduler is verified against a behavioural model of the DRAM's command rules, not against the part or a MIG PHY.
- One command per clock at tCK: a controller clock four times slower needs a four-wide decision (section 3, last paragraph).
- No periodic reads, `tempmon_sample_en` or FIFO flow control (level B's own requirements), no ZQ, no ODT, no init sequence, no power-down, no self-refresh.
- JEDEC's refresh postponement allowance is taken from memory of JESD79-2 and checked only against the bench's 9 x tREFI rule, not the standard's text.
- The bounded-response proof is at small parameters (2 banks, 3 queue entries); the real-parameter evidence is simulation.
- The timing proofs hold for the properties as written; a rule the data sheet has and we did not write (tXP, tCKE, tMRD, tDAL with auto-precharge, tXSNR) is not checked because the scheduler never issues those commands.
- Simulation speed (Icarus) limits run lengths; the distributions are from thousands of requests, not millions.

## 9. Verification: the model, the proofs and what they are worth

**The model** (`designs/m141_ddr2_sched/tb/tb_ddr2.sv`). A behavioural DDR2 written from the data sheet, in the bench, independent of the scheduler's timers: it keeps absolute clock stamps for the last ACTIVATE, PRECHARGE, READ, WRITE and REFRESH of each bank and
checks every command on the bus against the rules of section 2 in picoseconds converted to clocks by its own ceiling function. It also checks the bank state (a column command needs the bank open on the request's row; ACTIVATE needs a closed bank; REFRESH needs every bank closed), the data bus (no
overlap, one idle clock between a read burst and a write burst, tWTR after a write burst), the refresh obligation (the gap between REFRESH commands at most 9 x tREFI) and request integrity (each request gets exactly one column command with its own bank, column and direction, in an order that keeps
same-address order). It uses no vendor model: Micron's DDR2 simulation model was not fetched (its licence was not checked), so there is nothing to keep outside the repository. This is a limit: the model encodes our reading of the data sheet.

**The seeded faults** (`tests/test_m141_faults_rtl.py`): 16 deliberate bugs in a copy of the RTL (a timing constant short, the dependency check removed, refresh disabled, REFRESH with a bank open, a wrong bank on the command bus, a wrong row opened) must each make the bench report a violation.
Two were missed at first and the traffic had to change to reach them (the read-to-write spacing is only exercised when a write finds its row already open, which the hazard-stress pattern produces and the random patterns do not; REFRESH with a bank open needs a busy run past a refresh): a mutant the bench cannot see is a gap in the traffic, and the list records the traffic that finds each one.
tRC has no mutant: it is implied by tRAS + tRP at the data sheet's values.

**The proofs** (`verif/formal/`, SymbiYosys with the slang front end, OSS CAD Suite 2026-11-12, the release CI pins). The properties are bound to the RTL (`ddr2_bind.sv`), which is not edited, and are written as Boolean assertions (the free front end reads no `|->` or `##`; each assertion's SVA form is in its comment).

- **Independence.** The monitor (`ddr2_props.sv`) watches only the registered command output and keeps, for each kind of event, the number of clocks since it last happened (saturating) and the open or closed state of each bank. The RTL enforces the rules with down-counters loaded at each decision. A rule is "the age of the earlier
  event is at least N when the later command is on the bus": 25 assertions, one per rule (the per-bank ones over a generate loop).
- **Timing rules and request order: unbounded proofs.** By k-induction at depth 3 (`smtbmc boolector`), for the real data sheet constants (eight banks) and for the small constants, both policies, for every request sequence the front end can present. The induction needs **helper invariants** that tie each RTL counter to the monitor's age
  (`counter + age + 1 >= N`, one per rule and bank, a stronger pairing for tFAW's four counters, banks closed while the REFRESH timer runs, the bank state of the RTL equal to the monitor's): without them the induction fails at a state the design cannot reach, and property-directed reachability alone had not converged on the real constants after about six minutes (it was stopped) while it
  did converge on the small constants (275 s). With them, every rule is proved in seconds. Each invariant is itself checked in the same run; the induction step for the ordering proof needed five more (the tracked requests are real queue slots with the addresses the monitor recorded, B waits for A through the dependency vector).
- **Refresh never starved.** The debt of refreshes due and not yet issued never exceeds `REF_POST + 2`, and a REFRESH is only issued when one is due. By property-directed reachability: seconds at the small constants, and minutes at the real constants with tREFI at the elaboration guard's minimum (the worst case for the property; a longer tREFI gives the forced sequence more time).
- **Bounded response.** A tracked request (chosen freely by the solver) is served within `bound(...)` clocks of entering the queue: bounded model check from reset to the bound plus six clocks at small parameters (`abc bmc3`), a check not a proof for all time. The formula and its terms are in `run_formal.py:bound`; at the real parameters it is a number of clocks that the saturated simulations stay under (section 10).
- **Covers** (`smtbmc`, 220 steps): every command kind, a read soon after a write and a write soon after a read, the tracked request served, a refresh debt of two, and two requests ordered by the dependency vector are all reachable, so the proofs are not vacuous.
- **Mutants**: 14 seeded bugs, one per rule or property (the timing constants one or more clocks short, the refresh never requested, the dependency vector removed, the aging removed), each caught by a named assertion (`run_formal.py` lists which).

**What the proofs are worth.** The timing rules are proved of the command stream the scheduler emits, against our monitor, which is our reading of the data sheet; they say nothing about the part, the PHY or JEDEC's text beyond that reading. The proofs hold for the properties as written: a rule the scheduler never exercises (tXP, tCKE, tMRD, auto-precharge tDAL) has no property.
The one defect the proofs surfaced was in the monitor, not the RTL: the ordering monitor re-picked its first request after it was served and so judged a later request against an unrelated one; the fix was to pick each tracked request once. The proofs found no RTL bug; the simulations found one design flaw (section 10).

## 10. Results (simulation; `results/b141/sim_summary.json`, tables in `designs/m141_ddr2_sched/docs/results.md`)

All at the `nexys_650` profile (tCK 3077 ps, CL 5) unless said; latency is clocks from the request handshake to the first data beat of the command bus model, without any PHY pipeline (a real PHY adds a fixed amount that the board test measures);
every run has zero violations of the DDR2 model. Peak bandwidth is 4 bytes a clock (2 bytes, 2 beats), 1.30 GB/s at this clock.

**Random reads, light load** (one request every 40 clocks on average, 3000 reads).

- Latency-first: median 12 clocks (37 ns), p99 31, p99.9 53, maximum 59 (182 ns).
- Bandwidth-first: median 17 clocks (52 ns), p99 47, p99.9 78, maximum 82 (252 ns).
- The 5 clocks between the two medians are the PRECHARGE time (tRP is 5 clocks at this profile): the open-page policy finds the previous row open and pays PRECHARGE before ACTIVATE; eager precharge has already paid it. The hypothesis of the owner's question holds in the model, to the clock.
- The tail is a refresh landing on a read: the latency-first maximum is 59 clocks with refresh postponed (`REF_POST` 4) and 73 with `REF_POST` 0.
- With reads in related bursts (the `lat_bursts` runs) the open-page policy wins: median 7 clocks against 12, because the burst's later reads hit the open row (0.18 ACTIVATEs per column command against 0.88). **The better policy depends on the application's address locality**, which is the answer to "optimised for some application".
- Under heavier random load (a request every 8 clocks on average) the medians stay at 12 and 17 and the tails grow (69 and 95 clocks at p99.9).
- **Refresh in a latency-critical window.** `ref_defer` high for 5000 of every 12000 clocks (a window of about two refresh intervals), latency-first. With `REF_POST` 0 the refreshes that fall due in the window are done in it: the reads accepted in the window have a p99.9 of 72 clocks (222 ns) and a maximum of 73 (225 ns). With `REF_POST` 4 they are postponed and done after the window: p99.9 26 clocks (80 ns), maximum 28 (86 ns), and the reads outside the window pay for it (p99.9 85 against 53, maximum 91 against 73). The shift is the point: the tail moves out of the window the application cares about; it is not removed.
- A cross-check at the part's own fastest clock (`ddr2_800`, tCK 2500 ps, CL 6): zero violations, median 14 and 20 clocks (latency-first, bandwidth-first, 30 % writes).

**Bandwidth** (data-bus utilisation = data clocks over elapsed clocks; GB/s of the 1.30 peak).

- Sequential read stream: 0.980 for both policies with the page-interleaved map (the bus is busy on every clock but the refreshes: both use `REF_POST` 0 in the bandwidth runs, so a refresh postponed past the end of a short run does not flatter either), and the same with maps 1 and 2 (0.980, 0.980): a pure read stream needs no policy.
- Copy (alternating read and write streams in two regions): this is where the policies differ. Bandwidth-first reaches 0.762 with the page-interleaved map, 0.814 with map 1 and 0.861 with every burst to the next bank (map 2); latency-first 0.669, 0.710, 0.810.
  The two streams sit in one bank under map 0, so every direction change is a row conflict; interleaving the banks (maps 1 and 2) removes that. Fewer turnarounds is the other lever: a deeper queue lets the bandwidth policy batch longer (queue of 8, 16, 32: 0.760, 0.796, 0.809), at the price of every request waiting longer (median read latency 56, 116, 194 clocks).
- Saturated random access: reads only 0.845 and 0.855 (equal: bank parallelism is the limit); reads and writes 0.735 (latency-first) against 0.665 (bandwidth-first). **Bandwidth-first is not better everywhere**: on random mixed traffic its direction runs are short and latency-first's watermarks batch the writes better. The names describe the intent, and the measurement says which wins where.

**A flaw the simulations found.** With the first default `AGE_LIM` of 64 clocks the bandwidth-first copy run reached only 0.224 (against 0.760 at 256 and above): in a full queue every request waits longer than 64 clocks, so the oldest was always "aged", the scheduler served it alone, and the queue degenerated to first-come first-served with a row conflict and a bus turnaround on nearly every request.
The aging is the price of a provable bound and its limit must exceed the wait of a request in a full queue; the default is now 1024 and the handover and `blocks.md` say so. The formal proofs could not have found this: it is a performance property, not a rule. The wasted ACTIVATEs are visible too: above 1 ACTIVATE per column command means a row was opened and closed again before its column command (a refresh or a direction change closed it).

**Bounded wait at real parameters.** The longest wait of any request in the saturated runs is 296 clocks at a queue of 8 (and 422 at a queue of 32), well under the proved-form bound of 1507 clocks for a queue of 8 at the default `AGE_LIM` (the bound is loose by design: it assumes the worst forced service for every entry ahead). At `AGE_LIM` 64 the longest wait is 225 against a bound of 547.
The simulation test (`test_wait_bound_holds_in_a_saturated_run`) checks both.

## 11. Vivado build plan with MIG (prepared, not run)

Goal of the first build: show that the scheduler and a MIG PHY fit the Nexys A7-100T (`xc7a100tcsg324-1`), that every clock is right, and that the design passes the project's gates, before any board time.
No command is shown here: the owner's rule is that a runnable board or build command appears only when it is time to run it, and this one is not scheduled. What follows is the plan in words.

1. **Take one heavy slot** with a text that starts "141:" and names Vivado and its peak memory; one Vivado implementation run, alone or beside a run the admission rule allows; wall power for the board part later, not now.
2. **Generate the MIG core** with Digilent's settings (reference manual Table 3.1.1: DDR2 SDRAM, clock period 3077 ps, part MT47H64M16HR-25E, data width 16, data mask on, chip select on, Rtt 50 ohm, internal Vref on) and the pin-out from Digilent's MIG pin file
   (names and links only are kept in this repository; the file's content is Digilent's). Generate three variants of the same core: **R** (reference: native interface, ordering NORM), **S** (ordering STRICT), **U** (`USER_REFRESH` on, for level A).
   The level B variant takes the generated PHY files (`user_design/rtl/phy`, the clocking files) and the MIG controller's `mem_intfc.v` as the worked example of the PHY interface (UG586 p. 155 onward); whether the Vivado generator can emit
   the PHY without the controller or the controller is replaced by hand in the generated sources is **the first thing the build plan must find out** (UG586 documents the interface; the generator option is not described in the text we hold).
3. **Top level**: the 100 MHz oscillator into an MMCM that makes the memory clock (325 MHz), the 200 MHz reference for IDELAYCTRL and the controller clock (81.25 MHz in 4:1; the ratio is a generator choice, 2:1 gives 162.5 MHz and lower latency, UG586), reset from the CPU_RESETN button through the standard synchroniser,
   `init_calib_complete` to an LED and to `en`.
4. **Measurement fabric** (shared by every arm): a request generator that replays the pattern seeds of `tb/tb_ddr2.sv` (xorshift32, the same sequence), a free-running controller-clock counter for timestamps, a latency histogram in block RAM (one bin per controller clock), bandwidth counters, and a read-back register block
   over the existing UART shell (`shell/`). Data integrity: every write has a known pattern and a read-back compare.
5. **Gates to read on the first build**: synthesis and implementation complete; timing met at the memory and controller clocks (WNS and WHS recorded with the clock names); `report_methodology`, DRC and CDC (the user-to-controller crossing and the PHY's own); the scheduler's utilisation and Fmax out of context first (an out-of-context run
   of `ddr2_sched` alone, which does not need MIG, is the cheapest first step and was not done in phase 0: both heavy slots were taken by other sessions during the work, and the block has no hardware number yet).
6. **Expected finding to check**: the scheduler's decision logic is a combinational scan of an eight-entry queue and an eight-bank timer file; at one decision per clock it will close at a controller-clock rate, not at the memory-clock rate; the four-slot packing of section 3 is the design change that follows.

## 12. Pre-registered board test (prepared, not run)

Written before any board result exists, so that the outcome cannot move the criteria. Board: the Nexys A7-100T on wall power (JP3 = WALL; `inventory.yaml` says the DDR2 alone can draw 0.47 W from the 0.8 A 1.8 V rail and that a MIG design is large:
run `report_power` first; USB power is not enough), room temperature, the FPGA's XADC temperature logged with every run. One board, one DRAM part.

**Arms** (each its own bitstream, the same measurement fabric): (R) MIG's own controller, ordering NORM; (S) MIG, ordering STRICT; (A) our scheduler in front of the native interface with `USER_REFRESH` on (level A); (B0) our scheduler on the PHY, latency-first (level B);
(B1) our scheduler on the PHY, bandwidth-first (level B); (L) LiteDRAM for this board built with LiteX, **only if its build and the same measurement fabric are practical in one session**; it is the optional arm and its absence is not a failure.

**Workloads**, the patterns of the simulation with their seeds: P0 random reads at light load (one request every 40 memory clocks on average, the simulation's figure; on the board the generator uses the same mean gap converted to controller clocks), P1 random reads with 30 % writes, P2 sequential read stream, P3 copy (read stream plus write stream), P4 bursts of related reads, P5 hazard stress (read-modify-write on a small address set),
and the refresh experiment (P0 with `ref_defer` held for a window, and with the refresh postponement set to 0 and to 4).

**Measurements.** Read latency from request accepted to first data beat, as a histogram (bin = one controller clock; at 4:1 that is 12.3 ns, so a difference smaller than one bin is not resolved: this is a limit of the instrument, stated now);
bandwidth as data bursts per elapsed time; row-hit rate is not observable on the MIG arms and is reported for ours only; refresh count from the DRAM's side is not observable, the scheduler's own counter is; data integrity from the read-back compare. At least 5 runs per arm and workload, in a randomised order, with a pause that returns the FPGA to the same XADC temperature
(within 2 C), 100000 requests per run for P0 to P4 and 10 million operations for P5.

**Pre-registered hypotheses, each with what would falsify it.**

- **H1 (latency)**: on P0 the median read latency of B0 is lower than that of R by at least the PRECHARGE time the eager precharge hides (tRP, 5 memory clocks = 15.4 ns, 1.25 controller clocks at 4:1); falsified if the medians differ by less than one bin or R is lower.
  This hypothesis assumes MIG leaves a row open after a read; if the generated controller closes it, there is no difference to find, and that is a finding, not a failure of B0.
- **H2 (tail)**: on P0 with `ref_defer` held for a window, no read in the window has a latency above the window's own p99.9 outside the window plus one bin (refresh did not land in it); falsified by one read in the window that waits a tRFC. Arm A tests the same with `app_ref_req` timing.
- **H3 (bandwidth)**: on P2, B1's bandwidth is within 5 % of the better of R and S; falsified by more than 5 % below. (We do not claim a win here: MIG's controller is tuned for streams; a tie is the expected result.)
- **H4 (ordering and integrity)**: P5 and every read-back compare finish with zero mismatches on every arm; falsified by one.
- **H5 (predictability)**: on P0, p99.9 minus median is smaller for B0 than for R; falsified otherwise. This is the figure of merit the trading direction cares about.

**Stop and abort rules**: calibration not complete within a stated time, a read-back mismatch on any arm (stop, do not average), XADC temperature above 70 C (the part's case temperature limit is not read, the proxy is conservative), a power-supply trip. **Reporting**: every run's histogram is kept in the results folder; medians, p99, p99.9 and max per arm; all five runs shown; arms that did not run said so; the simulation's prediction for B0 and B1 next to the board result with the difference named, never merged into one number (the project's latency-path rule).

## 13. Library entry (owner decision 24)

This block's entry in the IP library's form. It is held in this design, not yet in `ip_lib/`, because the entry's per-family characterisation needs Vivado runs that phase 0 did not make (section 11, step 5).

- **Interface contract** (written without the larger design): section 7 of this page; the ports are in `rtl/ddr2_sched.sv`; the clock and reset assumptions are one clock and one reset applied before `en`; the data path, calibration and initialisation are the integrator's (a PHY's).
  What a user could guess wrong: section 7's list.
- **Packaged harness**: the model (`tb/tb_ddr2.sv`, a DDR2 command-rule checker with data-bus, refresh and order checks, written from the data sheet), the bench and runner (`tests/m141_measure.py`, `tests/test_m141_*_rtl.py`), the formal properties (`verif/formal/ddr2_props.sv`, bound to the RTL without editing it) and their runner with the mutants (`verif/formal/run_formal.py`),
  the covers (the proofs' non-vacuity), the seeded faults (16 in simulation, 14 in the proofs). To reuse it for another DDR2 part, change `tests/m141_timing.py` (the data sheet values) and the model's constants; for DDR3 the rules change (tCCD, tRRD, tFAW, tWTR values, ZQ, CWL) and the properties must be rewritten.
- **Variants**: `POLICY` 0 (latency-first) and 1 (bandwidth-first); `MAP` 0, 1, 2; `QD`; `REF_POST`; `AGE_LIM`; `WR_HI`/`WR_LO`; `RUN_MAX`. Characterisation (LUT, FF, Fmax per family, Pareto points) is **not done**; the plan is an out-of-context sweep over `QD` 4 to 16 and `POLICY` on the Artix-7 100T and the K26 (section 11, step 5).
- **Integration guidance**: use `POLICY` 0 for few outstanding requests where the latency tail matters, with `ref_defer` driven by the application's critical window; use `POLICY` 1 with `MAP` 1 or 2 and the largest `QD` that closes timing for streams; keep tags unique among outstanding requests; do not reset while the part is in use; give the scheduler the periodic reads and the temperature enable that AMD's PHY needs (section 3).
