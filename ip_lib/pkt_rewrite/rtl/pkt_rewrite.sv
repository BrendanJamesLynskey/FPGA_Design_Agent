// pkt_rewrite.sv: apply a match-action result to a packet as it streams: forward/drop, MAC rewrite, VLAN push, pop
// or VID rewrite, TTL / hop-limit decrement, IPv4 destination rewrite, with the IPv4 header checksum and the
// TCP/UDP checksum updated incrementally (RFC 1624, equation 3: HC' = ~(~HC + ~m + m')).
//
// Per packet, one meta word {hdr (pkt_parser layout), action} is taken with the packet's first byte. Action layout
// (bit 0 first; flow/net/model.py ACT_FIELDS is the reference):
//   [0] drop, [4:1] port, [7:5] queue, [8] set_dmac, [56:9] dmac, [57] set_smac, [105:58] smac, [106] dec_ttl,
//   [107] set_vid, [119:108] vid, [120] push_vlan (TPID 0x8100, PCP 0), [121] pop_vlan (outer tag), [122] set_dip,
//   [154:123] dip (IPv4 only)
// A packet whose TTL / hop limit is 0 or 1 with dec_ttl set is dropped (ev_ttl_drop), as a router must (RFC 791).
// set_dip applies to IPv4 without version or IHL errors; the L4 checksum is updated when the parser found the ports
// (not a non-first fragment); a UDP checksum of 0 (none) stays 0, and a computed 0 is sent as 0xFFFF (RFC 768).
// set_vid rewrites the outermost tag left after pop/push.
//
// Output: m_axis with tdest = {queue, port}. The stream lags by two bytes (a two-byte window lets the checksum's high
// byte be patched when its low byte arrives); a push costs four clocks of input stall. One byte a clock otherwise.

