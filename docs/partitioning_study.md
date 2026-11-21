# Partitioning a large design, and registering between sub-modules (brief 151, phase 0)

Written 2026-11-21. Owner direction: "Possible area of expertise: partitioning a large system for best results; when to register
signals between sub-modules, whether to use >1 register stage for this, handshakes etc", and, the same evening, "We should favour AMBA
AXI where appropriate". Every boundary register is a clock of latency, so each question below has its latency cost beside its
timing and area. Nothing here is a Vivado measurement: the Vivado points are written and queued
(`partition/sweep.py`, `_handoff/fpga_agent/vivado_later_queue.md`); what has been measured is simulation (latency, throughput,
bubbles, data) and Yosys area, recorded in `results/b151/`. Every rule that follows from this study is **provisional until the
queued runs have been read**; the draft rule set is in the private knowledge base (`family_matrix/drafts/`).

## 1. What the guidance and the literature say (our words)

Where a statement comes from a file in the knowledge base it is marked KB; where it is from the published guide named and not yet
re-read against the 2026.1 text it is marked "guide, to check".

**Module boundaries.** AMD's methodology guide (UG949, design creation with RTL) advises registering the outputs of hierarchical
blocks, keeping a combinational cone inside one block, and avoiding logic between a block's output port and the next block's first
register (KB: `techniques/integration/rtl-hierarchy-and-register-boundaries`, citing UG949 v2025.2 chapter 3). The reasoning is that
a path then starts at a flip-flop and a consumer cannot lengthen the producer's path. Registering inputs as well is worth it when
the incoming path is long or its source is unknown. The reuse literature (Keating and Bricaud, *Reuse Methodology Manual*) says the
same for IP that is dropped into unknown surroundings.

**One stage or more.** UG949 and the UltraScale architecture guides tie the number of stages to distance, not to logic: a route
that crosses clock regions, or an SLR, or reaches a hard block at the edge of the fabric, is slow by itself, so extra registers on
the wire (not logic) pay (guide, to check: the SLR advice is a register on each side of the crossing; `phys_opt_design
-slr_crossing_opt` and auto-pipelining exist for UltraScale and later, KB `family_matrix/notes/toolflow.md`). High fanout is a
different case: replicate the register instead of adding a stage (KB `vendor/vivado_synthesis/timing-methodology/fanout-replication-and-physopt`).
Neither the K26 (monolithic) nor the xc7a100t has an SLR, so the SLR case cannot be measured on the owner's parts.

**Retiming and hierarchy.** Vivado's synthesis retiming (`-retiming`, UG901) moves registers across logic inside the design it can
see. `KEEP_HIERARCHY TRUE` stops all optimisation across the boundary, `SOFT` stops all but constant propagation (KB
`vendor/vivado_synthesis/synthesis-attributes`); a `KEEP` or `DONT_TOUCH` register is not retimed. So a hierarchy kept for reuse or
floorplanning also fixes where the registers are. A boundary that is a plain register on both data and valid is the one retiming
can move.

