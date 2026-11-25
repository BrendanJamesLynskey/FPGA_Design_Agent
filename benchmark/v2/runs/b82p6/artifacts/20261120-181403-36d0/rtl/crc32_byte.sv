// crc32_byte: one byte step of the Ethernet CRC-32 (reflected 0xEDB88320), combinational.
// State starts at 32'hFFFFFFFF; the CRC of a message is ~state after the last byte.
module crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    always_comb begin
        logic [31:0] c;
        c = crc_in ^ {24'b0, data};
        for (int i = 0; i < 8; i++) begin
            c = (c >> 1) ^ (c[0] ? 32'hEDB88320 : 32'h0);
        end
        crc_out = c;
    end
endmodule
