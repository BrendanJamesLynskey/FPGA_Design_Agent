// reloc_top.sv: four copies of brief 96's pcs_tx_blk, each between its own shift-register source and xor-reduced sink (brief 100, capability 1).
// The copies are separate cells (c0/u_b .. c3/u_b) so that each can be a pre-implemented block (read_checkpoint -cell) or an ordinary
// cell with a pblock: the same top serves the relocation runs and the Vivado-alone runs.
module reloc_one (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic dout
);
    logic [71:0] sh;
    logic        adv, rst_q;
    logic [63:0] gt_d;
    logic [64:0] o;
    always_ff @(posedge clk) begin sh <= {sh[70:0], din}; rst_q <= rst; end
    pcs_tx_blk u_b (.clk(clk), .rst(rst_q), .x_d(sh[63:0]), .x_c(sh[71:64]), .adv(adv), .gt_d(gt_d));
    always_ff @(posedge clk) begin
        o    <= {adv, gt_d};
        dout <= ^o;
    end
endmodule

module reloc_top (
    input  logic       clk,
    input  logic       rst,
    input  logic [3:0] din,
    output logic [3:0] dout
);
    reloc_one c0 (.clk(clk), .rst(rst), .din(din[0]), .dout(dout[0]));
    reloc_one c1 (.clk(clk), .rst(rst), .din(din[1]), .dout(dout[1]));
    reloc_one c2 (.clk(clk), .rst(rst), .din(din[2]), .dout(dout[2]));
    reloc_one c3 (.clk(clk), .rst(rst), .din(din[3]), .dout(dout[3]));
endmodule
