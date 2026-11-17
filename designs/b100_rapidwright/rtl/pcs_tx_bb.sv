// pcs_tx_bb.sv: the ports of pcs_tx as a black box, so that a top can be synthesised without the block and the pre-implemented block
// (a routed out-of-context checkpoint of pcs_tx) read into each instance with read_checkpoint -cell. Keep in step with pcs_tx.sv.
(* black_box *)
module pcs_tx (
    input  logic        clk,
    input  logic        rst,
    input  logic [63:0] x_d,
    input  logic [7:0]  x_c,
    output logic        adv,
    output logic [63:0] gt_d
);
endmodule
