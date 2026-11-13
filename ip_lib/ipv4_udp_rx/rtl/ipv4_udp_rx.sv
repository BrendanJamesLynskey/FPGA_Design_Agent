// ipv4_udp_rx.sv: IPv4 and UDP receive with port demultiplexing (RFC 791, RFC 768, RFC 1071) (ip_lib, brief 63D).
// Byte-wide AXI-Stream in (Ethernet frames without the FCS) and out (UDP payloads).
//
// A frame is a datagram for us when: EtherType 0x0800; version 4 and IHL 5..15 (options are skipped); the header
// checksum is right; total length at least the header plus 8; not a fragment (MF = 0, offset 0); protocol 17; the
// destination is own_ip, or 255.255.255.255 with ACCEPT_BCAST, or a class D (multicast) address with ACCEPT_MCAST; the
// UDP length is 8..(total length - header); and its destination port is one of the enabled `ports` (the lowest index
// wins; it leaves on m_axis_tdest).
// The payload streams out as it arrives, one byte held back so that tlast can mark the last payload byte once the
// frame has ended (Ethernet padding after the datagram is dropped). On tlast, tuser = 1 when the datagram must be
// discarded: the frame was bad (s_axis_tuser), ended inside the datagram, or (CHECK_UDP = 1) a non-zero UDP checksum
// is wrong (pseudo-header of RFC 768 included). Header fields leave beside every payload byte (m_*). A datagram with
// no payload produces no output (ev_empty). The input stalls only while the output is stalled, and for one clock after
// each frame.

