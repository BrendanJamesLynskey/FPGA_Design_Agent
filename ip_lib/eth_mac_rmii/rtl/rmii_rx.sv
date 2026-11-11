// rmii_rx.sv: RMII receive path, 10 and 100 Mb/s, to a byte-wide AXI-Stream with the FCS checked and removed.
//
// clk is the 50 MHz RMII reference clock. At 100 Mb/s every clock carries a dibit; at 10 Mb/s each dibit is held for
// 10 clocks and is sampled at the 5th, counted from the rise of CRS_DV. rxd[0] is the earlier bit on the wire
// (IEEE 802.3 clause 22 bit order, RMII specification rev 1.2).
//
// Start of frame: preamble dibits 01, then the SFD's last dibit 11. End of frame: CRS_DV low on two dibit samples in
// a row. The PHY toggles CRS_DV (low, high, low, ...) at the end of a frame while data are still in its FIFO, so a
// single low sample is data; the dibit taken with the first of two lows is not (the one-dibit delay handles both).
//
// Output: the frame from the destination address to the last payload byte. The FCS is checked over the whole frame
// and is not passed on; the stream lags the wire by five bytes so that tlast can mark the last byte before the FCS.
// tuser on the tlast beat = 1 when the frame is bad: FCS residue wrong, dibit count not a whole number of bytes, a
// frame shorter than MIN_FRAME bytes (FCS included), or rx_er during the frame. Frames of fewer than five bytes
// produce no output (counted as runts). There is no tready: like most MAC receive interfaces, the line cannot be
// stopped, so the consumer accepts every beat (put a FIFO after it).

