// pcs_tx_blk.sv: brief 96's pcs_tx with a register on every port (brief 100, capability 1: the relocatable block).
// A pre-implemented block is routed out of context and stamped into a design later; its input pins are reached by the router of the
// design it is stamped into, through whatever wires the block's own locked routing left free. A first attempt with pcs_tx's inputs
// feeding LUT pins directly failed that way: one LUT input could not be reached (results/b100/c1/stamp4.log, "Expansion wavefront from
// Load was blocked by locked nodes"). Registering the ports puts every block input on a flip-flop D pin, which has many ways in. The cost
// is one clock on each side of the block: this wrapper is for the relocation experiment, not for the 96 design's latency path.
module pcs_tx_blk (
    input  logic        clk,
    input  logic        rst,
    input  logic [63:0] x_d,
    input  logic [7:0]  x_c,
    output logic        adv,
    output logic [63:0] gt_d
);
    logic [63:0] x_d_r, gt_q;
    logic [7:0]  x_c_r;
    logic        rst_r, adv_w;
    logic [63:0] gt_w;
    always_ff @(posedge clk) begin x_d_r <= x_d; x_c_r <= x_c; rst_r <= rst; end
    pcs_tx u_core (.clk(clk), .rst(rst_r), .x_d(x_d_r), .x_c(x_c_r), .adv(adv_w), .gt_d(gt_w));
    always_ff @(posedge clk) begin gt_q <= gt_w; adv <= adv_w; end
    assign gt_d = gt_q;
endmodule
