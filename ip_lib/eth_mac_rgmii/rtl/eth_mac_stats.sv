// eth_mac_stats.sv: Ethernet MAC statistics counters (ip_lib), fed by one event per frame.
//
// Every counter is STAT_W bits wide and wraps (as RMON and IEEE 802.3 clause 30 counters do; read them often enough).
// Octets count the frame from the destination address to the FCS, without preamble and SFD. A receive frame is good
// when its FCS is right, its length is in range and the PHY reported no error; broadcast, multicast and pause count
// good frames only. Read: rd_addr selects a counter, rd_data holds it one clock later. clear zeroes every counter (an
// event in the same clock is lost).
//
//   addr name             counts
//   0    rx_frames_good   good frames, whether or not the filter kept them
//   1    rx_octets_good   their octets
//   2    rx_frames_bad    frames with a bad FCS, a bad length or a PHY error
//   3    rx_fcs_err       frames whose FCS was wrong
//   4    rx_runt          frames shorter than MIN_FRAME
//   5    rx_giant         frames longer than MAX_FRAME
//   6    rx_phy_err       frames with RX_ER during the frame
//   7    rx_bcast         good broadcast frames
//   8    rx_mcast         good multicast frames (broadcast excluded)
//   9    rx_pause         good pause frames
//   10   rx_vlan          good tagged frames
//   11   rx_filtered      good frames the address filter rejected (MAC control frames consumed by PAUSE excluded)
//   12   rx_dropped       good, kept frames lost for want of buffer room (store-and-forward)
//   13   rx_fifo_ovf      clock-crossing FIFO overflows
//   14   tx_frames_good   frames sent with a good FCS
//   15   tx_octets_good   their octets (padding and FCS included)
//   16   tx_frames_bad    frames sent with a bad FCS (tuser, poison or underrun)
//   17   tx_bcast         good broadcast frames sent
//   18   tx_mcast         good multicast frames sent (broadcast excluded)
//   19   tx_pause         pause frames sent
//   20   tx_underrun      frames cut short by an AXI-Stream underrun

module eth_mac_stats #(
    parameter int STAT_W = 32,          // counter width, 16..64
    parameter int LEN_W  = 11           // width of the length inputs
) (
    input  logic              clk,
    input  logic              rst,
    input  logic              clear,
    // one receive event per frame
    input  logic              rx_ev,
    input  logic [LEN_W-1:0]  rx_len,
    input  logic              rx_good,
    input  logic              rx_fcs_err,
    input  logic              rx_runt,
    input  logic              rx_giant,
    input  logic              rx_phy_err,
    input  logic              rx_bcast,
    input  logic              rx_mcast,
    input  logic              rx_pause,
    input  logic              rx_vlan,
    input  logic              rx_filtered,
    input  logic              rx_dropped,     // pulse, any clock
    input  logic              rx_fifo_ovf,    // pulse, any clock
    // one transmit event per frame
    input  logic              tx_ev,
    input  logic [LEN_W-1:0]  tx_len,
    input  logic              tx_good,
    input  logic              tx_bcast,
    input  logic              tx_mcast,
    input  logic              tx_pause,
    input  logic              tx_underrun,    // pulse, any clock
    // read
    input  logic [4:0]        rd_addr,
    output logic [STAT_W-1:0] rd_data
);
    initial begin
        if (STAT_W < 16 || STAT_W > 64) $error("eth_mac_stats: STAT_W must be in 16..64 (got %0d)", STAT_W);
        if (LEN_W < 11 || LEN_W > 16) $error("eth_mac_stats: LEN_W must be in 11..16 (got %0d)", LEN_W);
    end
    localparam int N = 21;
    logic [STAT_W-1:0] c [N];
    logic [STAT_W-1:0] inc [N];

    always_comb begin
        for (int i = 0; i < N; i++) inc[i] = '0;
        if (rx_ev) begin
            if (rx_good) begin
                inc[0] = STAT_W'(1);
                inc[1] = STAT_W'(rx_len);
                inc[7] = STAT_W'(rx_bcast);
                inc[8] = STAT_W'(rx_mcast && !rx_bcast);
                inc[9] = STAT_W'(rx_pause);
                inc[10] = STAT_W'(rx_vlan);
                inc[11] = STAT_W'(rx_filtered);
            end else begin
                inc[2] = STAT_W'(1);
            end
            inc[3] = STAT_W'(rx_fcs_err);
            inc[4] = STAT_W'(rx_runt);
            inc[5] = STAT_W'(rx_giant);
            inc[6] = STAT_W'(rx_phy_err);
        end
        inc[12] = STAT_W'(rx_dropped);
        inc[13] = STAT_W'(rx_fifo_ovf);
        if (tx_ev) begin
            if (tx_good) begin
                inc[14] = STAT_W'(1);
                inc[15] = STAT_W'(tx_len);
                inc[17] = STAT_W'(tx_bcast);
                inc[18] = STAT_W'(tx_mcast && !tx_bcast);
            end else begin
                inc[16] = STAT_W'(1);
            end
            inc[19] = STAT_W'(tx_pause);
        end
        inc[20] = STAT_W'(tx_underrun);
    end

    always_ff @(posedge clk) begin
        for (int i = 0; i < N; i++) begin
            if (rst || clear) c[i] <= '0;
            else c[i] <= c[i] + inc[i];
        end
        rd_data <= (int'(rd_addr) < N) ? c[rd_addr] : '0;
    end
endmodule
