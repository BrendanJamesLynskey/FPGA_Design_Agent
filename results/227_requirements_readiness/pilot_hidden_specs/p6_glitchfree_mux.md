# P6 hidden full spec (oracle only): answers the user would give about the glitch-free clock mux
Written for brief 227 as the user's answers; it adds facts the request leaves open and carries no test values.
- Reset: SEL 0 (clock A), GATE_LEN 25,000,000, SWITCH_COUNT 0, MUX_ERRS 0, STATUS 0, FREQ_STATUS 0, FREQ_COUNT 0.
- A write to SEL with the same value as the current selection is not a switch: SWITCH_COUNT does not change and SWITCHING stays 0. A write to SEL with the other value starts a switch; SWITCHING is 1 until ACTIVE_SEL equals SEL, and SWITCH_COUNT increments on completion.
- A write to SEL while SWITCHING is 1 is queued: the last value written wins and is acted on when the current switch ends (a switch is never aborted).
- B_DIV is fixed at build time to 1 (clock B is the GT reference clock undivided) and the register reads 1; the divide range 1 to 8 stays in the interface.
- The muxed-domain counter is 32 bits and wraps. MUX_ERRS counts a compare mismatch between the counter and its Gray-coded twin, or a counter step other than +1, per muxed clock; it is 32 bits, saturates at 0xFFFFFFFF and never counts while the muxed clock is stopped.
- During the switch itself the muxed clock is allowed to stop for a few cycles (as the BUFGCTRL mux does); no count is made during that time and the counter is not reset.
- FREQ_CTRL.START is ignored while BUSY. A frequency measurement counts edges of the muxed clock in a gate of GATE_LEN cycles of the C3 clock; it is valid only if no switch happens inside the gate: a SEL change during a gate is held off until the gate ends (SWITCHING is not raised until then).
- GATE_LEN below 1000 is stored as 1000. DONE stays set until the next START.
- SNAPSHOT latches MUX_COUNT across the clock domains with a handshake; any write value is accepted.
- The CDC between the muxed domain and the bus clock is by documented crossings (a handshake for the snapshot, synchronised flags for status); constraints use set_max_delay -datapath_only, with no blanket clock groups.
- Names and files: the top-level module is named `p6_glitchfree_mux_top` in `rtl/p6_glitchfree_mux_top.sv`; the register-port core (the logic behind the `h_*` port, with no vendor primitive) is a separate module named `p6_glitchfree_mux_core` in `rtl/p6_glitchfree_mux_core.sv`, with ports `clk`, `rst` (active high), `h_we`, `h_re`, `h_addr[11:0]`, `h_wdata[31:0]`, `h_rdata[31:0]` and the design's own signals. Files are SystemVerilog (`.sv`). The bench drives the core.
