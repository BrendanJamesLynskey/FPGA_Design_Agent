// crc32_byte: one byte step of the reflected Ethernet CRC-32 (poly 0xEDB88320).
// The register is kept without the final inversion; the caller inverts at the end.
module crc32_byte (
    input  logic [31:0] crc_i,
    input  logic [7:0]  d,
    output logic [31:0] crc_o
);
    logic [31:0] c;
    always_comb begin
        c = crc_i ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            c = c[0] ? ((c >> 1) ^ 32'hEDB88320) : (c >> 1);
        end
        crc_o = c;
    end
endmodule
