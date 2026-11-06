# Reference QoR: P13-5

Memory estimate by the course's sizing exercise: 16 x 96 = 1536 cells, 16-bit counts = 2 RAMB18 or 1 RAMB36 (`hough_bram36` of 16 angles, 32 x 32 picture, 1024 votes = 1). The
reference clears all cells in one clock, which a block RAM cannot do (a sweep or a generation counter is the real design). Vivado QoR: **not run**.
