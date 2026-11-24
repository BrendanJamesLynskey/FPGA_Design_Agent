// crc32_engine: one byte of the reflected CRC-32 (poly 0xEDB88320) register update, combinational.
// Register starts at 0xFFFFFFFF; the trailer is the inverted register, low byte first.
module crc32_engine (
    input  logic [31:0] c,
    input  logic [7:0]  d,
    output logic [31:0] n
);
    always_comb begin
        logic [31:0] t;
        t = c ^ {24'b0, d};
        for (int k = 0; k < 8; k++) begin
            t = t[0] ? ((t >> 1) ^ 32'hEDB88320) : (t >> 1);
        end
        n = t;
    end
endmodule
