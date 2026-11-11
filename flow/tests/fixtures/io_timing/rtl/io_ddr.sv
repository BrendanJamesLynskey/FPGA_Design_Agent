// io_ddr (brief 20 part B): a source-synchronous DDR input. The source forwards rx_clk (100 MHz) with two data bits that
// change on both edges. rx_clk enters a clock-capable pin and drives a BUFIO (the IDDRs in the IOBs) and a BUFR (the
// fabric registers), the 7-series source-synchronous capture structure (UG471 ch. 2).
module io_ddr (input logic rx_clk, input logic [1:0] rx_d, output logic [0:0] LED);
    logic rx_ibuf, clk_io, clk_r;
    IBUF ib (.I(rx_clk), .O(rx_ibuf));
    BUFIO bio (.I(rx_ibuf), .O(clk_io));
    BUFR #(.BUFR_DIVIDE("BYPASS")) br (.I(rx_ibuf), .O(clk_r), .CE(1'b1), .CLR(1'b0));
    logic [1:0] q1, q2;
    for (genvar i = 0; i < 2; i++) begin : g
        IDDR #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .SRTYPE("SYNC"))
            iddr (.Q1(q1[i]), .Q2(q2[i]), .C(clk_io), .CE(1'b1), .D(rx_d[i]), .R(1'b0), .S(1'b0));
    end
    logic [3:0] word = '0;
    logic par = 1'b0;
    always_ff @(posedge clk_r) begin
        word <= {q2, q1};
        par  <= par ^ (^word);
    end
    assign LED[0] = par;
endmodule
