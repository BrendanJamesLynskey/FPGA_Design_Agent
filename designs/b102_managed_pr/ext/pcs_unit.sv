// pcs_unit.sv: the ports of the supplier's block as a black box, so that the project's top synthesises without it and the
// supplier's placed-and-routed checkpoint fills the instance (read_checkpoint -cell). Keep in step with reference/pcs_unit.sv.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
(* black_box *)
module pcs_unit (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic dout
);
endmodule