module rmii_rx #(
    parameter int MIN_FRAME = 64            // bytes, FCS included; shorter frames are flagged bad (runt)
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       speed_100,           // 1 = 100 Mb/s, 0 = 10 Mb/s (from the PHY's auto-negotiation result)
    input  logic       crs_dv,
    input  logic [1:0] rxd,
    input  logic       rx_er,
    output logic [7:0] m_axis_tdata,
    output logic       m_axis_tvalid,
    output logic       m_axis_tlast,
    output logic       m_axis_tuser,
    // one-clock event pulses (for counters)
    output logic       ev_frame_ok,
    output logic       ev_frame_bad,         // any bad frame that produced output
    output logic       ev_fcs_err,
    output logic       ev_runt
);
    initial begin
        if (MIN_FRAME < 5 || MIN_FRAME > 1522) $error("rmii_rx: MIN_FRAME must be in 5..1522 (got %0d)", MIN_FRAME);
    end

    typedef enum logic [1:0] {S_IDLE, S_PRE, S_DATA} st_t;
    st_t st;

    // ---- dibit enable --------------------------------------------------------------------------------------
    logic [3:0] div;
    logic       crs_q;
    logic       de;                          // sample a dibit this clock
    always_ff @(posedge clk) begin
        if (rst) begin
            div <= '0; crs_q <= 1'b0;
        end else begin
            crs_q <= crs_dv;
            if (crs_dv && !crs_q && st == S_IDLE) div <= 4'd1;     // phase from the carrier's rise
            else if (div == 4'd9)                 div <= 4'd0;
            else                                  div <= div + 4'd1;
        end
    end
    assign de = speed_100 ? 1'b1 : (div == 4'd5);

    // ---- frame state ---------------------------------------------------------------------------------------
    logic [1:0]  d1;                         // the previous dibit, held one dibit
    logic        dv1, v1;                    // its CRS_DV, and whether d1 holds a dibit of this frame
    logic [7:0]  sh;                         // byte assembly, first dibit ends in [1:0]
    logic [1:0]  dcnt;                       // dibits in sh
    logic [7:0]  hold [0:4];                 // the five-byte lag line, hold[0] oldest
    logic [2:0]  nheld;
    logic [10:0] nbytes;                     // bytes in this frame (saturating)
    logic        err;                        // rx_er seen
    logic        pre_ok;                     // at least one preamble dibit 01 seen

    logic        crc_init, crc_en, crc_ok;
    logic [7:0]  crc_d;
    logic [31:0] crc_q;
    eth_crc32 u_crc (.clk(clk), .rst(rst), .init(crc_init), .en(crc_en), .d(crc_d), .crc(crc_q), .residue_ok(crc_ok));

    logic        push;                       // push d1 into the byte assembler this sample
    logic        byte_done;
    logic [7:0]  byte_new;
    logic        eof;

    always_comb begin
        eof       = (st == S_DATA) && de && v1 && !dv1 && !crs_dv;
        push      = (st == S_DATA) && de && v1 && !eof;
        byte_new  = {d1, sh[7:2]};
        byte_done = push && (dcnt == 2'd3);
        crc_init  = (st != S_DATA);
        crc_en    = byte_done;
        crc_d     = byte_new;
    end

    always_ff @(posedge clk) begin
        m_axis_tvalid <= 1'b0;
        m_axis_tlast  <= 1'b0;
        m_axis_tuser  <= 1'b0;
        ev_frame_ok   <= 1'b0;
        ev_frame_bad  <= 1'b0;
        ev_fcs_err    <= 1'b0;
        ev_runt       <= 1'b0;
        if (rst) begin
            st <= S_IDLE; v1 <= 1'b0; dv1 <= 1'b0; d1 <= '0; sh <= '0; dcnt <= '0; nheld <= '0; nbytes <= '0;
            err <= 1'b0; pre_ok <= 1'b0; m_axis_tdata <= '0;
        end else begin
            case (st)
                S_IDLE: if (de && crs_dv) begin
                    st <= S_PRE; pre_ok <= (rxd == 2'b01); err <= rx_er;
                end
                S_PRE: if (de) begin
                    if (!crs_dv)                        st <= S_IDLE;
                    else if (rxd == 2'b11 && pre_ok) begin
                        st <= S_DATA; v1 <= 1'b0; dcnt <= '0; nheld <= '0; nbytes <= '0;
                    end else if (rxd == 2'b01)          pre_ok <= 1'b1;
                    if (rx_er) err <= 1'b1;
                end
                S_DATA: if (de) begin
                    if (rx_er && crs_dv) err <= 1'b1;
                    if (eof) begin
                        st <= S_IDLE; v1 <= 1'b0;
                        if (nheld == 3'd5) begin
                            m_axis_tvalid <= 1'b1; m_axis_tlast <= 1'b1; m_axis_tdata <= hold[0];
                            m_axis_tuser  <= !crc_ok || (dcnt != 2'd0) || (nbytes < 11'(MIN_FRAME)) || err;
                            ev_frame_ok   <= crc_ok && (dcnt == 2'd0) && (nbytes >= 11'(MIN_FRAME)) && !err;
                            ev_frame_bad  <= !(crc_ok && (dcnt == 2'd0) && (nbytes >= 11'(MIN_FRAME)) && !err);
                            ev_fcs_err    <= !crc_ok;
                        end
                        ev_runt <= (nbytes < 11'(MIN_FRAME));
                    end else begin
                        d1 <= rxd; dv1 <= crs_dv; v1 <= 1'b1;
                        if (push) begin
                            sh   <= byte_new;
                            dcnt <= dcnt + 2'd1;
                        end
                        if (byte_done) begin
                            if (nbytes != 11'h7FF) nbytes <= nbytes + 11'd1;
                            if (nheld == 3'd5) begin
                                m_axis_tvalid <= 1'b1; m_axis_tdata <= hold[0];
                                hold[0] <= hold[1]; hold[1] <= hold[2]; hold[2] <= hold[3]; hold[3] <= hold[4];
                                hold[4] <= byte_new;
                            end else begin
                                hold[nheld] <= byte_new;
                                nheld <= nheld + 3'd1;
                            end
                        end
                    end
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
