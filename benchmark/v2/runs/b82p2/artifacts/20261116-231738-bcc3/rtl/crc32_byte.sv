// crc32_byte: one byte of the reflected Ethernet CRC-32 (poly 0xEDB88320), combinational.
// c is the running register (init 0xFFFFFFFF), n is the register after byte d.
module crc32_byte (
    input  logic [31:0] c,
    input  logic [7:0]  d,
    output logic [31:0] n
);
    always_comb begin
        logic [31:0] r;
        r = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        end
        n = r;
    end
endmodule
