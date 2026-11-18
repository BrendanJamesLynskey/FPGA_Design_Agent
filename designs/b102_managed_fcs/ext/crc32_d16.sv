// crc32_d16.sv: the black-box slot for the frozen, externally produced CRC-32 block (ext/crc32_d16.edf). Synthesis fills it
// from the EDIF (flow/build.tcl reads it before synth_design); Verilator lint and the RTL elaboration see only this port list,
// which is the interface contract in project.yaml. Frozen with the component.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
(* black_box *)
module crc32_d16 (
    input  logic        clk,
    input  logic        rst,
    input  logic        init,
    input  logic        en,
    input  logic [15:0] d,
    output logic [31:0] crc
);
endmodule
/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
