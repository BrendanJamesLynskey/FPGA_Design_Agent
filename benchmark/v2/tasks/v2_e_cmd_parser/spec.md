# Command packet screener

I want the front end of a small command protocol, built for the Nexys A7-100T. Packets of a command protocol arrive as a
stream of bytes, one byte per write to a byte register, with a flag on the byte that ends the packet. The block must decide,
for every packet, whether it is a good command, and if not say why. It does not carry the command out: it only screens
packets and hands over the fields of the good ones.

A command packet is, in order:

- one byte of command type: 1 read, 2 write, 3 status, 4 telemetry start, 5 telemetry stop;
- one byte, the length of the payload that follows (0 to 8);
- two bytes of sequence number, high byte first;
- the payload, as many bytes as the length says;
- four bytes of cyclic redundancy check, low byte first: the Ethernet CRC-32 (reflected, polynomial 0xEDB88320, start
  0xFFFFFFFF, final inversion, the same as `zlib.crc32` in Python) over every byte before them.

The payload a type needs is fixed: read 2 bytes (a register address), write 6 (an address, then a 32-bit value, high byte
first), telemetry start 2, status and telemetry stop none.

Every packet ends up in exactly one of these classes, and the first rule that applies decides:

1. Too long: the length byte is above 8, or more bytes arrive than the length announces.
2. Too short: the packet ends before its announced size (including a packet of fewer than four bytes, whatever those bytes say: a packet of three bytes with a length byte of 9 is too short).
3. Bad check: the check bytes do not match.
4. Unknown type, or a length that is not the one the type needs.
5. Not new: the sequence number is "new" when (number minus the last accepted number) modulo 65536 is between 1 and 32767. The
   number equal to the last accepted one is a repeat; any other is out of order. After reset the first packet may carry any
   number.
6. Good: it is counted, its type, sequence number and payload fields are kept, and its sequence number becomes the last
   accepted number. A packet in any other class changes nothing except its counter and the result register.

A packet of any kind, however damaged, must leave the block ready for the next packet: the byte that carries the end flag
always ends the packet.

I read the outcome through the test shell on the USB-UART (115200 baud): the class of the last packet, the type, the sequence number,
the address-or-period field (first two payload bytes) and the value field (next four payload bytes; zero if the packet had
none), the last accepted sequence number, whether a packet is part-way through, and one counter per class. Counters are
16 bits and wrap. LED[7:0] shows the good-packet count and LED[15:8] the low byte of the last accepted sequence number.
CPU_RESETN resets everything. The design ID is "CPS1".

Bench notes: the top module is `v2_e_cmd_parser_top`; port names follow the board's master XDC; the shell's parameters
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` are present. After each byte write the block has about four clocks to finish with it.