module pkt_rewrite (
    input  logic         clk,
    input  logic         rst,
    input  logic [7:0]   s_axis_tdata,
    input  logic         s_axis_tvalid,
    output logic         s_axis_tready,
    input  logic         s_axis_tlast,
    input  logic         s_axis_tuser,
    input  logic [479:0] s_meta_hdr,
    input  logic [159:0] s_meta_act,
    input  logic         s_meta_tvalid,
    output logic         s_meta_tready,
    output logic [7:0]   m_axis_tdata,
    output logic         m_axis_tvalid,
    input  logic         m_axis_tready,
    output logic         m_axis_tlast,
    output logic         m_axis_tuser,
    output logic [6:0]   m_axis_tdest,
    output logic         ev_drop,
    output logic         ev_ttl_drop
);
    // ---- header fields (pkt_parser layout) ----
    function automatic logic [15:0] oc_add(input logic [15:0] a, input logic [15:0] b);
        logic [16:0] s;
        s = {1'b0, a} + {1'b0, b};
        return s[15:0] + {15'd0, s[16]};
    endfunction

    logic [15:0] h_flags;
    logic [7:0]  h_proto, h_ttl, h_l3off, h_l4off;
    logic [127:0] h_dst;
    always_comb begin
        h_proto = s_meta_hdr[335:328];
        h_ttl   = s_meta_hdr[327:320];
        h_dst   = s_meta_hdr[191:64];
        h_l3off = s_meta_hdr[31:24];
        h_l4off = s_meta_hdr[23:16];
        h_flags = s_meta_hdr[15:0];
    end

    // ---- per-packet registers (taken with the first byte) ----
    logic        active;                      // a packet is in progress, its meta taken
    logic        p_drop, p_dmac_en, p_smac_en, p_ttl_en, p_vid_en, p_push, p_pop, p_dip_en, p_l4_en, p_udp;
    logic [47:0] p_dmac, p_smac;
    logic [11:0] p_vid;
    logic [31:0] p_dip;
    logic [6:0]  p_dest;
    logic [7:0]  p_l3, p_l4, p_ttlpos, p_newttl;
    logic [1:0]  p_vlan_n;
    logic        p_v4;
    logic [15:0] p_dip_d, p_ttl_d;            // ones'-complement deltas: sum of (~m + m') for the changed words
    logic [10:0] pos;                         // input byte index
    logic [2:0]  ins;                         // pushed bytes emitted (0..4)

    // ---- decode the meta word for the packet starting now ----
    logic        n_v4, n_v6, n_l4, n_badv4, n_ttl_en, n_dip_en, n_expire;
    logic [159:0] a;
    always_comb begin
        a        = s_meta_act;
        n_v4     = h_flags[2];
        n_v6     = h_flags[3];
        n_l4     = h_flags[6];
        n_badv4  = h_flags[8] || h_flags[9];
        n_ttl_en = a[106] && ((n_v4 && !n_badv4) || (n_v6 && !h_flags[9]));
        n_expire = n_ttl_en && (h_ttl <= 8'd1);
        n_dip_en = a[122] && n_v4 && !n_badv4;
    end

    // two-byte window (w1 older) in front of the output register
    logic       w0_v, w1_v, w0_l, w1_l, w0_u, w1_u;
    logic [7:0] w0_d, w1_d;
    logic [6:0] w0_t, w1_t;

    // ---- byte producer ----
    logic       pv;                           // produce a byte this clock
    logic       take;                         // accept the input byte this clock
    logic [7:0] pb;
    logic       skip, inserting, first;
    logic       out_free;

    assign out_free = !m_axis_tvalid || m_axis_tready;
    assign first    = s_axis_tvalid && !active;

    always_comb begin
        inserting = active && p_push && !p_drop && pos == 11'd12 && ins != 3'd4;
        skip      = active && (p_drop || (p_pop && p_vlan_n != 2'd0 && pos >= 11'd12 && pos < 11'd16));
        // first byte: needs the meta word
        s_meta_tready = first && out_free;
        take  = out_free && s_axis_tvalid && (active || s_meta_tvalid) && !inserting;
        s_axis_tready = take;
        pv    = out_free && ((inserting) || (take && !skip && !(first && (a[0] || n_expire))));
        // the byte: inserted tag, or the input byte with its rewrites
        pb = s_axis_tdata;
        if (inserting) begin
            case (ins)
                3'd0: pb = 8'h81;
                3'd1: pb = 8'h00;
                3'd2: pb = {4'h0, p_vid_en ? p_vid[11:8] : 4'h0};
                default: pb = p_vid_en ? p_vid[7:0] : 8'h00;
            endcase
        end else if (!active) begin
            if (a[8]) pb = a[56:49];          // byte 0 of a new packet: dmac[47:40]
        end else begin
            if (p_dmac_en && pos < 11'd6)                        pb = p_dmac[8 * (5 - pos[2:0]) +: 8];
            if (p_smac_en && pos >= 11'd6 && pos < 11'd12)       pb = p_smac[8 * (11 - pos[3:0]) +: 8];
            if (p_vid_en && !p_push) begin
                // the outermost tag left: the first tag, or the second when the first was popped
                if (!p_pop && p_vlan_n != 2'd0 && pos == 11'd14)  pb = {s_axis_tdata[7:4], p_vid[11:8]};
                if (!p_pop && p_vlan_n != 2'd0 && pos == 11'd15)  pb = p_vid[7:0];
                if (p_pop && p_vlan_n == 2'd2 && pos == 11'd18)   pb = {s_axis_tdata[7:4], p_vid[11:8]};
                if (p_pop && p_vlan_n == 2'd2 && pos == 11'd19)   pb = p_vid[7:0];
            end
            if (p_ttl_en && pos == {3'd0, p_ttlpos})             pb = p_newttl;
            if (p_dip_en && pos >= {3'd0, p_l3} + 11'd16 && pos < {3'd0, p_l3} + 11'd20)
                pb = p_dip[8 * (3 - (pos - {3'd0, p_l3} - 11'd16)) +: 8];
        end
    end

    // checksum patch: the low byte of a checksum arrives now; the high byte is in w0
    logic        ipck_lo, l4ck_lo;
    logic [15:0] old_ck, new_ip, new_l4, l4_tmp;
    always_comb begin
        ipck_lo = active && p_v4 && (p_ttl_en || p_dip_en) && pos == {3'd0, p_l3} + 11'd11;
        l4ck_lo = active && p_l4_en && pos == {3'd0, p_l4} + (p_udp ? 11'd7 : 11'd17);
        old_ck  = {w0_d, s_axis_tdata};
        new_ip  = ~oc_add(oc_add(~old_ck, p_ttl_d), p_dip_d);
        l4_tmp  = ~oc_add(~old_ck, p_dip_d);
        new_l4  = (p_udp && old_ck == 16'h0000) ? 16'h0000 : ((p_udp && l4_tmp == 16'h0000) ? 16'hFFFF : l4_tmp);
    end

    // ---- two-byte window and output register ----
    logic       drain;
    // drain when no byte is produced and the newest byte in the window ends a packet
    assign drain = !pv && out_free && ((w0_v && w0_l) || (!w0_v && w1_v && w1_l));

    always_ff @(posedge clk) begin
        ev_drop <= 1'b0; ev_ttl_drop <= 1'b0;
        if (m_axis_tready) m_axis_tvalid <= 1'b0;
        if (rst) begin
            active <= 1'b0; pos <= '0; ins <= '0; w0_v <= 1'b0; w1_v <= 1'b0; m_axis_tvalid <= 1'b0;
            m_axis_tdata <= '0; m_axis_tlast <= 1'b0; m_axis_tuser <= 1'b0; m_axis_tdest <= '0;
            {p_drop, p_dmac_en, p_smac_en, p_ttl_en, p_vid_en, p_push, p_pop, p_dip_en, p_l4_en, p_udp, p_v4} <= '0;
            p_dmac <= '0; p_smac <= '0; p_vid <= '0; p_dip <= '0; p_dest <= '0; p_l3 <= '0; p_l4 <= '0;
            p_ttlpos <= '0; p_newttl <= '0; p_vlan_n <= '0; p_dip_d <= '0; p_ttl_d <= '0;
            w0_d <= '0; w1_d <= '0; w0_l <= 1'b0; w1_l <= 1'b0; w0_u <= 1'b0; w1_u <= 1'b0; w0_t <= '0; w1_t <= '0;
        end else begin
            // per-packet state
            if (take && first) begin
                active    <= !s_axis_tlast;
                p_drop    <= a[0] || n_expire;
                ev_drop   <= a[0] || n_expire;
                ev_ttl_drop <= n_expire && !a[0];
                p_dest    <= {a[7:5], a[4:1]};
                p_dmac_en <= a[8];  p_dmac <= a[56:9];
                p_smac_en <= a[57]; p_smac <= a[105:58];
                p_ttl_en  <= n_ttl_en;
                p_ttlpos  <= h_l3off + (n_v4 ? 8'd8 : 8'd7);
                p_newttl  <= h_ttl - 8'd1;
                p_vid_en  <= a[107]; p_vid <= a[119:108];
                p_push    <= a[120];
                p_pop     <= a[121];
                p_vlan_n  <= h_flags[1:0];
                p_dip_en  <= n_dip_en; p_dip <= a[154:123];
                p_l4_en   <= n_dip_en && n_l4;
                p_udp     <= h_flags[4];
                p_v4      <= n_v4 && !n_badv4;
                p_l3      <= h_l3off; p_l4 <= h_l4off;
                // deltas, RFC 1624: sum of (~old + new) over the changed 16-bit words
                p_ttl_d   <= (n_ttl_en && n_v4) ? oc_add(~{h_ttl, h_proto}, {h_ttl - 8'd1, h_proto}) : 16'h0000;
                p_dip_d   <= n_dip_en ? oc_add(oc_add(~h_dst[31:16], a[154:139]), oc_add(~h_dst[15:0], a[138:123]))
                                      : 16'h0000;
                pos <= s_axis_tlast ? 11'd0 : 11'd1;
                ins <= '0;
            end else if (take) begin
                pos <= pos + 11'd1;
                if (s_axis_tlast) active <= 1'b0;
            end
            if (inserting && out_free) ins <= ins + 3'd1;

            // window shift
            if (pv) begin
                if (w1_v) begin
                    m_axis_tvalid <= 1'b1; m_axis_tdata <= w1_d; m_axis_tlast <= w1_l; m_axis_tuser <= w1_u;
                    m_axis_tdest <= w1_t;
                end
                w1_v <= w0_v; w1_d <= w0_d; w1_l <= w0_l; w1_u <= w0_u; w1_t <= w0_t;
                w0_v <= 1'b1; w0_d <= pb; w0_l <= !inserting && s_axis_tlast;
                w0_u <= !inserting && s_axis_tlast && s_axis_tuser;
                w0_t <= first ? {a[7:5], a[4:1]} : p_dest;
                if (!inserting && ipck_lo) begin w1_d <= new_ip[15:8]; w0_d <= new_ip[7:0]; end
                if (!inserting && l4ck_lo) begin w1_d <= new_l4[15:8]; w0_d <= new_l4[7:0]; end
            end else if (take && skip && !p_drop && s_axis_tlast) begin
                // the packet ends on a popped byte: its last produced byte (in w0) ends it
                w0_l <= 1'b1; w0_u <= s_axis_tuser;
            end else if (drain) begin
                if (w1_v) begin
                    m_axis_tvalid <= 1'b1; m_axis_tdata <= w1_d; m_axis_tlast <= w1_l; m_axis_tuser <= w1_u;
                    m_axis_tdest <= w1_t;
                end
                w1_v <= w0_v; w1_d <= w0_d; w1_l <= w0_l; w1_u <= w0_u; w1_t <= w0_t;
                w0_v <= 1'b0;
            end
        end
    end
endmodule
