// One byte of the reflected Ethernet CRC-32 (poly 0xEDB88320), register form
// (no final inversion). Combinational.
module udp_crc32_byte (
    input  logic [31:0] crc,
    input  logic [7:0]  d,
    output logic [31:0] nxt
);
    always_comb begin
        logic [31:0] r;
        r = crc ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        end
        nxt = r;
    end
endmodule
