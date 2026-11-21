// rm_gp_fv_top.sv (brief 115): the proof harness: rate_match_gp with two free, unrelated clocks and free inputs.
//
// Clocks. wclk and rclk are free inputs; sby's `multiclock on` lets the solver pick, at every step, which clock rises (none, one, or both together), so the proof covers every interleaving of the two
// edge sequences: any phase, any drift, any ratio the assumption below allows. Nothing is said about duty cycle or jitter (edges are instants).
// The assumptions (A1 reset first, A2 clock-ratio band, A3 progress conditions) live with the properties in rm_gp_props.sv, so each is next to what it justifies. All inputs are otherwise free every step.
module rm_gp_fv_top #(
    parameter int AW       = 2,
    parameter int MIN_KEEP = 0,
    parameter int HI       = 1,
    parameter bit ENT_SYNC = 1'b1
) (
    input logic wclk, rclk,
    input logic wrst, rrst, clr_w, clr_r,
    input logic w_v, w_os, w_lock,
    input logic [63:0] w_d,
    input logic [7:0]  w_c
);
    logic [31:0] n_ovf, n_wr, n_ins, n_del, n_stall, n_out, n_drain, fill_min, fill_max;
    logic r_v, r_lock;
    logic [63:0] r_d;
    logic [7:0]  r_c;
    rate_match_gp #(.AW(AW), .HI(HI), .ENT_SYNC(ENT_SYNC), .MIN_KEEP(MIN_KEEP)) dut (.*);

endmodule
