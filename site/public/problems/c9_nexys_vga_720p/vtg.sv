// Part 9 lesson 2 reference solution: a video timing generator.
module vtg #(
    parameter int H_ACT = 640, H_FP = 16, H_SYNC = 96, H_BP = 48,
    parameter int V_ACT = 480, V_FP = 10, V_SYNC = 2,  V_BP = 33,
    parameter bit HS_POL = 1'b0,
    parameter bit VS_POL = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,
    output logic        hs,
    output logic        vs,
    output logic        de,
    output logic [11:0] x,
    output logic [11:0] y,
    output logic        sof,
    output logic        eol
);
    localparam int H_TOT = H_ACT + H_FP + H_SYNC + H_BP;
    localparam int V_TOT = V_ACT + V_FP + V_SYNC + V_BP;
    logic [11:0] h, v;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            h <= '0;
            v <= '0;
        end else if (h == H_TOT - 1) begin
            h <= '0;
            v <= (v == V_TOT - 1) ? 12'd0 : v + 12'd1;
        end else begin
            h <= h + 12'd1;
        end
    end
    wire h_in_sync = (h >= H_ACT + H_FP) && (h < H_ACT + H_FP + H_SYNC);
    wire v_in_sync = (v >= V_ACT + V_FP) && (v < V_ACT + V_FP + V_SYNC);
    assign de  = (h < H_ACT) && (v < V_ACT);
    assign hs  = h_in_sync ? HS_POL : ~HS_POL;
    assign vs  = v_in_sync ? VS_POL : ~VS_POL;
    assign x   = h;
    assign y   = v;
    assign sof = de && (h == 0) && (v == 0);
    assign eol = de && (h == H_ACT - 1);
endmodule
