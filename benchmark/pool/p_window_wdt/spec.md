# Window watchdog

I want a watchdog that is strict in both directions, for exercising a supervisor program on the PC.

- The PC "kicks" the watchdog by writing a secret key to it. A kick must come neither too early nor too late: the
  watchdog times from the previous kick, and a kick is only good inside a window that opens a while after it and
  closes a while later.
- A good kick starts the timing again. A kick that comes before the window opens is a fault, and so is no kick at
  all by the time the window closes. After any fault the timing starts again.
- A fault puts a pulse of fixed length on Pmod JA pin 1 and lights LED[0] until I clear it. LED[1] follows the pulse.
- SW[0] up enables the watchdog; while it is down nothing is timed and nothing faults.
- I want to read the status, how many early and late faults there have been and how many wrong keys were
  written, over the test shell (USB-UART, 115200 baud). The design ID is "WWDT".

Test hooks: top module `p_window_wdt_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `WIN_OPEN` and `WIN_CLOSE` (clocks after the
previous kick at which the window opens and closes) and `RST_PULSE` (pulse length in clocks) as top-level parameters.
