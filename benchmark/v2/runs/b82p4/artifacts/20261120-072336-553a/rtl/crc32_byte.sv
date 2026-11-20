// crc32_byte: one byte of the reflected Ethernet CRC-32 (poly 0xEDB88320), combinational.
// Start from 32'hFFFFFFFF and invert the result at the end to get zlib.crc32.
module crc32_byte (
    input  logic [31:0] c,
    input  logic [7:0]  d,
    output logic [31:0] n
);
    always_comb begin
        logic [31:0] x;
        x = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        end
        n = x;
    end
endmodule
