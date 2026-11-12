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
//
// Block-RAM form: the 1536 counts live in two block RAMs written together (one read port each: the read-modify-write of a vote, and the read port), and one
// valid bit per cell in flip-flops. A cell whose valid bit is 0 reads as 0, so `clear` still zeroes every cell in ONE clock (it clears the valid bits, not the RAMs).
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

    logic [7:0] x, y;
    logic [4:0] k;
    logic start_q;
    wire launch = start_q || (k != 0);

    // DSP48E1 multiply pipeline. These datapath registers intentionally have no reset.
    logic signed [8:0]  ax_r, bx_r, ay_r, by_r;
    logic signed [17:0] mx_r, my_r;
    logic signed [17:0] px_r, py_r;

    always_ff @(posedge clk) begin
        ax_r <= $signed({1'b0, x});
        bx_r <= ctab(k[3:0]);
        ay_r <= $signed({1'b0, y});
        by_r <= stab(k[3:0]);

        mx_r <= ax_r * bx_r;
        my_r <= ay_r * by_r;

        px_r <= mx_r;
        py_r <= my_r;
    end

    // Fabric pipeline: sum the products, apply the fixed-point rounding and select the bin.
    logic valid0, valid1, valid2, valid3;
    logic [3:0] theta0, theta1, theta2, theta3;
    logic signed [18:0] sum_r;
    logic [10:0] addr5;
    logic vote5;

    always_ff @(posedge clk) begin
        valid0 <= launch;
        theta0 <= k[3:0];
        valid1 <= valid0;
        theta1 <= theta0;
        valid2 <= valid1;
        theta2 <= theta1;

        sum_r <= {{1{px_r[17]}}, px_r} + {{1{py_r[17]}}, py_r};
        valid3 <= valid2;
        theta3 <= theta2;

        if (valid3) begin
            // Keep the rounding addition and arithmetic shift bit-for-bit equivalent to the reference.
            if (((($signed(sum_r) + 19'sd64) >>> 7) + ROFF) >= 0 &&
                ((($signed(sum_r) + 19'sd64) >>> 7) + ROFF) < NR) begin
                addr5 <= 11'(theta3 * NR + ((($signed(sum_r) + 19'sd64) >>> 7) + ROFF));
                vote5 <= 1'b1;
            end else begin
                addr5 <= 11'd0;
                vote5 <= 1'b0;
            end
        end else begin
            addr5 <= 11'd0;
            vote5 <= 1'b0;
        end

        if (!rst_n) begin
            valid0 <= 1'b0;
            valid1 <= 1'b0;
            valid2 <= 1'b0;
            valid3 <= 1'b0;
            vote5 <= 1'b0;
        end
    end

    logic read_valid;
    logic [10:0] wr_addr;
    logic vld_a, vld_b;
    logic [15:0] q_a, q_b;

    wire [10:0] ridx = 11'(rd_theta * NR + rd_rho);
    wire [15:0] newc = (vld_a ? q_a : 16'd0) + 16'd1;

    hough_cell_ram #(.N(NC)) u_a (
        .clk(clk), .we(read_valid), .waddr(wr_addr), .wdata(newc),
        .raddr(addr5), .rdata(q_a)
    );
    hough_cell_ram #(.N(NC)) u_b (
        .clk(clk), .we(read_valid), .waddr(wr_addr), .wdata(newc),
        .raddr(ridx), .rdata(q_b)
    );

    assign rd_cnt = vld_b ? q_b : 16'd0;

    always_ff @(posedge clk) begin
        read_valid <= vote5;
        wr_addr <= addr5;
        vld_a <= vld[addr5];
        vld_b <= vld[ridx];

        if (!rst_n) begin
            k <= 5'd0;
            start_q <= 1'b0;
            valid0 <= 1'b0;
            valid1 <= 1'b0;
            valid2 <= 1'b0;
            valid3 <= 1'b0;
            vote5 <= 1'b0;
            read_valid <= 1'b0;
        end else begin
            start_q <= 1'b0;

            if (clear && !busy)
                vld <= '0;

            if (read_valid)
                vld[wr_addr] <= 1'b1;

            if (pt_valid && !busy) begin
                x <= pt_x;
                y <= pt_y;
                start_q <= 1'b1;
            end

            if (launch)
                k <= (k == NT - 1) ? 5'd0 : k + 5'd1;
        end
    end

    assign busy = (k != 0) || start_q || valid0 || valid1 || valid2 || valid3 || vote5 || read_valid;
endmodule
