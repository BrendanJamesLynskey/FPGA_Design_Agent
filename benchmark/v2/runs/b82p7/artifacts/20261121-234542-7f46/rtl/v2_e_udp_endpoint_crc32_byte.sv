// Ethernet CRC-32 (reflected 0xEDB88320), one byte per call, combinational.
// crc_in is the running register (init 32'hFFFFFFFF); the final CRC is ~register.
module v2_e_udp_endpoint_crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    logic [31:0] x;
    always_comb begin
        x = crc_in ^ {24'b0, data};
        for (int i = 0; i < 8; i++) begin
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        end
        crc_out = x;
    end
endmodule
