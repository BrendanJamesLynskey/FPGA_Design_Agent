# Scrolling message on the eight 7-segment digits

I want to scroll a short message across the Nexys A7-100T's eight 7-segment digits, with full control of every
segment (it is for odd symbols and letters, not numbers).

- The message is up to 16 characters, and each character is a raw segment pattern I write myself: one byte per
  character, bit 0 = segment a through bit 6 = segment g, bit 7 = the decimal point, 1 = lit. No character
  decoding of any kind in the FPGA. The message buffer sits at window offsets 0x10 to 0x1F of the test shell.
- A length register (1 to 16) says how much of the buffer is the message. The digits show an 8-character window
  onto the message, which wraps round continuously (a message shorter than 8 just repeats).
- When scrolling is on, the window moves by one character every so often (a parameter, in clocks); a direction
  bit chooses which way. I also want to read and set the current scroll position.
- A brightness setting from 0 to 7 that dims the whole display by shortening how long each digit is lit.
- Design ID "MARQ".

Test hooks: top module `t2_sevenseg_marquee_top`, ports named as in the board's master XDC (`CA`..`CG`, `DP`,
`AN`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and
`BUILD_STAMP` parameters, plus `SCROLL_CYCLES` (clocks between scroll steps) and `REFRESH_BITS` (each digit's
time slot is 2^REFRESH_BITS clocks) as top-level parameters.
