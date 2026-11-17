// One byte of the reflected CRC-32 (poly 0xEDB88320), no init and no final inversion.
module v2_e_udp_endpoint_crc8 (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    always_comb begin
        crc_out = crc_in ^ {24'h0, data};
        for (int i = 0; i < 8; i++) begin
            crc_out = crc_out[0] ? ((crc_out >> 1) ^ 32'hEDB88320) : (crc_out >> 1);
        end
    end
endmodule
