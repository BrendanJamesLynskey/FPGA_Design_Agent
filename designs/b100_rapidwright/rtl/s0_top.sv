// s0_top.sv: stage 0 of brief 100 (does RapidWright read and write Vivado 2026.1 checkpoints?). Brief 96's own pcs_tx between a
// shift register and an xor reduction, so that the design has four pins and a real logic path. Used for xck26 and xc7a100t.
module s0_top (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic dout
);
    logic [71:0] sh;
    logic        adv;
    logic [63:0] gt_d;
    logic [64:0] o;
    always_ff @(posedge clk) sh <= {sh[70:0], din};
    pcs_tx u_pcs (.clk(clk), .rst(rst), .x_d(sh[63:0]), .x_c(sh[71:64]), .adv(adv), .gt_d(gt_d));
    always_ff @(posedge clk) begin
        o    <= {adv, gt_d};
        dout <= ^o;
    end
endmodule
