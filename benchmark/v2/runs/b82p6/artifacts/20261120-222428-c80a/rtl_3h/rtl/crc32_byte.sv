// crc32_byte: one byte step of the Ethernet CRC-32 (reflected, polynomial 0xEDB88320).
// Register convention: start from 32'hFFFFFFFF, final value is the complement of the register.
module crc32_byte (
    input  logic [31:0] crc_in,
    input  logic [7:0]  data,
    output logic [31:0] crc_out
);
    function automatic logic [31:0] step8(input logic [31:0] c_in, input logic [7:0] d);
        logic [31:0] c;
        c = c_in ^ {24'h0, d};
        for (int i = 0; i < 8; i++) begin
            c = (c >> 1) ^ (32'hEDB88320 & {32{c[0]}});
        end
        step8 = c;
    endfunction

    assign crc_out = step8(crc_in, data);
endmodule
