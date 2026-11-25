// crc64_rx.sv: the brief 96 receive CRC-32 stage on its own (brief 101): one 64-bit data word a clock into the register
// mac64_rx keeps (crc <= crc_upd(crc, d, 8); the same function from b96_pkg), start value FFFFFFFF.
// rst is synchronous, active high, and sets the register to all ones. `en` holds the register when low.
`default_nettype none
module crc64_rx (
    input  wire logic        clk,
    input  wire logic        rst,
    input  wire logic        en,
    input  wire logic [63:0] d,
    output logic [31:0]      crc
);
    import b96_pkg::*;
    always_ff @(posedge clk) begin
        if (rst) crc <= '1;
        else if (en) crc <= crc_upd(crc, d, 8);
    end
endmodule
