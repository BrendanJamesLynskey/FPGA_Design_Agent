// crc32_byte: one byte of the reflected Ethernet CRC-32 (0xEDB88320), combinational.
// c is the running register (init 0xFFFFFFFF, no final inversion here).
module crc32_byte (
    input  logic [31:0] c,
    input  logic [7:0]  d,
    output logic [31:0] n
);
    logic [31:0] x;
    always_comb begin
        x = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++) begin
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        end
        n = x;
    end
endmodule
