// crc32_byte: one byte step of the reflected CRC-32 (0xEDB88320), combinational.
// The caller holds the running register (init 0xFFFFFFFF) and inverts it at the end.
module crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    always_comb begin
        logic [31:0] c;
        c = crc_in ^ {24'b0, data};
        for (int i = 0; i < 8; i++) begin
            c = c[0] ? ((c >> 1) ^ 32'hEDB88320) : (c >> 1);
        end
        crc_out = c;
    end
endmodule
