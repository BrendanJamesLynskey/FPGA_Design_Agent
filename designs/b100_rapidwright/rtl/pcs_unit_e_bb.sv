// pcs_unit_e_bb.sv: the ports of pcs_unit_e (brief 100B) as a black box, so that a top can be synthesised without the block and the pre-implemented
// block (a routed out-of-context checkpoint of pcs_unit_e) read into each instance with read_checkpoint -cell. Keep in step with pcs_unit_e.sv.
(* black_box *)
module pcs_unit_e (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic dout
);
endmodule
