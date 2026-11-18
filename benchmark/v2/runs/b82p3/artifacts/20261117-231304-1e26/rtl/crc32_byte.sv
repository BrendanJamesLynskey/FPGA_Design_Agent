// crc32_byte.sv: one byte of the reflected CRC-32 (zlib.crc32 polynomial), combinational.
module crc32_byte #(
    parameter logic [31:0] POLY = 32'hEDB88320
) (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    always_comb begin
        logic [31:0] c;
        c = crc_in ^ {24'b0, data};
        for (int k = 0; k < 8; k++) begin
            c = c[0] ? ((c >> 1) ^ POLY) : (c >> 1);
        end
        crc_out = c;
    end
endmodule
