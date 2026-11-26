# P3 hidden full spec (oracle only): answers the user would give about the CRC-32 engine
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: CRC state is the start value 0xFFFFFFFF internally, so CRC reads 0x00000000 for no bytes (the final XOR is applied on read); BYTE_COUNT 0, BUSY_CYCLES 0, TAIL_LEN 0, CTRL 0.
- INIT written takes effect in the clock after the write and clears CRC state, BYTE_COUNT and BUSY_CYCLES; it wins over a PUSH4 or PUSH_N in the same clock (the push is dropped).
- PUSH4 consumes four bytes, least significant first; PUSH_N consumes the low TAIL_LEN bytes of the written word; with TAIL_LEN 0 it pushes nothing and BYTE_COUNT does not change. TAIL_LEN values above 3 cannot be written: the upper bits are ignored (only bits 1:0 are stored).
- The CRC register can be read at any time and shows the CRC of everything pushed so far, including the push of the previous clock cycle but not one in the same cycle.
- BYTE_COUNT is 32 bits and wraps. BUSY_CYCLES counts one per clock in which a push is processed (PUSH4 or PUSH_N with N>0), it is 32 bits and wraps; a PUSH_N with N = 0 does not count.
- Pushes can arrive in consecutive clocks without a gap; the engine accepts one push per clock and has no busy or back-pressure signal.
- Writes to read-only registers are ignored. Unmapped addresses read 0.
- The engine processes four bytes per clock in one clock cycle; the data clock is the register bus clock, which must be at least 100 MHz (it is 156.25 MHz).
- Names and files: the top-level module is named `p3_crc_engine_top` in `rtl/p3_crc_engine_top.sv`; the register-port core (the logic behind the `h_*` port, with no vendor primitive) is a separate module named `p3_crc_engine_core` in `rtl/p3_crc_engine_core.sv`, with ports `clk`, `rst` (active high), `h_we`, `h_re`, `h_addr[11:0]`, `h_wdata[31:0]`, `h_rdata[31:0]` and the design's own signals. Files are SystemVerilog (`.sv`). The bench drives the core.
