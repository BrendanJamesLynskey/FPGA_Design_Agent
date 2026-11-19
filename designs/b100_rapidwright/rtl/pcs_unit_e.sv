// pcs_unit_e.sv: pcs_unit with one small edit, the 'agent edit' of brief 100B's compile-speed runs (dout reduces one more bit of the shift register).
// Same ports and size as pcs_unit.sv, which is the relocatable block of brief 100, capability 1; see that file for why the interface is three pins.
//
// Why a self-contained unit and not pcs_tx with its 73-bit input bus: a pre-implemented block is routed out of context and its input
// pins are reached later by the router of the design it is stamped into, past the block's own locked routing. With the bus on the
// ports, one or two of the 73 input pins were unreachable in every copy ("Load Pin does not reach Interconnect fabric within 5 hops",
// "Expansion wavefront from Load was blocked by locked nodes"; results/b100/c1/failed_direct_ports/), whether the bus fed LUT pins or
// registers inside the block. Three input pins is the interface that stamps; design.md section 6 records the limit.
module pcs_unit_e (
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
        dout <= ^o ^ sh[7];   // the edit: one more term in the reduction
    end
endmodule