module ipv4_udp_rx #(
    parameter int N_PORTS      = 4,     // 1..8
    parameter int CHECK_UDP    = 1,     // 1: verify a non-zero UDP checksum
    parameter int ACCEPT_BCAST = 1,     // 1: accept 255.255.255.255
    parameter int ACCEPT_MCAST = 1      // 1: accept 224.0.0.0/4 (the MAC's filter chooses the groups)
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic [31:0]           own_ip,
    input  logic [N_PORTS*16-1:0] ports,        // port i in [16*i +: 16]
    input  logic [N_PORTS-1:0]    port_en,
    input  logic [7:0]            s_axis_tdata,
    input  logic                  s_axis_tvalid,
    output logic                  s_axis_tready,
    input  logic                  s_axis_tlast,
    input  logic                  s_axis_tuser,
    output logic [7:0]            m_axis_tdata,
    output logic                  m_axis_tvalid,
    input  logic                  m_axis_tready,
    output logic                  m_axis_tlast,
    output logic                  m_axis_tuser,     // on tlast: discard this datagram
    output logic [2:0]            m_axis_tdest,     // index of the matching port
    output logic [31:0]           m_src_ip,
    output logic [31:0]           m_dst_ip,
    output logic [15:0]           m_src_port,
    output logic [15:0]           m_dst_port,
    output logic [15:0]           m_len,            // payload bytes the UDP header announces
    output logic                  ev_ok,            // a datagram was passed on (tuser = 0)
    output logic                  ev_bad_ip,        // an IPv4 header failed its checks (version, IHL, checksum, length)
    output logic                  ev_bad_udp,       // a datagram for us was discarded (checksum, short frame, bad frame)
    output logic                  ev_no_port,       // a datagram for us to a port not in the table
    output logic                  ev_frag,          // a fragment (not reassembled)
    output logic                  ev_empty          // a datagram for us with no payload
);
    initial begin
        if (N_PORTS < 1 || N_PORTS > 8) $error("ipv4_udp_rx: N_PORTS must be in 1..8 (got %0d)", N_PORTS);
        if (CHECK_UDP != 0 && CHECK_UDP != 1) $error("ipv4_udp_rx: CHECK_UDP must be 0 or 1 (got %0d)", CHECK_UDP);
        if (ACCEPT_BCAST != 0 && ACCEPT_BCAST != 1) $error("ipv4_udp_rx: ACCEPT_BCAST must be 0 or 1 (got %0d)", ACCEPT_BCAST);
        if (ACCEPT_MCAST != 0 && ACCEPT_MCAST != 1) $error("ipv4_udp_rx: ACCEPT_MCAST must be 0 or 1 (got %0d)", ACCEPT_MCAST);
    end
    function automatic logic [15:0] fold(input logic [31:0] s);
        logic [16:0] t;
        t = {1'b0, s[31:16]} + {1'b0, s[15:0]};
        fold = t[15:0] + {15'd0, t[16]};
    endfunction

    logic        fin;                   // the clock after a frame's last byte: the verdict
    logic        take;                  // the output register is free this clock
    assign take = !m_axis_tvalid || m_axis_tready;
    assign s_axis_tready = !fin && take;
    logic        beat;
    assign beat = s_axis_tvalid && s_axis_tready;

    logic [15:0] k;                     // index of the next byte (saturates)
    logic [15:0] et, tl, ff, sport, dport, ulen, ucs;
    logic [7:0]  vi, proto;
    logic [31:0] src, dst;
    logic [31:0] ip_acc, u_acc;
    logic        f_bad;
    logic [15:0] u0;                    // the UDP header's index: 14 + 4 x IHL
    assign u0 = 16'd14 + {10'd0, vi[3:0], 2'b00};
    logic [15:0] wv;
    assign wv = k[0] ? {8'd0, s_axis_tdata} : {s_axis_tdata, 8'd0};
    logic [16:0] u_end;                 // index after the datagram's last byte
    assign u_end = {1'b0, u0} + {1'b0, ulen};

    // header checks, complete when the first payload byte arrives (k = u0 + 8)
    logic        hdr_ok, dst_ok, frag, port_hit;
    logic [2:0]  port_i;
    assign dst_ok = dst == own_ip || (ACCEPT_BCAST != 0 && dst == 32'hFFFF_FFFF) || (ACCEPT_MCAST != 0 && dst[31:28] == 4'hE);
    assign frag   = ff[13:0] != 14'd0;
    assign hdr_ok = et == 16'h0800 && vi[7:4] == 4'd4 && vi[3:0] >= 4'd5 && fold(ip_acc) == 16'hFFFF &&
                    tl >= {10'd0, vi[3:0], 2'b00};
    always_comb begin
        port_hit = 1'b0; port_i = '0;
        for (int i = N_PORTS - 1; i >= 0; i--)
            if (port_en[i] && ports[16*i +: 16] == dport) begin port_hit = 1'b1; port_i = 3'(i); end
    end
    logic        mine;                  // a UDP datagram for us (before the port and length checks)
    assign mine = hdr_ok && !frag && proto == 8'd17 && dst_ok;
    logic        len_ok;
    assign len_ok = ulen >= 16'd8 && ulen <= tl - {10'd0, vi[3:0], 2'b00};
    logic        fwd;                   // this frame's payload is being passed on
    logic        decided;               // the header verdict for this frame has been taken
    logic        h_v;                   // a payload byte is held back
    logic [7:0]  h_d;
    logic [2:0]  f_dest;

    logic in_ip, in_udp, in_pay;
    assign in_ip  = (k == 16'd14) || (k > 16'd14 && k < u0);
    assign in_udp = k >= u0 && (k < u0 + 16'd8 || {1'b0, k} < u_end);     // ulen is complete from u0 + 6
    assign in_pay = k >= u0 + 16'd8 && {1'b0, k} < u_end;

    // the UDP checksum's verdict: the datagram's words plus the pseudo-header (source, destination, 17, UDP length)
    logic [31:0] u_tot;
    assign u_tot = u_acc + {16'd0, src[31:16]} + {16'd0, src[15:0]} + {16'd0, dst[31:16]} + {16'd0, dst[15:0]} +
                   32'd17 + {16'd0, ulen};
    logic        u_bad;
    assign u_bad = f_bad || {1'b0, k} + 17'd1 < u_end || (CHECK_UDP != 0 && ucs != 16'd0 && fold(u_tot) != 16'hFFFF);

    always_ff @(posedge clk) begin
        ev_ok <= 1'b0; ev_bad_ip <= 1'b0; ev_bad_udp <= 1'b0; ev_no_port <= 1'b0; ev_frag <= 1'b0; ev_empty <= 1'b0;
        if (rst) begin
            fin <= 1'b0; k <= '0; et <= '0; tl <= '0; ff <= '0; sport <= '0; dport <= '0; ulen <= '0; ucs <= '0; vi <= '0;
            proto <= '0; src <= '0; dst <= '0; ip_acc <= '0; u_acc <= '0; f_bad <= 1'b0; fwd <= 1'b0; decided <= 1'b0;
            h_v <= 1'b0; h_d <= '0; f_dest <= '0;
            m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0; m_axis_tuser <= 1'b0; m_axis_tdest <= '0;
            m_src_ip <= '0; m_dst_ip <= '0; m_src_port <= '0; m_dst_port <= '0; m_len <= '0;
        end else begin
            if (m_axis_tvalid && m_axis_tready) m_axis_tvalid <= 1'b0;
            if (beat) begin
                if (k == 16'd0) begin ip_acc <= '0; u_acc <= '0; fwd <= 1'b0; decided <= 1'b0; f_bad <= 1'b0; end
                case (k)
                    16'd12, 16'd13: et    <= {et[7:0], s_axis_tdata};
                    16'd14:         vi    <= s_axis_tdata;
                    16'd16, 16'd17: tl    <= {tl[7:0], s_axis_tdata};
                    16'd20, 16'd21: ff    <= {ff[7:0], s_axis_tdata};
                    16'd23:         proto <= s_axis_tdata;
                    default: ;
                endcase
                if (k >= 16'd26 && k <= 16'd29) src <= {src[23:0], s_axis_tdata};
                if (k >= 16'd30 && k <= 16'd33) dst <= {dst[23:0], s_axis_tdata};
                if (k >= 16'd34) begin
                    if (k == u0 || k == u0 + 16'd1)               sport <= {sport[7:0], s_axis_tdata};
                    if (k == u0 + 16'd2 || k == u0 + 16'd3)       dport <= {dport[7:0], s_axis_tdata};
                    if (k == u0 + 16'd4 || k == u0 + 16'd5)       ulen  <= {ulen[7:0], s_axis_tdata};
                    if (k == u0 + 16'd6 || k == u0 + 16'd7)       ucs   <= {ucs[7:0], s_axis_tdata};
                end
                if (in_ip)  ip_acc <= ip_acc + 32'(wv);
                if (in_udp && k >= 16'd34) u_acc <= u_acc + 32'(wv);
                // the header verdict, at the first payload byte
                if (k == u0 + 16'd8 && k >= 16'd42 && !decided) begin
                    decided <= 1'b1;
                    fwd <= mine && len_ok && port_hit;
                    f_dest <= port_i;
                end
                if (in_pay && (k == u0 + 16'd8 ? (mine && len_ok && port_hit && !decided) : fwd)) begin
                    if (h_v) begin                                  // the held byte goes out
                        m_axis_tvalid <= 1'b1; m_axis_tdata <= h_d; m_axis_tlast <= 1'b0; m_axis_tuser <= 1'b0;
                        m_axis_tdest <= (k == u0 + 16'd8) ? port_i : f_dest;
                        m_src_ip <= src; m_dst_ip <= dst; m_src_port <= sport; m_dst_port <= dport;
                        m_len <= ulen - 16'd8;
                    end
                    h_v <= 1'b1; h_d <= s_axis_tdata;
                end
                if (s_axis_tlast) begin fin <= 1'b1; f_bad <= s_axis_tuser; end
                if (!s_axis_tlast && k != 16'hFFFF) k <= k + 16'd1;
            end
            if (fin && take) begin
                fin <= 1'b0;
                k <= '0;
                if (h_v) begin                                      // the last payload byte, with the verdict
                    m_axis_tvalid <= 1'b1; m_axis_tdata <= h_d; m_axis_tlast <= 1'b1; m_axis_tuser <= u_bad;
                    m_axis_tdest <= f_dest;
                    m_src_ip <= src; m_dst_ip <= dst; m_src_port <= sport; m_dst_port <= dport; m_len <= ulen - 16'd8;
                    h_v <= 1'b0;
                    if (u_bad) ev_bad_udp <= 1'b1; else ev_ok <= 1'b1;
                end else if (k >= 16'd33 && et == 16'h0800) begin      // no payload passed on: say why
                    if (!hdr_ok) ev_bad_ip <= 1'b1;
                    else if (frag && dst_ok) ev_frag <= 1'b1;
                    else if (mine && k + 16'd1 >= u0 + 16'd8 && len_ok && !port_hit) ev_no_port <= 1'b1;
                    else if (mine && k + 16'd1 >= u0 + 16'd8 && len_ok && ulen == 16'd8 && !u_bad) ev_empty <= 1'b1;
                    else if (mine) ev_bad_udp <= 1'b1;
                end
            end
        end
    end
endmodule
