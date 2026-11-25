// wrap_pcs_tx: an input register for the MAC word, then the transmit PCS (its gt_d register is the output register).
module ooc_wrap (input wire logic clk, input wire logic rst, input wire logic [63:0] x_d, input wire logic [7:0] x_c,
                 output logic adv, output logic [63:0] gt_d);
    logic [63:0] d_q;
    logic [7:0]  c_q;
    always_ff @(posedge clk) begin
        d_q <= x_d;
        c_q <= x_c;
    end
    pcs_tx u_blk (.clk, .rst, .x_d(d_q), .x_c(c_q), .adv, .gt_d);
endmodule
