// Part 9 lesson 2 reference solution: a test-pattern generator.
module tpg #(
    parameter int W = 160,
    parameter int H = 120
) (
    input  logic        clk,
    input  logic        de,
    input  logic [11:0] x,
    input  logic [11:0] y,
    input  logic [1:0]  sel,
    input  logic [7:0]  frame,
    output logic        de_q,
    output logic [3:0]  r,
    output logic [3:0]  g,
    output logic [3:0]  b
);
    localparam int BAR_W = W / 8;
    function automatic logic [11:0] bar_colour(input int idx);
        case (idx)
            0: bar_colour = 12'hFFF;
            1: bar_colour = 12'hFF0;
            2: bar_colour = 12'h0FF;
            3: bar_colour = 12'h0F0;
            4: bar_colour = 12'hF0F;
            5: bar_colour = 12'hF00;
            6: bar_colour = 12'h00F;
            default: bar_colour = 12'h000;
        endcase
    endfunction

    int ox, oy;
    logic [11:0] px;
    always_comb begin
        ox = (2 * int'(frame)) % (W - 32);
        oy = int'(frame) % (H - 32);
        px = 12'h000;
        case (sel)
            2'd0: px = bar_colour(int'(x) / BAR_W);
            2'd1: px = (((x >> 3) ^ (y >> 3)) & 12'd1) ? 12'hFFF : 12'h000;
            2'd2: px = {3{4'((int'(x) * 16) / W)}};
            2'd3: px = (int'(x) >= ox && int'(x) < ox + 32 && int'(y) >= oy && int'(y) < oy + 32) ? 12'hFFF : 12'h888;
        endcase
    end
    always_ff @(posedge clk) begin
        de_q <= de;
        {r, g, b} <= de ? px : 12'h000;
    end
endmodule
