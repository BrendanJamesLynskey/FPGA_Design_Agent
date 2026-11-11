// eth_mac_rmii.sv: a 10/100 Ethernet MAC for an RMII PHY with byte-wide AXI-Stream user ports.
// Receive: preamble/SFD detection, FCS check and strip, runt and alignment flags (rmii_rx). Transmit: preamble, SFD,
// padding to the minimum frame, FCS generation and the inter-frame gap (rmii_tx). Full duplex only (no collision
// handling, no half-duplex back-off), no pause frames, no MDIO (a separate block).
//
// All logic runs on clk, the 50 MHz RMII reference clock that the PHY also uses. The RMII inputs are registered once
// here (place these in the IOB); the transmit outputs are registers in rmii_tx.

module eth_mac_rmii #(
    parameter int MIN_FRAME = 64,           // receive: shortest good frame, FCS included
    parameter int MIN_DATA  = 60,           // transmit: pad up to this many bytes before the FCS
    parameter int IFG_BYTES = 12            // transmit: inter-frame gap, byte times
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       speed_100,
    // RMII
    input  logic       rmii_crs_dv,
    input  logic [1:0] rmii_rxd,
    input  logic       rmii_rx_er,
    output logic       rmii_tx_en,
    output logic [1:0] rmii_txd,
    // receive stream (no tready: accept every beat)
    output logic [7:0] rx_axis_tdata,
    output logic       rx_axis_tvalid,
    output logic       rx_axis_tlast,
    output logic       rx_axis_tuser,       // on tlast: 1 = bad frame
    // transmit stream
    input  logic [7:0] tx_axis_tdata,
    input  logic       tx_axis_tvalid,
    output logic       tx_axis_tready,
    input  logic       tx_axis_tlast,
    input  logic       tx_axis_tuser,       // 1 on any beat: abort the frame (sent with a bad FCS)
    // event pulses
    output logic       ev_rx_ok,
    output logic       ev_rx_bad,
    output logic       ev_rx_fcs_err,
    output logic       ev_rx_runt,
    output logic       ev_tx_sent,
    output logic       ev_tx_underrun
);
    logic       crs_q, er_q;
    logic [1:0] rxd_q;
    always_ff @(posedge clk) begin
        if (rst) begin crs_q <= 1'b0; rxd_q <= 2'b00; er_q <= 1'b0; end
        else     begin crs_q <= rmii_crs_dv; rxd_q <= rmii_rxd; er_q <= rmii_rx_er; end
    end

    rmii_rx #(.MIN_FRAME(MIN_FRAME)) u_rx (
        .clk(clk), .rst(rst), .speed_100(speed_100), .crs_dv(crs_q), .rxd(rxd_q), .rx_er(er_q),
        .m_axis_tdata(rx_axis_tdata), .m_axis_tvalid(rx_axis_tvalid), .m_axis_tlast(rx_axis_tlast),
        .m_axis_tuser(rx_axis_tuser), .ev_frame_ok(ev_rx_ok), .ev_frame_bad(ev_rx_bad), .ev_fcs_err(ev_rx_fcs_err),
        .ev_runt(ev_rx_runt));

    rmii_tx #(.MIN_DATA(MIN_DATA), .IFG_BYTES(IFG_BYTES)) u_tx (
        .clk(clk), .rst(rst), .speed_100(speed_100),
        .s_axis_tdata(tx_axis_tdata), .s_axis_tvalid(tx_axis_tvalid), .s_axis_tready(tx_axis_tready),
        .s_axis_tlast(tx_axis_tlast), .s_axis_tuser(tx_axis_tuser), .tx_en(rmii_tx_en), .txd(rmii_txd),
        .ev_frame_sent(ev_tx_sent), .ev_underrun(ev_tx_underrun));
endmodule
