// rgmii_rx.sv: RGMII receive, 10/100/1000 Mb/s -> one GMII byte per gmii_v in the RX_CLK domain.
//
// 1000 Mb/s (speed 2): RXD[3:0] on the rising edge of RX_CLK is data[3:0], on the falling edge data[7:4]; RX_CTL is
// RX_DV on the rising edge and RX_DV xor RX_ER on the falling edge (RGMII v2.0). A byte every clock.
// 10 and 100 Mb/s (speed 0, 1): RX_CLK is 2.5 or 25 MHz and each clock carries one nibble (the same on both edges),
// least significant nibble first. Bytes are aligned on the start-of-frame delimiter: the nibble 0xD that follows a
// 0x5 is the SFD's upper half; the SFD byte 0xD5 is passed on, then a byte every second nibble. Preamble nibbles
// before it are not passed on (mac_rx accepts a frame that starts at its SFD).
// gmii_dv stays high for the whole frame (the clock-crossing FIFO writes its end token when it falls).
// Synthesis uses IDDRE1 (FAMILY "ultrascale": UltraScale and UltraScale+) or IDDR (FAMILY "7series"), both in
// SAME_EDGE_PIPELINED mode; simulation the equivalent behaviour. The input delay (IDELAY_PS) is UltraScale only.

module rgmii_rx #(
    parameter int IDELAY_PS = 0,        // 0: no input delay; else each RXD/RX_CTL input through an IDELAYE3 of this many
                                        // ps (TIME mode, 0..1100; the design must have an IDELAYCTRL)
    parameter     FAMILY    = "ultrascale"  // "ultrascale" (IDDRE1) or "7series" (IDDR)
) (
    input  logic       rx_clk,
    input  logic [1:0] speed,           // 2 = 1000, 1 = 100, 0 = 10 Mb/s (stable while frames arrive)
    input  logic [3:0] rxd,
    input  logic       rx_ctl,
    output logic [7:0] gmii_d,
    output logic       gmii_v,
    output logic       gmii_dv,
    output logic       gmii_er
);
    logic [4:0] q_r, q_f;
    initial begin
        if (IDELAY_PS < 0 || IDELAY_PS > 1100) $error("rgmii_rx: IDELAY_PS must be in 0..1100 (got %0d)", IDELAY_PS);
        if (FAMILY != "ultrascale" && FAMILY != "7series") $error("rgmii_rx: FAMILY must be \"ultrascale\" or \"7series\"");
        if (FAMILY == "7series" && IDELAY_PS != 0) $error("rgmii_rx: IDELAY_PS is supported for FAMILY \"ultrascale\" only");
    end
`ifdef SYNTHESIS
    for (genvar i = 0; i < 5; i++) begin : g_iddr
        logic d_in, d_dly;
        assign d_in = (i == 4) ? rx_ctl : rxd[i];
        if (IDELAY_PS > 0) begin : g_dly
            (* IODELAY_GROUP = "rgmii_rx" *) IDELAYE3 #(.DELAY_SRC("IDATAIN"), .DELAY_TYPE("FIXED"), .DELAY_VALUE(IDELAY_PS),
                .DELAY_FORMAT("TIME"), .REFCLK_FREQUENCY(333.333), .SIM_DEVICE("ULTRASCALE_PLUS"),
                .UPDATE_MODE("ASYNC"), .CASCADE("NONE")) u_dly (
                .IDATAIN(d_in), .DATAIN(1'b0), .DATAOUT(d_dly), .CLK(1'b0), .CE(1'b0), .INC(1'b0), .LOAD(1'b0),
                .CNTVALUEIN(9'd0), .CNTVALUEOUT(), .EN_VTC(1'b1), .RST(1'b0), .CASC_IN(1'b0), .CASC_OUT(),
                .CASC_RETURN(1'b0));
        end else begin : g_nodly
            assign d_dly = d_in;
        end
        if (FAMILY == "7series") begin : g_7s
            IDDR #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .INIT_Q1(1'b0), .INIT_Q2(1'b0), .SRTYPE("SYNC")) u_iddr (
                .Q1(q_r[i]), .Q2(q_f[i]), .C(rx_clk), .CE(1'b1), .D(d_dly), .R(1'b0), .S(1'b0));
        end else begin : g_us
            IDDRE1 #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .IS_CB_INVERTED(1'b1), .IS_C_INVERTED(1'b0)) u_iddr (
                .Q1(q_r[i]), .Q2(q_f[i]), .C(rx_clk), .CB(rx_clk), .D(d_dly), .R(1'b0));
        end
    end
`else
    logic [4:0] r0, f0;
    always_ff @(posedge rx_clk) r0 <= {rx_ctl, rxd};
    always_ff @(negedge rx_clk) f0 <= {rx_ctl, rxd};
    always_ff @(posedge rx_clk) begin q_r <= r0; q_f <= f0; end
`endif
    logic       aligned, half;
    logic [3:0] lo;
    always_ff @(posedge rx_clk) begin
        gmii_v  <= 1'b0;
        gmii_dv <= q_r[4];
        gmii_er <= q_r[4] ^ q_f[4];
        if (speed == 2'd2) begin
            gmii_d  <= {q_f[3:0], q_r[3:0]};
            gmii_v  <= q_r[4];
            aligned <= 1'b0; half <= 1'b0;
        end else if (!q_r[4]) begin
            aligned <= 1'b0; half <= 1'b0;
        end else if (!aligned) begin
            lo <= q_r[3:0];
            if (q_r[3:0] == 4'hD && lo == 4'h5) begin
                aligned <= 1'b1; half <= 1'b0; gmii_d <= 8'hD5; gmii_v <= 1'b1;
            end
        end else begin
            half <= !half;
            if (!half) lo <= q_r[3:0];
            else begin gmii_d <= {q_r[3:0], lo}; gmii_v <= 1'b1; end
        end
    end
endmodule
