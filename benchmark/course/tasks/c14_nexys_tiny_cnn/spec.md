# Tiny CNN shape classifier

I want the Nexys A7-100T to recognise which of four simple shapes is in a small grey picture, using a tiny neural network whose numbers I give you in files.

- The pictures: eight of them, each 12 by 12 pixels, each pixel a signed 8-bit number from 0 to 127 (`data/cnn_images.hex`, one number per line, picture after picture, row by row). They show a horizontal bar, a vertical
  bar, a box outline or a cross; the four classes are numbered 0 (horizontal bar), 1 (vertical bar), 2 (box), 3 (cross).
- The network, which must be followed exactly (all numbers are whole numbers):
  1. Layer 1: four filters of 3 by 3, each sliding over the picture without going over the edge (so the result is 10 by 10 for each filter). For each place, multiply the nine pixels by the filter's nine
     weights, add them and add the filter's bias. Then scale the total by the fraction M1 / 2^S1, rounding to the nearest whole number with exact halves going up, and limit it to 0 to 127 (so negatives become 0).
  2. Shrink each 10 by 10 result to 5 by 5 by keeping the largest of every 2 by 2 block.
  3. Layer 2: eight filters of 3 by 3 over all four 5 by 5 results at once (each filter has 36 weights, one 3 by 3 per input result; add everything and a bias), giving 3 by 3 for each filter; then scale by M2 / 2^S2, round and
     limit to 0 to 127 in the same way.
  4. Final layer: four sums, each of the 72 numbers from step 3 (taken filter by filter, row by row) times 72 weights, plus a bias. These four whole numbers ("scores") are not scaled or limited. The answer is the number of
     the biggest score (if two tie, the lower number).
- The file `data/cnn_params.hex` holds all 612 weights, 16 biases (a 32-bit signed number each) and M1, S1, M2, S2 (one 32-bit hexadecimal word per line, in the order: layer 1 weights, layer 2 weights, final
  layer weights, then the 16 biases, then M1, S1, M2, S2; the weights of a layer are ordered by filter, then input result, then row, then column).
- Using the board: switches SW0 to SW2 choose the picture (0 to 7). Pressing the centre button (it needs debouncing) classifies that picture. When the answer is ready, show its number (0 to 3) on the right-hand
  seven-segment digit (blank before the first answer) and send one letter on the USB serial port at 115200 baud, 8 data bits, no parity, 1 stop bit, followed by a line feed: H for 0, V for 1, B for 2, X for 3.
- I will check the letter and the digit for each of the eight pictures. The USB-UART carries the answer, so this design does not embed the test shell.

Test hooks: top module `c14_nexys_tiny_cnn_top`, ports named as in the board's master XDC, and the parameters `DEBOUNCE_CYCLES` (the button must be stable for this many clocks, 10 ms on the board) and `CLKS_PER_BIT` (868 on the board)
as top-level parameters; the bench shrinks both. There are no other time constants.
