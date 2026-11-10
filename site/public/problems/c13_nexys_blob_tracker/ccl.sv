// Part 13 project reference (07a1c form): single-pass connected-component labelling with a union-find parent table and per-root statistics.
// The first form of this reference was behavioural (32-bit integer arrays, two union-find searches unrolled to 64 steps in one clock, one clock per pixel); Vivado could not
// finish it. This form takes a few clocks per pixel, follows the parent chain one step per clock, and uses sized registers. The labels, areas and sums are the same.
// Per object (label 1 .. MAXL-1): area, sum of x, sum of y, bounding box. Pixels with s_tdata[0] = 1 are object pixels; s_tuser marks the first pixel of a picture.
module ccl #(
    parameter int W = 20,
    parameter int H = 14,
    parameter int MAXL = 64
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  s_tdata,
    input  logic        s_tvalid,
    output logic        s_tready,
    input  logic        s_tuser,
    input  logic        s_tlast,
    output logic        busy,
    output logic        out_valid,
    output logic [15:0] out_area,
    output logic [19:0] out_sx,
    output logic [19:0] out_sy,
    output logic [7:0]  out_xmin,
    output logic [7:0]  out_xmax,
    output logic [7:0]  out_ymin,
    output logic [7:0]  out_ymax,
    output logic        done,
    output logic        overflow
);
    localparam int LW = $clog2(MAXL);                 // label width
    localparam int XW = $clog2(W);
    localparam int YW = $clog2(H);
    typedef enum logic [2:0] {S_IDLE, S_FIND_U, S_FIND_L, S_READ, S_APPLY, S_ADV, S_SCAN} state_t;
    state_t st;

    logic [LW-1:0] parent [0:MAXL-1];
    logic [15:0]   area   [0:MAXL-1];
    logic [19:0]   sx     [0:MAXL-1];
    logic [19:0]   sy     [0:MAXL-1];
    logic [7:0]    xmin   [0:MAXL-1];
    logic [7:0]    xmax   [0:MAXL-1];
    logic [7:0]    ymin   [0:MAXL-1];
    logic [7:0]    ymax   [0:MAXL-1];
    logic [LW-1:0] line_q [0:W-1];                    // labels of the previous row
    logic [XW-1:0] x, xi;                             // position of the next pixel, and of the pixel being processed
    logic [YW-1:0] y, yi;
    logic [LW-1:0] left, cur, ru, rl, rootp;
    logic [LW:0]   nxt_ext;                           // next free label, with a spare top bit so that MAXL is representable
    logic [LW:0]   scan;
    logic [LW:0]   it;                                // find steps taken
    logic          pix;

    assign busy     = (st == S_SCAN);
    assign s_tready = (st == S_IDLE);

    // statistics of the pixel being applied: the chosen root, optionally merged with the other root, plus this pixel
    wire           both   = (ru != 0) && (rl != 0) && (ru != rl);
    wire [LW-1:0]  r_lo   = (ru < rl) ? ru : rl;
    wire [LW-1:0]  r_hi   = (ru < rl) ? rl : ru;
    wire           is_new = (ru == 0) && (rl == 0);
    wire  [LW-1:0] sel    = both ? r_lo : ((ru != 0) ? ru : rl);
    wire  [15:0]   a_base_w = area[sel] + (both ? area[r_hi] : 16'd0);
    wire  [19:0]   sx_base_w = sx[sel] + (both ? sx[r_hi] : 20'd0);
    wire  [19:0]   sy_base_w = sy[sel] + (both ? sy[r_hi] : 20'd0);
    wire  [7:0]    xmin_b_w = (both && xmin[r_hi] < xmin[sel]) ? xmin[r_hi] : xmin[sel];
    wire  [7:0]    xmax_b_w = (both && xmax[r_hi] > xmax[sel]) ? xmax[r_hi] : xmax[sel];
    wire  [7:0]    ymin_b_w = (both && ymin[r_hi] < ymin[sel]) ? ymin[r_hi] : ymin[sel];
    wire  [7:0]    ymax_b_w = (both && ymax[r_hi] > ymax[sel]) ? ymax[r_hi] : ymax[sel];
    logic [15:0] a_base;
    logic [19:0] sx_base, sy_base;
    logic [7:0]  xmin_b, xmax_b, ymin_b, ymax_b;
    wire  [7:0]    xi8 = 8'(xi), yi8 = 8'(yi);

    integer i;
    always_ff @(posedge clk) begin
        out_valid <= 1'b0;
        done <= 1'b0;
        if (!rst_n) begin
            st <= S_IDLE; x <= '0; y <= '0; left <= '0; nxt_ext <= (LW+1)'(1); overflow <= 1'b0;
        end else begin
            case (st)
                S_IDLE: if (s_tvalid) begin
                    xi  <= s_tuser ? '0 : x;
                    yi  <= s_tuser ? '0 : y;
                    pix <= s_tdata[0];
                    if (s_tuser) begin
                        left <= '0; nxt_ext <= (LW+1)'(1); overflow <= 1'b0;
                        for (i = 0; i < MAXL; i = i + 1) begin parent[i] <= LW'(i); area[i] <= 16'd0; end
                    end
                    if (s_tdata[0]) begin
                        // up = previous row's label at this x (0 on the first row); the left label is 0 on the first column
                        cur <= (s_tuser || y == 0) ? '0 : line_q[x];
                        it  <= '0;
                        st  <= S_FIND_U;
                    end else begin
                        rootp <= '0;                                  // a dark pixel has no label
                        st <= S_ADV;
                    end
                end
                S_FIND_U: begin
                    if (cur != 0 && parent[cur] != cur && it < MAXL) begin cur <= parent[cur]; it <= it + 1'b1; end
                    else begin
                        ru  <= cur;
                        cur <= (xi == 0) ? '0 : left;
                        it  <= '0;
                        st  <= S_FIND_L;
                    end
                end
                S_FIND_L: begin
                    if (cur != 0 && parent[cur] != cur && it < MAXL) begin cur <= parent[cur]; it <= it + 1'b1; end
                    else begin
                        rl <= cur;
                        st <= S_READ;
                    end
                end
                S_READ: begin                                      // read the chosen root (and the one merged into it) into registers
                    a_base <= a_base_w; sx_base <= sx_base_w; sy_base <= sy_base_w;
                    xmin_b <= xmin_b_w; xmax_b <= xmax_b_w; ymin_b <= ymin_b_w; ymax_b <= ymax_b_w;
                    st <= S_APPLY;
                end
                S_APPLY: begin
                    if (is_new) begin
                        if (nxt_ext < MAXL) begin
                            // a new object: label nxt_ext, statistics start from this pixel
                            parent[nxt_ext[LW-1:0]] <= nxt_ext[LW-1:0];
                            area[nxt_ext[LW-1:0]] <= 16'd1;
                            sx[nxt_ext[LW-1:0]] <= 20'(xi); sy[nxt_ext[LW-1:0]] <= 20'(yi);
                            xmin[nxt_ext[LW-1:0]] <= xi8; xmax[nxt_ext[LW-1:0]] <= xi8;
                            ymin[nxt_ext[LW-1:0]] <= yi8; ymax[nxt_ext[LW-1:0]] <= yi8;
                            rootp <= nxt_ext[LW-1:0];
                            nxt_ext <= nxt_ext + 1'b1;
                        end else begin
                            rootp <= '0; overflow <= 1'b1;
                        end
                    end else begin
                        if (both) begin
                            parent[r_hi] <= r_lo;
                            area[r_hi] <= 16'd0;
                        end
                        area[sel] <= a_base + 16'd1;
                        sx[sel]   <= sx_base + 20'(xi);
                        sy[sel]   <= sy_base + 20'(yi);
                        xmin[sel] <= (xi8 < xmin_b) ? xi8 : xmin_b;
                        xmax[sel] <= (xi8 > xmax_b) ? xi8 : xmax_b;
                        ymin[sel] <= (yi8 < ymin_b) ? yi8 : ymin_b;
                        ymax[sel] <= (yi8 > ymax_b) ? yi8 : ymax_b;
                        rootp <= sel;
                    end
                    st <= S_ADV;
                end
                S_ADV: begin
                    line_q[xi] <= rootp;
                    y <= yi;                                        // (the first pixel of a picture restarts the row count)
                    if (xi == W - 1) begin
                        left <= '0; x <= '0;
                        y <= yi + 1'b1;
                    end else begin
                        left <= rootp; x <= xi + 1'b1;
                    end
                    if (xi == W - 1 && yi == H - 1) begin st <= S_SCAN; scan <= (LW+1)'(1); end
                    else st <= S_IDLE;
                end
                S_SCAN: begin
                    if (scan < nxt_ext) begin
                        if (parent[scan[LW-1:0]] == scan[LW-1:0] && area[scan[LW-1:0]] != 0) begin
                            out_valid <= 1'b1;
                            out_area <= area[scan[LW-1:0]]; out_sx <= sx[scan[LW-1:0]]; out_sy <= sy[scan[LW-1:0]];
                            out_xmin <= xmin[scan[LW-1:0]]; out_xmax <= xmax[scan[LW-1:0]]; out_ymin <= ymin[scan[LW-1:0]]; out_ymax <= ymax[scan[LW-1:0]];
                        end
                        scan <= scan + 1'b1;
                    end else begin
                        st <= S_IDLE;
                        done <= 1'b1;
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
