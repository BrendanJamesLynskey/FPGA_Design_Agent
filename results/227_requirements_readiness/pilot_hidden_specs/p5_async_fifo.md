# P5 hidden full spec (oracle only): answers the user would give about the asynchronous-FIFO soak test
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: RUN 0, SLOW_READ 0, all counters 0, both sequences at the seed 0x7FFFFFFF, the FIFO empty. A reset is asynchronous-assert, synchronous-release in each clock domain.
- RUN 0 to 1 starts both the writer and the reader from the seed; RUN 1 to 0 stops the writer first, then the reader keeps reading until the FIFO is empty. The counters keep their values until CLEAR.
- CLEAR is accepted only while RUN is 0; a CLEAR written while RUN is 1 is ignored. CLEAR also empties the FIFO and restarts both sequences from the seed.
- The PRBS is a Fibonacci LFSR advanced 32 times per word; bits are packed with the first generated bit as bit 0 of the word.
- INJECT flips bit 0 of the next received word before the check, once; DATA_ERRS then counts 1. A second INJECT while one is pending is ignored.
- A write while full (an overflow) cannot happen because the writer waits; OVERFLOWS counts a write attempt that the FIFO rejected and must stay 0. UNDERFLOWS counts a read attempt on an empty FIFO and must stay 0. They are monitors, not behaviours.
- STALL_W counts writer clock cycles in which the writer had a word to write and the FIFO was full. OCC_MAX is the maximum of the FIFO's occupancy as seen from the writer side (conservative) over all time since CLEAR.
- SNAPSHOT: a write latches all counters into holding registers at one reader-clock instant; the counters of the two domains are brought across with a documented handshake so that the set is consistent to within one word. WORDS_W and WORDS_R in a snapshot may differ by up to the FIFO depth.
- All counters are 32 bits and wrap without any flag.
- The FIFO is a Gray-coded pointer asynchronous FIFO with 2-flop synchronisers, depth 512 words; the constraints are set_max_delay -datapath_only on the pointer crossings, not a clock group between the two clocks.
- Names and files: the top-level module is named `p5_async_fifo_top` in `rtl/p5_async_fifo_top.sv`; the register-port core (the logic behind the `h_*` port, with no vendor primitive) is a separate module named `p5_async_fifo_core` in `rtl/p5_async_fifo_core.sv`, with ports `clk`, `rst` (active high), `h_we`, `h_re`, `h_addr[11:0]`, `h_wdata[31:0]`, `h_rdata[31:0]` and the design's own signals. Files are SystemVerilog (`.sv`). The bench drives the core.
