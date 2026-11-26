// itch_ref_pkg.sv: the reference model of the ITCH/OUCH trading path for the independent UVM bench (brief 170).
//
// Written in SystemVerilog from the public documents (Nasdaq TotalView-ITCH 5.0, MoldUDP64 V1.00, OUCH 5.0, SoupBinTCP 3.00; RFC 791, 793, 768, 1071; IEEE 802.3 frame
// check sequence) and from the DATASHEETS of the design (designs/b110_itch_ouch/docs/itch_ouch.md, designs/b96_kr260_10g/rm_gp_itch/docs/itch_integration.md). It was written without
// opening designs/b110_itch_ouch/model/*.py or the RTL's code (only the interface packages itch_pkg.sv and itch_pkg2.sv, for the counter and register indices, and the header comments of the
// RTL, which restate the datasheet). Nothing is imported from the design's own model. Every place where the datasheet is silent and the model had to take a reading, and where it
// agrees with the design's own model only because both take the same reading, is listed in README.md under "Shared assumptions".
//
// The model is a pure function of what was seen on the wires: the bytes of every received Ethernet frame (with its own CRC verdict), the configuration words and the command pulses.
package itch_ref_pkg;
  import itch_pkg::*;

  typedef byte unsigned bq_t[$];

  // ---------------------------------------------------------------------------------------------------------------- byte helpers
  function automatic int unsigned be16(ref bq_t b, input int o);
    return {b[o], b[o+1]};
  endfunction
  function automatic int unsigned be32(ref bq_t b, input int o);
    return {b[o], b[o+1], b[o+2], b[o+3]};
  endfunction
  function automatic longint unsigned be64(ref bq_t b, input int o);
    return {b[o], b[o+1], b[o+2], b[o+3], b[o+4], b[o+5], b[o+6], b[o+7]};
  endfunction
  function automatic void put_be(ref bq_t b, input longint unsigned v, input int n);
    for (int i = n - 1; i >= 0; i--) b.push_back(byte'((v >> (8 * i)) & 8'hFF));
  endfunction
  function automatic void put_str(ref bq_t b, input string s, input int n);       // left justified, space padded
    for (int i = 0; i < n; i++) b.push_back(i < s.len() ? byte'(s[i]) : 8'h20);
  endfunction

  // IEEE 802.3 frame check sequence: CRC-32, reflected polynomial 0xEDB88320, preset ones, final complement; the 32-bit result goes on the wire least significant byte first
  function automatic bit [31:0] crc32(ref bq_t b);
    bit [31:0] c;
    c = 32'hFFFF_FFFF;
    foreach (b[i]) begin
      c = c ^ {24'd0, b[i]};
      for (int k = 0; k < 8; k++) c = c[0] ? ((c >> 1) ^ 32'hEDB8_8320) : (c >> 1);
    end
    return ~c;
  endfunction

  // RFC 1071 Internet checksum over b[off +: len] (a header that carries its own checksum sums to 0xFFFF)
  function automatic bit [15:0] inet_sum(ref bq_t b, input int off, input int len);
    bit [31:0] s;
    s = 0;
    for (int i = 0; i < len; i += 2) s += {b[off+i], (i + 1 < len) ? b[off+i+1] : 8'h00};
    while (s >> 16) s = (s & 32'hFFFF) + (s >> 16);
    return s[15:0];
  endfunction

  function automatic string hex8(input int unsigned v);     // eight upper-case hexadecimal digits (%X would print lower case)
    string r, hx; r = ""; hx = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) r = {r, hx.substr((v >> (4 * i)) & 15, (v >> (4 * i)) & 15)};
    return r;
  endfunction

  // ---------------------------------------------------------------------------------------------------------------- configuration
  class itch_cfg;
    bit [47:0] my_mac, venue_mac;          // byte 0 of the address is bits 7:0
    bit [31:0] my_ip, venue_ip;            // first octet in bits 31:24
    bit [15:0] sport, port_order;
    bit [31:0] feed_ip;
    bit [15:0] feed_port;
    bit en, arm, kill, spec, halt, strict;
    bit [31:0] thr, qty, max_qty, max_pos, band, px_off, minqty;
    bit [7:0]  tif, display, capacity, ise, cross_t, custtype;
    bit [63:0] watch [4];                  // first character in bits 63:56
    bit [31:0] tcp_seq0, tcp_ack;
    function itch_cfg clone();
      itch_cfg c = new();
      c.my_mac = my_mac; c.venue_mac = venue_mac; c.my_ip = my_ip; c.venue_ip = venue_ip; c.sport = sport; c.port_order = port_order;
      c.feed_ip = feed_ip; c.feed_port = feed_port; c.en = en; c.arm = arm; c.kill = kill; c.spec = spec; c.halt = halt; c.strict = strict;
      c.thr = thr; c.qty = qty; c.max_qty = max_qty; c.max_pos = max_pos; c.band = band; c.px_off = px_off; c.minqty = minqty;
      c.tif = tif; c.display = display; c.capacity = capacity; c.ise = ise; c.cross_t = cross_t; c.custtype = custtype;
      for (int i = 0; i < 4; i++) c.watch[i] = watch[i];
      c.tcp_seq0 = tcp_seq0; c.tcp_ack = tcp_ack;
      return c;
    endfunction
    function void defaults();
      my_mac = {8'h5A, 8'h00, 8'h00, 8'h00, 8'h00, 8'h02};      // byte 0 = 02 (locally administered unicast)
      venue_mac = {8'hAB, 8'h00, 8'h00, 8'h00, 8'h00, 8'h02};
      my_ip = 32'hC0A8_3A0A;         // 192.168.58.10
      venue_ip = 32'hC0A8_3A0F;      // 192.168.58.15
      sport = 16'd5800; port_order = 16'd5801;
      feed_ip = 32'hC0A8_3A0A; feed_port = 16'd5810;
      en = 1; arm = 1; kill = 0; spec = 0; halt = 0; strict = 1;     // STRICT is the default (owner decision 31)
      thr = 32'd1_000_000; qty = 32'd100; max_qty = 32'd1000; max_pos = 32'd100_000; band = 32'd5_000; px_off = 32'd0; minqty = 32'd0;
      tif = "3"; display = "Y"; capacity = "P"; ise = "N"; cross_t = "N"; custtype = "N";
      watch[0] = "AAPL    "; watch[1] = "MSFT    "; watch[2] = "NVDA    "; watch[3] = "TSLA    ";
      tcp_seq0 = 32'd1000; tcp_ack = 32'd5000;
    endfunction
    // byte i of a 48-bit MAC address as it appears on the wire
    function byte unsigned mac_byte(bit [47:0] m, int i);
      return m[8*i +: 8];
    endfunction
    function bit [420:0] pack_cfg();      // the 96 design's configuration vector (421 bits); only the fields this path reads are meaningful
      bit [420:0] v;
      v = '0;
      v[47:0]    = my_mac;
      v[95:48]   = venue_mac;
      v[127:96]  = my_ip;
      v[159:128] = venue_ip;
      v[175:160] = sport;
      v[191:176] = 16'd5800;
      v[207:192] = port_order;
      v[223:208] = 16'd5802;
      return v;
    endfunction
  endclass

  // ---------------------------------------------------------------------------------------------------------------- frames in and orders out
  class in_frame_t;                         // one received Ethernet frame as the input monitor saw it
    bq_t   data;                            // destination MAC ... payload, FCS removed
    bit    fcs_ok;
    bit    lane4;
    longint unsigned c_start, c_end;        // clock numbers of the start block and of the terminate
  endclass

  class exp_order;                          // one order the model says the design started
    int unsigned num;                       // the OUCH UserRefNum
    bit [63:0]   sym;
    bit [31:0]   px;
    bit [31:0]   qty;
    int          klass;                     // 0 MUST appear with a good FCS; 1 MAY; 2 MUST NOT appear with a good FCS
    string       why;
    itch_cfg     c;                         // the configuration when the order fired
    longint unsigned c_frame_end;
    bit [31:0]   seq;                       // filled in by the scoreboard from the observed good frames
  endclass

  localparam int K_MUST = 0, K_MAY = 1, K_MUSTNOT = 2;
  localparam int LEVELS = 8, ORD_AW = 8, NINST = 4;
  localparam int NUS = 15;
  typedef struct { bit v; longint unsigned ref_; int inst; bit side; bit [31:0] px; bit [31:0] sh; } ord_t;
  typedef struct { bit v; bit [31:0] px; bit [31:0] sz; } lvl_t;

  // ---------------------------------------------------------------------------------------------------------------- the model
  class itch_model;
    itch_cfg cfg;
    int unsigned cnt [NC];
    int unsigned us  [NUS];                 // udp_strip counters: frames fwd drop_off drop_mac drop_type drop_frag drop_proto drop_dip drop_port drop_len drop_ipck bad_fcs
    exp_order    exp_q [$];
    // Mold state
    bit          sess_lock; bit [79:0] sess; bit seq_valid; longint unsigned exp_seq;
    bit          gap_flag, untrusted, eos_seen;
    // book
    ord_t        tab [1 << ORD_AW];
    lvl_t        lv [NINST][2][LEVELS];
    bit          loc_v [NINST]; bit [15:0] loc [NINST];
    bit          inexact [NINST];
    int unsigned pos [NINST];
    int unsigned next_ref;
    bit [7:0]    sys_code;
    // frame context for the classification of orders
    longint unsigned cur_stretch;
    int          cur_tail, cur_tail_e; bit cur_bad; int cur_fired; longint unsigned cur_c_start, cur_c_end;
    longint unsigned last_fire_end;
    string       log_q [$];
    // coverage hooks (the scoreboard forwards these to the coverage collector)
    string       ev_q [$];

    function new();
      cfg = new(); cfg.defaults();
      do_reset();
    endfunction

    function void ev(string s); ev_q.push_back(s); endfunction

    function void clear_counters();
      foreach (cnt[i]) cnt[i] = 0;
      foreach (us[i]) us[i] = 0;
    endfunction
    function void clear_flags();
      gap_flag = 0; untrusted = 0; eos_seen = 0; sess_lock = 0; seq_valid = 0;
    endfunction
    function void clear_book();
      foreach (tab[i]) tab[i].v = 0;
      for (int i = 0; i < NINST; i++) begin
        loc_v[i] = 0; inexact[i] = 0;
        for (int s = 0; s < 2; s++) for (int l = 0; l < LEVELS; l++) lv[i][s][l].v = 0;
      end
    endfunction
    function void do_reset();
      clear_counters(); clear_flags(); clear_book();
      for (int i = 0; i < NINST; i++) pos[i] = 0;
      next_ref = 1; sys_code = 0; last_fire_end = 0;
      exp_q.delete();
    endfunction
    function void cmd(int bits);            // the command bits of IT_CMD that act on this path
      if (bits[0]) clear_counters();
      if (bits[1]) clear_flags();
      if (bits[2]) clear_book();
      if (bits[3]) for (int i = 0; i < NINST; i++) pos[i] = 0;
      if (bits[4]) next_ref = 1;
    endfunction

    // ------------------------------------------------------------------------------------------------ ladders
    function int find_lvl(int inst, int side, bit [31:0] px);
      for (int l = 0; l < LEVELS; l++) if (lv[inst][side][l].v && lv[inst][side][l].px == px) return l;
      return -1;
    endfunction
    function int free_lvl(int inst, int side);
      for (int l = 0; l < LEVELS; l++) if (!lv[inst][side][l].v) return l;
      return -1;
    endfunction
    function bit best(int inst, int side, output bit [31:0] px);     // side 0 = bid (highest), 1 = ask (lowest)
      bit ok; ok = 0; px = 0;
      for (int l = 0; l < LEVELS; l++) if (lv[inst][side][l].v) begin
        if (!ok || (side == 0 && lv[inst][side][l].px > px) || (side == 1 && lv[inst][side][l].px < px)) px = lv[inst][side][l].px;
        ok = 1;
      end
      return ok;
    endfunction
    function void lvl_reduce(int inst, int side, bit [31:0] px, bit [31:0] sh);
      int l; l = find_lvl(inst, side, px);
      if (l < 0) begin cnt[C_LVMISS]++; return; end
      lv[inst][side][l].sz = lv[inst][side][l].sz - sh;
      if (lv[inst][side][l].sz == 0) lv[inst][side][l].v = 0;
    endfunction

    // an Add (or the new half of a Replace); returns 1 when the order was stored
    function bit book_add(int inst, bit side, longint unsigned r, bit [31:0] sh, bit [31:0] px);
      int idx, l;
      idx = int'(r & ((1 << ORD_AW) - 1));
      if (tab[idx].v) begin
        if (tab[idx].ref_ == r) begin cnt[C_ODUP]++; ev("odup"); end
        else begin cnt[C_OOVF]++; inexact[inst] = 1; ev("oovf"); end
        return 0;
      end
      l = find_lvl(inst, side, px);
      if (l < 0) begin
        l = free_lvl(inst, side);
        if (l < 0) begin
          // ladder full: the level is not added and the instrument becomes inexact, but the order IS kept in the order table (a later removal of it finds no level: lvmiss).
          // Shared-assumption note (README): the datasheet says "not added"; the reading that the table keeps it was taken after the first disagreement with the design.
          cnt[C_LVOVF]++; inexact[inst] = 1; ev("lvovf");
          tab[idx].v = 1; tab[idx].ref_ = r; tab[idx].inst = inst; tab[idx].side = side; tab[idx].px = px; tab[idx].sh = sh;
          return 1;
        end
        lv[inst][side][l].v = 1; lv[inst][side][l].px = px; lv[inst][side][l].sz = 0;
      end
      lv[inst][side][l].sz = lv[inst][side][l].sz + sh;
      tab[idx].v = 1; tab[idx].ref_ = r; tab[idx].inst = inst; tab[idx].side = side; tab[idx].px = px; tab[idx].sh = sh;
      return 1;
    endfunction

    function int lookup_inst(bit [15:0] l);
      for (int i = 0; i < NINST; i++) if (loc_v[i] && loc[i] == l) return i;
      return -1;
    endfunction

    // ------------------------------------------------------------------------------------------------ risk and the order
    function void candidate(int inst, bit [31:0] px);
      bit [31:0] opx, bid; bit bok; exp_order o; int unsigned q;
      cnt[C_CAND]++;
      opx = px + cfg.px_off;
      bok = best(inst, 0, bid);
      q = cfg.qty;
      if (!cfg.arm) begin cnt[C_REJ_ARM]++; ev("rej_arm"); return; end
      if (cfg.kill) begin cnt[C_REJ_KILL]++; ev("rej_kill"); return; end
      if (untrusted || (cfg.halt && gap_flag)) begin cnt[C_REJ_GAP]++; ev("rej_gap"); return; end
      if (inexact[inst]) begin cnt[C_REJ_STALE]++; ev("rej_stale"); return; end
      if (q == 0 || q > cfg.max_qty || q >= 1000000) begin cnt[C_REJ_SIZE]++; ev("rej_size"); return; end
      if (longint'(pos[inst]) + longint'(q) > longint'(cfg.max_pos)) begin cnt[C_REJ_POS]++; ev("rej_pos"); return; end
      if (!bok || longint'(opx) > longint'(bid) + longint'(cfg.band)) begin cnt[C_REJ_BAND]++; ev(bok ? "rej_band" : "rej_nobid"); return; end
      cnt[C_FIRE]++; pos[inst] += q;
      o = new();
      o.num = next_ref; next_ref++;
      o.c = cfg.clone();
      o.sym = cfg.watch[inst]; o.px = opx; o.qty = q; o.c_frame_end = cur_c_end;
      // how sure is the model that this order leaves with a good frame check sequence? (README, "Order classification")
      begin
        bit isolated; int tlo, thi;
        isolated = (cur_c_start >= last_fire_end + 50) && (cur_fired == 0);
        tlo = cfg.spec ? 118 : 158; thi = cfg.spec ? 136 : 176;
        if (cur_bad) begin
          if (cfg.strict) begin o.klass = K_MUSTNOT; o.why = "bad FCS, STRICT"; end
          else if (cur_tail <= tlo && isolated) begin o.klass = K_MUSTNOT; o.why = "bad FCS known before the last word"; end
          else begin o.klass = K_MAY; o.why = "bad FCS, verdict late or order queued"; end
        end else begin
          if (cur_stretch > 105) begin o.klass = K_MAY; o.why = "good frame with bubbles: the verdict's clock is not known from the byte count"; end
          else if (!cfg.strict) begin o.klass = isolated ? K_MUST : K_MAY; o.why = isolated ? "good frame, cut-through" : "cut-through, order may queue"; end
          else if (isolated && cur_tail <= tlo) begin o.klass = K_MUST; o.why = "good frame, STRICT, verdict known"; end
          else if (isolated && cur_tail >= thi) begin o.klass = K_MUSTNOT; o.why = "good frame, STRICT, verdict not yet known"; end
          else begin o.klass = K_MAY; o.why = "STRICT, near the window or queued"; end
        end
      end
      cur_fired++;
      exp_q.push_back(o);
      begin
        string tc, md;
        if (cur_tail <= (cfg.spec ? 118 : 158)) tc = "near"; else if (cur_tail >= (cfg.spec ? 136 : 176)) tc = "far"; else tc = "edge";
        md = cfg.strict ? "strict" : "cut";
        ev({"tail_", tc, "_", md});
      end
      if (cfg.spec) ev("fire_spec");
      if (cur_fired >= 3) ev("burst_3");
      ev(cfg.strict ? "fire_strict" : "fire_cut");
    endfunction

    // ------------------------------------------------------------------------------------------------ ITCH messages (TotalView-ITCH 5.0, section numbers in docs/spec_notes.md)
    function void itch_msg(ref bq_t m, input int n);
      byte unsigned t; int explen; bit known; bit [15:0] l; int inst; longint unsigned r, nr; bit [31:0] sh, px; byte unsigned sd; bit side;
      t = m[0]; known = 1;
      case (t)
        "S": explen = 12;  "R": explen = 39;  "A": explen = 36;  "F": explen = 40;  "E": explen = 31;
        "C": explen = 36;  "X": explen = 23;  "D": explen = 19;  "U": explen = 35;
        default: begin known = 0; explen = 0; end
      endcase
      if (!known) begin cnt[C_M_SKIP]++; ev("m_skip"); return; end
      if (n != explen) begin cnt[C_M_BAD]++; ev("m_badlen"); return; end
      case (t)
        "S": cnt[C_M_S]++;  "R": cnt[C_M_R]++;  "A": cnt[C_M_A]++;  "F": cnt[C_M_F]++;  "E": cnt[C_M_E]++;
        "C": cnt[C_M_C]++;  "X": cnt[C_M_X]++;  "D": cnt[C_M_D]++;  "U": cnt[C_M_U]++;
      endcase
      ev($sformatf("msg_%c", t));
      l = be16(m, 1);
      if (t == "S") begin sys_code = m[11]; return; end
      if (t == "R") begin
        longint unsigned nm; nm = be64(m, 11);
        for (int i = 0; i < NINST; i++) if (cfg.watch[i] == nm) begin loc_v[i] = 1; loc[i] = l; break; end
        return;
      end
      // validity rules of the design (datasheet): bad side letter, zero shares
      if (t == "A" || t == "F") begin
        sd = m[19]; sh = be32(m, 20);
        if ((sd != "B" && sd != "S") || sh == 0) begin cnt[C_M_BAD]++; ev("m_bad"); return; end
      end else if (t == "E" || t == "C" || t == "X") begin
        if (be32(m, 19) == 0) begin cnt[C_M_BAD]++; ev("m_bad"); return; end
      end else if (t == "U") begin
        if (be32(m, 27) == 0) begin cnt[C_M_BAD]++; ev("m_bad"); return; end
      end
      inst = lookup_inst(l);
      if (inst < 0) begin cnt[C_UNWATCH]++; ev("unwatch"); return; end
      case (t)
        "A", "F": begin
          bit st;
          r = be64(m, 11); side = (m[19] == "S"); sh = be32(m, 20); px = be32(m, 32);
          st = book_add(inst, side, r, sh, px);
          if (st && side && px != 0 && px <= cfg.thr) candidate(inst, px);
          ev(side ? "add_sell" : "add_buy");
        end
        "E", "C", "X": begin
          int idx;
          r = be64(m, 11); sh = be32(m, 19);
          idx = int'(r & ((1 << ORD_AW) - 1));
          if (!tab[idx].v || tab[idx].ref_ != r) begin cnt[C_OMISS]++; ev("omiss"); return; end
          if (sh > tab[idx].sh) begin
            cnt[C_OOVER]++; ev("oover");
            lvl_reduce(tab[idx].inst, tab[idx].side, tab[idx].px, tab[idx].sh);
            tab[idx].v = 0;
          end else begin
            lvl_reduce(tab[idx].inst, tab[idx].side, tab[idx].px, sh);
            tab[idx].sh = tab[idx].sh - sh;
            if (tab[idx].sh == 0) tab[idx].v = 0;
          end
        end
        "D": begin
          int idx;
          r = be64(m, 11);
          idx = int'(r & ((1 << ORD_AW) - 1));
          if (!tab[idx].v || tab[idx].ref_ != r) begin cnt[C_OMISS]++; ev("omiss"); return; end
          lvl_reduce(tab[idx].inst, tab[idx].side, tab[idx].px, tab[idx].sh);
          tab[idx].v = 0;
        end
        "U": begin
          int idx, oi; bit os;
          r = be64(m, 11); nr = be64(m, 19); sh = be32(m, 27); px = be32(m, 31);
          idx = int'(r & ((1 << ORD_AW) - 1));
          if (!tab[idx].v || tab[idx].ref_ != r) begin cnt[C_OMISS]++; ev("omiss"); return; end
          oi = tab[idx].inst; os = tab[idx].side;
          lvl_reduce(oi, os, tab[idx].px, tab[idx].sh);
          tab[idx].v = 0;
          void'(book_add(oi, os, nr, sh, px));            // a Replace never triggers an order
        end
      endcase
    endfunction

    // ------------------------------------------------------------------------------------------------ MoldUDP64 (V 1.00)
    function void mold(ref bq_t p, input bit bad_frame);
      int n; longint unsigned seq; int unsigned count; bit [79:0] s; int skip; int pos_i; int unsigned L; bq_t m;
      n = p.size();
      if (n < 20) begin cnt[C_SHORT]++; ev("short"); return; end
      s = '0; for (int i = 0; i < 10; i++) s = {s[71:0], p[i]};
      seq = be64(p, 10); count = be16(p, 18);
      if (!sess_lock) begin sess_lock = 1; sess = s; end
      else if (s != sess) begin cnt[C_SESS]++; ev("sess"); return; end
      if (!seq_valid) begin seq_valid = 1; exp_seq = seq; end
      if (count == 0 || count == 16'hFFFF) begin
        if (seq < exp_seq) begin cnt[C_DUP]++; ev("dup"); return; end
        cnt[C_PKT]++;
        if (count == 0) begin cnt[C_HB]++; ev("heartbeat"); end else begin cnt[C_EOS]++; eos_seen = 1; ev("eos"); end
        exp_seq = seq;
        return;
      end
      if (seq + count <= exp_seq) begin cnt[C_DUP]++; ev("dup"); return; end
      cnt[C_PKT]++;
      ev((count == 1 || count == 3 || count == 6) ? $sformatf("mpp_%0d", count) : "mpp_other");
      skip = 0;
      if (seq > exp_seq) begin cnt[C_GAP]++; cnt[C_MISSING] += int'(seq - exp_seq); gap_flag = 1; ev("gap"); end
      else if (seq < exp_seq) begin cnt[C_OVLP] += int'(exp_seq - seq); skip = int'(exp_seq - seq); ev("overlap"); end
      exp_seq = seq + count;
      pos_i = 20;
      for (int i = 0; i < int'(count); i++) begin
        if (pos_i + 2 > n) begin cnt[C_TRUNC]++; ev("trunc"); break; end
        L = be16(p, pos_i);
        if (L < 12) begin cnt[C_BADLEN]++; ev("badlen"); break; end
        if (pos_i + 2 + int'(L) > n) begin cnt[C_TRUNC]++; ev("trunc"); break; end
        if (i >= skip) begin
          cnt[C_MSG]++;
          m.delete();
          for (int k = 0; k < int'(L); k++) m.push_back(p[pos_i + 2 + k]);
          cur_tail = n - (pos_i + 2 + int'(L)); cur_tail_e = int'(cur_tail * cur_stretch / 100);
          itch_msg(m, int'(L));
        end
        pos_i += 2 + int'(L);
      end
    endfunction

    // ------------------------------------------------------------------------------------------------ one received frame (udp_strip's checks, then the payload)
    function void frame(in_frame_t f);
      int n, ihl_o, udp_len, ip_len; bit mc; bq_t pl; bq_t ipb;
      n = f.data.size();
      us[0]++;
      if (!cfg.en) begin us[2]++; ev("drop_off"); return; end
      if (n < 42) begin us[4]++; ev("drop_short"); return; end
      mc = (cfg.feed_ip[31:28] == 4'hE) && f.data[0] == 8'h01 && f.data[1] == 8'h00 && f.data[2] == 8'h5E;
      begin
        bit match; match = 1;
        for (int i = 0; i < 6; i++) if (f.data[i] != cfg.mac_byte(cfg.my_mac, i)) match = 0;
        if (!match && !mc) begin us[3]++; ev("drop_mac"); return; end
      end
      if (be16(f.data, 12) != 16'h0800 || f.data[14] != 8'h45) begin us[4]++; ev("drop_type"); return; end
      if ((f.data[20] & 8'h20) != 0 || ({f.data[20] & 8'h1F, f.data[21]}) != 0) begin us[5]++; ev("drop_frag"); return; end
      if (f.data[23] != 8'd17) begin us[6]++; ev("drop_proto"); return; end
      if (be32(f.data, 30) != cfg.feed_ip) begin us[7]++; ev("drop_dip"); return; end
      if (be16(f.data, 36) != cfg.feed_port) begin us[8]++; ev("drop_port"); return; end
      ip_len = be16(f.data, 16); udp_len = be16(f.data, 38);
      if (udp_len < 9 || udp_len != ip_len - 20) begin us[9]++; ev("drop_len"); return; end
      ipb.delete();
      for (int i = 0; i < 20; i++) ipb.push_back(f.data[14 + i]);
      if (inet_sum(ipb, 0, 20) != 16'hFFFF) begin us[10]++; ev("drop_ipck"); return; end
      us[1]++;
      pl.delete();
      for (int i = 0; i < udp_len - 8 && 42 + i < n; i++) pl.push_back(f.data[42 + i]);
      cur_stretch = (f.c_end - f.c_start + 1) * 100 / (((n + 12 + 7) / 8) + 1);
      if (cur_stretch < 100) cur_stretch = 100;
      cur_bad = !f.fcs_ok; cur_fired = 0; cur_c_start = f.c_start; cur_c_end = f.c_end; cur_tail = 0; cur_tail_e = 0;
      mold(pl, cur_bad);
      if (cur_fired > 0) last_fire_end = f.c_end;
      if (cur_bad) begin
        us[11]++; cnt[C_PKT_ERR]++; untrusted = 1; ev("bad_fcs");
        if (cur_fired > 0) ev("bad_fcs_with_order");
        // an order of an earlier good frame still in flight when this verdict arrives is poisoned too
        foreach (exp_q[i]) if (exp_q[i].klass == K_MUST && f.c_end <= exp_q[i].c_frame_end + 70) begin exp_q[i].klass = K_MAY; exp_q[i].why = {exp_q[i].why, " (a bad verdict followed within its flight)"}; end
      end
      ev("frame_fwd");
    endfunction

    // ------------------------------------------------------------------------------------------------ expected order frame (documented in itch_integration.md section 2 and spec_notes.md section 3)
    function bq_t order_frame(exp_order o, bit [31:0] seq);
      bq_t b, ip; bit [15:0] ck; bit [63:0] hex; string cl;
      b.delete();
      for (int i = 0; i < 6; i++) b.push_back(cfg.mac_byte(cfg.venue_mac, i));
      for (int i = 0; i < 6; i++) b.push_back(cfg.mac_byte(cfg.my_mac, i));
      put_be(b, 16'h0800, 2);
      ip.delete();
      ip.push_back(8'h45); ip.push_back(8'h00); put_be(ip, 99, 2); put_be(ip, 0, 2); put_be(ip, 16'h4000, 2); ip.push_back(8'd64); ip.push_back(8'd6); put_be(ip, 0, 2);
      put_be(ip, cfg.my_ip, 4); put_be(ip, cfg.venue_ip, 4);
      ck = ~inet_sum(ip, 0, 20);
      ip[10] = ck[15:8]; ip[11] = ck[7:0];
      foreach (ip[i]) b.push_back(ip[i]);
      put_be(b, cfg.sport, 2); put_be(b, cfg.port_order, 2); put_be(b, seq, 4); put_be(b, cfg.tcp_ack, 4);
      b.push_back(8'h50); b.push_back(8'h18); put_be(b, 16'hFFFF, 2); put_be(b, 0, 2); put_be(b, 0, 2);   // PSH+ACK, window, TCP checksum 0 (stand-in), urgent
      // SoupBinTCP 3.00 Unsequenced Data packet: length 57, type 'U', then the OUCH 5.0 Enter Order (56 bytes)
      put_be(b, 57, 2); b.push_back("U");
      b.push_back("O"); put_be(b, o.num, 4); b.push_back("B"); put_be(b, o.qty, 4);
      put_be(b, o.sym, 8); put_be(b, o.px, 8);
      b.push_back(cfg.tif); b.push_back(cfg.display); b.push_back(cfg.capacity); b.push_back(cfg.ise); b.push_back(cfg.cross_t);
      cl = {"FDA110", hex8(o.num)};
      for (int i = 0; i < 14; i++) b.push_back(byte'(cl[i]));
      put_be(b, 9, 2);
      b.push_back(8'd5); b.push_back(8'd3); put_be(b, cfg.minqty, 4);        // TagValue MinQty: length (tag + 4 value bytes), tag 3
      b.push_back(8'd2); b.push_back(8'd4); b.push_back(cfg.custtype);       // TagValue CustomerType: length 2, tag 4
      return b;
    endfunction

    // the names of the counters compared (timing dependent ones are left out: spec, abort, late_abort, rej_busy)
    function bit timing_dependent(int i);
      return (i == C_SPEC || i == C_ABORT || i == C_LATE_ABORT || i == C_REJ_BUSY);
    endfunction
  endclass
endpackage