**Handshakes.** AXI4-Stream (Arm IHI 0051B) fixes the rules: `tvalid` must not depend on `tready`; once `tvalid` is high the beat
and its sideband stay until `tready`; `tvalid` is low during reset and at the first edge after it. A ready that depends
combinationally on the next block's ready makes a chain of such blocks one long combinational loop in the backward direction, so
the standard cures are: a skid buffer (a register for the data path plus one spare entry, ready a flop; ZipCPU's *Building a Skid
Buffer for AXI processing* and the `axis_register` of Forencich's verilog-axis are the public references), a full register slice,
or a half-rate slice whose ready is a flop but which holds one beat and moves one beat per two clocks. AMD's AXI Register Slice
(KB `amba_axi/amba/axi-handshake-rules-and-register-slices`, recorded from the AXI infrastructure product guide, PG059 v2.1) offers
several register configurations per channel (fully registered, light-weight, forward registered, reverse registered, SLR crossing,
auto pipeline), adds one clock by default and keeps full throughput. The credit alternative (Dally and Towles, *Principles and
Practices of Interconnection Networks*, flow control; Carloni et al., latency-insensitive design) replaces ready by a count of free
receiver slots: the forward wires need no ready at all, and the buffer must cover the credit round trip to keep full rate.

**Floorplanning.** Pblocks fix where a block goes; UG949 recommends them sparingly and after the netlist is stable (guide, to check).
They are the only way to place sub-modules far apart *by construction*, which is what the sweep needs.

**Out of context and reuse.** An out-of-context (OOC) run builds a block alone, with only its own clock, and its checkpoint can be
reused; Vivado's incremental implementation is refused on the Basic licence (`Vivado 12-29181`, brief 100B), so the free-licence
answer is a locked OOC checkpoint per unchanged component (brief 147 item F12). Both work best if the cut is at a registered
boundary, because a path that crosses an OOC boundary is not timed unless the top constrains it.

## 2. The questions and their nulls

Each question is one the owner would ask in a design review. The null is what we expect to find *if the rule of thumb does not hold*;
the "expected" is what the guidance above predicts. The sweep is `partition/sweep.py` (90 points on two parts; Vivado 2026.1 out of
context, non-project, one thread); figures marked "measured" are from `results/b151/`.

| Q | Question | Null | Expected | Sweep | Status |
|---|---|---|---|---|---|
| Q1 | Registered outputs, registered inputs or both? | the side of the register does not matter when the tool may place it | with the boundary registers left to the placer the side is immaterial (one stage); the side matters only if one side's net is long by construction | `q1` (stages 0-3 x three distances), `q5` (no pblocks) | queued |
| Q2 | When does one boundary stage suffice, and when do two or more pay? | a second stage never pays inside one device | one stage suffices to about one clock region of distance at 4 ns on the xc7a100t; the second pays at the far corner of the K26 at 2.5 ns, where route delay exceeds half the period | `q1` | queued |
| Q3 | What do `KEEP_HIERARCHY` and retiming change? | neither changes WNS or LUT count by more than run-to-run noise | `KEEP_HIERARCHY` costs a few percent LUTs and some WNS where logic could have merged across the boundary; retiming helps only where stage depths are unequal or there are no boundary registers | `q3` | queued |
| Q4 | Which handshake: combinational ready, skid, full slice, half slice, forward-only, plain registers, credits? | all seven have the same area and Fmax | plain < half < comb = forward-only < skid = full in registers and LUTs; comb and forward-only lose Fmax as stages are added because ready is a chain; skid and full do not | `q4` | area from Yosys and latency, throughput, bubbles from simulation: measured; timing queued |
| Q5 | Do pblocks help, or is free placement as good? | placement with and without pblocks gives the same WNS | free placement is no worse than pblocks at distance 0 and better than pblocks that force distance | `q5` against `q1` | queued |
| Q6 | Does cutting at registered boundaries pay in compile time and reuse? | compile time does not depend on the cut | implementation time is roughly linear in the number of sub-modules; a locked OOC checkpoint per unchanged component re-implements only the changed one | `q6`, and F12 of brief 147 | queued |
| Q7 | When is a credit link better than valid/ready? | never: a chain of skid buffers has the same timing | credits do not win on latency (LF + 1 against N) and cost a buffer of RTT entries; they win only where forward wires must be bare registers or ready must cross a long distance as one signal | `q4` (credit at 1 and 2 stages) | simulation: measured; timing and area queued |

### What is already measured (no Vivado)

From `results/b151/pipe_reg_measure.jsonl`, `credit_chan_measure.jsonl` and `part_sys_sim.jsonl` (stamped 2026-11-21; Icarus Verilog
12, cocotb 2.0.1; every figure is also asserted by a test against the model that declares it):

| Boundary | Latency (clocks, N slices) | Throughput | Stored beats when stalled | Ready response (clocks, chain full, m_tready rises) | Ready depends on m_tready in the same clock |
|---|---|---|---|---|---|
| forward-only (FWD), N stages | N | 1 | N | 0 | yes (a combinational path through the whole chain) |
| skid buffer (SKID), N slices | N | 1 | 2N | N | no (a flop in every slice) |
| full register slice (FULL), N slices | N | 1 | 2N | N | no |
| half slice (HALF), N slices | N | 1/2 | N | N | no |
| combinational ready (COMB), N slices | N | 1 | N | 0 | yes (a chain of N) |
| credit link, `CREDITS`, `LF`, `LB` | `LF + 1` | `min(1, CREDITS / (LF + LB + 2))` | `CREDITS` | not defined: s_tready is a flop of the credit count | no |

SKID and FULL behave cycle for cycle alike (the same model matches both, to the clock, at every point); the difference is only in
structure (SKID: output register plus a side register behind a mux; FULL: two entries written alternately, a 2:1 read mux). A chain
of N half slices still moves one beat per two clocks (not worse). The credit link with `CREDITS` below `LF + LB + 2` sends bursts of
`CREDITS` beats and then waits for the first credit to come back, so the bubble is `LF + LB + 2 - CREDITS` clocks long and repeats.

**Yosys area** (`synth_xilinx`, 7-series mapping, flattened, no placement; a cell count, not a timing; `results/b151/part_sys_yosys.json`,
table in `results/b151/README.md`). The system has 8 sub-modules, 64-bit data, so 9 boundaries. One stage at every boundary costs, over the
unpartitioned system's 2037 LUTs and no flip-flops: plain registers 15 LUTs and 585 FFs (9 x 65: data plus valid); forward-only 27 LUTs and 585 FFs;
combinational ready 35 and 585; half slice 45 and 594; **full slice 624 and 1206; skid buffer 638 and 1179** (about 131 FFs per boundary: two
beats of storage and a mux); credit link 143 LUTs, 712 FFs and 99 LUT-RAM cells. Two and three stages scale the same way (skid 1250 and 1862 LUTs).
Three observations, all Yosys-only until Vivado confirms them. (1) The two-beat slices cost an order of magnitude more LUTs than the
one-beat ones, so the default "skid everywhere" is expensive on a wide bus: P1 of the draft rules should ask whether the boundary needs full
throughput with registered ready, or whether HALF or COMB would do. (2) At one and two stages the credit link is *cheaper* than a skid chain
on a 64-bit link, because its buffer is LUT RAM, though it adds a clock of latency per boundary (2 against 1 at one stage); that is the opposite of the
null of Q7 and the first thing the queued `q4` runs must confirm or refute. (3) A reset-free three-stage data pipeline (plain registers, the forward-only
data path, the credit link's forward stage) is mapped to SRLs by Yosys, so its FF count falls to 27: Vivado has the same inference (`SHREG_EXTRACT`), and
an SRL is not a register that retiming or placement can use at a boundary; the sweep's `q3` points will show whether it matters for timing.
Yosys does not know the delays, so it says nothing about Fmax.

## 3. Against the vendor (AMD AXI Register Slice)

Owner direction: "measure the vendor convention first". What we can say now, and what is queued.

* **What the KB records** of the vendor IP: one clock of latency per slice by default, full throughput, no bubbles, up to one
  configuration per channel (PG059 v2.1 as recorded in the KB). It also records that a register slice that crosses an SLR needs
  constraints.
* **Our hypothesis for the mapping, to be tested against the vendor build** (we do not have the guide's mode table in the KB, so this is a
  hypothesis, not a finding): fully registered is our FULL or SKID (both give full throughput with ready and valid registered);
  forward registered is our COMB or FWD (data and valid registered, ready combinational); reverse registered has no equivalent here
  (a combinational data path with a registered ready, which breaks the rule that a consumer should not lengthen the producer's
  path); light-weight we cannot place without the guide; SLR crossing and auto pipeline have no equivalent (no SLR on our parts).
* **Where ours differs, and why:** (1) we offer a half-rate slice (HALF) because it is the cheapest way to register ready and some
  control channels need no more than a beat per two clocks; (2) we offer FWD, an N-stage pipeline under one shared enable, because
  one enable for N stages is cheaper than N slices when the fanout is small; (3) the credit link is not an AXI mode at all: it
  exists for the case in which valid/ready does not fit (see section 4); (4) our AXI4 and AXI4-Lite slices (`axi_reg_slice`) carry
  each of the five channels through an independent chain with its own mode, as the vendor IP does, but they do not carry `awregion`
  and the user signals, and AXI3 `wid`.
* **Queued:** `partition/vendor/vendor_slice_ooc.tcl` builds the IP in every `REG_AW` value the tool lists and records LUT, FF and
  WNS at one clock on both parts; `partition/vendor/vendor_slice_tb.sv` is an xsim bench that measures latency, throughput and bubbles
  of each generated mode. Both are untested (Vivado is not run in this brief); the first run will also settle the mapping above.

## 4. When to use which

(From the study and the measurements so far; provisional until the sweep.)

* **Default: a `pipe_reg` SKID slice on every boundary that carries a handshake**, one stage. Full throughput, ready a flop, and
  `tvalid` a flop, so every AXI4-Stream rule holds by construction.
* **COMB or FWD** only on a short chain (one or two slices) where the extra clock of ready latency matters and the combinational
  ready path was checked at the target clock. They are one register per slice cheaper.
* **HALF** where a beat per two clocks is enough (configuration, status, slow control).
* **PLAIN registers** (no ready) only for a link whose sink is always ready by construction (a stream into a fixed-rate consumer).
* **Credit link** only where valid/ready does not fit: many stages in a row or a distance (several clock regions) over which a ready
  that must travel back through every stage cannot close timing, **or** where the forward wires must be plain registers so that
  they can be pipelined at any depth. Note what a chain of skid slices already gives: no ready loop longer than one slice, because
  every slice's ready is its own flop. So the credit link is *not* needed merely for "a long chain"; it pays for a long chain only
  when the skid chain's two stored beats per stage (2N entries) cost more than `CREDITS` entries of buffer (LUT RAM), or when the
  forward wires cannot take the skid mux. The measurement that settles it is `q4`. The bridge to and from AXI4-Stream is the block
  itself: `credit_chan` has an AXI4-Stream slave port at one end and an AXI4-Stream master port at the other.
* **Full AXI4 or AXI4-Lite channel sets:** `axi_reg_slice` (`axil_reg_slice`, `axi4_reg_slice`).

## 5. Questions for the owner (rules of thumb to check against the measurements)

1. Do you register outputs, inputs, or both at a module boundary, and does it depend on who wrote the module? (Q1; the sweep leaves
   the placer free to put the register on either side of a long wire.)
2. On a monolithic part such as the K26 or the Artix-7, how many clock regions of distance can one stage cover at which clock rate
   in your experience? We expect one stage to about one region at 4 ns.
3. Is a second stage ever worth its clock for a control path, or do you always cut the logic instead?
4. For a stream, do you prefer a skid buffer or a full slice, and would you ever use a combinational ready (what chain length do
   you allow)?
5. Is there a case for a reverse-registered slice (data combinational, ready registered) in your designs?
6. Do you use `KEEP_HIERARCHY` on sub-modules routinely (and `SOFT` or `TRUE`), or only for OOC and floorplanning?
7. Does retiming help in your designs, and do you leave it on?
8. Would you ever replace a long valid/ready chain with credits, and how deep must the chain be before you do?
9. Do you floorplan with pblocks on a part this size, or only for SLR parts and hard-block-heavy designs?
10. What is your rule for the number of logic levels allowed between two boundary registers at a given clock?

## 6. Files

`ip_lib/pipe_reg`, `ip_lib/credit_chan`, `ip_lib/axi_reg_slice` (library entries); `partition/` (the synthetic system, the sweep,
the Vivado point script, the vendor scripts); `results/b151/` (records); the report is `_handoff/fpga_agent/reports/151_partitioning_report.md`.
