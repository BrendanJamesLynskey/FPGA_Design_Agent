# Telemetry pacer

I want the timing block of a status-reporting stream, built for the Nexys A7-100T. A board sends me a report frame every
so many "ticks" while I have switched reporting on, and it must never report faster than that, however slowly the
transmitter takes the frames away. The block does not build the frames; it decides when one is due.

- Reporting is switched on and off with an enable bit. Switching on starts counting from zero. Switching off stops
  counting, forgets any frame that was waiting, and leaves the totals as they are.
- Each tick, while enabled, advances a counter. When the counter reaches the period, it goes back to zero and a frame
  falls due. A period of 100 means a frame on every 100th tick, exactly, however long reporting stays on.
- The period I ask for is a 16-bit number (100 after reset). The period in force is that number, raised to
  `PERIOD_MIN` (4 by default) if it is lower. A new request does not disturb the frame being counted towards: it takes
  effect from the start of the next count, or from the moment reporting is switched on.
- The block holds one waiting frame at most. A frame that falls due while the previous one is still waiting is not
  queued: it is dropped and counted as an overrun. The transmitter takes the waiting frame with a write to the take
  register; taking when nothing waits does nothing.
- It counts the frames that fell due and were held (16 bits, wrapping) and the overruns (16 bits, wrapping). The totals
  survive switching off and on; only CPU_RESETN clears them.
- Time reaches the block through a tick register: writing a number n from 0 to 255 to it makes n ticks happen, one on each
  of the next n clocks (the next write is far enough away that they have finished).
- I can read: the enable bit, the period asked for, the period in force, the status (frame waiting, enabled), the two totals,
  and the counter. LED[15:0] shows the frame total.
- CPU_RESETN resets everything: off, period 100 asked and in force, nothing waiting, totals and counter zero.
- All of it is reachable through the test shell on the USB-UART (115200 baud); the design ID is "TLP1".

Bench notes: the top module is `v2_e_tlm_pacer_top` and it has a parameter `PERIOD_MIN`; its ports use the board's master XDC
names; the shell parameters `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` are there as well.
