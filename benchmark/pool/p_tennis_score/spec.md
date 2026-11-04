# Tennis scoreboard

I want a scoreboard for one game of tennis between two players, with one button each.

- BTNL gives a point to the left-hand player (A) and BTNR a point to the right-hand player (B). The buttons bounce,
  so one press must score exactly once.
- Scoring is the real thing: 0, 15, 30, 40, then the game. At 40-40 (deuce) a player needs two clear points: the
  next point gives that player the advantage, and if the player with the advantage loses the next point it is deuce
  again.
- Player A's score is on the two left-hand digits of the display and player B's on the two right-hand digits. Advantage
  shows as "Ad" for the leader while the other still shows 40. When someone wins the game, the winner's two digits show
  two dashes and further points are ignored. The middle four digits stay dark.
- BTNC starts the next game. The game wins of each player are kept and shown on the LEDs: LED[15:12] for A and
  LED[11:8] for B in binary, and LED[0] lights while a game is over.
- CPU_RESETN clears everything. Over the test shell (USB-UART, 115200 baud) I can read the points and games. The
  design ID is "TENN".

Test hooks: top module `p_tennis_score_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks) and
`REFRESH_BITS` (each display digit is lit for 2^REFRESH_BITS clocks) as top-level parameters.
