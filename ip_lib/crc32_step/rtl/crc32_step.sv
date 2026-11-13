// crc32_step: one update of the reflected CRC-32 (IEEE 802.3, zlib's polynomial 0xEDB88320) by a 32-bit word, least
// significant byte first, with no initial or final inversion (the caller keeps the running value: start from
// 0xFFFFFFFF and invert at the end for zlib's CRC-32). Stateless between operations, two operands and one result: the
// shape of a CPU custom instruction (brief 64A+; the function_unit contract in ip.yaml, hwsw/cfu.py).
// Implementation variants, same ports and result, selected by IMPL:
//   "word"  the whole 32-bit update in one clock (an XOR network): latency 1, a new word every clock
//   "byte"  one byte per clock through an 8-bit update: latency 4, a new word every 4 clocks, a smaller network
// in_valid is a one-clock pulse with the operands; out_valid is a one-clock pulse with crc_out, LATENCY clocks later.
// "byte" ignores in_valid while busy (II 4: the caller waits for out_valid).
module crc32_step #(
    parameter IMPL = "word"           // a string: "word" or "byte"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic [31:0] crc_in,
    input  logic [31:0] data_in,
    output logic        out_valid,
    output logic [31:0] crc_out
);
    initial begin
        if (!(IMPL == "word" || IMPL == "byte")) $error("crc32_step: IMPL %s is not word or byte", IMPL);
    end
    localparam int LATENCY = (IMPL == "byte") ? 4 : 1;
    localparam int II      = (IMPL == "byte") ? 4 : 1;
    localparam logic [31:0] POLY = 32'hEDB88320;

    // the reflected update by N data bits (data bit 0 enters first)
    function automatic logic [31:0] upd32(input logic [31:0] c, input logic [31:0] d);
        logic [31:0] x;
        x = c ^ d;
        for (int i = 0; i < 32; i++) x = x[0] ? ((x >> 1) ^ POLY) : (x >> 1);
        return x;
    endfunction
    function automatic logic [31:0] upd8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'd0, d};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ POLY) : (x >> 1);
        return x;
    endfunction

    if (IMPL == "byte") begin : g_byte
        logic [31:0] acc, dat;
        logic [1:0]  n;
        logic        busy;
        always_ff @(posedge clk) begin
            out_valid <= 1'b0;
            if (rst) begin
                busy <= 1'b0;
                n <= 2'd0;
                acc <= '0;
                dat <= '0;
                crc_out <= '0;
            end else if (!busy) begin
                if (in_valid) begin                       // byte 0 now, bytes 1-3 in the next three clocks
                    acc <= upd8(crc_in, data_in[7:0]);
                    dat <= data_in >> 8;
                    n <= 2'd1;
                    busy <= 1'b1;
                end
            end else begin
                if (n == 2'd3) begin
                    crc_out <= upd8(acc, dat[7:0]);
                    out_valid <= 1'b1;
                    busy <= 1'b0;
                end else begin
                    acc <= upd8(acc, dat[7:0]);
                end
                dat <= dat >> 8;
                n <= n + 2'd1;
            end
        end
    end else begin : g_word
        always_ff @(posedge clk) begin
            if (rst) begin
                out_valid <= 1'b0;
                crc_out <= '0;
            end else begin
                out_valid <= in_valid;
                if (in_valid) crc_out <= upd32(crc_in, data_in);
            end
        end
    end
endmodule
