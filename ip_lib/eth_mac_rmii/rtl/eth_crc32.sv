// eth_crc32.sv: the Ethernet FCS (IEEE 802.3 clause 3.2.9) one byte a clock.
// CRC-32, polynomial 0x04C11DB7 in reflected form (0xEDB88320), initial value all ones. The FCS on the wire is
// the bitwise inverse of the register, least significant byte first. Running the register over the data and the
// received FCS leaves the constant residue 0xDEBB20E3 when the frame is intact.

module eth_crc32 (
    input  logic        clk,
    input  logic        rst,
    input  logic        init,           // load all ones (start of frame); has priority over en
    input  logic        en,             // fold in d this clock
    input  logic [7:0]  d,
    output logic [31:0] crc,            // the register (not inverted)
    output logic        residue_ok      // crc == 0xDEBB20E3
);
    function automatic logic [31:0] crc32_byte(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c;
        for (int i = 0; i < 8; i++)
            x = (x[0] ^ b[i]) ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    always_ff @(posedge clk) begin
        if (rst || init) crc <= 32'hFFFF_FFFF;
        else if (en)     crc <= crc32_byte(crc, d);
    end

    assign residue_ok = (crc == 32'hDEBB_20E3);
endmodule
