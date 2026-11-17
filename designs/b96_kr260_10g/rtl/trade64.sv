// trade64.sv: the mock trading decision of brief 58A, widened to the 64-bit receive path of brief 96 (receive clock domain).
//
// NOT the 58A core (that is byte wide and carries the book, eight rules, interlocks and ARP: designs/b96_kr260_10g/docs/design.md
// section 2.5). Same wire format (Bench Feed v1), one rule on the FIRST message of a frame: an ADD or MODIFY on the ask side whose price is
// at or below `thr` fires a buy order for that instrument. The price is complete in word 7 (bytes 56 to 63); the decision register
// `fire` is set the clock after that word leaves mac64_rx. Speculative: the frame's FCS verdict arrives later, at m_end; frames long
// enough for the verdict to arrive after the order has left (IPv4 total length above 60) are never acted on.
module trade64 (
    input  logic        clk,
    input  logic        rst,
    input  logic        clr,                // clear the counters and the order number
    input  logic        m_v,
    input  logic [63:0] m_d,
    input  logic        m_sof,
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
    output logic [31:0] n_frames, n_good, n_bad, n_fired, n_blocked, n_toolong
);
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
    assign widx = m_sof ? 4'd0 : wi;
    assign price = {ph, m_d[7:0], m_d[15:8]};
    assign hit = is_feed && hdr_ok && spec_ok && (mtype == 8'h01 || mtype == 8'h02) && side_ask && price != 32'd0 && price <= thr;
    always_ff @(posedge clk) begin
        fire <= 1'b0; cls_feed <= 1'b0; cls_order <= 1'b0; cls_probe <= 1'b0;
        if (rst) begin
            wi <= '0; mac_ok <= 1'b0; ven_ok <= 1'b0; ip_ok <= 1'b0; udp_ok <= 1'b0; hdr_ok <= 1'b0; is_feed <= 1'b0; spec_ok <= 1'b0; in_frame <= 1'b0;
            fired_this <= 1'b0; verdict_v <= 1'b0; verdict_bad <= 1'b0; verdict_seq <= '0; o_inst <= '0; o_price <= '0; o_qty <= '0;
            totlen <= '0; dport <= '0; mtype <= '0; mside <= '0; inst_r <= '0; ph <= '0; side_ask <= 1'b0;
        end else begin
            if (m_v) begin
                wi <= (widx == 4'd15) ? 4'd15 : widx + 4'd1;
                case (widx)
                    4'd0: begin mac_ok <= (m_d[47:0] == my_mac); ven_ok <= (m_d[47:0] == venue_mac); in_frame <= 1'b1; is_feed <= 1'b0; hdr_ok <= 1'b0; end
                    4'd1: ip_ok <= (m_d[47:32] == 16'h0008) && (m_d[55:48] == 8'h45);
                    4'd2: begin totlen <= {m_d[7:0], m_d[15:8]}; udp_ok <= (m_d[63:56] == 8'h11); end
                    4'd4: begin
                        dport <= {m_d[39:32], m_d[47:40]};
                        if ((mac_ok || ven_ok) && ip_ok && udp_ok) begin
                            if ({m_d[39:32], m_d[47:40]} == port_order) cls_order <= 1'b1;
                            if ({m_d[39:32], m_d[47:40]} == port_probe) cls_probe <= 1'b1;
                            if ({m_d[39:32], m_d[47:40]} == port_feed && mac_ok) begin cls_feed <= 1'b1; is_feed <= 1'b1; end
                        end
                        spec_ok <= (totlen <= 16'd60);
                    end
                    4'd5: hdr_ok <= ({m_d[23:16], m_d[31:24]} == 16'h4246) && (m_d[39:32] == 8'h01) && (m_d[47:40] != 8'h00);
                    4'd6: begin mtype <= m_d[23:16]; mside <= m_d[31:24]; inst_r <= {m_d[39:32], m_d[47:40]}; ph <= {m_d[55:48], m_d[63:56]}; side_ask <= m_d[24]; end
                    4'd7: begin
                        if (is_feed && hdr_ok) begin
                            if (!spec_ok) n_toolong <= n_toolong + 32'd1;
                            if (hit) begin
                                if (arm && !kill && trade_en) begin
                                    fire <= 1'b1; fired_this <= 1'b1;
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
                if (m_end) begin n_frames <= n_frames + 32'd1; if (m_fcs_ok) n_good <= n_good + 32'd1; else n_bad <= n_bad + 32'd1; end
                if (fired_this) begin verdict_v <= 1'b1; verdict_seq <= o_seq; verdict_bad <= m_err || !m_fcs_ok || (m_len != totlen + 16'd18); fired_this <= 1'b0; end
            end
        end
        if (clr) begin n_frames <= '0; n_good <= '0; n_bad <= '0; n_fired <= '0; n_blocked <= '0; n_toolong <= '0; o_seq <= '0; end
    end
    initial begin n_frames = '0; n_good = '0; n_bad = '0; n_fired = '0; n_blocked = '0; n_toolong = '0; o_seq = '0; end
endmodule
