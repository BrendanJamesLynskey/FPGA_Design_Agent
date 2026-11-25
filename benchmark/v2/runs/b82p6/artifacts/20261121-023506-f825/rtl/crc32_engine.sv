// crc32_engine: byte-serial reflected CRC-32 (0xEDB88320), the zlib / Ethernet one.
// init loads 0xFFFFFFFF; en folds one byte in. The transmitted CRC is ~crc, low byte first.
// After a message followed by its own CRC (low byte first) crc is 0xDEBB20E3.
module crc32_engine (
    input  logic        clk,
    input  logic        init,
    input  logic        en,
    input  logic [7:0]  data,
    output logic [31:0] crc
);
    function automatic logic [31:0] step(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) begin
            r = r[0] ? ((r >> 1) ^ 32'hEDB8_8320) : (r >> 1);
        end
        return r;
    endfunction

    always_ff @(posedge clk) begin
        if (init)    crc <= 32'hFFFF_FFFF;
        else if (en) crc <= step(crc, data);
    end
endmodule
