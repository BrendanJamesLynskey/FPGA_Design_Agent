// io_edge (brief 20 part B): an edge-aligned DDR input (data change with each rx_clk edge). Same capture structure as
// io_ddr (BUFIO to the IDDRs, BUFR to the fabric). USE_IDELAY = 1 puts a fixed IDELAYE2 (TAPS taps of 78 ps, reference
// clock 200 MHz from an MMCM on the board clock, IDELAYCTRL) in each data input to move the capture into the data eye.
module io_edge #(parameter int USE_IDELAY = 0, parameter int TAPS = 0)
               (input logic CLK100MHZ, input logic rx_clk, input logic [1:0] rx_d, output logic [0:0] LED);
    logic rx_ibuf, clk_io, clk_r;
    IBUF ib (.I(rx_clk), .O(rx_ibuf));
    BUFIO bio (.I(rx_ibuf), .O(clk_io));
    BUFR #(.BUFR_DIVIDE("BYPASS")) br (.I(rx_ibuf), .O(clk_r), .CE(1'b1), .CLR(1'b0));
    logic [1:0] d_dly, q1, q2;
    if (USE_IDELAY) begin : g_dly
        logic fb, c200, ref200, rdy;
        MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(5.0))
            mmcm (.CLKIN1(CLK100MHZ), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c200), .RST(1'b0), .PWRDWN(1'b0),
                  .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
                  .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED());
        BUFG bref (.I(c200), .O(ref200));
        (* IODELAY_GROUP = "rx" *) IDELAYCTRL ctrl (.REFCLK(ref200), .RST(1'b0), .RDY(rdy));
        for (genvar i = 0; i < 2; i++) begin : g
            (* IODELAY_GROUP = "rx" *)
            IDELAYE2 #(.IDELAY_TYPE("FIXED"), .IDELAY_VALUE(TAPS), .DELAY_SRC("IDATAIN"), .REFCLK_FREQUENCY(200.0),
                       .HIGH_PERFORMANCE_MODE("TRUE"), .SIGNAL_PATTERN("DATA"))
                dly (.IDATAIN(rx_d[i]), .DATAOUT(d_dly[i]), .C(1'b0), .CE(1'b0), .INC(1'b0), .LD(1'b0),
                     .LDPIPEEN(1'b0), .REGRST(1'b0), .CINVCTRL(1'b0), .CNTVALUEIN(5'd0), .CNTVALUEOUT(), .DATAIN(1'b0));
        end
    end else begin : g_nodly
        assign d_dly = rx_d;
    end
    for (genvar i = 0; i < 2; i++) begin : g
        IDDR #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .SRTYPE("SYNC"))
            iddr (.Q1(q1[i]), .Q2(q2[i]), .C(clk_io), .CE(1'b1), .D(d_dly[i]), .R(1'b0), .S(1'b0));
    end
    logic [3:0] word = '0;
    logic par = 1'b0;
    always_ff @(posedge clk_r) begin
        word <= {q2, q1};
        par  <= par ^ (^word);
    end
    assign LED[0] = par;
endmodule
