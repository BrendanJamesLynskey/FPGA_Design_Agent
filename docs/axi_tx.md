# The on-chip AXI transactor, protocol checker and scoreboard (brief 59A)

A synthesisable block that sits next to the IP under test, drives AXI4-Lite and AXI4-Stream traffic from a program
loaded at run time, checks the protocol at the ports, checks the data against a reference, and counts what happened.
59A covers AXI4-Lite and AXI4-Stream; full AXI4 (bursts, IDs, out-of-order), the slave side, a DMA target and soak mode
are 59B. Measured results: [results/59a_axi_tx](../results/59a_axi_tx/README.md).

```
             UART test shell (shell/PROTOCOL.md), window 0x80-0xFF
                   |
   program RAM --> sequencer --> axil_tx_master ==AXI4-Lite==> target mux --> AMD AXI BRAM Controller (board)
   256 x 128 bit       |                                 |                 \-> axil_demo_periph (seeded bugs)
                       |                                 +-- axil_rules + axi_viol_log  (protocol checker)
                       |                                 +-- axil_mon                   (latency, stalls, coverage)
                       |                                 +-- AMD AXI Protocol Checker   (cross-check, board only)
                       |                                 +-- logic_analyser             (capture, trigger = rule fired)
                       +--> axis_tx_source ==AXI4-Stream==> axis_demo_fifo ==> axis_tx_sink (expected data)
                       |                                                    +-- axis_rules + axi_viol_log, axis_mon
                       +--> scoreboard (reference memory, 4 KB window), transaction log, CRC digest
```

RTL: [axi_tx/rtl](../axi_tx/rtl); board top: [designs/b59a_axi_tx](../designs/b59a_axi_tx); host:
[axi_tx/host](../axi_tx/host); tests: [axi_tx/tests](../axi_tx/tests); formal: [axi_tx/formal](../axi_tx/formal).

## The transaction program

A YAML (or JSON) list of steps, assembled into 4-word instructions ([program.py](../axi_tx/host/program.py) has the
full field list). Changing the test is a new program, not a new bitstream.

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
| `write`, `read` | one AXI4-Lite transaction. Address fixed, from AREG (then AREG += 4) or with random bits; data and WSTRB fixed or random; write order `together`, `aw_first` or `w_first` with a gap; expected response; scoreboard record or check; expected read bytes; an injected master-side fault |
| `loop` / `body` | repeat, nested up to 4 deep |
| `set` | LFSR seeds (data, AXI4-Lite throttle, stream throttle), VALID and READY probabilities on both buses, AREG, the scoreboard window, the watchdog |
| `ssend`, `swait` | send a packet (length, first word or random, last-beat TKEEP, with or without TLAST), expect it at the sink; wait for the stream to drain |
| `wait`, `waitev` | wait cycles, or for an event input |

**Randomness replays.** Random fields come from a 32-bit data LFSR, one step per field in a fixed order (address, data,
WSTRB). VALID gaps and READY back-pressure come from two throttle LFSRs that step every cycle of the run. Every run
starts from the same reset of all three, so a run is exactly repeatable, and the same program gives the same traffic in
simulation and on the board.

**Timing knobs.** `valid_p` is the chance in 256 that a VALID waits one more cycle; `ready_p + 1` is the chance in 256 that
the transactor's READY is high in a cycle. The master never waits for AWREADY before WVALID, or the reverse (IHI 0022H
A3.3.1 forbids it; a slave may wait for both).

## The protocol checker

Port-only monitors: they see only the interface's signals, so they can watch any master and slave pair, ours or not
(`axil_checker` and `axis_checker` are the stand-alone blocks). Each rule raises its bit in every cycle in which it is
broken; `axi_viol_log` counts episodes (a rising edge of the bit), time-stamps the first and the latest, and pulses a
trigger that starts a capture.

AXI4-Lite rules, cited to Arm IHI 0022H (issue H) by section, in our words:

| # | Rule | Section |
|---|---|---|
| 0-4 | AW, W, B, AR, R: once VALID is high it stays high, with its payload unchanged, until READY | A3.2.1, A3.2.2 |
| 5 | BVALID only after both the AW and the W handshake of that write have completed at an earlier edge | A3.3.1 |
| 6 | RVALID only after the AR handshake of that read | A3.3.1 |
| 7 | every VALID is low at the first edge at which reset is seen released | A3.1.2 |
| 8 | no EXOKAY response on AXI4-Lite, which has no exclusive access | B1.1 |

AXI4-Stream rules, cited to Arm IHI 0051B by section: 0 TVALID held with TDATA, TKEEP, TSTRB and TLAST stable until
TREADY (2.2); 1 the reserved TKEEP low / TSTRB high byte (2.4); 2 TVALID low at the first edge out of reset (2.8). Two
profile rules, off unless enabled, check what particular IP documents: 3 a maximum packet length, 4 packed bytes (TKEEP
all ones except a run of ones from byte 0 on the last beat).

