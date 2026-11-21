// udp_strip.sv: the adapter between mac64_rx and brief 110's MoldUDP64 receiver (brief 127).
//
// mac64_rx hands over a frame as 64-bit words, byte-aligned to lane 0, FCS bytes included, and reports the FCS verdict (m_end, m_fcs_ok, m_len) a few clocks AFTER the
// last word. This block checks the headers, takes the 42 header bytes off (the payload starts at byte 2 of word 5, so every payload word is a 2-byte realignment of two
// frame words), trims the FCS and any padding by the UDP length (not by the frame length: Ethernet pads short frames), and gives mold_rx its `s_*` words. The FCS verdict
// is NOT put on the last word (`s_err` of mold_rx): it is its own late strobe `v_v` / `v_bad`, so no payload word is delayed for it (docs/itch_integration.md section 3).
//
// Per frame, from word 0 (m_sof) on, in the order of the words:
//   word 0  destination MAC (our unicast address, or the multicast MAC of the group when the feed address is 224.0.0.0/4)
//   word 1  EtherType 0x0800, IPv4 version 4 and header length 5 (any other header length, and any IPv6 or VLAN frame, is dropped and counted)
//   word 2  IP total length, no fragment (MF or offset != 0), protocol 17
//   word 3,4 destination address = cfg_ip, UDP destination port = cfg_port, UDP length >= 9 and IP total length = UDP length + 20
//   from word 1 to 4 the ten 16-bit words of the IPv4 header are summed; the sum is folded and checked in the clocks before the first payload word is made
// A frame that fails a check is not forwarded (the first failing check is counted) and its verdict is swallowed. The UDP checksum is NOT checked: the frame check sequence
// protects the frame on this link, and whether a feed carries a UDP checksum is UNCONFIRMED (spec_notes).
// Output: each payload word one clock after the frame word that carries its last byte (a word whose last byte is in frame word n is at `s_*` in the clock after n);
// when the payload ends in the upper six bytes of a frame word, its last word follows that frame word by one clock too. `s_keep` is the low-contiguous mask of valid bytes
// of the last word (UDP length minus 8, modulo 8), s_sof on the first word, s_eof on the last. Words are not always contiguous (a bubble in mac64_rx's output stays).
// Verdict: one pulse `v_v` per FORWARDED frame, `v_bad` = cut by an error character, bad FCS, or shorter than its IP length says; it comes with mac64_rx's m_end
// (about 3 clocks after the last frame word), never before the frame's last payload word.
// Capture (CAP = 1): frames of IPv4 protocol 6 (TCP; our own orders coming back round a loop) keep their words 3 to 14 (bytes 24 to 119: IP checksum, addresses, TCP
// header, the OUCH payload and the FCS) in a ring of 8 slots of 12 words; `cap_*` is the read side. The first 24 bytes are classified (EtherType, version, protocol) but
// not kept.
module udp_strip #(
    parameter bit CAP = 1'b1
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clr_cnt,
    // configuration (static while frames arrive)
    input  logic        cfg_en,
    input  logic [47:0] cfg_mac,         // our MAC, first byte on the wire in bits 7:0
    input  logic [31:0] cfg_ip,          // destination IPv4 address of the feed (first octet in bits 31:24)
    input  logic [15:0] cfg_port,        // UDP destination port of the feed
    input  logic        cap_clr,         // pulse: forget the captured frames
    // from mac64_rx
    input  logic        rx_sop,
    input  logic        m_v,
    input  logic [63:0] m_d,
    input  logic        m_sof,
    input  logic        m_end,
    input  logic        m_fcs_ok,
    input  logic [15:0] m_len,
    input  logic        m_err,
    // to mold_rx
    output logic        s_v,
    output logic [63:0] s_d,
    output logic        s_sof,
    output logic        s_eof,
    output logic [7:0]  s_keep,
    // late verdict of the forwarded frame
    output logic        v_v,
    output logic        v_bad,
    // capture read side (asynchronous read of a register file; slot[2:0], entry[3:0]: entries 0 to 11 are words 3 to 14, entry 12 is the slot's meta word)
    input  logic [6:0]  cap_addr,
    output logic [63:0] cap_data,
    // counters: frames fwd drop_off drop_mac drop_type drop_frag drop_proto drop_dip drop_port drop_len drop_ipck bad_fcs cut orphan cap_n
    output logic [15*32-1:0] cnt
);
    // ------------------------------------------------------------------ frame bookkeeping (two frames can await a verdict)
    logic        cs, rs;                 // slot of the frame being received / of the oldest frame awaiting its verdict
    logic [1:0]  oc;                     // frames awaiting a verdict
    logic [1:0]  q_fwd, q_tcp, q_cap;
    logic [15:0] q_len [2];
    logic [2:0]  q_cslot [2];

    // ------------------------------------------------------------------ per word
    logic [3:0]  wi_r, wi_n;
    assign wi_n = m_sof ? 4'd0 : wi_r;
    logic [63:0] hold;
    logic [47:0] mc_mac;
    logic        ip_mc;
    assign ip_mc  = (cfg_ip[31:28] == 4'hE);
    assign mc_mac = {cfg_ip[7:0], cfg_ip[15:8], 1'b0, cfg_ip[22:16], 8'h5E, 8'h00, 8'h01};

    logic        mac_ok, et_ok, ver_ok, frag_bad, proto_udp, tcp_cur, hdr_ok, dip_hi_v;
    logic [15:0] iptot, udplen, dip_hi;
    logic [19:0] acc;
    logic [16:0] s1r;
    logic [15:0] rem;
    logic        started, dropped, lp;
    logic [2:0]  cslot_cur;
    logic [2:0]  cap_wp;

    function automatic logic [15:0] w16(input logic [7:0] hi, input logic [7:0] lo);
        w16 = {hi, lo};
    endfunction

    // header checks at word 4 (all the earlier words are in registers)
    logic        c_dip, c_port, c_len, c_mac, c_type, c_frag, c_proto;
    logic [15:0] c_udplen;
    always_comb begin
        c_udplen = w16(m_d[55:48], m_d[63:56]);
        c_mac    = mac_ok;
        c_type   = et_ok && ver_ok;
        c_frag   = !frag_bad;
        c_proto  = proto_udp;
        c_dip    = ({dip_hi, w16(m_d[7:0], m_d[15:8])} == cfg_ip);
        c_port   = (w16(m_d[39:32], m_d[47:40]) == cfg_port);
        c_len    = (c_udplen >= 16'd9) && (iptot == c_udplen + 16'd20);
    end

    // the IPv4 header checksum: fold the running sum two steps (registered once) and compare
    logic        ipck_ok;
    logic [16:0] s2;
    assign s2      = {1'b0, s1r[15:0]} + {16'd0, s1r[16]};
    assign ipck_ok = (s2[15:0] == 16'hFFFF);

    // ------------------------------------------------------------------ emission
    logic [15:0] rem_eff, rem_after;
    logic        attempt, can_emit, last_w;
    logic [7:0]  keep_w;
    always_comb begin
        rem_eff = (m_v && wi_n == 4'd5) ? (udplen - 16'd8) : rem;
        attempt = ((m_v && wi_n >= 4'd6) || lp) && rem_eff != 16'd0 && hdr_ok && !dropped;
        can_emit = attempt && (started || ipck_ok);
        last_w  = (rem_eff <= 16'd8);
        keep_w  = (rem_eff >= 16'd8) ? 8'hFF : ((8'd1 << rem_eff[3:0]) - 8'd1);
        rem_after = can_emit ? (last_w ? 16'd0 : rem_eff - 16'd8) : rem_eff;
    end

    logic [31:0] n_frames, n_fwd, n_off, n_mac, n_type, n_frag, n_proto, n_dip, n_port, n_len, n_ipck, n_badfcs, n_cut, n_orphan, n_cap;
    assign cnt = {n_cap, n_orphan, n_cut, n_badfcs, n_ipck, n_len, n_port, n_dip, n_proto, n_frag, n_type, n_mac, n_off, n_fwd, n_frames};

    // capture storage: 8 slots x 16 entries of 64 bits (entry 12 holds the meta word)
    logic [63:0] cap_mem [0:127];
    logic        cap_w_en;
    logic [6:0]  cap_w_addr;
    logic [63:0] cap_w_data;
    logic [17:0] cap_meta [0:7];
    logic        vd;
    assign vd = m_end || m_err;
    logic vd_pop;
    assign vd_pop = vd && (oc != 2'd0);
    if (CAP) begin : g_cap
        always_ff @(posedge clk) if (cap_w_en) cap_mem[cap_w_addr] <= m_d;
        logic [17:0] mt;
        assign mt = cap_meta[cap_addr[6:4]];
        assign cap_data = (cap_addr[3:0] == 4'd12) ? {46'd0, mt} : (cap_addr[3:0] < 4'd12) ? cap_mem[cap_addr] : 64'd0;
    end else begin : g_nocap
        assign cap_data = 64'd0;
    end
    assign cap_w_data = m_d;
    assign cap_w_en   = CAP && m_v && tcp_cur && wi_n >= 4'd3 && wi_n <= 4'd14 && !cap_clr;
    assign cap_w_addr = {(wi_n == 4'd3) ? cap_wp : cslot_cur, 4'(wi_n - 4'd3)};

    always_ff @(posedge clk) begin
        s_v <= 1'b0; s_sof <= 1'b0; s_eof <= 1'b0; v_v <= 1'b0; v_bad <= 1'b0;
        if (rst) begin
            cs <= 1'b0; rs <= 1'b1; oc <= '0; q_fwd <= '0; q_tcp <= '0; q_cap <= '0; q_len[0] <= '0; q_len[1] <= '0; q_cslot[0] <= '0; q_cslot[1] <= '0;
            for (int i = 0; i < 8; i++) cap_meta[i] <= '0;
            wi_r <= '0; hold <= '0; mac_ok <= 1'b0; et_ok <= 1'b0; ver_ok <= 1'b0; frag_bad <= 1'b0; proto_udp <= 1'b0; tcp_cur <= 1'b0; hdr_ok <= 1'b0;
            iptot <= '0; udplen <= '0; dip_hi <= '0; acc <= '0; s1r <= '0; rem <= '0; started <= 1'b0; dropped <= 1'b0; lp <= 1'b0; cslot_cur <= '0; cap_wp <= '0;
            s_d <= '0; s_keep <= '0;
            n_frames <= '0; n_fwd <= '0; n_off <= '0; n_mac <= '0; n_type <= '0; n_frag <= '0; n_proto <= '0; n_dip <= '0; n_port <= '0; n_len <= '0; n_ipck <= '0;
            n_badfcs <= '0; n_cut <= '0; n_orphan <= '0; n_cap <= '0;
        end else begin
            // ---- frame start: allocate the next slot; the verdict of the oldest frame (m_end or m_err) releases it
            if (rx_sop) begin
                n_frames <= n_frames + 32'd1;
                cs <= !cs;
                q_fwd[!cs] <= 1'b0; q_tcp[!cs] <= 1'b0; q_cap[!cs] <= 1'b0; q_len[!cs] <= '0;
            end
            if (vd && oc == 2'd0) n_orphan <= n_orphan + 32'd1;
            case ({rx_sop, vd_pop})
                2'b10: if (oc == 2'd2) begin rs <= !rs; n_orphan <= n_orphan + 32'd1; end else oc <= oc + 2'd1;   // a third frame: drop the oldest
                2'b01: oc <= oc - 2'd1;
                default: ;
            endcase
            if (vd_pop) begin
                rs <= !rs;
                if (q_fwd[rs]) begin
                    v_v <= 1'b1;
                    v_bad <= m_err || !m_fcs_ok || (m_len < q_len[rs]);
                    if (m_err) n_cut <= n_cut + 32'd1;
                    else if (!m_fcs_ok || (m_len < q_len[rs])) n_badfcs <= n_badfcs + 32'd1;
                end
                if (CAP && q_cap[rs]) cap_meta[q_cslot[rs]] <= {1'b1, !m_err && m_fcs_ok, m_len};
            end
            // ---- one frame word
            if (m_v) begin
                hold <= m_d;
                wi_r <= (wi_n == 4'd15) ? 4'd15 : wi_n + 4'd1;
                if (m_sof) begin started <= 1'b0; dropped <= 1'b0; lp <= 1'b0; rem <= '0; hdr_ok <= 1'b0; tcp_cur <= 1'b0; end
                case (wi_n)
                    4'd0: begin
                        mac_ok <= (m_d[47:0] == cfg_mac) || (ip_mc && m_d[47:0] == mc_mac);
                        acc <= '0;
                    end
                    4'd1: begin
                        et_ok <= (m_d[47:32] == 16'h0008); ver_ok <= (m_d[55:48] == 8'h45);
                        acc <= {4'd0, w16(m_d[55:48], m_d[63:56])};
                    end
                    4'd2: begin
                        iptot <= w16(m_d[7:0], m_d[15:8]);
                        frag_bad <= m_d[37] || (m_d[36:32] != 5'd0) || (m_d[47:40] != 8'd0);
                        proto_udp <= (m_d[63:56] == 8'h11);
                        tcp_cur <= et_ok && ver_ok && (m_d[63:56] == 8'h06);
                        q_len[cs] <= w16(m_d[7:0], m_d[15:8]) + 16'd18;
                        acc <= acc + {4'd0, w16(m_d[7:0], m_d[15:8])} + {4'd0, w16(m_d[23:16], m_d[31:24])} + {4'd0, w16(m_d[39:32], m_d[47:40])}
                                   + {4'd0, w16(m_d[55:48], m_d[63:56])};
                    end
                    4'd3: begin
                        dip_hi <= w16(m_d[55:48], m_d[63:56]);
                        acc <= acc + {4'd0, w16(m_d[7:0], m_d[15:8])} + {4'd0, w16(m_d[23:16], m_d[31:24])} + {4'd0, w16(m_d[39:32], m_d[47:40])}
                                   + {4'd0, w16(m_d[55:48], m_d[63:56])};
                        if (CAP && tcp_cur && !cap_clr) begin
                            cslot_cur <= cap_wp; cap_wp <= cap_wp + 3'd1; q_cap[cs] <= 1'b1; q_cslot[cs] <= cap_wp;
                            cap_meta[cap_wp] <= '0; n_cap <= n_cap + 32'd1;
                        end
                    end
                    4'd4: begin
                        acc <= acc + {4'd0, w16(m_d[7:0], m_d[15:8])};
                        udplen <= c_udplen;
                        if (!cfg_en) begin n_off <= n_off + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_mac)  begin n_mac <= n_mac + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_type) begin n_type <= n_type + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_frag) begin n_frag <= n_frag + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_proto) begin n_proto <= n_proto + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_dip)  begin n_dip <= n_dip + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_port) begin n_port <= n_port + 32'd1; hdr_ok <= 1'b0; end
                        else if (!c_len)  begin n_len <= n_len + 32'd1; hdr_ok <= 1'b0; end
                        else hdr_ok <= 1'b1;
                    end
                    default: ;
                endcase
            end
            s1r <= {1'b0, acc[15:0]} + {13'd0, acc[19:16]};
            // ---- the payload words
            lp <= 1'b0;
            if (attempt && !started && !ipck_ok) begin dropped <= 1'b1; n_ipck <= n_ipck + 32'd1; end
            if (can_emit) begin
                s_v <= 1'b1; s_d <= {m_d[15:0], hold[63:16]}; s_sof <= !started; s_eof <= last_w; s_keep <= keep_w;
                if (!started) begin started <= 1'b1; q_fwd[cs] <= 1'b1; n_fwd <= n_fwd + 32'd1; end
                rem <= rem_after;
            end else if (m_v && wi_n == 4'd5) rem <= udplen - 16'd8;
            if (m_v && wi_n >= 4'd5 && hdr_ok && rem_after != 16'd0 && rem_after <= 16'd6 && !dropped) lp <= 1'b1;
            if (clr_cnt) begin
                n_frames <= '0; n_fwd <= '0; n_off <= '0; n_mac <= '0; n_type <= '0; n_frag <= '0; n_proto <= '0; n_dip <= '0; n_port <= '0; n_len <= '0; n_ipck <= '0;
                n_badfcs <= '0; n_cut <= '0; n_orphan <= '0; n_cap <= '0;
            end
            if (cap_clr) begin
                cap_wp <= '0;
                for (int i = 0; i < 8; i++) cap_meta[i] <= '0;
            end
        end
    end
endmodule
