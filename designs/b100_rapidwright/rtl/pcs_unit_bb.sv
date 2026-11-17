// pcs_unit_bb.sv: the ports of pcs_unit as a black box, so that a top can be synthesised without the block and the pre-implemented
// block (a routed out-of-context checkpoint of pcs_unit) read into each instance with read_checkpoint -cell. Keep in step with pcs_unit.sv.
(* black_box *)
module pcs_unit (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic dout
);
endmodule
