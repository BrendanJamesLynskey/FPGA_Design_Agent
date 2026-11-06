# Blob finder behind the test shell

I want a block for the Nexys A7-100T's FPGA that finds the biggest bright object in a small picture and says where its middle point is, and I want to exercise it entirely from the test shell.

- The picture is 40 pixels wide and 30 high, one bit per pixel (1 = bright), and arrives as a stream of pixels, one per clock when available, with a start-of-picture mark and an end-of-line mark.
  The pictures contain a few bright rectangles on a dark background and a stray pixel or two; sometimes two touch only at a corner, and one object is U-shaped.
- An object is a group of bright pixels that touch along their sides (up, down, left or right). Two groups that touch only at a corner are two objects; a U-shaped object is one object.
- When a picture has gone by, tell me the area (the number of pixels) of the biggest object and its middle point: the average of its pixel coordinates in whole pixels, rounded down, x counted from 0 at the
  left and y from 0 at the top. If two objects have the same area, the one that starts higher (the smaller top row), and if that is also equal, the one further left, is the biggest.
- A new picture can follow a finished one, and nothing is left over from the earlier picture.

The shell is slow, so the stream is driven for me: I park a whole picture over the shell (32 pixels per write, row by row, the first pixel of a word in its lowest bit) and give a "go" command, and the block
then presents the pixels to the stream, one per clock. A status flag says busy from "go" until the report for that picture is final, and another says that a report is available. I read the area and the x and y of
the middle point over the shell. CPU_RESETN returns the block to idle and forgets the report. LED0 shows busy. The shell runs at 115200 baud on the USB-UART. The design ID is "BLOB".

Test hooks: top module `c13_nexys_blob_tracker_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
