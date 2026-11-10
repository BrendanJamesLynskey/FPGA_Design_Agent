// P13-2 reference glue (v1.1 scope): the labeller (ccl.sv, the course's single-pass union-find labeller) plus the choice of the biggest object and its centroid.
// A picture goes in as a stream of 1-bit pixels (s_tdata[0], tuser on the first pixel); when the labeller has listed every object the report is final and `done` pulses for one clock.
// Biggest = largest area; on a tie the smaller top row, then the smaller left edge. Centroid = (sum x // area, sum y // area).
module blob_report #(
    parameter int W = 40,
    parameter int H = 30
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  s_tdata,
    input  logic        s_tvalid,
    output logic        s_tready,
    input  logic        s_tuser,
    input  logic        s_tlast,
    output logic        done,
    output logic [15:0] area,
    output logic [7:0]  cx,
    output logic [7:0]  cy
);
    logic        ov, ovf, ccl_done, ccl_busy;
    logic [15:0] o_area;
    logic [19:0] o_sx, o_sy;
    logic [7:0]  o_xmin, o_xmax, o_ymin, o_ymax;
    logic [15:0] b_area;
    logic [19:0] b_sx, b_sy;
    logic [7:0]  b_xmin, b_ymin;
    logic        have;
    logic        dbusy;
    logic [4:0]  dcnt;
    logic [19:0] qx, qy;                    // numerator shifting out, quotient shifting in
    logic [20:0] rx, ry;
    wire  [20:0] nrx = {rx[19:0], qx[19]}, nry = {ry[19:0], qy[19]};

    ccl #(.W(W), .H(H), .MAXL(64)) u_ccl (.clk(clk), .rst_n(rst_n), .s_tdata(s_tdata), .s_tvalid(s_tvalid), .s_tready(s_tready), .s_tuser(s_tuser), .s_tlast(s_tlast),
        .busy(ccl_busy), .out_valid(ov), .out_area(o_area), .out_sx(o_sx), .out_sy(o_sy), .out_xmin(o_xmin), .out_xmax(o_xmax), .out_ymin(o_ymin), .out_ymax(o_ymax),
        .done(ccl_done), .overflow(ovf));

    wire better = !have || (o_area > b_area) || (o_area == b_area && (o_ymin < b_ymin || (o_ymin == b_ymin && o_xmin < b_xmin)));

    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) begin
            have <= 1'b0; dbusy <= 1'b0; area <= 16'd0; cx <= 8'd0; cy <= 8'd0; b_area <= 16'd0;
        end else begin
            if (s_tvalid && s_tready && s_tuser) begin have <= 1'b0; b_area <= 16'd0; end   // a new picture: forget the previous choice
            if (ov && better) begin
                have <= 1'b1;
                b_area <= o_area; b_sx <= o_sx; b_sy <= o_sy; b_xmin <= o_xmin; b_ymin <= o_ymin;
            end
            if (ccl_done) begin
                area <= b_area;
                if (b_area == 0) begin cx <= 8'd0; cy <= 8'd0; done <= 1'b1; end
                else begin                                          // the centroid: two restoring divisions, one bit per clock
                    dbusy <= 1'b1; dcnt <= 5'd19; qx <= b_sx; qy <= b_sy; rx <= '0; ry <= '0;
                end
            end
            if (dbusy) begin
                qx <= {qx[18:0], (nrx >= {5'd0, b_area})};
                qy <= {qy[18:0], (nry >= {5'd0, b_area})};
                rx <= (nrx >= {5'd0, b_area}) ? nrx - {5'd0, b_area} : nrx;
                ry <= (nry >= {5'd0, b_area}) ? nry - {5'd0, b_area} : nry;
                dcnt <= dcnt - 5'd1;
                if (dcnt == 5'd0) begin
                    dbusy <= 1'b0; done <= 1'b1;
                    cx <= {qx[6:0], (nrx >= {5'd0, b_area})};
                    cy <= {qy[6:0], (nry >= {5'd0, b_area})};
                end
            end
        end
    end
endmodule
