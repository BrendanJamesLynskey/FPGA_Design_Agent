# UDP command and telemetry endpoint on the Nexys A7-100T (brief 82, ladder project 3): phase 1, the specification and the evidence harness

A board that obeys typed commands sent as UDP datagrams (read, write, status, start and stop telemetry), each with a sequence
number and a CRC-32, answers each one with an OK or an error code, and sends a rate-limited telemetry stream; damaged,
truncated, oversized, repeated and out-of-order packets are refused and counted without changing anything. It is built on the
network blocks of brief 63D ([ip_lib](../../ip_lib/README.md): the RMII MAC, `ipv4_udp_rx`, `ipv4_udp_tx`, `arp_responder`,
`icmp_echo`). This folder holds what phase 1 produced: the plain-English request, the formal specification, the packet-format
datasheet, a bit-exact Python model, a host client and a fuzzer with a dry-run mode, and benchmark tasks derived from the
design. The FPGA Design Agent has not been run on any of it and no board has been used: those are phases 2 and 3.

**Status of phase 1 (re-drawn 2026-11-15, brief 82R): complete.** Six benchmark tasks (domain E, board Nexys A7-100T) were written to the v2 layout, checked, frozen and submitted to the split ledger, then drawn by task family: the packet screener, the command executor and the whole endpoint form one family; the CRC unit, the telemetry pacer and the reply builder are one family each. One family is held out (it is neither named nor quoted here) and five tasks are development tasks, in [benchmark/v2/tasks](../../benchmark/v2/tasks): `v2_e_cmd_parser`, `v2_e_cmd_exec`, `v2_e_udp_endpoint` (the whole endpoint at the payload level), `v2_e_tlm_pacer` and `v2_e_resp_builder`. Nothing in this folder quotes a hidden test.

## What is here

