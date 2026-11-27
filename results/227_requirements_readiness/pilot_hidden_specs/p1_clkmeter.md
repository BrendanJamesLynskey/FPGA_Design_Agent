# P1 hidden full spec (oracle only): answers the user would give to questions about the clock-frequency meter
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: every register resets to 0 except GATE_LEN (156,250,000) and ID. STATUS.BUSY and STATUS.DONE are 0 after reset. COUNT, GATE_ACTUAL and MEAS_DONE are 0 after reset. LED_EN is 0 after reset, both LEDs are off.
- A write of GATE_LEN below 1,000 is stored as 1,000 (clamped); reading GATE_LEN back returns the clamped value. A write of GATE_LEN while BUSY is ignored.
- START written while BUSY is ignored and does not restart the gate. START written when GATE_LEN has been set returns BUSY=1 within 2 register-clock cycles and DONE=0 at once.
- DONE is set when the last reference cycle of the gate has been counted and COUNT and GATE_ACTUAL hold the final results in the same clock; DONE stays set until the next accepted START.
- COUNT is the number of rising edges of the 25 MHz C3 clock seen in the gate, counted after a two-flop synchroniser into the reference clock domain; plus or minus 1 edge is accepted. COUNT is 32 bits and does not saturate (it cannot overflow with the permitted gate lengths).
- MEAS_DONE increments by one on every completed measurement, wraps at 32 bits.
- LED 0 toggles every 12,500,000 cycles of the C3 clock and LED 1 every 78,125,000 cycles of the reference clock, only while LED_EN is 1; with LED_EN 0 both are 0.
- SCRATCH resets to 0 and reads back what was written. BUILD reads the USR_ACCESSE2 word. Writes to read-only registers are ignored. Unmapped addresses read 0.
- The register bus clock is the reference clock (156.25 MHz); a read returns the addressed value two clocks after h_re and holds it until the next h_re.
- sfp_tx_disable is driven 1 from reset on, always. No GT transceiver channel is used. The design must meet timing at 156.25 MHz with no unconstrained clock crossing; the C3 clock crossing is a documented asynchronous crossing.
- Names and files: the top-level module is named `p1_clkmeter_top` in `rtl/p1_clkmeter_top.sv`; the register-port core (the logic behind the `h_*` port, with no vendor primitive) is a separate module named `p1_clkmeter_core` in `rtl/p1_clkmeter_core.sv`, with ports `clk`, `rst` (active high), `h_we`, `h_re`, `h_addr[11:0]`, `h_wdata[31:0]`, `h_rdata[31:0]` and the design's own signals. Files are SystemVerilog (`.sv`). The bench drives the core.
