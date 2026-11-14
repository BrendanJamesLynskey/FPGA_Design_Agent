// rst_f1_async: a seeded design of the reset check (brief 71); the body is rst_common.svh.
`define F1_ASYNC
module rst_f1_async (
    input  logic        clk_a,
    input  logic        clk_b,
    input  logic        rst_n_btn,     // active-low button, asynchronous to both clocks
    input  logic        soft_rst,
    input  logic [15:0] a,
    input  logic [15:0] b,
    input  logic        we,
    input  logic [7:0]  waddr,
    input  logic [7:0]  raddr,
    input  logic [15:0] wdata,
    output logic [31:0] p,
    output logic [15:0] rdata,
    output logic [15:0] cnt_b,
    output logic [15:0] acc_o
);
`include "rst_common.svh"
endmodule
`undef F1_ASYNC