**What the checker does not check.** Every rule is ignored while ARESETn is low (the signals are don't-care there). A
combinational path from READY to VALID inside a block cannot be seen at the ports in one cycle; what the ports show of it
is a VALID that drops or changes, which rules 0-4 catch. Outstanding counts saturate at 255. Write data and read data
correctness are the scoreboard's, not the checker's. Burst, ID, WRAP and 4 KB rules belong to full AXI4 (59B).

## The scoreboard and the counters

- **Reference memory.** 1024 words of data plus a valid bit per byte, for one 4 KB window (`sb_base`). A write with an
  OKAY response records its strobed bytes; a read compares only bytes that were written. A read of a word with no
  known byte counts as unchecked.
- **Expected values.** A read can compare chosen bytes with a constant, and any transaction its response code.
- **Stream sink.** Each sent packet pushes its expected shape; every received beat is compared (kept bytes, TKEEP, TLAST
  position, unexpected beats).
- **Transaction log and digest.** The first 256 transactions (kind, response, verdict flags, latency, address, data) and
  a CRC-32 over all of them. Equal digests mean identical traffic, cycle for cycle.
- **Counters** ([regs.py](../axi_tx/host/regs.py) names all 76 + 21): handshakes and stall cycles per channel; READY-wait
  bins per channel (0, 1, 2-3, 4-15, 16+ cycles); responses per channel; WSTRB full, partial, zero; which VALID came first
  in each write; latency count, minimum, maximum, sum and eight log2 bins for writes and for reads; maximum outstanding;
  stream beats, packets, stall and idle cycles, packet-length and last-beat-TKEEP bins.

## The capture

`ip_lib/logic_analyser` (512 samples of 32 bits, every clock) on the AXI4-Lite handshakes, responses, low read-data byte
and the rule vector, armed by the host before the run and triggered by the first rule episode. The trigger sample shows
the cycle in which the rule broke; the samples before it show how the bus got there. The trigger is also an output of
`axi_tx_core` (`chk_trig`) for the brief 50 analyser.

## Host, agent tools and simulation parity

- [host.py](../axi_tx/host/host.py) writes every operation (load, arm, start, wait, read back) as a generator of register
  accesses. `SyncHost` runs it over the UART shell; `arun` runs it in cocotb over the shell's window. The board and the
  simulation therefore get the same program and the same register traffic.
- [model.py](../axi_tx/host/model.py) is the transaction-level model: it runs the instruction words as the sequencer does,
  against a model of the target, and predicts every transaction and verdict counter. It has no clock; latency and the
  digest are compared between the RTL in simulation and the board.
- Agent tools (MCP, [agent/core/axi_tools.py](../agent/core/axi_tools.py)): `axi_program_check` (assemble and model),
  `axi_simulate` (the program on the RTL in cocotb), `axi_board_run` (the program on the board; same hardware policy as
  `program`: stage, power gate, budget, SRAM only, cable serial from the local board file).
- [run_board.py](../axi_tx/host/run_board.py) runs a plan on the board with the operating conditions logged (JTAG XADC
  before and after, the fabric XADC with min/max and latched alarms after every run) and compares each run with its
  simulation record.

## Verification of the checker

A checker that is wrong is worse than none, so the rules are proved, not only simulated.

- **Formal** ([run_formal.py](../axi_tx/formal/run_formal.py)): each rule is restated as a property in `$past`/`$stable`
  form in a harness with every bus signal free and resets anywhere. *Quiet*: with every rule assumed, the checker never
  fires (bounded, depth 20). *Seed k*: with every rule but k assumed, whenever rule k is broken the checker flags k and
  only k, and a cover reaches it. Then the checker is mutated (each rule tied low, each reset guard removed, each hold
  rule's payload comparison removed) and every mutant must fail the proof aimed at it.
- **Simulation:** each seeded bug of the peripheral and the stream FIFO, and each injected master fault, fires exactly the
  rule it breaks; the clean runs fire none and match the model; a memory mutant that ignores WSTRB is caught by the
  scoreboard alone.
- **Cross-check on hardware:** AMD's AXI Protocol Checker on the same bus, read back after every run.

The restatements were written by the same author as the checker, so they share any misreading of the specification;
the AMD checker is the independent cross-check.

## Course impact

A lab candidate: "Prove your checker before you trust it" (the quiet / seeded / mutant pattern above) and "a READY
throttle finds the bug that full-speed traffic hides" (the R_HOLD bugs fire only under RREADY back-pressure). See the
59A report.
