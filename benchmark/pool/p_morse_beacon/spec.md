# Morse beacon

I want an LED that sends a short message in Morse code, with the message sent from the PC.

- I send characters one at a time into a buffer of 16. Letters (either case) and digits are accepted; a space is a
  word gap; anything else is ignored. Characters that do not fit are dropped and counted.
- When I start it, it sends the message once, keying LED[0] (and Pmod JA pin 1) on and off with standard International
  Morse timing: a dot is one unit, a dash three, one unit between the marks of a letter, three between letters
  and seven between words. The key is off at the end with no trailing gap.
- If SW[0] is up when the message has finished, it pauses for a long gap and sends it again, and keeps repeating
  until SW[0] goes down.
- LED[1] is lit while it is sending.
- Over the test shell (USB-UART, 115200 baud) I can load the buffer, clear it, start, and read how many characters
  are buffered, how many were dropped and whether it is busy. The design ID is "MORS".

Test hooks: top module `p_morse_beacon_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `UNIT_CYCLES` (clocks in one Morse unit) as a
top-level parameter.
