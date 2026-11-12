// Part 13 lesson 8 reference solution: a Hough transform accumulator for straight lines, 16 angles, one angle per clock.
//
// A line is the set of points (x, y) with x*cos(t) + y*sin(t) = rho. For each edge point and each of the NT = 16 angles t_k = k * pi / 16 (k = 0 .. 15, in steps of
// 11.25 degrees) the block computes   rho_k = ((x * ctab(k) + y * stab(k) + 64) >>> 7) + ROFF   (cos and sin are in Q7: ctab(k) = round(128 cos t_k), given below;
// >>> is the arithmetic shift, floor) and adds one to the accumulator cell acc[k][rho_k]. ROFF = 48 makes the index non-negative for x, y in 0 .. 63 (rho runs from
// about -64 to +64, of which cells 0 .. NR-1 = 0 .. 95 are kept; a point whose index falls outside is not counted).
// Handshake: pt_valid with busy low presents a point (pt_x, pt_y 8 bits each); the block then sets busy while it processes all angles and their votes; a point
// presented while busy is ignored. clear (a one-clock pulse, only when not busy) zeroes every cell in ONE clock. Read port: rd_theta (k), rd_rho (cell) select a cell
// and rd_cnt shows its 16-bit count one clock later. rst_n is synchronous, active low (it does not clear the cells).
//
// Block-RAM form (07a1c): the 1536 counts live in two block RAMs written together (one read port each: the read-modify-write of a vote, and the read port), and one
// valid bit per cell in flip-flops. A cell whose valid bit is 0 reads as 0, so `clear` still zeroes every cell in ONE clock (it clears the valid bits, not the RAMs).
// Each angle's operands, products, and sum are pipelined before the index and vote stages; busy covers all of these stages.
module hough_cell_ram #(
    parameter int N = 1536
) (
    input  logic        clk,
    input  logic        we,
    input  logic [10:0] waddr,
    input  logic [15:0] wdata,
    input  logic [10:0] raddr,
    output logic [15:0] rdata
);
    (* ram_style = "block" *) logic [15:0] mem [0:N-1];
    always_ff @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end
endmodule

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

    localparam int NC = NT * NR;
    logic [NC-1:0] vld;       // a cell that was never voted since the last clear reads as 0
    initial vld = '0;

    logic [7:0]  x, y;
    logic [4:0]  k;          // 0 .. NT-1 while busy
    logic start_q;

    // Registered lookup operands, followed by registered DSP products.
    logic signed [17:0] mul_ax, mul_ay;
    logic signed [17:0] mul_bx, mul_by;
    (* use_dsp = "yes" *) logic signed [17:0] prod_x, prod_y;
    logic signed [18:0] sum_r;
    logic [3:0] angle_k0, angle_k1, angle_k2;
    logic op_en, prod_en, sum_en;

    logic signed [15:0] rho_r;
    logic [3:0] k_r;
    logic p_en;
    logic s0_en, s0_vote, s1_en, s1_vote, vld_a, vld_b;
    logic [10:0] s0_idx, s1_idx;
    logic [15:0] q_a, q_b;

    assign busy = (k != 0) || start_q || op_en || prod_en || sum_en ||
                  p_en || s0_en || s1_en;

    wire vote0 = p_en && rho_r >= 0 && rho_r < NR;
    wire [10:0] idx0 = 11'(k_r * NR + rho_r);
    wire [10:0] ridx = 11'(rd_theta * NR + rd_rho);
    wire [15:0] newc = (vld_a ? q_a : 16'd0) + 16'd1;

    hough_cell_ram #(.N(NC)) u_a (
        .clk(clk), .we(s1_vote), .waddr(s1_idx), .wdata(newc),
        .raddr(s0_idx), .rdata(q_a)
    );
    hough_cell_ram #(.N(NC)) u_b (
        .clk(clk), .we(s1_vote), .waddr(s1_idx), .wdata(newc),
        .raddr(ridx), .rdata(q_b)
    );
    assign rd_cnt = vld_b ? q_b : 16'd0;

    always_ff @(posedge clk) begin
        // Lookup results are registered before the multipliers.
        mul_ax <= $signed({1'b0, x});
        mul_ay <= $signed({1'b0, y});
        mul_bx <= ctab(k[3:0]);
        mul_by <= stab(k[3:0]);
        angle_k0 <= k[3:0];
        op_en <= start_q || k != 0;

        // Registered multiplier outputs (MREG when mapped to DSP48E1).
        prod_x <= mul_ax * mul_bx;
        prod_y <= mul_ay * mul_by;
        angle_k1 <= angle_k0;
        prod_en <= op_en;

        // Registered product sum, including the rounding constant.
        sum_r <= $signed({prod_x[17], prod_x}) +
                 $signed({prod_y[17], prod_y}) + 19'sd64;
        angle_k2 <= angle_k1;
        sum_en <= prod_en;

        // Convert the registered sum to rho and carry its angle/valid onward.
        rho_r <= 16'(($signed(sum_r) >>> 7) + ROFF);
        k_r <= angle_k2;
        p_en <= sum_en;

        vld_b <= vld[ridx];
        vld_a <= vld[s0_idx];
        s0_en <= p_en;
        s0_vote <= vote0;
        s0_idx <= idx0;
        s1_en <= s0_en;
        s1_vote <= s0_vote;
        s1_idx <= s0_idx;

        if (!rst_n) begin
            k <= 5'd0;
            start_q <= 1'b0;
            op_en <= 1'b0;
            prod_en <= 1'b0;
            sum_en <= 1'b0;
            p_en <= 1'b0;
            s0_en <= 1'b0;
            s0_vote <= 1'b0;
            s1_en <= 1'b0;
            s1_vote <= 1'b0;
        end else begin
            start_q <= 1'b0;
            if (clear && !busy) begin
                vld <= '0;
            end
            if (s1_vote) vld[s1_idx] <= 1'b1;
            if (pt_valid && !busy) begin
                x <= pt_x;
                y <= pt_y;
                start_q <= 1'b1;
            end
            if (start_q || k != 0) begin
                k <= (k == NT - 1) ? 5'd0 : k + 5'd1;
            end
        end
    end
endmodule
