// crc32_byte.sv: one byte step of the Ethernet CRC-32 (reflected, polynomial 0xEDB88320).
// The register starts at 32'hFFFFFFFF; the CRC to send is the inverted register, low byte first.
module crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    always_comb begin
        logic [31:0] r;
        r = crc_in ^ {24'b0, data};
        for (int i = 0; i < 8; i++) begin
            r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        end
        crc_out = r;
    end
endmodule
