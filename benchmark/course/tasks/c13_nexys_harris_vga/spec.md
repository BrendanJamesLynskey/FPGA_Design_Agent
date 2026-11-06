# Corner finder behind the test shell

I want a block for the Nexys A7-100T's FPGA that finds the corners of the bright rectangles in a small picture, and I want to exercise it entirely from the test shell.

- The picture is 80 pixels wide and 60 high, 8-bit grey, and arrives as a stream of pixels, one per clock when available, row by row, with a start-of-picture mark and an end-of-line mark. It shows a few bright
  rectangles on a dark background; a different picture can follow.
- Find the corners of the rectangles. A corner is reported once, at the corner pixel: not along the edges, and not as a cluster of neighbouring pixels. Rectangles that are only faintly brighter than the background
  have no corners worth reporting. A rectangle that touches the edge of the picture has only the corners that are inside the picture; the edge of the picture itself is not a corner.
- When the picture has been processed, tell me how many corners were found and where each one is (x and y in whole pixels, x counted from 0 at the left and y from 0 at the top), as a list I can read.
- The 16 LEDs show, in binary, how many corners were found in the picture.
- The red CPU reset button returns the block to idle and forgets the list.

The shell is slow, so the stream is driven for me: I park a whole picture over the shell (four pixels per write, row by row, the first pixel of a word in its lowest byte) and give a "go" command, and the block
then presents the pixels to the stream, one per clock. A status flag says busy from "go" until the list is final, and another says that a list is available. I read the number of corners, and then the corners one
at a time (I select a place in the list and read it). The shell runs at 115200 baud on the USB-UART. The design ID is "HARR".

Test hooks: top module `c13_nexys_harris_vga_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
