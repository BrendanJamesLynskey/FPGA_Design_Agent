module rm_top(input wclk, rclk, rrst, clr_r, clr_w, w_v, w_os, w_lock, input [63:0] w_d, input [7:0] w_c, output [31:0] n_ovf, n_wr, n_ins, n_del, n_stall, n_out, n_drain, fill_min, fill_max, output r_v, r_lock, output [63:0] r_d, output [7:0] r_c);
 rate_match_x u(.*); endmodule
