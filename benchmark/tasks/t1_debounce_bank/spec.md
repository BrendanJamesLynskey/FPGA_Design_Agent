# Sixteen-switch debounce bank

I want all sixteen slide switches of the Nexys A7-100T cleaned up, each on its own.

- Every switch is synchronised and debounced separately: a switch's clean level only changes once the switch
  has stayed at the new level for the whole debounce time; anything shorter is noise and is ignored completely,
  however it lines up with anything else.
- LED[15:0] show the sixteen clean levels.
- For each switch, count how many times its clean level has changed (a small counter per switch is enough).
- Keep a register of sticky edge flags, one per switch, that I clear by writing ones to it. I want to choose, per
  switch, whether rising edges, falling edges or both set the flag.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can read the clean levels, the counts and the edge flags, clear
  them, and set the edge selection. The design ID is "DBNK".

Test hooks: top module `t1_debounce_bank_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (the debounce time in clocks)
as top-level parameters.
