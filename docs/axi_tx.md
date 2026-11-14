# The on-chip AXI transactor, protocol checker and scoreboard

This block sits next to the design you are testing, on the FPGA. It sends the design AXI bus traffic from a program you
load at run time (no rebuild). While the traffic runs it checks 10 AXI4-Lite and 5 AXI4-Stream protocol rules at the wires,
checks the data against a reference, and counts what happened. It handles AXI4-Lite (a simple register-access bus) and
AXI4-Stream (a one-way packet stream, 32-bit data in this version). Full AXI4 (bursts, IDs, several transactions in
flight), the slave side, a DMA target and long soak runs are a planned second phase.

**Try it** (simulation and formal only; needs Icarus Verilog, cocotb, Yosys and SymbiYosys, as in the README's Reproduce
section): `python -m pytest -q axi_tx/tests/test_59a_rtl.py && python axi_tx/formal/run_formal.py`. The first command
runs every program, seeded bug and memory fault in simulation (about a minute); the second runs the formal proofs and
the broken-checker campaign (tens of minutes) and prints one line per job. Measured results, including the board runs:
[results/59a_axi_tx](../results/59a_axi_tx/README.md).

## Terms

| Term | Meaning here |
|---|---|
| VALID / READY | every AXI channel's handshake: the sender raises VALID with its payload; the transfer happens on a clock edge where the receiver's READY is also high |
| AW, W, B, AR, R | the five AXI4-Lite channels: write address, write data, write response, read address, read data |
| WSTRB | the write byte-enables: which bytes of a 32-bit word a write changes |
| TKEEP, TSTRB, TLAST | stream sideband: which bytes of a beat are kept, which kept bytes are data rather than position bytes, and the last beat of a packet |
| back-pressure | the receiver holding READY low, so the sender must wait |
| rule, episode | a rule is one protocol requirement; an episode is one unbroken run of cycles in which it is broken |
| scoreboard | the reference copy of memory that every read can be checked against |
| digest | a CRC-32 over every transaction (kind, address, data, response, latency in cycles): equal digests mean identical traffic |
| bounded proof | a formal check that no violation of a property can be reached within N clock cycles (here 20); it says nothing about longer runs |
| mutant | a copy of the checker with one deliberate fault; a proof that does not fail on it is too weak |

## How it is built

```
             UART test shell (shell/PROTOCOL.md), window 0x80-0xFF
                   |
   program RAM --> sequencer --> axil_tx_master ==AXI4-Lite==> target mux --> block-RAM controller IP core (board)
   256 x 128 bit       |                                 |                 \-> axil_demo_periph (seeded bugs)
                       |                                 +-- axil_rules + axi_viol_log  (protocol checker)
                       |                                 +-- axil_mon                   (latency, stalls, coverage)
                       |                                 +-- AMD AXI Protocol Checker   (cross-check, board only)
                       |                                 +-- logic_analyser             (capture, trigger = rule fired)
                       +--> axis_tx_source ==AXI4-Stream==> axis_demo_fifo ==> axis_tx_sink (expected data)
                       |                                                    +-- axis_rules + axi_viol_log, axis_mon
                       +--> scoreboard (reference memory, 4 KB window), transaction log, digest
```

The sequencer runs the program; the scoreboard is the reference memory. RTL: [axi_tx/rtl](../axi_tx/rtl); board top:
[designs/b59a_axi_tx](../designs/b59a_axi_tx); host: [axi_tx/host](../axi_tx/host); tests: [axi_tx/tests](../axi_tx/tests);
formal: [axi_tx/formal](../axi_tx/formal). On the board, target 0 is a vendor block-RAM controller IP core (8 KB) and
target 1 our own small peripheral; AMD's AXI Protocol Checker watches the same AXI4-Lite bus as an independent check.

## The transaction program

A YAML (or JSON) list of steps, assembled into 4-word instructions ([program.py](../axi_tx/host/program.py) has every
field). Changing the test is a new program, not a new bitstream.

```yaml
name: bram_random_rw
target: bram                       # bram | periph
steps:
  - set: {seed_data: 0x59A1, seed_lite: 0x1234, valid_p: 64, ready_p: 160, sb_base: 0x0}
  - loop: 120
    body:
      - write: {addr: 0x0, rand_addr: 0xFFC, rand_data: true, rand_strb: true, sb: true, resp: OKAY}
      - read:  {addr: 0x0, rand_addr: 0xFFC, sb: true, resp: OKAY}
```

