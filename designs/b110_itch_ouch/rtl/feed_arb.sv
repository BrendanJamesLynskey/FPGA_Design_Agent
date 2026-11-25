// feed_arb.sv: A/B feed arbiter in front of mold_rx (brief 191; idea from Edwards 2026, ch 4, built from scratch).
//
// Exchanges send every MoldUDP64 packet on two multicast feeds (A and B). The arbiter takes both UDP payload streams (the interface of mold_rx: 64-bit words,
// byte 0 in bits 7:0, s_sof on the first word, s_eof on the last, s_keep the valid bytes of the last word, s_err on the last word of a bad or cut frame) and gives
// ONE stream with that interface, so the parser sees one sequence: the FIRST copy of each packet wins, the other copy is dropped as a duplicate, and when one feed
// lost a packet the other feed's copy is the first copy and fills the gap.
//
// How: each feed's words go into a small FIFO (feed_arb_in). The header's third word (from which the session, the sequence number and the message count are known)
// decides the packet against `nxt`, the arbiter's next expected sequence number (the end of the last packet it forwarded):
//   - a packet whose messages are all below `nxt` (seq + count <= nxt) is old: dropped and counted per feed;
//   - any other packet is forwarded whole: seq <= nxt < seq + count (in order, or an overlap that mold_rx trims) or seq > nxt (this feed is ahead of what was
//     forwarded: the gap is passed on and counted `gap`; if the other feed's copy of the missing packet comes later it is old and is dropped: see "fill window");
//   - a heartbeat or end-of-session packet (count 0 or 0xFFFF) is old below `nxt`; at `nxt` or above it is forwarded unless a heartbeat (or end of session) with the same
//     sequence number and kind was forwarded within HB_WIN clocks (periodic heartbeats of one feed all pass; the same heartbeat from the two feeds passes once);
//   - a packet of another session than the first one seen is forwarded unchanged (mold_rx counts and drops it, `sess` counts it here) and does not change `nxt`;
//   - a runt (it ends before its third word, so it has no sequence number) is forwarded unchanged, as is a packet whose header words were lost to FIFO overflow.
// When both feeds decide in the same clock feed A is judged first and B on the state A leaves. Forwarded packets leave in the order of their decisions, one packet
// at a time, with at least MIN_IDLE idle clocks between packets (mold_rx needs 4).
//
// FILL WINDOW: a missing packet is filled only if the other feed's copy has its third word in BEFORE the first feed's next packet has its own: the arbiter holds no
// packet back to wait for a late copy (that needs a buffer for a whole packet and delays every packet behind it). With the feeds within a few clocks of each other
// and packets more than a few clocks apart (the usual case) the window is not a problem; the tests measure where it ends (docs/itch_ouch.md).
// A frame that ends with s_err on the first copy is forwarded and flagged exactly as without the arbiter (cut-through: it cannot be called back); the other feed's
// good copy is dropped as old.
//
// Latency: a word of a forwarded packet leaves 4 clocks after it entered (a registered decision, then the FIFO read and the output register); all words of a packet
// keep that delay while the FIFO does not fill. A FIFO overflow (a feed far ahead of the packet being forwarded) drops words, counts `ovf` and sets s_err on the
// packet's last word, so mold_rx marks the path untrusted.
module feed_arb #(
    parameter int AW       = 5,      // FIFO depth per feed: 2^AW words
    parameter int MIN_IDLE = 4,      // idle clocks left between two forwarded packets
    parameter int HB_WIN   = 4096    // clocks within which the other feed's heartbeat with the same sequence number is the same heartbeat
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          clr_cnt,
    input  logic          a_v, a_sof, a_eof, a_err,
    input  logic [63:0]   a_d,
    input  logic [7:0]    a_keep,
    input  logic          b_v, b_sof, b_eof, b_err,
    input  logic [63:0]   b_d,
    input  logic [7:0]    b_keep,
    output logic          o_v, o_sof, o_eof, o_err,
    output logic [63:0]   o_d,
    output logic [7:0]    o_keep,
    output logic [7*32-1:0] cnt          // fwd_a fwd_b old_a old_b gap sess ovf
);
    // entry layout: err 74, sof 73, eof 72, keep 71:64, data 63:0
    logic        h3a, h3b, hba, hbb, fba, fbb, ova, ovb, rda, rdb, nza, nzb;
    logic [79:0] sa, sb;
    logic [63:0] qa, qb;
    logic [15:0] na, nb, rca, rcb;
    logic [74:0] ha, hb;
    logic        fwa, fwb, popa, popb;

    feed_arb_in #(.AW(AW)) u_a (.clk, .rst, .v(a_v), .sof(a_sof), .eof(a_eof), .err(a_err), .d(a_d), .keep(a_keep), .h3(h3a), .h_sess(sa), .h_seq(qa), .h_neff(na),
                                .h_hb(hba), .h_rawc(rca), .h3_fwd(fwa), .fb_fwd(fba), .ovf_p(ova), .fwd_ready(rda), .occ_nz(nza), .head(ha), .pop(popa));
    feed_arb_in #(.AW(AW)) u_b (.clk, .rst, .v(b_v), .sof(b_sof), .eof(b_eof), .err(b_err), .d(b_d), .keep(b_keep), .h3(h3b), .h_sess(sb), .h_seq(qb), .h_neff(nb),
                                .h_hb(hbb), .h_rawc(rcb), .h3_fwd(fwb), .fb_fwd(fbb), .ovf_p(ovb), .fwd_ready(rdb), .occ_nz(nzb), .head(hb), .pop(popb));

    // ------------------------------------------------------------------ the decision (A first, then B on the state A leaves)
    logic [63:0] nxt, hb_seq;
    logic [15:0] hb_rc;
    logic        nxt_v, lock_v;
    logic [79:0] sess_l;
    logic [15:0] hb_win;
    logic [63:0] s_nxt [3];
    logic        s_nxtv [3], s_lock [3];
    logic [79:0] s_sess [3];
    logic [63:0] s_hbseq [3];
    logic [15:0] s_hbwin [3];
    logic [15:0] s_hbrc [3];
    logic [15:0] h_rawc [2];
    logic [1:0]  h3, d_old, d_gap, d_sess, d_fwd;
    logic [1:0]  hh;
    logic [79:0] h_sess [2];
    logic [63:0] h_seq [2];
    logic [15:0] h_neff [2];
    assign h3 = {h3b, h3a}; assign hh = {hbb, hba};
    assign h_sess[0] = sa; assign h_sess[1] = sb; assign h_seq[0] = qa; assign h_seq[1] = qb; assign h_neff[0] = na; assign h_neff[1] = nb; assign h_rawc[0] = rca; assign h_rawc[1] = rcb;
    assign fwa = d_fwd[0]; assign fwb = d_fwd[1];
    always_comb begin
        s_nxt[0] = nxt; s_nxtv[0] = nxt_v; s_lock[0] = lock_v; s_sess[0] = sess_l; s_hbseq[0] = hb_seq; s_hbwin[0] = hb_win; s_hbrc[0] = hb_rc;
        for (int f = 0; f < 2; f++) begin
            s_nxt[f+1] = s_nxt[f]; s_nxtv[f+1] = s_nxtv[f]; s_lock[f+1] = s_lock[f]; s_sess[f+1] = s_sess[f]; s_hbseq[f+1] = s_hbseq[f]; s_hbwin[f+1] = s_hbwin[f]; s_hbrc[f+1] = s_hbrc[f];
            d_fwd[f] = 1'b1; d_old[f] = 1'b0; d_gap[f] = 1'b0; d_sess[f] = 1'b0;
            if (h3[f]) begin
                if (s_lock[f] && h_sess[f] != s_sess[f]) begin
                    d_sess[f] = 1'b1;                                        // another session: forwarded, mold_rx counts and drops it
                end else begin
                    s_lock[f+1] = 1'b1; s_sess[f+1] = h_sess[f];
                    if (!s_nxtv[f]) begin
                        s_nxt[f+1] = h_seq[f] + {48'd0, h_neff[f]}; s_nxtv[f+1] = 1'b1;
                        if (hh[f]) begin s_hbseq[f+1] = h_seq[f]; s_hbwin[f+1] = 16'(HB_WIN); s_hbrc[f+1] = h_rawc[f]; end
                    end else if (hh[f]) begin
                        if (h_seq[f] < s_nxt[f]) begin
                            d_fwd[f] = 1'b0; d_old[f] = 1'b1;
                        end else if (s_hbwin[f] != 16'd0 && s_hbseq[f] == h_seq[f] && s_hbrc[f] == h_rawc[f]) begin
                            d_fwd[f] = 1'b0; d_old[f] = 1'b1;                // the other feed's copy of a heartbeat just forwarded
                        end else begin
                            d_gap[f] = (h_seq[f] > s_nxt[f]);
                            s_nxt[f+1] = h_seq[f]; s_hbseq[f+1] = h_seq[f]; s_hbwin[f+1] = 16'(HB_WIN); s_hbrc[f+1] = h_rawc[f];
                        end
                    end else if (h_seq[f] + {48'd0, h_neff[f]} <= s_nxt[f]) begin
                        d_fwd[f] = 1'b0; d_old[f] = 1'b1;
                    end else begin
                        d_gap[f] = (h_seq[f] > s_nxt[f]);
                        s_nxt[f+1] = h_seq[f] + {48'd0, h_neff[f]};
                    end
                end
            end
        end
    end

    // ------------------------------------------------------------------ the order of forwarded packets: feed ids in decision order (16 entries)
    logic [15:0] of_ids;
    logic [3:0]  of_rp, of_wp;
    logic [4:0]  of_n;
    logic        push_a, push_b, rd_busy, rd_own, start, can_pop;
    logic [7:0]  idle_c;
    logic        of_front;
    assign push_a = (h3[0] && d_fwd[0]) || fba;
    assign push_b = (h3[1] && d_fwd[1]) || fbb;
    assign of_front = of_ids[of_rp];

    always_comb begin
        start = !rd_busy && (of_n != 5'd0) && (idle_c == 8'd0) && (of_front ? rdb : rda);
        can_pop = 1'b0;
        if (start) can_pop = 1'b1;
        else if (rd_busy) can_pop = rd_own ? nzb : nza;
        popa = can_pop && !(rd_busy ? rd_own : of_front);
        popb = can_pop &&  (rd_busy ? rd_own : of_front);
    end
    logic [74:0] rword;
    assign rword = (rd_busy ? rd_own : of_front) ? hb : ha;

    logic [31:0] c_fa, c_fb, c_oa, c_ob, c_gap, c_sess, c_ovf;
    assign cnt = {c_ovf, c_sess, c_gap, c_ob, c_oa, c_fb, c_fa};

    always_ff @(posedge clk) begin
        o_v <= 1'b0;
        if (rst) begin
            nxt <= '0; nxt_v <= 1'b0; lock_v <= 1'b0; sess_l <= '0; hb_seq <= '0; hb_win <= '0; hb_rc <= '0;
            of_ids <= '0; of_rp <= '0; of_wp <= '0; of_n <= '0; rd_busy <= 1'b0; rd_own <= 1'b0; idle_c <= '0;
            o_sof <= 1'b0; o_eof <= 1'b0; o_err <= 1'b0; o_d <= '0; o_keep <= '0;
            c_fa <= '0; c_fb <= '0; c_oa <= '0; c_ob <= '0; c_gap <= '0; c_sess <= '0; c_ovf <= '0;
        end else begin
            if (h3[0] || h3[1]) begin
                nxt <= s_nxt[2]; nxt_v <= s_nxtv[2]; lock_v <= s_lock[2]; sess_l <= s_sess[2]; hb_seq <= s_hbseq[2]; hb_win <= s_hbwin[2]; hb_rc <= s_hbrc[2];
            end else if (hb_win != 16'd0) hb_win <= hb_win - 16'd1;
            if (h3[0] && d_old[0]) c_oa <= c_oa + 32'd1;
            if (h3[1] && d_old[1]) c_ob <= c_ob + 32'd1;
            if (push_a) c_fa <= c_fa + 32'd1;
            if (push_b) c_fb <= c_fb + 32'd1;
            if (d_gap[0] && h3[0]) c_gap <= c_gap + 32'd1 + 32'(d_gap[1] && h3[1]);
            else if (d_gap[1] && h3[1]) c_gap <= c_gap + 32'd1;
            if ((d_sess[0] && h3[0]) || (d_sess[1] && h3[1])) c_sess <= c_sess + 32'd1 + 32'((d_sess[0] && h3[0]) && (d_sess[1] && h3[1]));
            if (ova || ovb) c_ovf <= c_ovf + 32'd1 + 32'(ova && ovb);
            // order queue
            begin
                logic [3:0] w; logic [4:0] n; logic [3:0] r;
                w = of_wp; n = of_n; r = of_rp;
                if (can_pop && rword[72]) begin r = r + 4'd1; n = n - 5'd1; end
                if (push_a) begin of_ids[w] <= 1'b0; w = w + 4'd1; n = n + 5'd1; end
                if (push_b) begin of_ids[w] <= 1'b1; w = w + 4'd1; n = n + 5'd1; end
                of_wp <= w; of_n <= n; of_rp <= r;
            end
            // reader
            if (idle_c != 8'd0) idle_c <= idle_c - 8'd1;
            if (start) begin rd_busy <= 1'b1; rd_own <= of_front; end
            if (can_pop) begin
                o_v <= 1'b1; o_d <= rword[63:0]; o_keep <= rword[71:64]; o_eof <= rword[72]; o_sof <= rword[73]; o_err <= rword[74];
                if (rword[72]) begin rd_busy <= 1'b0; idle_c <= 8'(MIN_IDLE); end
            end
            if (clr_cnt) begin
                c_fa <= '0; c_fb <= '0; c_oa <= '0; c_ob <= '0; c_gap <= '0; c_sess <= '0; c_ovf <= '0;
            end
        end
    end
endmodule
