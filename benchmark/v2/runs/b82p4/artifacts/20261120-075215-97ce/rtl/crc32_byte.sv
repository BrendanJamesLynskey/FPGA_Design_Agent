// Bytewise Ethernet CRC-32 step (reflected, polynomial 0xEDB88320), no final xor.
module crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    function automatic logic [31:0] step(input logic [31:0] c0, input logic [7:0] d);
        logic [31:0] c;
        c = c0 ^ {24'h0, d};
        for (int i = 0; i < 8; i++) begin
            if (c[0]) c = (c >> 1) ^ 32'hEDB88320;
            else      c = c >> 1;
        end
        return c;
    endfunction

    assign crc_out = step(crc_in, data);
endmodule
