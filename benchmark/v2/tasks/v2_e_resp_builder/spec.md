# Reply frame builder

I want the reply side of a small command protocol, built for the Nexys A7-100T. After the board has dealt with a command, it
must send back one reply packet, and I want a block that assembles it. I give the block the parts of the reply; it lays them
out as bytes, adds the check, and lets me read the finished packet back byte by byte.

A reply packet is, in order:

- one byte: the command type with the top bit set (type 3 is sent as 0x83);
- one byte: the status (0 means OK, other numbers are error codes);
- two bytes: the sequence number of the command being answered, high byte first;
- one byte: the length of the payload;
- the payload bytes;
- four bytes of check value, low byte first: the CRC-32 carried by Ethernet frames (the reflected form of polynomial 0xEDB88320,
  seeded with all ones, inverted at the end, as Python's `zlib.crc32` returns it), computed over all the bytes ahead of it.

How I use it, through the test shell on the USB-UART at 115200 baud:

- I write the type (7 bits are kept), the status (8 bits) and the sequence number (16 bits) into their registers; they stay
  until I write them again.
- I add payload bytes one at a time by writing to the payload register (the low byte). The block holds up to 24; a byte
  written when 24 are held is dropped and sets an overflow flag.
- I write to the build register. The block assembles the reply from the registers and the payload bytes held, then clears
  the payload (and the overflow flag) ready for the next reply. It needs up to 64 clocks to finish.
- The finished reply stays readable until the next build: I write a position into the index register, and the byte register
  then reads the reply byte at that position, or zero if the position is beyond the reply. The length register gives the
  reply's length in bytes (zero until the first build and after reset).
- I can read the number of payload bytes held now, and a status word (bit 0: building; bit 1: overflow).
- LED[7:0] shows the reply length and LED[15:8] its status byte (zero when there is no reply).
- CPU_RESETN resets everything. The design ID is "RSB1".

Bench notes: the top module is `v2_e_resp_builder_top`; its port names are those of the board's master XDC; the shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters are present.
