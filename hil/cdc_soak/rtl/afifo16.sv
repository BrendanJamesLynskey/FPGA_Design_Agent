`timescale 1ns / 1ps
// afifo16.sv: Cummings asynchronous FIFO (SNUG 2002, style #2), 16 x 16 in LUT RAM, for C10, C13 and M9.
// Gray pointers cross through 2-flop synchronisers (gsyn_*: constrained per copy with set_max_delay -datapath_only
// and set_bus_skew). Each side has its own asynchronous reset; rdata is the LUT-RAM output at the read address
// (registered by the user on a read). Registers named pbs_* sit on the write side, pbd_* on the read side.

module afifo16 #(
    parameter int AW = 4,
    parameter int DW = 16
) (
    input  logic          wclk,
    input  logic          wrst,
    input  logic          winc,
    input  logic [DW-1:0] wdata,
    output logic          wfull,
    input  logic          rclk,
    input  logic          rrst,
    input  logic          rinc,
    output logic [DW-1:0] rdata,
    output logic          rempty
);
    logic [DW-1:0] mem [2**AW];
    logic [AW:0] pbs_wbin = '0, pbs_wptr = '0, pbd_rbin = '0, pbd_rptr = '0;
    logic [AW:0] rq2_wptr, wq2_rptr;
    logic        pbs_full = 1'b0, pbd_empty = 1'b1;

    // pointer synchronisers (2 flops, ASYNC_REG, first flop injected in simulation)
    logic [AW:0] wq1, rq1;
    cff #(.W(AW+1), .ASYNC(1'b1), .INJ(1'b1)) pbs_gsyn_r1 (.clk(wclk), .arst(wrst), .d(pbd_rptr), .q(wq1));
    cff #(.W(AW+1), .ASYNC(1'b1))             pbs_gs2_r (.clk(wclk), .arst(wrst), .d(wq1),      .q(wq2_rptr));
    cff #(.W(AW+1), .ASYNC(1'b1), .INJ(1'b1)) pbd_gsyn_w1 (.clk(rclk), .arst(rrst), .d(pbs_wptr), .q(rq1));
    cff #(.W(AW+1), .ASYNC(1'b1))             pbd_gs2_w (.clk(rclk), .arst(rrst), .d(rq1),      .q(rq2_wptr));

    // write side
    wire [AW:0] wbinnext  = pbs_wbin + (AW+1)'(winc & ~pbs_full);
    wire [AW:0] wgraynext = (wbinnext >> 1) ^ wbinnext;
    wire        wfull_val = wgraynext == {~wq2_rptr[AW:AW-1], wq2_rptr[AW-2:0]};
    always_ff @(posedge wclk or posedge wrst)
        if (wrst) begin pbs_wbin <= '0; pbs_wptr <= '0; pbs_full <= 1'b0; end
        else begin pbs_wbin <= wbinnext; pbs_wptr <= wgraynext; pbs_full <= wfull_val; end
    always_ff @(posedge wclk)
        if (winc && !pbs_full) mem[pbs_wbin[AW-1:0]] <= wdata;
    assign wfull = pbs_full;

    // read side
    wire [AW:0] rbinnext   = pbd_rbin + (AW+1)'(rinc & ~pbd_empty);
    wire [AW:0] rgraynext  = (rbinnext >> 1) ^ rbinnext;
    wire        rempty_val = rgraynext == rq2_wptr;
    always_ff @(posedge rclk or posedge rrst)
        if (rrst) begin pbd_rbin <= '0; pbd_rptr <= '0; pbd_empty <= 1'b1; end
        else begin pbd_rbin <= rbinnext; pbd_rptr <= rgraynext; pbd_empty <= rempty_val; end
    assign rdata  = mem[pbd_rbin[AW-1:0]];
    assign rempty = pbd_empty;
endmodule
