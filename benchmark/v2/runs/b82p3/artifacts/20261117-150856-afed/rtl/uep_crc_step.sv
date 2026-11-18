// uep_crc_step: one byte of the reflected CRC-32 (0xEDB88320), register form (no init/final inversion here).
module uep_crc_step (
    input  logic [31:0] crc,
    input  logic [7:0]  d,
    output logic [31:0] nxt
);
    always_comb begin
        logic [31:0] c;
        c = crc ^ {24'h0, d};
        for (int i = 0; i < 8; i++) c = c[0] ? ((c >> 1) ^ 32'hEDB88320) : (c >> 1);
        nxt = c;
    end
endmodule
