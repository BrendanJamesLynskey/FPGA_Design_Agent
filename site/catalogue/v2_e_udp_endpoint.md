# UDP command and telemetry endpoint (v2_e_udp_endpoint)

Domain E (networking), tier T2 (L2, the whole endpoint), Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_udp_endpoint/`.

## The problem, and where it is used

The whole command-and-telemetry endpoint behind a UDP payload stream: screening, sequence numbers, execution, replies with CRC-32 and a rate-limited telemetry stream.

Embedded boards, instruments and test rigs commonly expose a small UDP command port with a telemetry stream. Getting the refusal rules right (damaged, truncated, oversize, repeated and old packets) without ever hanging or changing state is what makes it safe to leave on a network.

## Hero diagram

A packet's bytes stream in; a checker lights each rule in turn (length, check, type, number) until one refuses or all pass; a pass reaches the register bank and a reply is built byte by byte; beside it a tick counter drives the telemetry slot.

## Animation plan (driven by `hidden/model.py`)

Use Model.packet() and Model.write() from hidden/model.py to run a packet and show the rule that decided, the state, the reply and the telemetry slot, with a fuzz button that damages the packet.

## Interface

Shell registers: IN (packet bytes with an end flag), TICK, the reply length and words, the telemetry length and words, TAKE, STAT. LED[15:0] shows the commands-carried-out count. The design follows the protocol in showcase/udp_endpoint/protocol.md.

## Acceptance criteria in plain words

Packets are judged in a fixed order and the first rule that applies decides; the first three refusals are silent, the rest get a reply with a status code; a refused packet changes nothing and the block is ready for the next one; a command that passes the sequence rule uses up its number; telemetry frames fall due every period-th tick, one is held, overruns are dropped; replies and frames carry a CRC-32.