| Step | What the sequencer does |
|---|---|
| `write`, `read` | one AXI4-Lite transaction. Address fixed, from AREG (an address register that steps by 4) or with random bits; data and WSTRB fixed or random; write order `together`, `aw_first` or `w_first` with a gap; expected response; scoreboard record or check; expected read bytes; `inject`: make the transactor itself break a rule, to test the checker |
| `loop` / `body` | repeat, nested up to 4 deep |
| `set` | LFSR seeds (data, AXI4-Lite timing, stream timing), VALID and READY probabilities on both buses, AREG, the scoreboard window, the watchdog |
| `ssend`, `swait` | send a packet (length, first word or random, last-beat TKEEP, with or without TLAST), expect it at the sink; wait for the stream to drain |
| `wait`, `waitev` | wait cycles, or for an event input |

**Randomness replays.** Random fields come from a 32-bit data LFSR, one step per field in a fixed order (address, data,
WSTRB). VALID gaps and READY back-pressure come from two timing LFSRs that step every cycle of the run. A run starts from
the same reset of all three, and the demo peripheral's own counters run only while a program runs, so a run repeats exactly
and the same program gives the same traffic, cycle for cycle, in simulation and on the board.

**Timing knobs.** `valid_p` is the chance in 256 that a VALID waits one more cycle (0: never waits); `ready_p` sets how often
the transactor's READY is high: a cycle is ready when an 8-bit draw is at most `ready_p`, so 255 is always ready. The master
never waits for AWREADY before raising WVALID, nor for WREADY before raising AWVALID (IHI 0022H A3.3.1 forbids that; a
slave may wait for both).

## The protocol checker

Port-only monitors: they see only the interface's signals, so they can watch any master and slave pair, ours or not
(`axil_checker` and `axis_checker` are the stand-alone blocks). Each rule raises its bit in every cycle in which it is
broken; `axi_viol_log` counts episodes, time-stamps the first and the latest, and pulses a trigger that starts a capture.

AXI4-Lite rules, cited to Arm IHI 0022H (issue H) by section, in our words:

| # | Name | Rule | Section |
|---|---|---|---|
| 0-4 | AW_HOLD, W_HOLD, B_HOLD, AR_HOLD, R_HOLD | once VALID is high it stays high, with its payload unchanged, until READY | A3.2.1, A3.2.2 |
| 5 | B_EARLY | BVALID only after both the AW and the W handshake of that write have completed at an earlier edge | A3.3.1 |
| 6 | R_EARLY | RVALID only after the AR handshake of that read | A3.3.1 |
| 7 | RESET | AWVALID, WVALID and ARVALID are low at the first edge at which reset is seen released (a BVALID or RVALID there breaks rule 5 or 6, which fires instead) | A3.1.2 |
| 8 | EXOKAY | no EXOKAY response on AXI4-Lite, which has no exclusive access | B1.1 |
| 9 | IN_RESET | every VALID is low while ARESETn is held low, from the second edge of a reset (a design with a synchronous reset clears its VALID at the first edge at which it sees reset) | A3.1.2 |
| 10 | RESP_LOST | brief 71, a separate monitor (`axi_tx/rtl/axil_resp_rules.sv`, placed beside `axil_rules`): while a write (AW and W both accepted) or a read (AR accepted) is unanswered, its B or R comes within `TIMEOUT` clocks (a parameter, default 256) of that moment or of the previous response; `lost[0]` (writes) or `lost[1]` (reads) is high every cycle past the bound. The case it exists for: brief 69's AXI DMA register port accepted a second write while the first B waited and returned one B for both. A slave legally slower than `TIMEOUT` fires it, so set `TIMEOUT` from the slave's documented worst case. Not part of `axil_checker`'s 10-bit `viol` (its users and their logs keep their width); seeded faults in `axi_tx/tests/test_71_resp_rules_rtl.py` | A3.3 |

AXI4-Stream rules, cited to Arm IHI 0051B:

| # | Name | Rule | Section |
|---|---|---|---|
| 0 | HOLD | once TVALID is high it stays high, with TDATA, TKEEP, TSTRB and TLAST unchanged, until TREADY | 2.2 |
| 1 | KEEP_STRB | no byte marked as not kept (TKEEP low) but as data (TSTRB high): the specification reserves that combination | 2.4 |
| 2 | RESET | TVALID low at the first edge out of reset | 2.8 |
| 3 | MAXLEN | profile rule, off by default: no packet longer than a set number of beats | |
| 4 | PACKED | profile rule, off by default: TKEEP all ones, except a run of ones from byte 0 on the last beat | |

Profile rules check what a particular IP core documents about itself, not the protocol.

