# Clock-frequency meter (fixture)

Count the rising edges of an asynchronous clock `clk_in` over a window of 8 cycles of the reference clock `clk_ref`, after a one-cycle `start`
request, then show the count. `busy` is high while the window is open and `valid` when the count is ready. A read of the count (`reg_rd`) returns it
on `reg_rdata` one cycle later with `reg_rvalid`. A start while busy is ignored.
