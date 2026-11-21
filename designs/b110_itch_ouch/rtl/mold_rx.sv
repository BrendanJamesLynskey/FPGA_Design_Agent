// mold_rx.sv: MoldUDP64 1.00 receiver on the UDP payload words of a 64-bit path (brief 110).
//
// Input: one UDP payload as 64-bit words (byte 0 in bits 7:0), s_sof on the first word, s_eof on the last, s_keep the valid bytes of the last word
// (a low-contiguous mask; every other word is full), s_err on the last word when the frame's check failed or the frame was cut. Words need not
// be contiguous (s_v may drop inside a packet) but a packet must be followed by at least 4 idle clocks before the next s_sof (an Ethernet frame
// always leaves more: the next payload starts after a 42 byte header, the FCS and the inter-frame gap).
// Output: one strobe m_v per delivered message, one clock after the word that carries its last byte. The message is delivered raw: 6 word slots
// m_w (slot 0 in [63:0]) and m_off, the byte offset of its first byte in slot 0; itch_dec aligns it. m_len is its length from the block header.
//
// What it does (section "Downstream Packet" of the MoldUDP64 specification): header (session 10, sequence number 8, message count 2), then
// message blocks (length 2, data). Count 0 is a heartbeat, 0xFFFF an end of session (no blocks follow). Packet level checks, once the header is
// in (one clock after the third word): session lock (the first accepted packet fixes the session; another session is dropped and counted), the
// expected sequence number (gap: counted and flagged, the packet is still delivered, no retransmission request in phase 1; duplicate or old
// packet: dropped; partial overlap: only the messages from the expected number on are delivered). A block shorter than MIN_LEN (12, the smallest
// ITCH 5.0 message) is counted and the rest of the packet is dropped. A packet that ends inside a block is counted as truncated and the cut
// block is not delivered.
// Messages are delivered while the frame's check is still pending (cut-through); s_err on the last word then counts and raises `untrusted`.
module mold_rx #(
    parameter int MIN_LEN = 12
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          clr_cnt,
    input  logic          clr_flags,     // gap, untrusted, end-of-session flags, the session lock and the expected sequence number
    input  logic          s_v,
    input  logic [63:0]   s_d,
    input  logic          s_sof,
    input  logic          s_eof,
    input  logic [7:0]    s_keep,
    input  logic          s_err,
    output logic          m_v,
    output logic [383:0]  m_w,
    output logic [2:0]    m_off,
    output logic [15:0]   m_len,
    output logic [31:0]   m_seq,
    output logic          pk_end,        // one clock after the last word of every packet
    output logic          gap_flag,
    output logic          untrusted,
    output logic          eos_seen,
    output logic          sess_lock,
    output logic [13*32-1:0] cnt         // pkt msg gap missing dup ovlp sess hb eos short trunc badlen pkt_err
);
    // ------------------------------------------------------------------ per-word view
    logic [3:0]  nv;
    always_comb begin
        nv = 4'd8;
        if (s_eof) begin
            case (s_keep)
                8'h01:   nv = 4'd1;
                8'h03:   nv = 4'd2;
                8'h07:   nv = 4'd3;
                8'h0F:   nv = 4'd4;
                8'h1F:   nv = 4'd5;
                8'h3F:   nv = 4'd6;
                8'h7F:   nv = 4'd7;
                default: nv = 4'd8;
            endcase
        end
    end

    logic [1:0]   wi;
    logic [16:0]  nxt;
    logic         in_data, hip, stop;
    logic [7:0]   lenhi;
    logic [2:0]   slot, soff;
    logic [15:0]  mlen, started, done_blk, cur_idx, cnt_r;
    logic [63:0]  wb0, wb1, wb2, wb3, wb4, wb5;
    logic [63:0]  hw0, hw1;
    logic [79:0]  sess_r, sess_l;
    logic [63:0]  seq_r, exp_seq;
    logic         hd, exp_v;
    logic         pk_bad;
    logic [15:0]  skip;

    // effective state (a start of frame restarts the packet whatever the previous packet left behind)
    logic [1:0]   w_idx;
    logic [16:0]  e_nxt;
    logic         e_ind, e_hip, e_stop;
    logic [15:0]  e_st, e_dn;
    logic [2:0]   e_slot, e_soff;
    logic [15:0]  e_mlen, e_cidx;
    assign w_idx  = s_sof ? 2'd0 : wi;
    assign e_nxt  = s_sof ? 17'd20 : nxt;
    assign e_ind  = !s_sof && in_data;
    assign e_hip  = !s_sof && hip;
    assign e_stop = !s_sof && stop;
    assign e_st   = s_sof ? 16'd0 : started;
    assign e_dn   = s_sof ? 16'd0 : done_blk;
    assign e_slot = slot;
    assign e_soff = soff;
    assign e_mlen = mlen;
    assign e_cidx = cur_idx;

    logic [15:0]  cnt_now;
    logic         hdr_known, cnt_ok, start_ok, nxt_lt8, comp, normal_start, hip_start, l_known, l_bad, new_msg, data_in_word, hdr_word;
    logic [2:0]   ph;
    logic [15:0]  l_val;
    logic [16:0]  e_rel;
    logic [3:0]   ph2;
    always_comb begin
        cnt_now   = (w_idx == 2'd2) ? {s_d[23:16], s_d[31:24]} : cnt_r;
        hdr_word  = (w_idx == 2'd2) && (nv >= 4'd4);
        hdr_known = (w_idx == 2'd3) || hdr_word;
        cnt_ok    = (cnt_now != 16'd0) && (cnt_now != 16'hFFFF);
        ph        = e_nxt[2:0];
        ph2       = {1'b0, ph};
        nxt_lt8   = (e_nxt[16:3] == 14'd0);
        comp      = e_ind && (e_nxt <= {13'd0, nv});
        start_ok  = hdr_known && cnt_ok && !e_stop && (e_st < cnt_now);
        normal_start = start_ok && !e_hip && nxt_lt8 && (!e_ind || comp) && ((ph != 3'd7) ? (ph2 + 4'd2 <= nv) : (nv == 4'd8));
        hip_start = e_hip;
        l_known   = hip_start || (normal_start && (ph != 3'd7));
        l_val     = hip_start ? {lenhi, s_d[7:0]} : {s_d[{ph, 3'b000} +: 8], s_d[{ph + 3'd1, 3'b000} +: 8]};
        l_bad     = l_known && (l_val < 16'(MIN_LEN));
        new_msg   = l_known && !l_bad;
        data_in_word = hip_start || (ph <= 3'd5);
        e_rel     = hip_start ? (17'd1 + {1'b0, l_val}) : ({14'd0, ph} + 17'd2 + {1'b0, l_val});
    end

    // ------------------------------------------------------------------ message output stage
    logic          mv_pre;
    logic [383:0]  mw_r;
    logic [2:0]    moff_r;
    logic [15:0]   mlen_r, midx_r;
    logic [31:0]   mseq_r;
    logic          gate_ok, gate_skip;
    assign gate_ok   = !pk_bad && (midx_r >= skip);
    assign gate_skip = !pk_bad && (midx_r < skip);
    assign m_v   = mv_pre && gate_ok;
    assign m_w   = mw_r;
    assign m_off = moff_r;
    assign m_len = mlen_r;
    assign m_seq = mseq_r;

    // ------------------------------------------------------------------ the packet's decision (one clock after the third word)
    logic         d_sess_ok, d_hbeos, d_lt, d_gt, d_dup, d_acc;
    logic [15:0]  d_neff;
    logic [31:0]  d_delta;
    logic [63:0]  d_next;
    always_comb begin
        d_sess_ok = !sess_lock || (sess_r == sess_l);
        d_hbeos   = (cnt_r == 16'd0) || (cnt_r == 16'hFFFF);
        d_neff    = d_hbeos ? 16'd0 : cnt_r;
        d_lt      = seq_r < exp_seq;
        d_gt      = seq_r > exp_seq;
        d_delta   = exp_seq[31:0] - seq_r[31:0];
        d_dup     = (exp_seq[63:32] != seq_r[63:32]) || (d_neff == 16'd0) || (d_delta >= {16'd0, d_neff});
        d_next    = seq_r + {48'd0, d_neff};
        d_acc     = d_sess_ok && (!exp_v || !d_lt || !d_dup);
    end

    logic [31:0] c_pkt, c_msg, c_gap, c_missing, c_dup, c_ovlp, c_sess, c_hb, c_eos, c_short, c_trunc, c_badlen, c_err;
    assign cnt = {c_err, c_badlen, c_trunc, c_short, c_eos, c_hb, c_sess, c_ovlp, c_dup, c_missing, c_gap, c_msg, c_pkt};

    always_ff @(posedge clk) begin
        mv_pre <= 1'b0;
        hd     <= 1'b0;
        pk_end <= 1'b0;
        if (rst) begin
            wi <= '0; nxt <= '0; in_data <= 1'b0; hip <= 1'b0; stop <= 1'b0; lenhi <= '0; slot <= '0; soff <= '0; mlen <= '0;
            started <= '0; done_blk <= '0; cur_idx <= '0; cnt_r <= '0; sess_r <= '0; seq_r <= '0; hw0 <= '0; hw1 <= '0;
            sess_l <= '0; sess_lock <= 1'b0; exp_seq <= '0; exp_v <= 1'b0; pk_bad <= 1'b0; skip <= '0;
            gap_flag <= 1'b0; untrusted <= 1'b0; eos_seen <= 1'b0;
            wb0 <= '0; wb1 <= '0; wb2 <= '0; wb3 <= '0; wb4 <= '0; wb5 <= '0;
            mw_r <= '0; moff_r <= '0; mlen_r <= '0; midx_r <= '0; mseq_r <= '0;
            c_pkt <= '0; c_msg <= '0; c_gap <= '0; c_missing <= '0; c_dup <= '0; c_ovlp <= '0; c_sess <= '0; c_hb <= '0; c_eos <= '0;
            c_short <= '0; c_trunc <= '0; c_badlen <= '0; c_err <= '0;
        end else begin
            // ---- the decision of the packet whose third word was last clock
            if (hd) begin
                if (!d_sess_ok) begin
                    c_sess <= c_sess + 32'd1;
                    pk_bad <= 1'b1;
                    skip   <= '0;
                end else begin
                    sess_lock <= 1'b1;
                    if (!sess_lock) sess_l <= sess_r;
                    pk_bad <= 1'b0;
                    skip   <= '0;
                    if (!exp_v) begin
                        exp_seq <= d_next; exp_v <= 1'b1;
                    end else if (d_gt) begin
                        c_gap <= c_gap + 32'd1;
                        c_missing <= c_missing + (seq_r[31:0] - exp_seq[31:0]);
                        gap_flag <= 1'b1;
                        exp_seq <= d_next;
                    end else if (!d_lt) begin
                        exp_seq <= d_next;
                    end else if (d_dup) begin
                        c_dup <= c_dup + 32'd1;
                        pk_bad <= 1'b1;
                    end else begin
                        skip <= d_delta[15:0];
                        exp_seq <= d_next;
                    end
                    if (d_acc) begin
                        c_pkt <= c_pkt + 32'd1;
                        if (cnt_r == 16'd0) c_hb <= c_hb + 32'd1;
                        if (cnt_r == 16'hFFFF) begin c_eos <= c_eos + 32'd1; eos_seen <= 1'b1; end
                    end
                end
            end
            // ---- message gating counters
            if (mv_pre) begin
                if (gate_ok) c_msg <= c_msg + 32'd1;
                if (gate_skip) c_ovlp <= c_ovlp + 32'd1;
            end
            // ---- one word
            if (s_v) begin
                if (w_idx == 2'd0) hw0 <= s_d;
                if (w_idx == 2'd1) hw1 <= s_d;
                if (hdr_word && w_idx == 2'd2) begin
                    sess_r <= {hw1[15:0], hw0};
                    seq_r  <= {hw1[23:16], hw1[31:24], hw1[39:32], hw1[47:40], hw1[55:48], hw1[63:56], s_d[7:0], s_d[15:8]};
                    cnt_r  <= {s_d[23:16], s_d[31:24]};
                    hd     <= 1'b1;
                end
                // completion of the message in progress
                if (comp) begin
                    mv_pre <= 1'b1;
                    mw_r   <= {(e_slot == 3'd5) ? s_d : wb5, (e_slot == 3'd4) ? s_d : wb4, (e_slot == 3'd3) ? s_d : wb3,
                               (e_slot == 3'd2) ? s_d : wb2, (e_slot == 3'd1) ? s_d : wb1, (e_slot == 3'd0) ? s_d : wb0};
                    moff_r <= e_soff;
                    mlen_r <= e_mlen;
                    midx_r <= e_cidx;
                    mseq_r <= seq_r[31:0] + {16'd0, e_cidx};
                    done_blk <= e_dn + 16'd1;
                end else begin
                    done_blk <= e_dn;
                end
                // the message in progress takes this word
                if (e_ind && !comp) begin
                    case (e_slot)
                        3'd0: wb0 <= s_d;
                        3'd1: wb1 <= s_d;
                        3'd2: wb2 <= s_d;
                        3'd3: wb3 <= s_d;
                        3'd4: wb4 <= s_d;
                        3'd5: wb5 <= s_d;
                        default: ;
                    endcase
                    slot <= (e_slot == 3'd7) ? 3'd7 : e_slot + 3'd1;
                end
                // a block starts
                started <= e_st + {15'd0, normal_start};
                if (new_msg) begin
                    in_data <= 1'b1;
                    mlen    <= l_val;
                    cur_idx <= hip_start ? (e_st - 16'd1) : e_st;
                    soff    <= hip_start ? 3'd1 : (ph <= 3'd5 ? ph + 3'd2 : 3'd0);
                    slot    <= data_in_word ? 3'd1 : 3'd0;
                    nxt     <= e_rel - 17'd8;
                    if (data_in_word) wb0 <= s_d;
                end else begin
                    in_data <= e_ind && !comp;
                    nxt <= nxt_lt8 ? 17'd0 : (e_nxt - 17'd8);
                end
                hip <= normal_start && (ph == 3'd7);
                if (normal_start && (ph == 3'd7)) lenhi <= s_d[63:56];
                if (l_bad) begin
                    stop <= 1'b1;
                    c_badlen <= c_badlen + 32'd1;
                    in_data <= 1'b0;
                end else if (s_sof) begin
                    stop <= 1'b0;
                end
                // end of the packet
                if (s_eof) begin
                    pk_end <= 1'b1;
                    wi <= 2'd0;
                    if (!hdr_known) c_short <= c_short + 32'd1;
                    else if (cnt_ok && !e_stop && !l_bad && ((e_dn + {15'd0, comp}) < cnt_now)) c_trunc <= c_trunc + 32'd1;
                    if (s_err) begin
                        c_err <= c_err + 32'd1;
                        untrusted <= 1'b1;
                    end
                end else begin
                    wi <= (w_idx == 2'd3) ? 2'd3 : w_idx + 2'd1;
                end
            end
            if (clr_cnt) begin
                c_pkt <= '0; c_msg <= '0; c_gap <= '0; c_missing <= '0; c_dup <= '0; c_ovlp <= '0; c_sess <= '0; c_hb <= '0; c_eos <= '0;
                c_short <= '0; c_trunc <= '0; c_badlen <= '0; c_err <= '0;
            end
            if (clr_flags) begin
                gap_flag <= 1'b0; untrusted <= 1'b0; eos_seen <= 1'b0; sess_lock <= 1'b0; exp_v <= 1'b0;
            end
        end
    end
endmodule
