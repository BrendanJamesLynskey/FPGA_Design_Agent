# UDP command and telemetry endpoint for the Nexys A7-100T

I want the Nexys A7-100T to answer commands sent from my PC as UDP datagrams over its Ethernet port, and to send me a
steady stream of status counters while I ask for it. Build it on the network blocks already in the project's IP
library (the Ethernet MAC, the IPv4/UDP receive and transmit blocks, ARP and ping), so that the board also answers ARP
requests and pings at its address.

**Commands.** A command is one datagram to the board's UDP port. It has a type, a sequence number I choose, a few
bytes of payload and a CRC-32 over everything before it. The types I need: read a register, write a register, report
the board's status counters, start the telemetry stream (with its period) and stop it. There are eight 32-bit
registers: an identification word, three scratch registers I can read and write, and four read-only ones (commands
accepted, packets rejected, the telemetry period, an uptime counter).

**Answers.** Every command that is well formed gets an answer carrying the same sequence number: OK, or an error code
(unknown command, wrong length, unknown register, write to a read-only register, bad sequence number).

**Telemetry.** While it is on, the board sends me a frame with its uptime and counters once per period. I can set the
period. The board must never send faster than that, however busy it is.

**Robustness.** My PC will sometimes send garbage, and I want to know that it does no harm. Damaged, truncated,
oversized, repeated and out-of-order packets must be refused and counted, must not change anything, and must never make
the board stop answering. A command number that has already been used must not be run twice. A flood of packets may
cost me answers but not the board's health, and the counters must still add up.

**What I will check.** The maximum command rate, the delay from the last byte of a command to the first byte of its
answer (in clock cycles), the spread of the telemetry timing, and what happens under a flood. Give me these as numbers
in the specification, and a document of the packet formats that someone could write a client from. I would like a small
Python client to send commands, and a fuzzer that sends damaged packets, which can run against a model of the board
without any hardware.
