// Part 13 lesson 8 reference solution: single-pass connected-component labelling with a union-find parent table and per-root statistics.
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
    integer parent [0:MAXL-1];
    integer area [0:MAXL-1], sx [0:MAXL-1], sy [0:MAXL-1], xmin [0:MAXL-1], xmax [0:MAXL-1], ymin [0:MAXL-1], ymax [0:MAXL-1];
    integer line [0:W-1];
    integer left, nxt, x, y, scan;
    reg scanning;
    assign busy = scanning;
    assign s_tready = !scanning;

    function automatic integer find(input integer l);
        integer i, k;
        begin
            k = l;
            for (i = 0; i < MAXL; i = i + 1)
                if (k != 0 && parent[k] != k) k = parent[k];
            find = k;
        end
    endfunction

    integer xi, yi, up, ru, rl, root, other, i;
    always @(posedge clk) begin
        out_valid <= 1'b0;
        done <= 1'b0;
        if (!rst_n) begin
            scanning <= 1'b0; x = 0; y = 0; left = 0; nxt = 1; overflow <= 1'b0;
        end else if (scanning) begin
            if (scan < nxt) begin
                if (parent[scan] == scan && area[scan] != 0) begin
                    out_valid <= 1'b1;
                    out_area <= area[scan]; out_sx <= sx[scan]; out_sy <= sy[scan];
                    out_xmin <= xmin[scan]; out_xmax <= xmax[scan]; out_ymin <= ymin[scan]; out_ymax <= ymax[scan];
                end
                scan = scan + 1;
            end else begin
                scanning <= 1'b0;
                done <= 1'b1;
            end
        end else if (s_tvalid) begin
            if (s_tuser) begin
                x = 0; y = 0; left = 0; nxt = 1; overflow <= 1'b0;
                for (i = 0; i < MAXL; i = i + 1) begin parent[i] = i; area[i] = 0; end
            end
            xi = x; yi = y;
            if (s_tdata[0]) begin
                up = (yi > 0) ? line[xi] : 0;
                ru = find(up);
                rl = (xi > 0) ? find(left) : 0;
                if (ru == 0 && rl == 0) begin
                    if (nxt < MAXL) begin
                        root = nxt; nxt = nxt + 1;
                        parent[root] = root; area[root] = 0; sx[root] = 0; sy[root] = 0;
                        xmin[root] = xi; xmax[root] = xi; ymin[root] = yi; ymax[root] = yi;
                    end else begin
                        root = 0; overflow <= 1'b1;
                    end
                end else if (ru != 0 && rl != 0 && ru != rl) begin
                    root = (ru < rl) ? ru : rl;
                    other = (ru < rl) ? rl : ru;
                    parent[other] = root;
                    area[root] = area[root] + area[other];
                    sx[root] = sx[root] + sx[other];
                    sy[root] = sy[root] + sy[other];
                    if (xmin[other] < xmin[root]) xmin[root] = xmin[other];
                    if (xmax[other] > xmax[root]) xmax[root] = xmax[other];
                    if (ymin[other] < ymin[root]) ymin[root] = ymin[other];
                    if (ymax[other] > ymax[root]) ymax[root] = ymax[other];
                    area[other] = 0;
                end else begin
                    root = (ru != 0) ? ru : rl;
                end
                if (root != 0) begin
                    area[root] = area[root] + 1;
                    sx[root] = sx[root] + xi;
                    sy[root] = sy[root] + yi;
                    if (xi < xmin[root]) xmin[root] = xi;
                    if (xi > xmax[root]) xmax[root] = xi;
                    if (yi < ymin[root]) ymin[root] = yi;
                    if (yi > ymax[root]) ymax[root] = yi;
                end
                line[xi] = root;
                left = root;
            end else begin
                line[xi] = 0;
                left = 0;
            end
            if (xi == W - 1) begin
                x = 0;
                y = yi + 1;
                left = 0;
            end else begin
                x = xi + 1;
            end
            if (xi == W - 1 && yi == H - 1) begin
                scanning <= 1'b1;
                scan = 1;
            end
        end
    end
endmodule
