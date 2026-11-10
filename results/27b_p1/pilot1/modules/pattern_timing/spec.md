Generates CEA-861 720p60 timing: 1650 pixel clocks per line and 750 lines
per frame, with 1280 by 720 active pixels, the specified porches and sync
intervals, and positive sync. Generates eight 160-pixel vertical colour
bars by default, and also provides a grayscale ramp and checkerboard.
Pattern values are 0=colour bars, 1=grayscale ramp, and 2=checkerboard.
Increments a 32-bit unsigned frame counter once per completed displayed
frame and resets it to zero.
