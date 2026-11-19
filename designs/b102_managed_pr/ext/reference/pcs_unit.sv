// pcs_unit.sv: the relocatable block of brief 100, capability 1: brief 96's pcs_tx between a shift-register source and an xor-reduced
// sink, with three input pins (clk, rst, din) and one output (dout). Every wide interface of the block is inside it.
//
// Why a self-contained unit and not pcs_tx with its 73-bit input bus: a pre-implemented block is routed out of context and its input
// pins are reached later by the router of the design it is stamped into, past the block's own locked routing. With the bus on the
// ports, one or two of the 73 input pins were unreachable in every copy ("Load Pin does not reach Interconnect fabric within 5 hops",
// "Expansion wavefront from Load was blocked by locked nodes"; results/b100/c1/failed_direct_ports/), whether the bus fed LUT pins or
// registers inside the block. Three input pins is the interface that stamps; design.md section 6 records the limit.
module pcs_unit (
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
    pcs_tx u_core (.clk(clk), .rst(rst_q), .x_d(sh[63:0]), .x_c(sh[71:64]), .adv(adv), .gt_d(gt_d));
    always_ff @(posedge clk) begin
        o    <= {adv, gt_d};
        dout <= ^o;
    end
endmodule
