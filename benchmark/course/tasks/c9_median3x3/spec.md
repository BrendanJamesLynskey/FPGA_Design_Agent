# Median filter behind the test shell

I want a block for the Nexys A7-100T's FPGA that takes a 3 x 3 window of 8-bit pixels and returns the median value of the nine (the fifth smallest), to remove speckle noise from a video stream, and I want to exercise it entirely from the test shell. Nine multipliers or a software sort are out of the question: it has to be pure logic and run at 100 MHz.

- The order of the nine pixels in a window is irrelevant to a median.
- A window presented to the block at one clock gives its median as a result exactly one clock later (one clock of latency); there is no result on a clock unless a window was presented one clock earlier. A window can be presented on any clock or on consecutive clocks. CPU_RESETN clears the block and the loaded values.
- The block must close timing at 100 MHz.
- Over the shell I load up to 8 windows, give a 32-bit pattern that says on which of the next 32 clocks a window is presented (a 1 bit presents the next window, in order), and a "go". Afterwards I read the medians in order, how many results came out, and a 32-bit record of the clocks on which a result appeared, so that I can check the latency and that there are no extra results. I will compare a couple of hundred windows (random pixels, equal pixels, runs of 0 and 255, single outliers), with gaps.
- The shell runs at 115200 baud on the USB-UART. The design ID is "MEDN".

Test hooks: top module `c9_median3x3_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
