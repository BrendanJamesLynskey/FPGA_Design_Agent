// One byte of the reflected CRC-32 (Ethernet, zlib) as pure logic: crc_o = state after folding byte d into crc_i.
// The caller keeps the register, starts from CRC_INIT and inverts the final value.
module crc32_byte #(
    parameter logic [31:0] CRC_POLY = 32'hEDB88320
) (
    input  logic [31:0] crc_i,
    input  logic [7:0]  d,
    output logic [31:0] crc_o
);
    always_comb begin
        logic [31:0] t;
        t = crc_i ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            t = t[0] ? ((t >> 1) ^ CRC_POLY) : (t >> 1);
        end
        crc_o = t;
    end
endmodule
