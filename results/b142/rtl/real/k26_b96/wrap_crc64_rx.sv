// wrap_crc64_rx: an input register for the data, then the CRC stage (its register is the output register).
module ooc_wrap (input wire logic clk, input wire logic rst, input wire logic en, input wire logic [63:0] d, output logic [31:0] crc);
    logic en_q;
    logic [63:0] d_q;
    always_ff @(posedge clk) begin
        en_q <= en;
        d_q  <= d;
    end
    crc64_rx u_blk (.clk, .rst, .en(en_q), .d(d_q), .crc);
endmodule
