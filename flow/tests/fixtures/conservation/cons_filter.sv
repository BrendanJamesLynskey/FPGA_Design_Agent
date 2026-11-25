// A small development design for brief 189 item 4: a frame filter with a four-deep FIFO and no backpressure on its input (a feed
// that cannot be slowed). A frame flagged bad is dropped and counted; a good frame that finds the FIFO full is dropped and counted.
// SILENT_DROP = 1 plants the mutant: the full-FIFO drop no longer increments the counter (the frame vanishes uncounted).
module cons_filter #(parameter bit SILENT_DROP = 1'b0) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic        in_bad,
    input  logic [15:0] in_data,
    output logic        out_valid,
    input  logic        out_ready,
    output logic [15:0] out_data,
    output logic [31:0] drop_count,
    output logic [31:0] occupancy
);
    logic [15:0] mem [4];
    logic [2:0]  wp, rp;
    wire [2:0]   cnt  = wp - rp;
    wire         full = cnt == 3'd4;
    wire         pop  = out_valid && out_ready;
    wire         push = in_valid && !in_bad && !full;
    assign out_valid = cnt != 3'd0;
    assign out_data  = mem[rp[1:0]];
    assign occupancy = 32'(cnt);
    always_ff @(posedge clk) begin
        if (rst) begin wp <= '0; rp <= '0; drop_count <= '0; end
        else begin
            if (push) begin mem[wp[1:0]] <= in_data; wp <= wp + 1'b1; end
            if (pop) rp <= rp + 1'b1;
            if (in_valid && (in_bad || full) && !(SILENT_DROP && !in_bad)) drop_count <= drop_count + 1'b1;
        end
    end
endmodule
