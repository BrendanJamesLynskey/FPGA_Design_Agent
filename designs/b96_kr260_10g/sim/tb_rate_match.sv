`timescale 1ns/1fs
// tb_rate_match.sv: bench top for rtl/rate_match.sv (brief 96C): the two clocks and every input come from the cocotb bench.
module tb_rate_match #(
    parameter int HI = 4,
    parameter int MIN_KEEP = 1,
    parameter int WP_REG = 1
) (
    input  logic        wclk, rclk, rrst, clr_r, clr_w,
    input  logic        w_v, w_os, w_lock,
    input  logic [63:0] w_d,
    input  logic [7:0]  w_c,
    output logic [31:0] n_ovf, n_wr, n_ins, n_del, n_stall, n_out, n_drain, fill_min, fill_max,
    output logic        r_v, r_lock,
    output logic [63:0] r_d,
    output logic [7:0]  r_c
);
    rate_match #(.HI(HI), .MIN_KEEP(MIN_KEEP), .WP_REG(WP_REG)) u (.wclk, .w_v, .w_d, .w_c, .w_os, .w_lock, .clr_w, .n_ovf, .n_wr,
        .rclk, .rrst, .clr_r, .r_v, .r_d, .r_c, .r_lock, .n_ins, .n_del, .n_stall, .n_out, .n_drain, .fill_min, .fill_max);
endmodule
