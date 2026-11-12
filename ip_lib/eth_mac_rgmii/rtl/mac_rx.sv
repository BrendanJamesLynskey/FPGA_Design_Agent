// mac_rx.sv: cut-through Ethernet receive MAC, one byte a clock (GMII byte stream after the RX clock crossing).
//
// Input: the bytes the PHY delivered while RX_DV was high, each with its RX_ER, plus an end token when RX_DV fell
// (in_eof = 1, data ignored). Gaps between input beats (in_valid low) are allowed anywhere: the clock crossing can
// insert them.
//
// Cut-through: every frame byte (destination address first, FCS last) leaves on out_* one clock after it arrives,
// before the frame is known to be good. The FCS is checked over the whole frame (CRC residue, IEEE 802.3 clause
// 3.2.9) and the verdict comes with the end token: end_valid with end_good = 1 only when the residue is right, the
// frame is MIN_FRAME..MAX_FRAME bytes (FCS included) and no RX_ER was seen. Consumers act speculatively on the bytes
// and undo on end_good = 0 (the trading path's speculative/safe split).
//
// Start of frame: one or more preamble bytes 0x55, then the SFD 0xD5. A PHY may shorten the preamble, so one 0x55 is
// enough; a frame whose first byte is the SFD is also accepted (counted the same). Anything else before the SFD
// drops the frame until the end token (ev_bad_pre). out_sof marks the first byte after the SFD and sof_pulse is the
// receive timestamp point (the clock the SFD was taken).

module mac_rx #(
    parameter int MIN_FRAME = 64,       // bytes, FCS included
    parameter int MAX_FRAME = 1522      // bytes, FCS included (one VLAN tag)
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic        in_eof,
    input  logic        in_er,
    input  logic [7:0]  in_data,
    output logic        sof_pulse,      // the SFD was taken this clock (timestamp point)
    output logic        out_valid,
    output logic        out_sof,
    output logic [7:0]  out_data,
    output logic [10:0] out_idx,        // byte index from the destination address (saturates at 2047)
    output logic        end_valid,      // one clock: the frame ended (end token)
    output logic        end_good,
    output logic        end_fcs_err,
    output logic        end_runt,
    output logic        end_giant,
    output logic        end_er,
    output logic [10:0] end_len,        // bytes, FCS included (saturating)
    output logic        ev_bad_pre      // one clock: bytes before an SFD that were not preamble
);
    initial begin
        if (MIN_FRAME < 5 || MIN_FRAME > MAX_FRAME) $error("mac_rx: MIN_FRAME must be in 5..MAX_FRAME (got %0d)", MIN_FRAME);
        if (MAX_FRAME > 2000) $error("mac_rx: MAX_FRAME must be at most 2000 (got %0d)", MAX_FRAME);
    end

    localparam logic [1:0] S_IDLE = 2'd0, S_DATA = 2'd1, S_DROP = 2'd2;
    logic [1:0]  st;
    logic [10:0] n;                     // data bytes so far
    logic        err;

    logic        crc_init, crc_en, crc_ok;
    logic [31:0] crc_q;
    eth_crc32 u_crc (.clk(clk), .rst(rst), .init(crc_init), .en(crc_en), .d(in_data), .crc(crc_q), .residue_ok(crc_ok));

    logic data_beat;
    assign data_beat = in_valid && !in_eof && st == S_DATA;
    assign crc_init  = (st != S_DATA);
    assign crc_en    = data_beat;

    always_ff @(posedge clk) begin
        sof_pulse  <= 1'b0;
        out_valid  <= 1'b0;
        out_sof    <= 1'b0;
        end_valid  <= 1'b0;
        ev_bad_pre <= 1'b0;
        if (rst) begin
            st <= S_IDLE; n <= '0; err <= 1'b0; out_data <= '0; out_idx <= '0;
            end_good <= 1'b0; end_fcs_err <= 1'b0; end_runt <= 1'b0; end_giant <= 1'b0; end_er <= 1'b0; end_len <= '0;
        end else if (in_valid) begin
            case (st)
                S_IDLE: begin
                    if (in_eof) begin
                        err <= 1'b0;                                     // carrier ended inside the preamble
                    end else if (in_data == 8'hD5) begin
                        st <= S_DATA; n <= '0; sof_pulse <= 1'b1; err <= err | in_er;
                    end else if (in_data == 8'h55) begin
                        err <= err | in_er;
                    end else begin
                        st <= S_DROP; ev_bad_pre <= 1'b1;
                    end
                end
                S_DATA: begin
                    if (in_eof) begin
                        st <= S_IDLE; err <= 1'b0;
                        end_valid   <= 1'b1;
                        end_len     <= n;
                        end_fcs_err <= !crc_ok;
                        end_runt    <= n < 11'(MIN_FRAME);
                        end_giant   <= n > 11'(MAX_FRAME);
                        end_er      <= err;
                        end_good    <= crc_ok && n >= 11'(MIN_FRAME) && n <= 11'(MAX_FRAME) && !err;
                    end else begin
                        out_valid <= 1'b1;
                        out_sof   <= (n == 11'd0);
                        out_data  <= in_data;
                        out_idx   <= n;
                        if (n != 11'h7FF) n <= n + 11'd1;
                        if (in_er) err <= 1'b1;
                    end
                end
                default: begin                                           // S_DROP: wait for the end token
                    if (in_eof) begin st <= S_IDLE; err <= 1'b0; end
                end
            endcase
        end
    end
endmodule
