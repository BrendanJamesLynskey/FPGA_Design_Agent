// gray_fv.sv (brief 156): formal wrapper of the SystemVerilog twin gray_stepper. The twin's own `ifdef FORMAL assertions (REQ-01 one-bit step,
// the Gray-of-binary invariant) are read with -DFORMAL; this wrapper adds only the assumption that the first cycle is a reset cycle
// (the VHDL side says the same with `-- psl assume rst = '1'`), shrinks the time constants, and covers a change of the LEDs.
module gray_fv (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn,
    input  logic        dir_async,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata
);
    logic [15:0] led;
    logic [31:0] win_rdata;
    gray_stepper #(.DEBOUNCE_CYCLES(2), .TICK_CYCLES(2)) dut (.*);      // time constants shrunk so a step is reachable in 20 clocks
    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb if (first) assume (rst);
    logic [9:0] led_q;
    always_ff @(posedge clk) led_q <= led[9:0];
    always_ff @(posedge clk) cover_gray_changed: cover (!first && led[9:0] != led_q);      // the Gray register changed (a step or a BIN write)
endmodule
