// rmii_tx.sv: byte-wide AXI-Stream to RMII transmit, 10 and 100 Mb/s, with preamble, SFD, padding and FCS added.
//
// Input: one frame per packet, destination address to the last payload byte, no FCS. The transmitter sends
// 7 x 0x55 and 0xD5, the frame, zero padding up to MIN_DATA bytes, the FCS (inverse CRC-32, least significant byte
// first), then holds TX_EN low for IFG_BYTES byte times before the next frame. Each byte goes out least significant
// dibit first (txd[0] is the earlier bit). At 10 Mb/s each dibit is held for 10 clocks.
//
// Back-pressure: tready pulses for one clock when the transmitter takes a byte; the wire cannot wait, so a missing
// byte inside a frame (tvalid low when the next byte is due) is an underrun: the frame is ended at once with an
// inverted (bad) FCS so that receivers drop it, and the rest of the packet is drained from the input and discarded.
// tuser on any input beat of a packet also aborts it the same way (a deliberate bad frame).

module rmii_tx #(
    parameter int MIN_DATA  = 60,           // destination address .. pad, without FCS (802.3: 60)
    parameter int IFG_BYTES = 12            // inter-frame gap in byte times (802.3: 96 bit times = 12)
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       speed_100,
    input  logic [7:0] s_axis_tdata,
    input  logic       s_axis_tvalid,
    output logic       s_axis_tready,
    input  logic       s_axis_tlast,
    input  logic       s_axis_tuser,
    output logic       tx_en,
    output logic [1:0] txd,
    output logic       ev_frame_sent,
    output logic       ev_underrun
);
    initial begin
        if (MIN_DATA < 1 || MIN_DATA > 1514) $error("rmii_tx: MIN_DATA must be in 1..1514 (got %0d)", MIN_DATA);
        if (IFG_BYTES < 1 || IFG_BYTES > 255) $error("rmii_tx: IFG_BYTES must be in 1..255 (got %0d)", IFG_BYTES);
    end

    // dibit enable: every clock at 100 Mb/s, every 10th clock at 10 Mb/s
    logic [3:0] div;
    logic       de;
    always_ff @(posedge clk) begin
        if (rst || div == 4'd9) div <= '0;
        else                    div <= div + 4'd1;
    end
    assign de = speed_100 ? 1'b1 : (div == 4'd9);

    typedef enum logic [2:0] {S_IDLE, S_PRE, S_DATA, S_PAD, S_FCS, S_IFG, S_DRAIN} st_t;
    st_t st;

    logic [7:0]  sh;                 // byte on the wire, shifted right by 2 each dibit
    logic [1:0]  dcnt;               // dibit within the byte
    logic [10:0] bcnt;               // byte counter within a phase
    logic        last_taken;         // the byte in sh is the packet's last
    logic        bad;                // abort: send an inverted FCS
    logic [31:0] fcs;                // FCS latched for S_FCS

    logic        crc_init, crc_en;
    logic [7:0]  crc_d;
    logic [31:0] crc_q;
    /* verilator lint_off PINCONNECTEMPTY */
    eth_crc32 u_crc (.clk(clk), .rst(rst), .init(crc_init), .en(crc_en), .d(crc_d), .crc(crc_q), .residue_ok());
    /* verilator lint_on PINCONNECTEMPTY */

    // a new byte is loaded into sh at the last dibit of the current one
    logic byte_end;
    assign byte_end = de && (dcnt == 2'd3);

    always_comb begin
        s_axis_tready = 1'b0;
        crc_init = (st == S_IDLE) || (st == S_IFG);
        crc_en = 1'b0;
        crc_d = s_axis_tdata;
        if (st == S_DRAIN) s_axis_tready = 1'b1;
        else if (byte_end) begin
            // take the next frame byte when one is due: the first at the end of the SFD, then after each byte
            if ((st == S_PRE && bcnt == 11'd7) || (st == S_DATA && !last_taken && !bad)) begin
                s_axis_tready = s_axis_tvalid;
                crc_en = s_axis_tvalid;
            end else if (st == S_DATA && last_taken && bcnt < 11'(MIN_DATA)) begin
                crc_en = 1'b1; crc_d = 8'h00;                 // first pad byte
            end else if (st == S_PAD && bcnt < 11'(MIN_DATA)) begin
                crc_en = 1'b1; crc_d = 8'h00;
            end
        end
    end

    always_ff @(posedge clk) begin
        ev_frame_sent <= 1'b0;
        ev_underrun   <= 1'b0;
        if (rst) begin
            st <= S_IDLE; tx_en <= 1'b0; txd <= 2'b00; sh <= '0; dcnt <= '0; bcnt <= '0;
            last_taken <= 1'b0; bad <= 1'b0; fcs <= '0;
        end else if (st == S_DRAIN) begin
            if (s_axis_tvalid && s_axis_tlast) begin st <= S_IDLE; bcnt <= '0; dcnt <= '0; end
        end else if (de) begin
            dcnt <= dcnt + 2'd1;
            // drive the current dibit
            case (st)
                S_IDLE: begin
                    tx_en <= 1'b0; txd <= 2'b00; dcnt <= '0;
                    if (s_axis_tvalid) begin
                        st <= S_PRE; bcnt <= '0; sh <= 8'h55; dcnt <= 2'd0; bad <= 1'b0; last_taken <= 1'b0;
                    end
                end
                default: ;
            endcase
            if (st != S_IDLE && st != S_IFG) begin
                tx_en <= 1'b1; txd <= sh[1:0]; sh <= {2'b00, sh[7:2]};
            end else if (st == S_IFG) begin
                tx_en <= 1'b0; txd <= 2'b00;
            end
            if (dcnt == 2'd3) begin
                bcnt <= bcnt + 11'd1;
                case (st)
                    S_PRE: begin
                        if (bcnt == 11'd6) sh <= 8'hD5;
                        else if (bcnt == 11'd7) begin
                            // SFD sent: first frame byte (tvalid was seen in S_IDLE, but may have dropped: underrun)
                            st <= S_DATA; bcnt <= 11'd1;
                            if (s_axis_tvalid) begin
                                sh <= s_axis_tdata; last_taken <= s_axis_tlast; bad <= s_axis_tuser;
                            end else begin
                                sh <= 8'h00; bad <= 1'b1; ev_underrun <= 1'b1;
                            end
                        end else sh <= 8'h55;
                    end
                    S_DATA: begin
                        if (bad) begin
                            // abort: send the inverted FCS now
                            st <= S_FCS; bcnt <= '0; sh <= crc_q[7:0]; fcs <= crc_q;     // not inverted: a bad FCS
                        end else if (!last_taken) begin
                            if (s_axis_tvalid) begin
                                sh <= s_axis_tdata; last_taken <= s_axis_tlast;
                                if (s_axis_tuser) bad <= 1'b1;
                            end else begin
                                sh <= 8'h00; bad <= 1'b1; ev_underrun <= 1'b1;
                            end
                        end else if (bcnt < 11'(MIN_DATA)) begin
                            st <= S_PAD; sh <= 8'h00;
                        end else begin
                            st <= S_FCS; bcnt <= '0; sh <= ~crc_q[7:0]; fcs <= crc_q;
                        end
                    end
                    S_PAD: begin
                        if (bcnt < 11'(MIN_DATA)) sh <= 8'h00;
                        else begin st <= S_FCS; bcnt <= '0; sh <= ~crc_q[7:0]; fcs <= crc_q; end
                    end
                    S_FCS: begin
                        // fcs holds the register; bytes 1..3 of its inverse (or of itself, when bad)
                        case (bcnt[1:0])
                            2'd0: sh <= bad ? fcs[15:8]  : ~fcs[15:8];
                            2'd1: sh <= bad ? fcs[23:16] : ~fcs[23:16];
                            2'd2: sh <= bad ? fcs[31:24] : ~fcs[31:24];
                            default: begin
                                st <= S_IFG; bcnt <= '0;
                                if (!bad) ev_frame_sent <= 1'b1;
                            end
                        endcase
                    end
                    S_IFG: begin
                        if (bcnt == 11'(IFG_BYTES - 1)) begin
                            // a packet aborted before its last byte is drained next
                            bcnt <= '0;
                            if (bad && !last_taken) st <= S_DRAIN;
                            else if (s_axis_tvalid) begin       // back to back: preamble at the next dibit
                                st <= S_PRE; sh <= 8'h55; bad <= 1'b0; last_taken <= 1'b0;
                            end else st <= S_IDLE;
                        end
                    end
                    default: ;
                endcase
            end
        end
    end
endmodule
