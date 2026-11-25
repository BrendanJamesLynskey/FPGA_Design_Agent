// trade64.sv: the mock trading decision of brief 58A, widened to the 64-bit receive path of brief 96 (receive clock domain).
//
// NOT the 58A core (that is byte wide and carries the book, eight rules, interlocks and ARP: designs/b96_kr260_10g/docs/design.md
// section 2.5). Same wire format (Bench Feed v1), one rule on the FIRST message of a frame: an ADD or MODIFY on the ask side whose price is
// at or below `thr` fires a buy order for that instrument. The price is complete in word 7 (bytes 56 to 63); the decision register
// `fire` is set the clock after that word leaves mac64_rx. Speculative: the frame's FCS verdict arrives later, at m_end; frames long
// enough for the verdict to arrive after the order has left (IPv4 total length above 60) are never acted on.
// Brief 169 (EARLY = 1): the decision runs on mac64_rx's early word (e_v/e_d/e_sof, the D inputs of m_v/m_d/m_sof) instead of the registered word: `fire`
// is one clock earlier. The end/verdict inputs (m_end, m_fcs_ok, m_len, m_err) are unchanged, and arrive at least as late after the last word as before.
// With EARLY = 0 (the default) m_v/m_d/m_sof are used and this file is brief 97C's lat_all3/rtl/trade64.sv.
module trade64 #(
    parameter bit EARLY = 1'b0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clr,                // clear the counters and the order number
    input  logic        seq_clr,            // clear the order number only (97C: a restart of either side, from the register domain)
    input  logic        m_v,
    input  logic [63:0] m_d,
    input  logic        m_sof,
    input  logic        e_v,                // brief 169: the word the MAC's registers will hold (EARLY = 1)
    input  logic [63:0] e_d,
    input  logic        e_sof,
    input  logic        m_end,
    input  logic        m_fcs_ok,
    input  logic [15:0] m_len,
    input  logic        m_err,
    // configuration (static)
    input  logic [47:0] my_mac, venue_mac,   // frames to us are fed to the rule; frames to the venue's address (our own orders coming back round a loop) are only classified
    input  logic [15:0] port_feed, port_order, port_probe,
    input  logic [31:0] thr,
    input  logic [31:0] qty,
    input  logic        arm, kill, trade_en,
    // outputs
    output logic        fire,               // one clock
    output logic [15:0] o_inst,
    output logic [31:0] o_price,
    output logic [31:0] o_qty,
    output logic [31:0] o_seq,              // order number (1, 2, ...)
    output logic        cls_feed, cls_order, cls_probe,   // one clock, at word 4 of a frame addressed to us
    output logic        verdict_v,          // a level: the frame that fired has finished; verdict_bad: its FCS failed or it was cut
    output logic        verdict_bad,
    output logic [31:0] verdict_seq,        // the order number the verdict belongs to (the verdict is never cleared: the transmitter compares this tag)
    output logic [31:0] n_frames, n_good, n_bad, n_fired, n_blocked, n_toolong,
    output logic [31:0] n_order_ok, n_order_bad   // 97C: returned order frames that matched what the rule decided / that did not
);
    logic        v_i, sof_i;
    logic [63:0] d_i;
    assign v_i = EARLY ? e_v : m_v;
    assign d_i = EARLY ? e_d : m_d;
    assign sof_i = EARLY ? e_sof : m_sof;
    logic [3:0]  wi;
    logic        mac_ok, ven_ok, ip_ok, udp_ok, hdr_ok, is_feed, spec_ok, in_frame, fired_this;
    logic [15:0] totlen, dport;
    logic [7:0]  mtype, mside;
    logic [15:0] inst_r;
    logic [15:0] ph;
    logic        side_ask;
    logic        decide, hit;
    logic [31:0] price;
    logic [3:0]  widx;
    // Order-content check (brief 97C), beside the decision and never in front of it: a frame classified as an order (UDP port `port_order`,
    // addressed to us or to the venue) is compared word by word, as it comes back, with what the rule decided (o_inst, o_price, o_qty, o_seq):
    // the template, number, type NEW_ORDER (0x10), side BUY (0), instrument, price, quantity and reference. It is counted ok only if every field
    // matched, the length is 66 bytes plus the FCS, the FCS was good and no error character cut it; anything else is counted bad.
    // Valid for one order in flight (o_* hold the latest decision): an order frame that returns after the next decision is counted bad.
    logic        chk_on, chk_miss;
    logic        miss5, miss6, miss7, miss8;
    assign miss5 = !(d_i[23:16] == 8'h42 && d_i[31:24] == 8'h46 && d_i[39:32] == 8'h01 && d_i[47:40] == 8'h01 && {d_i[55:48], d_i[63:56]} == o_seq[31:16]);
    assign miss6 = !({d_i[7:0], d_i[15:8]} == o_seq[15:0] && d_i[23:16] == 8'h10 && d_i[31:24] == 8'h00 && {d_i[39:32], d_i[47:40]} == o_inst
                     && {d_i[55:48], d_i[63:56]} == o_price[31:16]);
    assign miss7 = !({d_i[7:0], d_i[15:8]} == o_price[15:0] && {d_i[23:16], d_i[31:24], d_i[39:32], d_i[47:40]} == o_qty
                     && {d_i[55:48], d_i[63:56]} == o_seq[31:16]);
    assign miss8 = !({d_i[7:0], d_i[15:8]} == o_seq[15:0]);
    assign widx = sof_i ? 4'd0 : wi;
    assign price = {ph, d_i[7:0], d_i[15:8]};
    assign hit = is_feed && hdr_ok && spec_ok && (mtype == 8'h01 || mtype == 8'h02) && side_ask && price != 32'd0 && price <= thr;
    // Drive the event directly from the complete word-7 decision; order fields still register below.
    assign fire = !rst && v_i && (widx == 4'd7) && hit && arm && !kill && trade_en;
    always_ff @(posedge clk) begin
        cls_feed <= 1'b0; cls_order <= 1'b0; cls_probe <= 1'b0;
        if (rst) begin
            wi <= '0; mac_ok <= 1'b0; ven_ok <= 1'b0; ip_ok <= 1'b0; udp_ok <= 1'b0; hdr_ok <= 1'b0; is_feed <= 1'b0; spec_ok <= 1'b0; in_frame <= 1'b0;
            fired_this <= 1'b0; verdict_v <= 1'b0; verdict_bad <= 1'b0; verdict_seq <= '0; o_inst <= '0; o_price <= '0; o_qty <= '0;
            totlen <= '0; dport <= '0; mtype <= '0; mside <= '0; inst_r <= '0; ph <= '0; side_ask <= 1'b0;
            chk_on <= 1'b0; chk_miss <= 1'b0;
        end else begin
            if (v_i) begin
                wi <= (widx == 4'd15) ? 4'd15 : widx + 4'd1;
                case (widx)
                    4'd0: begin mac_ok <= (d_i[47:0] == my_mac); ven_ok <= (d_i[47:0] == venue_mac); in_frame <= 1'b1; is_feed <= 1'b0; hdr_ok <= 1'b0; end
                    4'd1: ip_ok <= (d_i[47:32] == 16'h0008) && (d_i[55:48] == 8'h45);
                    4'd2: begin totlen <= {d_i[7:0], d_i[15:8]}; udp_ok <= (d_i[63:56] == 8'h11); end
                    4'd4: begin
                        dport <= {d_i[39:32], d_i[47:40]};
                        if ((mac_ok || ven_ok) && ip_ok && udp_ok) begin
                            if ({d_i[39:32], d_i[47:40]} == port_order) begin cls_order <= 1'b1; chk_on <= 1'b1; chk_miss <= 1'b0; end
                            if ({d_i[39:32], d_i[47:40]} == port_probe) cls_probe <= 1'b1;
                            if ({d_i[39:32], d_i[47:40]} == port_feed && mac_ok) begin cls_feed <= 1'b1; is_feed <= 1'b1; end
                        end
                        spec_ok <= (totlen <= 16'd60);
                    end
                    4'd5: begin if (chk_on && miss5) chk_miss <= 1'b1; hdr_ok <= ({d_i[23:16], d_i[31:24]} == 16'h4246) && (d_i[39:32] == 8'h01) && (d_i[47:40] != 8'h00); end
                    4'd6: begin if (chk_on && miss6) chk_miss <= 1'b1; mtype <= d_i[23:16]; mside <= d_i[31:24]; inst_r <= {d_i[39:32], d_i[47:40]}; ph <= {d_i[55:48], d_i[63:56]}; side_ask <= d_i[24]; end
                    4'd8: if (chk_on && miss8) chk_miss <= 1'b1;
                    4'd7: begin
                        if (chk_on && miss7) chk_miss <= 1'b1;
                        if (is_feed && hdr_ok) begin
                            if (!spec_ok) n_toolong <= n_toolong + 32'd1;
                            if (hit) begin
                                if (arm && !kill && trade_en) begin
                                    fired_this <= 1'b1;
                                    o_inst <= inst_r; o_price <= price; o_qty <= qty; o_seq <= o_seq + 32'd1; n_fired <= n_fired + 32'd1;
                                end else n_blocked <= n_blocked + 32'd1;
                            end
                        end
                    end
                    default: ;
                endcase
            end
            if (m_end || m_err) begin
                in_frame <= 1'b0;
                if (chk_on) begin
                    chk_on <= 1'b0;
                    if (m_end && !m_err && m_fcs_ok && m_len == 16'd70 && !chk_miss) n_order_ok <= n_order_ok + 32'd1;
                    else n_order_bad <= n_order_bad + 32'd1;
                end
                if (m_end) begin n_frames <= n_frames + 32'd1; if (m_fcs_ok) n_good <= n_good + 32'd1; else n_bad <= n_bad + 32'd1; end
                if (fired_this) begin verdict_v <= 1'b1; verdict_seq <= o_seq; verdict_bad <= m_err || !m_fcs_ok || (m_len != totlen + 16'd18); fired_this <= 1'b0; end
            end
        end
        if (clr) begin n_frames <= '0; n_good <= '0; n_bad <= '0; n_fired <= '0; n_blocked <= '0; n_toolong <= '0; n_order_ok <= '0; n_order_bad <= '0; end
        // the order number restarts with the counters, and with a restart of either side (97C): the transmit side's expectation restarts with it
        if (clr || seq_clr || rst) o_seq <= '0;
    end
    initial begin n_frames = '0; n_good = '0; n_bad = '0; n_fired = '0; n_blocked = '0; n_toolong = '0; n_order_ok = '0; n_order_bad = '0; o_seq = '0; end
endmodule
