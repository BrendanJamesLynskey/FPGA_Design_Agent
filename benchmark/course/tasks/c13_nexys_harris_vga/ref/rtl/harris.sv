// Part 13 project reference (07a1c form): Harris response and non-maximum suppression on a 7 x 7 window, pipelined and with one shared response unit.
// The first form of this reference computed the nine responses of the 3 x 3 neighbourhood in parallel (243 multipliers, about 100,000 LUTs): it did not fit the device.
// This form computes the same numbers in a different order:
//   cycle 1: the Sobel gradients ix, iy of the 25 pixels of the central 5 x 5 (each >>> 2, as the model does);
//   cycle 2: their products ix*ix, iy*iy, ix*iy;
//   cycle 3: the sums of three neighbouring products along each row;
//   cycle 4: the 3 x 3 box sums sxx, syy, sxy for each of the nine response positions (the three row sums added);
//   cycles 5 .. 15: one position per clock through one det - trace^2/16 unit (three multipliers, pipelined);
//   cycle 16: the non-maximum suppression and the threshold; out_valid is high in cycle 17.
// Cycle 0 is the clock in which in_valid is high; the window must hold still from then until out_valid (harris_detect does that).
module harris (
    input  logic                clk,
    input  logic                rst_n,
    input  logic                in_valid,
    input  logic [391:0]        win,
    input  logic signed [47:0]  thresh,
    output logic                out_valid,
    output logic signed [47:0]  resp,
    output logic                corner
);
    function automatic integer px(input [391:0] w, input integer r, input integer c);
        px = w[(7*r + c)*8 +: 8];
    endfunction
    function automatic integer gx(input [391:0] w, input integer r, input integer c);
        gx = (px(w, r-1, c+1) + 2*px(w, r, c+1) + px(w, r+1, c+1)) - (px(w, r-1, c-1) + 2*px(w, r, c-1) + px(w, r+1, c-1));
    endfunction
    function automatic integer gy(input [391:0] w, input integer r, input integer c);
        gy = (px(w, r+1, c-1) + 2*px(w, r+1, c) + px(w, r+1, c+1)) - (px(w, r-1, c-1) + 2*px(w, r-1, c) + px(w, r-1, c+1));
    endfunction

    // stage 1: gradients of window rows / columns 1 .. 5 (index 0 .. 4)
    logic signed [8:0]  ix  [0:4][0:4], iy  [0:4][0:4];
    // stage 2: products
    logic signed [17:0] ixx [0:4][0:4], iyy [0:4][0:4], ixy [0:4][0:4];
    // stage 3: sums of three products along a row (index: row 0 .. 4, first column 0 .. 2)
    logic signed [20:0] hxx [0:4][0:2], hyy [0:4][0:2], hxy [0:4][0:2];
    // stage 4: box sums for the nine response positions (row-major: nw n ne w c e sw s se)
    logic signed [23:0] sxx [0:8], syy [0:8], sxy [0:8];
    // the shared response unit: operands, products, response
    logic [4:0]         t;                          // the cycle number once a window has been presented (cycle 0 = in_valid)
    logic               run;
    logic signed [23:0] o_xx, o_yy, o_xy, o_tr;
    logic signed [47:0] p_det_a, p_det_b, p_tr2, rsp;
    logic signed [47:0] rr [0:8];

    integer a, b;
    always_ff @(posedge clk) begin
        for (a = 0; a < 5; a = a + 1)
            for (b = 0; b < 5; b = b + 1) begin
                ix[a][b]  <= 9'(gx(win, a + 1, b + 1) >>> 2);
                iy[a][b]  <= 9'(gy(win, a + 1, b + 1) >>> 2);
                ixx[a][b] <= ix[a][b] * ix[a][b];
                iyy[a][b] <= iy[a][b] * iy[a][b];
                ixy[a][b] <= ix[a][b] * iy[a][b];
            end
        for (a = 0; a < 5; a = a + 1)
            for (b = 0; b < 3; b = b + 1) begin
                hxx[a][b] <= 21'(ixx[a][b]) + 21'(ixx[a][b + 1]) + 21'(ixx[a][b + 2]);
                hyy[a][b] <= 21'(iyy[a][b]) + 21'(iyy[a][b + 1]) + 21'(iyy[a][b + 2]);
                hxy[a][b] <= 21'(ixy[a][b]) + 21'(ixy[a][b + 1]) + 21'(ixy[a][b + 2]);
            end
        for (a = 0; a < 3; a = a + 1)
            for (b = 0; b < 3; b = b + 1) begin
                sxx[3*a + b] <= 24'(hxx[a][b]) + 24'(hxx[a + 1][b]) + 24'(hxx[a + 2][b]);
                syy[3*a + b] <= 24'(hyy[a][b]) + 24'(hyy[a + 1][b]) + 24'(hyy[a + 2][b]);
                sxy[3*a + b] <= 24'(hxy[a][b]) + 24'(hxy[a + 1][b]) + 24'(hxy[a + 2][b]);
            end
        // one position per clock: position p is selected in cycle 4 + p, its response is stored in cycle 7 + p
        o_xx <= sxx[(t >= 4 && t <= 12) ? t - 4 : 0];
        o_yy <= syy[(t >= 4 && t <= 12) ? t - 4 : 0];
        o_xy <= sxy[(t >= 4 && t <= 12) ? t - 4 : 0];
        o_tr <= sxx[(t >= 4 && t <= 12) ? t - 4 : 0] + syy[(t >= 4 && t <= 12) ? t - 4 : 0];
        p_det_a <= o_xx * o_yy;
        p_det_b <= o_xy * o_xy;
        p_tr2   <= o_tr * o_tr;
        rsp     <= (p_det_a - p_det_b) - (p_tr2 >>> 4);
        if (t >= 7 && t <= 15) rr[t - 7] <= rsp;
    end

    wire signed [47:0] rc = rr[4];
    wire is_max = (rc > rr[0]) && (rc > rr[1]) && (rc > rr[2]) && (rc > rr[3]) && (rc >= rr[5]) && (rc >= rr[6]) && (rc >= rr[7]) && (rc >= rr[8]);

    always_ff @(posedge clk) begin
        if (t == 5'd16) begin
            resp   <= rc;
            corner <= (rc > thresh) && is_max;
        end
        if (!rst_n) begin
            out_valid <= 1'b0; run <= 1'b0; t <= 5'd0;
        end else begin
            out_valid <= 1'b0;
            if (in_valid) begin run <= 1'b1; t <= 5'd1; end
            else if (run) begin
                t <= t + 5'd1;
                if (t == 5'd16) begin run <= 1'b0; t <= 5'd0; out_valid <= 1'b1; end
            end
        end
    end
endmodule
