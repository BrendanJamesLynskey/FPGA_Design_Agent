// reloc_top.sv: four copies of pcs_unit (brief 100, capability 1). The copies are separate cells (c0 .. c3) so that each can be a
// pre-implemented block (read_checkpoint -cell) or an ordinary cell with a pblock: the same top serves the relocation runs and the
// Vivado-alone runs. rst is shared; each copy has its own din and dout.
module reloc_top (
    input  logic       clk,
    input  logic       rst,
    input  logic [3:0] din,
    output logic [3:0] dout
);
    pcs_unit c0 (.clk(clk), .rst(rst), .din(din[0]), .dout(dout[0]));
    pcs_unit c1 (.clk(clk), .rst(rst), .din(din[1]), .dout(dout[1]));
    pcs_unit c2 (.clk(clk), .rst(rst), .din(din[2]), .dout(dout[2]));
    pcs_unit c3 (.clk(clk), .rst(rst), .din(din[3]), .dout(dout[3]));
endmodule
