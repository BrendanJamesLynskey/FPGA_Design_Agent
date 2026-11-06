// Part 13 lesson 8 reference solution: a Hough transform accumulator for straight lines, 16 angles, one angle per clock.
//
// A line is the set of points (x, y) with x*cos(t) + y*sin(t) = rho. For each edge point and each of the NT = 16 angles t_k = k * pi / 16 (k = 0 .. 15, in steps of
// 11.25 degrees) the block computes   rho_k = ((x * ctab(k) + y * stab(k) + 64) >>> 7) + ROFF   (cos and sin are in Q7: ctab(k) = round(128 cos t_k), given below;
// >>> is the arithmetic shift, floor) and adds one to the accumulator cell acc[k][rho_k]. ROFF = 48 makes the index non-negative for x, y in 0 .. 63 (rho runs from
// about -64 to +64, of which cells 0 .. NR-1 = 0 .. 95 are kept; a point whose index falls outside is not counted).
// Handshake: pt_valid with busy low presents a point (pt_x, pt_y 8 bits each); the block then sets busy for the NT clocks it takes (one angle per clock, k = 0 first)
// and clears it at the end; a point presented while busy is ignored. clear (a one-clock pulse, only when not busy) zeroes every cell in ONE clock.
// Read port: rd_theta (k), rd_rho (cell) select a cell and rd_cnt shows its 16-bit count one clock later. rst_n is synchronous, active low (it does not clear the cells).
// The tables are computed by a CORDIC or a small ROM; lesson 8 discusses which and the cost.
module hough #(
    parameter int NT = 16,
    parameter int NR = 96,
    parameter int ROFF = 48
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        pt_valid,
    input  logic [7:0]  pt_x,
    input  logic [7:0]  pt_y,
    output logic        busy,
    input  logic        clear,
    input  logic [3:0]  rd_theta,
    input  logic [6:0]  rd_rho,
    output logic [15:0] rd_cnt
);
    function automatic signed [8:0] ctab(input [3:0] k);
        case (k)
            4'd0: ctab = 128;
            4'd1: ctab = 126;
            4'd2: ctab = 118;
            4'd3: ctab = 106;
            4'd4: ctab = 91;
            4'd5: ctab = 71;
            4'd6: ctab = 49;
            4'd7: ctab = 25;
            4'd8: ctab = 0;
            4'd9: ctab = -25;
            4'd10: ctab = -49;
            4'd11: ctab = -71;
            4'd12: ctab = -91;
            4'd13: ctab = -106;
            4'd14: ctab = -118;
            4'd15: ctab = -126;
            default: ctab = 0;
        endcase
    endfunction
    function automatic signed [8:0] stab(input [3:0] k);
        case (k)
            4'd0: stab = 0;
            4'd1: stab = 25;
            4'd2: stab = 49;
            4'd3: stab = 71;
            4'd4: stab = 91;
            4'd5: stab = 106;
            4'd6: stab = 118;
            4'd7: stab = 126;
            4'd8: stab = 128;
            4'd9: stab = 126;
            4'd10: stab = 118;
            4'd11: stab = 106;
            4'd12: stab = 91;
            4'd13: stab = 71;
            4'd14: stab = 49;
            4'd15: stab = 25;
            default: stab = 0;
        endcase
    endfunction
    logic [15:0] acc [0:NT*NR-1];
    logic [7:0]  x, y;
    logic [4:0]  k;          // 0 .. NT-1 while busy
    integer i, rho;
    logic start_q;
    assign busy = (k != 0) || start_q;
    always_ff @(posedge clk) begin
        rd_cnt <= acc[rd_theta * NR + rd_rho];
        if (!rst_n) begin
            k <= 5'd0; start_q <= 1'b0;
        end else begin
            start_q <= 1'b0;
            if (clear && !busy) begin
                for (i = 0; i < NT*NR; i = i + 1) acc[i] <= 16'd0;
            end
            if (pt_valid && !busy) begin
                x <= pt_x; y <= pt_y;
                start_q <= 1'b1;
            end
            if (start_q || k != 0) begin
                // angle index is k (start_q: k = 0)
                rho = (($signed({1'b0, x}) * ctab(k[3:0]) + $signed({1'b0, y}) * stab(k[3:0]) + 64) >>> 7) + ROFF;
                if (rho >= 0 && rho < NR) acc[k * NR + rho] <= acc[k * NR + rho] + 16'd1;
                k <= (k == NT - 1) ? 5'd0 : k + 5'd1;
            end
        end
    end
endmodule
