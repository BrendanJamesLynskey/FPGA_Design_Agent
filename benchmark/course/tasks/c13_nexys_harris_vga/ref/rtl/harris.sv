// Part 13 lesson 4 reference solution: Harris response and non-maximum suppression on a 7 x 7 window (behavioural; the lesson discusses the pipelined form).
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
    function automatic signed [47:0] response(input [391:0] w, input integer r, input integer c);
        reg signed [63:0] sxx, syy, sxy, det, tr, ix, iy;
        integer dr, dc;
        begin
            sxx = 0; syy = 0; sxy = 0;
            for (dr = -1; dr <= 1; dr = dr + 1)
                for (dc = -1; dc <= 1; dc = dc + 1) begin
                    ix = gx(w, r + dr, c + dc) >>> 2;
                    iy = gy(w, r + dr, c + dc) >>> 2;
                    sxx = sxx + ix * ix;
                    syy = syy + iy * iy;
                    sxy = sxy + ix * iy;
                end
            det = sxx * syy - sxy * sxy;
            tr  = sxx + syy;
            response = det - ((tr * tr) >>> 4);
        end
    endfunction
    wire signed [47:0] rc  = response(win, 3, 3);
    wire signed [47:0] rnw = response(win, 2, 2), rn = response(win, 2, 3), rne = response(win, 2, 4);
    wire signed [47:0] rw  = response(win, 3, 2), re = response(win, 3, 4);
    wire signed [47:0] rsw = response(win, 4, 2), rs = response(win, 4, 3), rse = response(win, 4, 4);
    wire is_max = (rc > rnw) && (rc > rn) && (rc > rne) && (rc > rw) && (rc >= re) && (rc >= rsw) && (rc >= rs) && (rc >= rse);
    always_ff @(posedge clk) begin
        resp   <= rc;
        corner <= (rc > thresh) && is_max;
        if (!rst_n) out_valid <= 1'b0;
        else        out_valid <= in_valid;
    end
endmodule