| File | What |
|---|---|
| [request.md](request.md) | the plain-English request, as a customer would write it; the only text the agent is given |
| [spec.yaml](spec.yaml) | the formal specification (planner's copy; not shown to the agent): clocks, parameters, reused blocks, behaviour, the specification numbers |
| [protocol.md](protocol.md) | the packet-format datasheet, generated from the model's constants (a test checks it is current) |
| [model/udp_ref.py](model/udp_ref.py) | the bit-exact reference model of the parser, the sequence rules, the register file, the reply builder and the telemetry pacer; bytes and integers only |
| [host/client.py](host/client.py) | the Python client (typed commands, sequence numbers) with a UDP transport and a dry-run transport against the model |
| [host/fuzz.py](host/fuzz.py) | the fuzzer: seeded damaged packets, an independent oracle written from the protocol text, counters compared by deltas |
| [records/fuzz_dry_run_2026-11-14.json](records/fuzz_dry_run_2026-11-14.json) | one dry-run record (3000 packets against the model) |
| [tests/](tests/) | 11 tests of the model, the client, the fuzzer (including three seeded faults it must catch), the generated datasheet and the numbers in `spec.yaml` |

## Technical parameters

| Item | Value |
|---|---|
| Board, part | Nexys A7-100T, `xc7a100tcsg324-1`; Ethernet over the on-board RMII PHY through `eth_mac_rmii` |
| Clock | 100 MHz system clock; the PHY side is the MAC's own business (its FIFO crosses the domains) |
| Command format | `TYPE LEN SEQ(2) PAYLOAD CRC32(4)`, payload 0 to 8 bytes, CRC-32 little-endian over everything before it ([protocol.md](protocol.md)) |
| Registers | 8 x 32 bit: ID `0x55445031`, three scratch, commands carried out, packets refused, telemetry period, uptime ticks |
| Sequence rule | new when `(seq - last) mod 65536` is 1 to 0x7FFF; the first packet after reset may carry any number; an accepted command consumes its number even if the register access then fails |
| Telemetry | one frame per PERIOD ticks (100 after reset, minimum 4), one frame held at most, an overrun is dropped and counted, never queued |
| Specification numbers (targets, from the model's cycle formula; not measured) | READ and WRITE each 26 clocks end to end at one byte per clock, so at most 3.85 million commands/s from the logic and about 164 thousand/s from a 100 Mbit/s link (64-byte frame plus gap 6.08 us); decision latency 3 clocks after the last byte; telemetry spacing exact in ticks (jitter 0 ticks) plus one transmit delay |
| Flood | the link, not the logic, limits the rate; the receive path never blocks the MAC; bytes the endpoint cannot take are dropped and counted by the MAC |

## How to run and reproduce

| Step | Command | Heavy slot | Time |
|---|---|---|---|
| model, client, fuzzer and datasheet tests | `python3 -m pytest -q showcase/udp_endpoint/tests` | no | under a second |
| dry-run fuzz | `python3 -m showcase.udp_endpoint.host.fuzz --dry-run --seed 1 --n 3000 --out showcase/udp_endpoint/records/fuzz_dry_run_2026-11-14.json` | no | under a second |
| dry-run client | `python3 -m showcase.udp_endpoint.host.client --dry-run` | no | under a second |
| real board (phase 3, not done) | `python3 -m showcase.udp_endpoint.host.fuzz --host <board ip> --port 5005` | board lock | minutes |

## What was verified

- `pytest showcase/udp_endpoint/tests`: 11 passed. They check the CRC against `zlib` and the residue constant, every command and
  error code, the consumed-number rule, replay, out-of-order, half-span and wrap, framing drops (no reply, no state change),
  byte-serial against whole-datagram feeding, the telemetry pacer (period, floor, overrun, stop), that the fuzzer passes the
  model, and that the fuzzer catches three seeded faults: a parser that accepts a bad CRC, one that does not recover from a
  truncated packet, and one that loses the sequence order.
- The fuzzer's oracle is written from the protocol text, not from the model's code; it reads the endpoint only through replies and
  STATUS counters, so the same run works against the board.

## What is illustrative

The dry-run record is the model talking to its own fuzzer: it shows that the harness and the model agree and that the harness
catches faults, not that any hardware works. The specification numbers are design targets from a cycle formula (one byte per
clock in, three to decide, one per clock out), not measurements.

## Known gaps and limits

- The agent has not built any of this and no board has been used (phases 2 and 3).
- Task benches use the Nexys shell (about 1 200 clocks per register access), so wide counters are only partly exercised in the task benches.
- Mutant sweeps were run once on the final files, with one exception: the endpoint's `test_ep_sequence_rules` gained one check (the refused-packets register after an out-of-order packet) after the first sweep chunks; only the mutant that needed it was re-run (killed), the others cannot be un-killed by an added check.
- Pre-freeze leak check: each of the six tasks in turn as the secret against the other five, this folder, the bench helpers, the existing v2 tasks, the shell and the CRC and UDP entries of `ip_lib`: 0 hits (80-byte windows, `site/leak_guard.py`, no allowance). It took per-task rewording and a unique trailing comment on every code line of the reference and hidden Python.
- The benchmark tasks work at the payload level through the Nexys test shell; the Ethernet blocks, ARP, ping and the
  RMII PHY are not in them. The whole-endpoint task therefore tests the endpoint's behaviour, not the integration with `ip_lib`.
- Counter widths above 16 bits (the wrap at 65 536 commands) are not testable through the UART shell and are not tested.
- The dry run cannot test flood behaviour, link-level loss, ARP or ping; those need the board and a PC on the same network
  (phase 3). The maximum command rate, latency and telemetry jitter in `spec.yaml` are targets until then.
- The register map is 8 x 32 bit over a UDP command, not an AXI4-Lite block; the house register-block generator is not used.

## Next steps

1. Planner: review and merge the branch (it carries ledger entries; rebase on main first if other v2 batches merged).
2. Phase 2 (after the weekly reset): the agent builds the development tasks, k = 3 repeats each; record pass@1, pass@k, cost and
   the failure profile.
3. Phase 3: build the whole endpoint on `ip_lib`, run on the board with the PC client and fuzzer, and measure the numbers.
