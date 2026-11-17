// word_buf: 32-byte buffer written a byte at a time, read as a big-endian 32-bit word
// (bytes 4i..4i+3, first byte on top); bytes at or past len read 0.
module word_buf (
    input  logic        clk,
    input  logic        we,
    input  logic [4:0]  widx,
    input  logic [7:0]  wdata,
    input  logic [6:0]  ridx,
    input  logic [5:0]  len,
    output logic [31:0] rword
);
    logic [7:0] mem [0:31];

    always_ff @(posedge clk) begin
        if (we) mem[widx] <= wdata;
    end

    logic [8:0] base;
    assign base = {ridx, 2'b00};

    always_comb begin
        logic [8:0] pos;
        for (int k = 0; k < 4; k++) begin
            pos = base + 9'(k);
            rword[31 - 8*k -: 8] = ({3'b0, len} > pos) ? mem[pos[4:0]] : 8'h00;
        end
    end
endmodule
