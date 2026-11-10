// io_fwd (brief 20 part B): a DAC output with a forwarded clock. An ODDR sends sys_clk inverted (D1=0, D2=1) to dac_clk,
// so the DAC's rising edge falls in the middle of each data bit; the data leave from IOB flip-flops on sys_clk.
module io_fwd (input logic CLK100MHZ, output logic dac_clk, output logic [7:0] dac_d);
    logic clk, cnt_en;
    BUFG bg (.I(CLK100MHZ), .O(clk));
    ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC"))
        fwd_oddr (.Q(dac_clk), .C(clk), .CE(1'b1), .D1(1'b0), .D2(1'b1), .R(1'b0), .S(1'b0));
    logic [7:0] cnt = '0;
    (* IOB = "true" *) logic [7:0] dac_q = '0;
    always_ff @(posedge clk) begin
        cnt   <= cnt + 8'd5;
        dac_q <= cnt;
    end
    assign dac_d = dac_q;
endmodule
