# Board test plan, build `rm_gp_itch` (brief 127): PRE-REGISTERED, NOT RUN

**No step here has been run.** The KR260 was not powered, programmed or touched for this brief. The owner runs the script
(`! bash /home/brendan/Claude_sandbox/_handoff/fpga_agent/run_127_stage1.sh <fibre loopback lead length in metres> YES`). This page and `results/b127/preregistration.md` were written before any board time; the criteria below
are the ones the result is judged by, and a failed criterion is reported with its number, not adjusted.

Terms: **loopback** = the module's transmitter fibre is patched to its own receiver (no second device); **replay** = frames the host writes into a 256-word memory in the fabric and the fabric transmits; **capture ring** = the receiver's
memory of the last 8 TCP frames it saw; **T** and **sop** are defined in [itch_integration.md](itch_integration.md) section 3; **ROC** = recommended operating conditions.

## 0. What the board adds to the simulation, and what it cannot add

The simulation ran the whole core (PCS, elastic buffer, MACs, the ITCH path, the multiplexer, the register block) in xsim with AMD's real XPM macros and a behavioural stand-in for the transceiver, and the stages' own code (the dry run).
The board adds: the real GTH (its clocking, gearbox phase at each link-up, the real line), the real clock-domain relationship of the two user clocks, timing closure at temperature and supply (the build closes at the nominal conditions the tool assumes),
and the real JTAG register bus. **It does not add** a second implementation of the MAC or PCS (the loopback talks to itself: a mistake both ends share is accepted), an exchange's or a NIC's view of the TCP segment (the stand-in's TCP checksum is 0:
no real stack would accept it), a frequency offset between two clocks (a loopback has none: the elastic buffer's insert and delete path is not exercised), or any wire-to-wire time (that needs a NIC and its timestamps, brief 110's plan section 3).

## 1. Preconditions and rules (house rules, unchanged)

SRAM only; the owner's board; wall power; at most 2.0 W predicted and Tj at most 85 C (the build's own figures are in itch_integration.md section 9); one board job through `_handoff/board.lock` with a text starting `97I:`; the laser is off at
reset, on for the stages, off on every path out; nobody looks into the port. **Operating conditions are evidence:** die temperature, VCCINT, VCCAUX and VCCBRAM are read from the SYSMON at the start, at the end and between plans at least once
a minute (`host/b127_board.py`), and every failed stage is reported "inside ROC" (a design, constraint or tool question: audit the constraints and CDC first) or "outside ROC" (a power or thermal question: the run is void until repeated inside).
The SYSMON samples at about 1 MSPS across channels and cannot see supply droop at the nanosecond scale; the report says so when a failure looks timing-related.

## 2. Steps and pass criteria

Step 0 (the driver stops with a message if any fails): `ID` 0x96A00001, `FEATURES` bit 7 = 1, the polarity check (RX_LOS 1 with the laser off, 0 on, 1 again off; MOD_ABS 0), link up on the loop within 5 s.

All stages configure through the register map, play synthetic frames from the replay memory (`host/b127_stages.py`), read the counter window and the capture ring, and compare with brief 110's model. A stage passes when **all** of its criteria hold.

| Stage | Arms and runs | Pass criteria (written before the run) |
|---|---|---|
| **smoke** (a) | one seeded session of 60 messages, one message a packet, frames 150 clocks apart, speculation off | every one of the 45 counters of the path except `spec`, `abort`, `late_abort`, `rej_busy` equals the model's; every captured order frame equals the model's frame byte for byte from byte 24 (with the stand-in header, sequence number from `IT_TCP_SEQ`); `ord.sent` = the model's order count, at least 1; `rp.frames` = frames sent; `ord.drop`, `ord.fifo_ofl`, `ord.pz_*`, `ord.late`, `us.orphan`, `itch.evdrop`, `us.drop_off`, `us.drop_ipck`, `us.drop_len`, `us.drop_frag` all 0 |
| **counters** (b) | one session of 120 messages with sequence gaps, duplicates, heartbeats (6 to 8 %), bad-FCS heartbeats (the replay's poison bit), and stray frames for another MAC, port, address and protocol | every counter equals the model's (`halt_on_gap` off); `us.bad_fcs` = bad frames sent; `us.drop_port`, `us.drop_dip`, `us.drop_proto` = strays sent of each kind, `us.drop_mac` = the MAC strays sent plus the order frames that came back (they are addressed to the venue MAC); `us.fwd` = packets; the safety counters of smoke are 0 |
| **latency** (c) | 125 passes, each: clear, replay of 8 single-candidate packets (one for each alignment of the message end in its 64-bit word); 1000 orders; once with speculation off, once on | the hardware histogram of the order latency (clocks from the last payload word at the Mold receiver, T, to the order frame's start strobe) has **no count outside** {10, 11} (speculation off) or {5, 6} (speculation on); `lat.count` = 1000 (`lat.neg` = 0); the share in the upper bin of each pair is at most 10 % (the gearbox pause: 1 in 33 expected, about 3 %); the safety counters are 0 |
| **rate** (d) | 100 passes of 19 frames played back to back (no gap) | every frame sent and forwarded (`rp.frames` = `us.fwd` = 1900); `us.bad_fcs`, `us.cut`, `us.orphan`, `itch.evdrop`, `itch.pkt_err` all 0 |
| **risk** (e) | 4 candidate packets played three times: with the path armed; with KILL set; with `IT_MAXPOS` 150 | 4 orders in the first play; 0 orders and `rej_kill` up by 4 with KILL; 1 order and `rej_pos` up by 3 with the limit |

The latency prediction is not a guess about the board: T to the start strobe is a path between two registers in the transmit clock, so the board must reproduce the simulation's histogram exactly. Any other bin means the built logic is not the simulated logic.
`results/b127/latency_sim.json` and `latency_unit_sim.json` are the simulation's numbers.

## 3. What a pass would and would not show

A pass shows that the built design does what the simulation did, on a real transceiver, with real frames from the transmitter's MAC through the receiver's MAC. It does not show interoperability, a wire-to-wire figure, the behaviour under a frequency offset, or a
valid TCP segment. Those need a NIC (the owner's later purchase), the real-offset plan (`designs/b96_kr260_10g/docs/real_offset_plan.md`) and brief 119's `tcp_fast` (section 8 of the integration note).

## 4. Files

`host/b127_board.py` (the driver), `host/b127_stages.py` (the stages, shared with the simulation's dry run), `host/itch_bench.py` and `host/itch_host.py` (plans and frames), `_handoff/fpga_agent/run_127_stage1.sh` (the owner's script), results go to
`results/b127/hw/<timestamp>/rm_gp_itch/stage1.json`.
