# UDP command and telemetry endpoint

I want a board that obeys commands sent as UDP datagrams and reports on itself, built for the Nexys A7-100T. Everything runs on the single 125 MHz system clock (an 8 ns period in the clock constraint). The network blocks
(Ethernet, IP, UDP) already deliver each datagram's payload as a stream of bytes with a flag on the last one, and take reply
payloads the same way, so this block works at the payload level. For testing, I give it the payload bytes one at a time through the test shell on the USB-UART (115200 baud) and read the reply frames back.

**Commands.** A command packet is, in order: one byte of type (1 read, 2 write, 3 status, 4 telemetry start, 5 telemetry stop);
one byte, the payload length (0 to 8); two bytes of sequence number, high byte first; the payload; and a four-byte CRC-32 trailer, low byte first, covering the bytes before it (the Ethernet CRC-32: reflected 0xEDB88320, initial value 0xFFFFFFFF, result inverted, as `zlib.crc32` computes it). The payload a type needs: read 2 bytes (a register number), write 6
(a register number, then a 32-bit value, high byte first), telemetry start 2 (the period in ticks), status and stop none.

**Registers.** Eight 32-bit registers: 0 identification word 0x55445031 (read only; this is also the word the shell's design-ID register must show); 1, 2 and 3 scratch (read and write, 0 after
reset); 4 the number of commands carried out (read only); 5 the number of packets refused of any kind (read only); 6 the telemetry
period, 100 after reset (read only); 7 the number of ticks since reset (read only). A read of register 4 or 5 shows the count as
it was before that read was counted.

**Replies.** Every packet that is whole, has the right check and a known type and length gets a reply, with the same sequence
number: one byte, the type with the top bit set; one byte of status; two bytes of sequence number; one byte, the payload length;
the payload; the four-byte CRC-32 trailer as for commands, over the bytes before it. Status: 0 OK, 1 unknown type, 2 wrong length for the type,
3 unknown register (a number of 8 or more), 4 sequence number refused, 5 write to a read-only register. A read replies with the
register's value as four bytes, high byte first; a status command replies with sixteen bytes and one more: seven 16-bit counters
(commands carried out, bad check, too short, too long, repeated number, out-of-order number, and type, length, register or access
errors), a 16-bit count of telemetry frames, and one byte that is 1 if telemetry is on. The counters wrap at 65536 and show the
counts before this command is counted.

**Refusals.** A packet is judged in this order and the first rule that applies decides: too long (the length byte above 8, or more
bytes than the length announces); too short (ends before its announced size, or before four bytes); bad check; unknown type;
wrong length for the type; sequence number refused; then register number and access. A packet of fewer than four bytes is too short whatever its bytes say. The first three are dropped silently: no
reply. Each refused packet is counted in exactly one counter and counts in the refused-packets register. A sequence number is new
when (number minus the last accepted number) modulo 65536 is from 1 to 32767; after reset the first packet may carry any
number. A packet with a repeated or old number is refused with status 4 and changes nothing. A packet that passes the sequence
rule uses up its number even if the register number or access then fails it (and that failure is counted). A refused packet
never changes a register, the last accepted number or the telemetry state, and the block is ready for the next packet as soon as
the byte with the end flag has been handled; I never send a new packet before the reply to the last one has been built (within 100 clocks).

**Telemetry.** Telemetry start with a non-zero period sets the period (4 if lower); zero keeps it; it switches telemetry on and
restarts the count. While on, a frame falls due every period-th tick. The block holds one frame at most: a frame falling due while
one is held is dropped, never queued. A frame is: type 0xC0, status 0, its own sequence number (0 for the first frame, then up by
one), length 8, then the tick count (4 bytes), the commands-carried-out count (2 bytes) and the refused-packets count (2 bytes),
all as they were when it fell due (the uptime includes the tick that made the frame due), all high byte first, then the CRC-32. The frame sequence number and the telemetry frame count rise only when a frame is held (a dropped frame uses neither) and are cleared only by reset, not by stop or start. Telemetry stop switches it off and forgets a held frame.
I take the held frame away by writing to the take register.

**Time** reaches the block through the tick register: writing n (0 to 255) makes n ticks, one on each of the next n clocks.

I can read the length of the latest reply in bytes (zero if the latest packet earned none), and its bytes four at a time: I write
a word number i, and the next read gives bytes 4i to 4i+3 of the reply with the first of them in the top byte, bytes past its end
reading as zero. The same for the held telemetry frame: its length (zero if none) and its words. I can also read a status word (bit 0: telemetry on; bit 1:
the block is busy). LED[15:0] shows the commands-carried-out count. CPU_RESETN resets everything. The design ID is "UEP1".

Bench notes: the top module is `v2_e_udp_endpoint_top`; the port names follow the board's master XDC; the shell parameters `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` are supplied.
