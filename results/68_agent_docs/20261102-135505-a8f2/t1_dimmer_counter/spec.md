# T1: LED dimmer and push-button counter (natural-language spec)

*Written as a user would write it. `spec.yaml` is the structured version that the agent will produce from text like
this; where this text is vague, `spec.yaml` records the assumption made and why.*

I want a small design for the Nexys A7-100T that I can see working on the board and test over the USB cable.

- There is a 16-bit counter. The **up** button adds one, the **down** button takes one away, and the **centre**
  button clears it. One press should change it by exactly one, however bouncy the button is. It wraps around at
  both ends.
- The 16 LEDs show the counter in binary, and their **brightness** is adjustable with PWM. The brightness is set by
  a register over the UART, or, if I flip a control bit, by the eight right-hand switches. It should not flicker.
- The **7-segment display** shows the counter in hex on the four right-hand digits and the current brightness
  setting in hex on the two left-hand digits. The middle two digits are off. The display can be turned off by a
  register bit.
- The red **CPU reset** button resets everything.
- Everything is reachable through the standard test shell over the USB-UART at 115200 baud: I can read and set the
  counter, read and set the brightness, read the buttons and switches, and see how many times each button has been
  pressed, so a script can test the board without anyone watching it.
- The design ID reads "T1DC".
