// iob_probe_k26.sv (brief 129): what IOB = "TRUE" does on a plain flip-flop of the K26 (UltraScale+), next to the same pins used
// the way the RGMII MAC uses them (IDDRE1 / ODDRE1). Pins are the KR260's RGMII PHY A pins (boards/kr260/kr260-pins.xdc).
//   a_rxd[0]  flop marked IOB, nothing else between pad and flop           (the case that should pack)
//   a_rxd[1]  flop marked IOB behind an AND gate                           (planted fault 1: logic before the input flop)
//   a_txd[0]  flop marked IOB driving only the pad                         (should pack)
//   a_txd[1]  flop marked IOB also read inside the design                  (planted fault 2: the output flop has a second load)
//   a_rx_ctl  IDDRE1, a_tx_ctl ODDRE1                                      (the RGMII style: primitives, no attribute)
module iob_probe_k26 (
    input  logic       clk_25,
    input  logic [3:0] a_rxd,
    input  logic       a_rx_ctl,
    output logic [3:0] a_txd,
    output logic       a_tx_ctl
);
    logic clk;
    BUFG u_bufg (.I(clk_25), .O(clk));
    (* IOB = "TRUE" *) logic q_rx0, q_rx1;
    (* IOB = "TRUE" *) logic q_tx0, q_tx1;
    logic [15:0] cnt;
    logic        id1, id2, mon;
    always_ff @(posedge clk) begin
        q_rx0 <= a_rxd[0];
        q_rx1 <= a_rxd[1] & a_rxd[2];
        cnt   <= cnt + {15'b0, q_rx0 ^ q_rx1 ^ id1 ^ id2 ^ a_rxd[3]};
        q_tx0 <= cnt[0];
        q_tx1 <= cnt[1];
        mon   <= q_tx1 ^ cnt[2];
    end
    assign a_txd[0] = q_tx0;
    assign a_txd[1] = q_tx1;
    assign a_txd[2] = mon;
    assign a_txd[3] = cnt[3];
    IDDRE1 #(.DDR_CLK_EDGE("SAME_EDGE_PIPELINED"), .IS_CB_INVERTED(1'b1), .IS_C_INVERTED(1'b0)) u_iddr (
        .Q1(id1), .Q2(id2), .C(clk), .CB(clk), .D(a_rx_ctl), .R(1'b0));
    ODDRE1 #(.SRVAL(1'b0)) u_oddr (.Q(a_tx_ctl), .C(clk), .D1(cnt[4]), .D2(cnt[5]), .SR(1'b0));
endmodule