**What the checker does not check.** Rules 0-8 are not evaluated while ARESETn is low (rule 9 is). A combinational path from
READY to VALID inside a block cannot be seen at the ports; what the ports show of it is a VALID that drops or changes, which
rules 0-4 catch. Outstanding counts saturate at 255. Write and read data correctness belong to the scoreboard. Bursts, IDs,
WRAP, the 4 KB boundary and exclusive access belong to full AXI4, the planned second phase. On the stream, only the receiver
checks TLAST positions (against the expected packets).

## The scoreboard and the counters

- **Reference memory.** 1024 words of data plus a valid bit per byte, for one 4 KB window (`sb_base`). A write with an
  OKAY response records its strobed bytes; a read compares only bytes that were written in this run. A read of a word with
  no known byte counts as unchecked (random reads over a large window leave many unchecked).
- **Expected values.** A read can compare chosen bytes with a constant, and any transaction its response code.
- **Stream receiver.** Each sent packet pushes its expected shape; every received beat is compared (kept bytes, TKEEP, TLAST
  position, unexpected beats).
- **Transaction log and digest.** The first 256 transactions (kind, response, verdict flags, latency, address, data) and a
  digest over all of them. The digest covers the AXI4-Lite transactions; stream runs are compared through the stream counters.
- **Counters** ([regs.py](../axi_tx/host/regs.py) names them all): 76 for AXI4-Lite (handshakes and stall cycles per channel;
  READY-wait bins per channel of 0, 1, 2-3, 4-15 and 16 or more cycles; responses per channel; WSTRB full, partial or zero;
  which VALID came first in each write; latency count, minimum, maximum, sum and eight bins for writes and for reads; the most
  outstanding) and 21 for the stream (beats, packets, stall and idle cycles, packet-length and last-beat TKEEP bins).

## The capture

`ip_lib/logic_analyser` (512 samples of 32 bits, every clock) on the AXI4-Lite handshakes, responses, the low read-data bits
and the rule vector, armed by the host before the run and triggered by the first rule episode. The trigger sample shows the
cycle in which the rule broke; the samples before it show how the bus got there. The trigger is also an output of
`axi_tx_core` (`chk_trig`) for the repository's other capture tools.

## Host, agent tools and simulation parity

- [host.py](../axi_tx/host/host.py) writes every operation (load, arm, start, wait, read back) as a generator of register
  accesses. `SyncHost` runs it over the UART shell; `arun` runs it in cocotb over the shell's window, so the board and the
  simulation get the same program and the same register traffic.
- [model.py](../axi_tx/host/model.py) is the transaction-level model: it runs the instruction words as the sequencer does,
  against a model of the target, and predicts every transaction and verdict counter. It has no clock; latency and the digest
  are compared between the RTL in simulation and the board. Memory words the run did not write are unknown to it (block RAM
  keeps its contents between runs).
- Agent tools (MCP, [agent/core/axi_tools.py](../agent/core/axi_tools.py)): `axi_program_check` (assemble and model),
  `axi_simulate` (the program on the RTL in cocotb), `axi_board_run` (the program on the board, within the agent's usual
  hardware limits: only in the debug stage, power check first, volatile configuration only, and only while it can take the
  board lock).
- [run_board.py](../axi_tx/host/run_board.py) runs a plan on the board (the caller holds the board lock) with the operating
  conditions logged (JTAG XADC before and after, the fabric XADC with min/max and latched alarms after every run) and compares
  each run with its simulation record.

## Verification of the checker

A checker that is wrong is worse than none, so each rule is checked formally to a depth of 20 clock cycles (bounded), as
well as in simulation and on the board.

- **Formal** ([run_formal.py](../axi_tx/formal/run_formal.py)): each rule is restated as a property in `$past`/`$stable`
  form in a harness with every bus signal free and resets anywhere. *Quiet*: with every rule assumed, the checker never
  fires. *Seed k*: with every rule but k assumed, whenever rule k is broken the checker flags k and only k, and a cover
  reaches it. Then the checker is mutated, structurally (a rule tied low, a reset guard removed, a hold rule's payload
  comparison removed) and semantically (a counter on the wrong handshake, a wrong response code, one payload field left out,
  a wrong cycle of history), and every mutant must make the quiet or a seed proof fail.
- **Simulation:** each seeded bug of the peripheral and the stream FIFO, and each injected master fault, fires exactly the
  rule it breaks; the clean runs fire none and match the model; a memory fault that ignores WSTRB is caught by the scoreboard
  alone.
- **Cross-check on hardware:** AMD's AXI Protocol Checker on the same AXI4-Lite bus, read back after every run. It does not
  watch the stream (AMD's stream checker was only build-tested).

The restatements were written by the same author as the checker, so they share any misreading of the specification; the
AMD checker is the independent check.
