// Asynchronous FIFO, 512 x 32, 10-bit binary pointers (extra wrap bit) crossed in Gray code
// by xpm_cdc_gray with two-flop synchronisers. The RAM is xpm_memory_sdpram (independent clocks).
module async_fifo (
    // write side
    input  logic        wclk,
    input  logic        w_clr,        // synchronous clear of the write pointer
    input  logic        w_en,
    input  logic [31:0] w_data,
    output logic        w_full,
    output logic [9:0]  w_fill,       // conservative fill seen from the write side
    output logic        w_overflow,   // write enabled while full
    // read side
    input  logic        rclk,
    input  logic        r_clr,
    input  logic        r_en,
    output logic [31:0] r_data,       // valid the cycle after r_en
    output logic        r_empty,
    output logic        r_underflow   // read enabled while empty
);
    logic [9:0] wptr, rptr, rptr_w, wptr_r;

    assign w_fill     = wptr - rptr_w;
    assign w_full     = w_fill[9];
    assign r_empty    = (wptr_r == rptr);
    assign w_overflow  = w_en && w_full;
    assign r_underflow = r_en && r_empty;

    wire do_w = w_en && !w_full;
    wire do_r = r_en && !r_empty;

    always_ff @(posedge wclk) begin
        if (w_clr)     wptr <= '0;
        else if (do_w) wptr <= wptr + 10'd1;
    end

    always_ff @(posedge rclk) begin
        if (r_clr)     rptr <= '0;
        else if (do_r) rptr <= rptr + 10'd1;
    end

    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(10)) u_w2r (
        .src_clk(wclk), .src_in_bin(wptr), .dest_clk(rclk), .dest_out_bin(wptr_r));

    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(10)) u_r2w (
        .src_clk(rclk), .src_in_bin(rptr), .dest_clk(wclk), .dest_out_bin(rptr_w));

    // inferred simple dual-port block RAM, independent clocks
    (* ram_style = "block" *) logic [31:0] mem [512];
    always_ff @(posedge wclk) if (do_w) mem[wptr[8:0]] <= w_data;
    always_ff @(posedge rclk) if (do_r) r_data <= mem[rptr[8:0]];
endmodule
