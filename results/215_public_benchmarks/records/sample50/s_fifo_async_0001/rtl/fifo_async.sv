// Asynchronous FIFO with Gray-coded pointers.
module fifo_async #(
    parameter int DATA_WIDTH = 8,
    parameter int DEPTH      = 16
) (
    input  logic                  w_clk,
    input  logic                  w_rst,
    input  logic                  w_inc,
    input  logic [DATA_WIDTH-1:0] w_data,
    input  logic                  r_clk,
    input  logic                  r_rst,
    input  logic                  r_inc,
    output logic                  w_full,
    output logic                  r_empty,
    output logic [DATA_WIDTH-1:0] r_data
);
    localparam int AW = (DEPTH > 1) ? $clog2(DEPTH) : 1;
    localparam int PW = AW + 1;

    logic [DATA_WIDTH-1:0] mem [DEPTH];

    logic [PW-1:0] wbin, rbin, wgray, rgray;
    logic [PW-1:0] wbin_nxt, rbin_nxt, wgray_nxt, rgray_nxt;
    logic [PW-1:0] rgray_w, rgray_w1;  // read Gray pointer synchronised into w_clk (stage 2, stage 1)
    logic [PW-1:0] wgray_r, wgray_r1;  // write Gray pointer synchronised into r_clk
    logic          w_en, r_en;

    // Power-up values equal the reset values (empty, not full).
    /* verilator lint_off PROCASSINIT */
    logic w_full_q = 1'b0;
    logic r_empty_q = 1'b1;
    /* verilator lint_on PROCASSINIT */
    // Flags are registered; reset takes effect at the clock edge (synchronous reset).
    assign w_full  = w_full_q;
    assign r_empty = r_empty_q;

    assign w_en = w_inc && !w_full;
    assign r_en = r_inc && !r_empty;

    assign wbin_nxt  = wbin + PW'(w_en);
    assign rbin_nxt  = rbin + PW'(r_en);
    assign wgray_nxt = (wbin_nxt >> 1) ^ wbin_nxt;
    assign rgray_nxt = (rbin_nxt >> 1) ^ rbin_nxt;

    // Flags are registered, computed from the next pointer and next synchronised value.
    always_ff @(posedge w_clk) begin
        if (w_rst) begin
            wbin     <= '0;
            wgray    <= '0;
            w_full_q <= 1'b0;
        end else begin
            wbin     <= wbin_nxt;
            wgray    <= wgray_nxt;
            w_full_q <= (wgray_nxt == {~rgray_w1[PW-1:PW-2], rgray_w1[PW-3:0]});
        end
    end

    always_ff @(posedge r_clk) begin
        if (r_rst) begin
            rbin      <= '0;
            rgray     <= '0;
            r_empty_q <= 1'b1;
        end else begin
            rbin      <= rbin_nxt;
            rgray     <= rgray_nxt;
            r_empty_q <= (rgray_nxt == wgray_r1);
        end
    end

    always_ff @(posedge w_clk) begin
        if (w_en && !w_rst) mem[wbin[AW-1:0]] <= w_data;
    end

    assign r_data = mem[rbin[AW-1:0]];

    sync_2ff #(.WIDTH(PW)) u_sync_r2w (.clk(w_clk), .rst(w_rst), .d(rgray), .q(rgray_w), .q1(rgray_w1));
    sync_2ff #(.WIDTH(PW)) u_sync_w2r (.clk(r_clk), .rst(r_rst), .d(wgray), .q(wgray_r), .q1(wgray_r1));

    // Stage-2 outputs are the architectural synchronised pointers; the flags use stage 1
    // because the flag register adds the second stage of delay.
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_sync;
    assign unused_sync = ^{rgray_w, wgray_r};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
