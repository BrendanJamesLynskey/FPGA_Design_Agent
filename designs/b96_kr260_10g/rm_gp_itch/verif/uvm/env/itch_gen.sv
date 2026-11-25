// itch_gen.sv: message, packet and frame builders for the stimulus (brief 170). Written from the field tables of TotalView-ITCH 5.0, MoldUDP64 V1.00, RFC 791 and RFC 768; it shares no
// code with the design's model/proto.py. All integers big endian; alpha fields left justified and space padded.

typedef struct {
  bit [47:0] dst_mac;             // 0 = use the configuration's
  bit        use_dst_mac;
  int        ethertype;           // -1 = 0x0800
  int        ver_ihl;             // -1 = 0x45
  int        flags_frag;          // -1 = 0x4000 (DF); any other value is the 16-bit flags and fragment offset field
  int        proto;               // -1 = 17
  longint    dst_ip;              // -1 = the configuration's feed address
  int        dst_port;            // -1 = the configuration's feed port
  int        udp_len_delta;       // added to the correct UDP length
  bit        bad_ip_ck;
  int        pad_to;              // minimum frame size before the FCS (default 60)
} fopts_t;

class itch_gen;
  // ---- ITCH 5.0 messages (header: type, locate(2), tracking(2), timestamp(6))
  static function void hdr(ref bq_t m, input byte unsigned t, input int unsigned loc);
    m.delete(); m.push_back(t); put_be(m, loc, 2); put_be(m, 0, 2); put_be(m, 0, 6);
  endfunction
  static function bq_t msg_S(byte unsigned code);
    bq_t m; hdr(m, "S", 0); m.push_back(code); return m;
  endfunction
  static function bq_t msg_R(int unsigned loc, string stock);
    bq_t m; hdr(m, "R", loc); put_str(m, stock, 8);
    m.push_back("Q"); m.push_back("N"); put_be(m, 100, 4); m.push_back("N"); m.push_back("C"); put_str(m, "  ", 2); m.push_back("P"); m.push_back("N"); m.push_back("N"); m.push_back("1");
    m.push_back("N"); put_be(m, 0, 4); m.push_back("N");
    return m;
  endfunction
  static function bq_t msg_A(int unsigned loc, longint unsigned r, byte unsigned side, int unsigned sh, string stock, int unsigned px, bit mpid = 0);
    bq_t m; hdr(m, mpid ? "F" : "A", loc); put_be(m, r, 8); m.push_back(side); put_be(m, sh, 4); put_str(m, stock, 8); put_be(m, px, 4);
    if (mpid) put_str(m, "GSCO", 4);
    return m;
  endfunction
  static function bq_t msg_E(int unsigned loc, longint unsigned r, int unsigned sh, bit with_price = 0, int unsigned px = 0);
    bq_t m; hdr(m, with_price ? "C" : "E", loc); put_be(m, r, 8); put_be(m, sh, 4); put_be(m, 64'h1234, 8);
    if (with_price) begin m.push_back("Y"); put_be(m, px, 4); end
    return m;
  endfunction
  static function bq_t msg_X(int unsigned loc, longint unsigned r, int unsigned sh);
    bq_t m; hdr(m, "X", loc); put_be(m, r, 8); put_be(m, sh, 4); return m;
  endfunction
  static function bq_t msg_D(int unsigned loc, longint unsigned r);
    bq_t m; hdr(m, "D", loc); put_be(m, r, 8); return m;
  endfunction
  static function bq_t msg_U(int unsigned loc, longint unsigned r, longint unsigned nr, int unsigned sh, int unsigned px);
    bq_t m; hdr(m, "U", loc); put_be(m, r, 8); put_be(m, nr, 8); put_be(m, sh, 4); put_be(m, px, 4); return m;
  endfunction
  // another ITCH message type (skipped by the design) or a known type with a wrong length
  static function bq_t msg_other(byte unsigned t, int n);
    bq_t m; hdr(m, t, 1); while (m.size() < n) m.push_back(8'h00); return m;
  endfunction
  static function bq_t resize(bq_t m, int n);       // cut or zero-extend to n bytes (a known type with the wrong length)
    bq_t o; foreach (m[i]) if (i < n) o.push_back(m[i]); while (o.size() < n) o.push_back(8'h00); return o;
  endfunction

  // ---- MoldUDP64 packet: session(10) sequence(8) count(2), then blocks of length(2) + message
  static function bq_t mold(string session, longint unsigned seq, bq_t msgs[$], int count_override = -1);
    bq_t p;
    put_str(p, session, 10); put_be(p, seq, 8); put_be(p, (count_override >= 0) ? count_override : msgs.size(), 2);
    foreach (msgs[i]) begin put_be(p, msgs[i].size(), 2); foreach (msgs[i][k]) p.push_back(msgs[i][k]); end
    return p;
  endfunction
  static function bq_t mold_hb(string session, longint unsigned seq, bit eos = 0);
    bq_t p; put_str(p, session, 10); put_be(p, seq, 8); put_be(p, eos ? 16'hFFFF : 16'h0000, 2); return p;
  endfunction

  // ---- Ethernet / IPv4 / UDP frame (RFC 791, RFC 768); the FCS is added by the driver. The UDP checksum is sent as 0 ("not computed", RFC 768).
  static function fopts_t no_opts();
    fopts_t o;
    o.dst_mac = 0; o.use_dst_mac = 0; o.ethertype = -1; o.ver_ihl = -1; o.flags_frag = -1; o.proto = -1; o.dst_ip = -1; o.dst_port = -1; o.udp_len_delta = 0; o.bad_ip_ck = 0; o.pad_to = 60;
    return o;
  endfunction
  static function bq_t eth_frame(bq_t payload, itch_cfg c, fopts_t o);
    bq_t f, ip; bit [15:0] ck; int ulen;
    // destination = our MAC (the receiver), source = the venue's
    if (o.use_dst_mac) for (int i = 0; i < 6; i++) f.push_back(o.dst_mac[8*i +: 8]);
    else for (int i = 0; i < 6; i++) f.push_back(c.my_mac[8*i +: 8]);
    for (int i = 0; i < 6; i++) f.push_back(c.venue_mac[8*i +: 8]);
    put_be(f, (o.ethertype >= 0) ? o.ethertype : 16'h0800, 2);
    ulen = payload.size() + 8;
    ip.push_back((o.ver_ihl >= 0) ? byte'(o.ver_ihl) : 8'h45); ip.push_back(8'h00);
    put_be(ip, 20 + ulen, 2); put_be(ip, 16'h0001, 2);
    put_be(ip, (o.flags_frag >= 0) ? o.flags_frag : 16'h4000, 2);
    ip.push_back(8'd64); ip.push_back((o.proto >= 0) ? byte'(o.proto) : 8'd17); put_be(ip, 0, 2);
    put_be(ip, c.venue_ip, 4); put_be(ip, (o.dst_ip >= 0) ? o.dst_ip : c.feed_ip, 4);
    ck = ~inet_sum(ip, 0, 20);
    if (o.bad_ip_ck) ck = ck ^ 16'h0100;
    ip[10] = ck[15:8]; ip[11] = ck[7:0];
    foreach (ip[i]) f.push_back(ip[i]);
    put_be(f, 26000, 2); put_be(f, (o.dst_port >= 0) ? o.dst_port : c.feed_port, 2); put_be(f, ulen + o.udp_len_delta, 2); put_be(f, 0, 2);
    foreach (payload[i]) f.push_back(payload[i]);
    while (f.size() < o.pad_to) f.push_back(8'h00);
    return f;
  endfunction
  static function bq_t simple_frame(bq_t payload, itch_cfg c);
    return eth_frame(payload, c, no_opts());
  endfunction
endclass
