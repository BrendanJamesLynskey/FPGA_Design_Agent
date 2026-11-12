// rgmii_rx.sv: RGMII receive, 10/100/1000 Mb/s -> one GMII byte per gmii_v in the RX_CLK domain.
//
// 1000 Mb/s (speed 2): RXD[3:0] on the rising edge of RX_CLK is data[3:0], on the falling edge data[7:4]; RX_CTL is
// RX_DV on the rising edge and RX_DV xor RX_ER on the falling edge (RGMII v2.0). A byte every clock.
// 10 and 100 Mb/s (speed 0, 1): RX_CLK is 2.5 or 25 MHz and each clock carries one nibble (the same on both edges),
// least significant nibble first. Bytes are aligned on the start-of-frame delimiter: the nibble 0xD that follows a
// 0x5 is the SFD's upper half; the SFD byte 0xD5 is passed on, then a byte every second nibble. Preamble nibbles
// before it are not passed on (mac_rx accepts a frame that starts at its SFD).
// gmii_dv stays high for the whole frame (the clock-crossing FIFO writes its end token when it falls).
// Synthesis uses IDDRE1 (SAME_EDGE_PIPELINED); simulation the equivalent behaviour.

module rgmii_rx (
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
`ifdef SYNTHESIS
    for (genvar i = 0; i < 5; i++) begin : g_iddr
        IDDRE1 #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .IS_CB_INVERTED(1'b1), .IS_C_INVERTED(1'b0)) u_iddr (
            .Q1(q_r[i]), .Q2(q_f[i]), .C(rx_clk), .CB(rx_clk), .D(i == 4 ? rx_ctl : rxd[i]), .R(1'b0));
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
