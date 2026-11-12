// eth_crc32_free.sv: a formal stand-in for ip_lib eth_crc32: its outputs are free on every clock, so the frame-FSM
// properties are proved for any CRC value (the CRC itself is checked bit-exact in simulation against zlib).
module eth_crc32 (
    input  logic        clk,
    input  logic        rst,
    input  logic        init,
    input  logic        en,
    input  logic [7:0]  d,
    output logic [31:0] crc,
    output logic        residue_ok
);
    (* anyseq *) logic [31:0] c;
    (* anyseq *) logic        r;
    assign crc = c;
    assign residue_ok = r;
endmodule
