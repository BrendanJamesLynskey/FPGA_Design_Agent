// pcs_ref_pkg.sv: the reference models of the UVM bench for the b96 PCS and MAC (brief 112). No UVM in here, and nothing imported from the RTL
// package b96_pkg: the block tables, the scrambler and the CRC are written again, bit by bit, from model/pcs.py (itself written from the
// IEEE 802.3 clause 49 block formats), so an error shared by the RTL's transmit and receive halves is still caught.
//   ref_tx_pcs  one step() per clock edge: XGMII word in, 64-bit GT word out (encode, scramble, gearbox, the one-in-33 pause)
//   ref_rx_pcs  one step() per clock edge: GT word in; the registered outputs of pcs_rx (lock, x_v, x_d, x_c, x_os, six event pulses)
//   ref_mac_rx  one step() per clock edge on ref_rx_pcs's outputs: the list of frames (bytes, FCS verdict) and aborted frames mac64_rx must report
//   functions   encode/decode of a 66-bit block, CRC-32, XGMII word lists for a frame
package pcs_ref_pkg;
  localparam bit [7:0] IDLE = 8'h07, START = 8'hFB, TERM = 8'hFD, ERRC = 8'hFE;
  localparam bit [7:0] T_CTRL = 8'h1E, T_S0 = 8'h78, T_S4 = 8'h33;
  localparam bit [7:0] T_TERM [8] = '{8'h87, 8'h99, 8'hAA, 8'hB4, 8'hCC, 8'hD2, 8'hE1, 8'hFF};
  localparam bit [7:0] T_OS   [4] = '{8'h2D, 8'h4B, 8'h55, 8'h66};
  localparam bit [63:0] IDLE_D = {8{IDLE}};
  localparam bit [63:0] ERR_D  = {8{ERRC}};

  typedef bit [7:0] bq_t [$];
  typedef bit [63:0] data_t;

  // a 66-bit block as sent: sh = the two header bits (bit 0 sent first), p = the payload (bit 0 sent first)
  typedef struct packed { bit [1:0] sh; bit [63:0] p; } blk_t;
  // decoder verdict: note 0 normal, 1 invalid sync header, 2 unknown block type, 3 ordered set (shown as idles)
  typedef struct packed { bit [1:0] note; bit [7:0] c; bit [63:0] d; } dec_t;
  typedef blk_t blkq_t [$];
  typedef struct { bit [63:0] d; bit [7:0] c; } xw_t;
  typedef xw_t xwq_t [$];

  // block kinds, for coverage and for the line-side stimulus
  typedef enum int { BK_DATA, BK_IDLE, BK_S0, BK_S4, BK_T0, BK_T1, BK_T2, BK_T3, BK_T4, BK_T5, BK_T6, BK_T7, BK_OS, BK_ERRCTL, BK_BADTYPE, BK_BADSH } blk_kind_e;

  function automatic bit [7:0] lane(input bit [63:0] d, input int i);
    return d[8*i +: 8];
  endfunction

  // ---------------------------------------------------------------------------------------------------- CRC-32 (reflected, bit by bit)
  function automatic bit [31:0] crc32(input bq_t b);
    bit [31:0] r;
    r = 32'hFFFF_FFFF;
    foreach (b[i]) begin
      r ^= {24'd0, b[i]};
      for (int k = 0; k < 8; k++) r = r[0] ? ((r >> 1) ^ 32'hEDB8_8320) : (r >> 1);
    end
    return ~r;
  endfunction

  // the frame check sequence appended after the data, low byte first
  function automatic bq_t fcs_bytes(input bq_t data, input bit poison, input bit [31:0] xor_mask = 32'd0);
    bit [31:0] f; bq_t o;
    f = crc32(data);
    if (poison) f = ~f;
    f ^= xor_mask;
    for (int i = 0; i < 4; i++) o.push_back(f[8*i +: 8]);
    return o;
  endfunction

  // ---------------------------------------------------------------------------------------------------- block codes
  function automatic bit [6:0] ctl7(input bit [7:0] ch);
    return (ch == IDLE) ? 7'h00 : 7'h1E;
  endfunction

  function automatic blk_t err_block();
    blk_t b; b.sh = 2'b10; b.p = '0; b.p[7:0] = T_CTRL;
    for (int i = 0; i < 8; i++) b.p[8 + 7*i +: 7] = 7'h1E;
    return b;
  endfunction

  function automatic bit lanes_ok(input bit [63:0] d, input int from);   // lanes from..7 are idle or error characters
    for (int i = from; i < 8; i++) if (lane(d, i) != IDLE && lane(d, i) != ERRC) return 1'b0;
    return 1'b1;
  endfunction

  // one XGMII word -> block, as pcs_tx does it. Words the MAC never produces (a start in lane 4, ordered sets, malformed words) become an all-error
  // block (pcs_tx.sv's header comment, b96_pkg::enc66). With `with_s4` set a lane-4 start is encoded as a real S4 block instead: the line agent uses
  // that to put lane-4 frames on the wire, since pcs_tx cannot.
  function automatic blk_t encode_block(input bit [63:0] d, input bit [7:0] c, input bit with_s4 = 1'b0);
    blk_t b;
    if (c == 8'h00) begin b.sh = 2'b01; b.p = d; return b; end
    if (c == 8'hFF && lanes_ok(d, 0)) begin
      b.sh = 2'b10; b.p = '0; b.p[7:0] = T_CTRL;
      for (int i = 0; i < 8; i++) b.p[8 + 7*i +: 7] = ctl7(lane(d, i));
      return b;
    end
    if (c == 8'h01 && lane(d, 0) == START) begin b.sh = 2'b10; b.p = {d[63:8], T_S0}; return b; end
    if (with_s4 && c == 8'h1F && lane(d, 4) == START) begin
      bit ok4; ok4 = 1'b1;
      for (int i = 0; i < 4; i++) if (lane(d, i) != IDLE && lane(d, i) != ERRC) ok4 = 1'b0;
      if (ok4) begin
        b.sh = 2'b10; b.p = '0; b.p[7:0] = T_S4;
        for (int i = 0; i < 4; i++) b.p[8 + 7*i +: 7] = ctl7(lane(d, i));
        b.p[63:40] = d[63:40];
        return b;
      end
    end
    for (int k = 0; k < 8; k++) begin
      bit [7:0] want; want = 8'hFF << k;
      if (c == want && lane(d, k) == TERM && lanes_ok(d, k + 1)) begin
        b.sh = 2'b10; b.p = '0; b.p[7:0] = T_TERM[k];
        for (int i = 0; i < k; i++) b.p[8 + 8*i +: 8] = lane(d, i);
        for (int i = k + 1; i < 8; i++) b.p[8 + 8*k + (7 - k) + 7*(i - k - 1) +: 7] = ctl7(lane(d, i));
        return b;
      end
    end
    return err_block();
  endfunction

  function automatic dec_t decode_block(input bit [1:0] sh, input bit [63:0] p);
    dec_t r; bit [7:0] t; bit [6:0] code;
    r = '0; t = p[7:0];
    if (sh == 2'b01) begin r.d = p; r.c = 8'h00; r.note = 2'd0; return r; end
    if (sh != 2'b10) begin r.d = ERR_D; r.c = 8'hFF; r.note = 2'd1; return r; end
    if (t == T_CTRL) begin
      for (int i = 0; i < 8; i++) begin code = p[8 + 7*i +: 7]; r.d[8*i +: 8] = (code == 0) ? IDLE : ERRC; end
      r.c = 8'hFF; return r;
    end
    if (t == T_S0) begin r.d = {p[63:8], START}; r.c = 8'h01; return r; end
    if (t == T_S4) begin
      for (int i = 0; i < 4; i++) begin code = p[8 + 7*i +: 7]; r.d[8*i +: 8] = (code == 0) ? IDLE : ERRC; end
      r.d[39:32] = START; r.d[63:40] = p[63:40]; r.c = 8'h1F; return r;
    end
    for (int k = 0; k < 8; k++) begin
      if (t == T_TERM[k]) begin
        for (int i = 0; i < k; i++) r.d[8*i +: 8] = p[8 + 8*i +: 8];
        r.d[8*k +: 8] = TERM;
        for (int i = k + 1; i < 8; i++) begin
          code = p[8 + 8*k + (7 - k) + 7*(i - k - 1) +: 7];
          r.d[8*i +: 8] = (code == 0) ? IDLE : ERRC;
        end
        r.c = 8'hFF << k; return r;
      end
    end
    for (int j = 0; j < 4; j++) if (t == T_OS[j]) begin r.d = IDLE_D; r.c = 8'hFF; r.note = 2'd3; return r; end
    r.d = ERR_D; r.c = 8'hFF; r.note = 2'd2; return r;
  endfunction

  // the kind of a received block, for coverage
  function automatic blk_kind_e kind_of(input bit [1:0] sh, input bit [63:0] p);
    bit [7:0] t; t = p[7:0];
    if (sh == 2'b01) return BK_DATA;
    if (sh != 2'b10) return BK_BADSH;
    if (t == T_CTRL) begin
      for (int i = 0; i < 8; i++) if (p[8 + 7*i +: 7] != 0) return BK_ERRCTL;
      return BK_IDLE;
    end
    if (t == T_S0) return BK_S0;
    if (t == T_S4) return BK_S4;
    for (int k = 0; k < 8; k++) if (t == T_TERM[k]) return blk_kind_e'(int'(BK_T0) + k);
    for (int j = 0; j < 4; j++) if (t == T_OS[j]) return BK_OS;
    return BK_BADTYPE;
  endfunction

  // ---------------------------------------------------------------------------------------------------- XGMII lists
  function automatic xw_t idle_word();
    xw_t w; w.d = IDLE_D; w.c = 8'hFF; return w;
  endfunction

  // one frame's XGMII words: preamble, data, FCS, terminate, idles to the word end. lane4 puts four idle bytes first (start in lane 4).
  function automatic xwq_t frame_words(input bq_t data, input bit lane4 = 0, input bit poison = 0, input bit [31:0] fcs_xor = 32'd0);
    bq_t s, fcs; bit cs [$]; xwq_t o; xw_t w;
    s.push_back(START); cs.push_back(1);
    repeat (6) begin s.push_back(8'h55); cs.push_back(0); end
    s.push_back(8'hD5); cs.push_back(0);
    foreach (data[i]) begin s.push_back(data[i]); cs.push_back(0); end
    fcs = fcs_bytes(data, poison, fcs_xor);
    foreach (fcs[i]) begin s.push_back(fcs[i]); cs.push_back(0); end
    if (lane4) begin
      repeat (4) begin s.push_front(IDLE); cs.push_front(1); end
    end
    s.push_back(TERM); cs.push_back(1);
    while (s.size() % 8 != 0) begin s.push_back(IDLE); cs.push_back(1); end
    for (int i = 0; i < s.size(); i += 8) begin
      w.d = '0; w.c = '0;
      for (int j = 0; j < 8; j++) begin w.d[8*j +: 8] = s[i + j]; w.c[j] = cs[i + j]; end
      o.push_back(w);
    end
    return o;
  endfunction

  // ---------------------------------------------------------------------------------------------------- scrambler, bit at a time
  class ref_scr;
    bit [57:0] hist;     // bit 0 = newest scrambled bit
    function void reset(); hist = '0; endfunction
    function bit scramble(input bit d);
      bit o; o = d ^ hist[38] ^ hist[57]; hist = {hist[56:0], o}; return o;
    endfunction
    function bit descramble(input bit s);
      bit o; o = s ^ hist[38] ^ hist[57]; hist = {hist[56:0], s}; return o;
    endfunction
    function bit [63:0] scramble_word(input bit [63:0] d);
      bit [63:0] o; for (int i = 0; i < 64; i++) o[i] = scramble(d[i]); return o;
    endfunction
    function bit [63:0] descramble_word(input bit [63:0] s);
      bit [63:0] o; for (int i = 0; i < 64; i++) o[i] = descramble(s[i]); return o;
    endfunction
  endclass

  // ---------------------------------------------------------------------------------------------------- transmit PCS
  class ref_tx_pcs;
    ref_scr scr;
    bit [127:0] acc;
    int n;
    bit [63:0] out;
    function new(); scr = new(); reset(); endfunction
    function void reset(); scr.reset(); acc = '0; n = 0; out = '0; endfunction
    function bit adv(); return (n != 64); endfunction
    // one clock edge; the offered word counts only when adv is high
    function bit [63:0] step(input bit [63:0] d, input bit [7:0] c);
      if (adv()) begin
        blk_t b; bit [65:0] blk; bit [191:0] m;
        b = encode_block(d, c);
        blk = {scr.scramble_word(b.p), b.sh};
        m = {64'd0, acc} | ({126'd0, blk} << n);
        out = m[63:0]; acc = m[127:64]; n += 2;
      end else begin
        out = acc[63:0]; acc = '0; n = 0;
      end
      return out;
    endfunction
  endclass

  // ---------------------------------------------------------------------------------------------------- receive PCS
  // block lock as built (clause 49): 64 valid headers with no invalid one to lock; 16 invalid headers inside 64 lose it; a failure while
  // hunting, or a loss, slips one bit; the block formed before the slip takes effect is ignored.
  class ref_rx_pcs;
    bit [135:0] acc; int cnt;
    bit have_blk; bit [1:0] blk_sh; bit [63:0] blk_p;
    bit slip_r;
    ref_scr desc;
    bit lock; int sh_cnt, inv_cnt, settle;
    // outputs after the last step (the registered values pcs_rx shows)
    bit x_v; bit [63:0] x_d; bit [7:0] x_c; bit x_os;
    bit ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
    // what the step decoded (for coverage): the block that stage B processed
    bit blk_done; blk_kind_e blk_kind; bit blk_locked;
    function new(); desc = new(); reset(); endfunction
    function void reset();
      acc = '0; cnt = 0; have_blk = 0; blk_sh = 0; blk_p = '0; slip_r = 0; desc.reset(); lock = 0; sh_cnt = 0; inv_cnt = 0; settle = 0;
      x_v = 0; x_d = '0; x_c = '0; x_os = 0; {ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock} = '0; blk_done = 0; blk_locked = 0;
    endfunction
    function void step(input bit [63:0] word);
      bit slip_n; bit [135:0] m; int k; bit valid_sh; bit lock_old; dec_t dec; bit [63:0] pd; bit nblk; bit [1:0] nsh; bit [63:0] np;
      {ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock} = '0;
      slip_n = 0; x_v = 0; blk_done = 0;
      // stage B + the lock FSM on the block registered at the previous edge
      if (have_blk) begin
        pd = desc.descramble_word(blk_p);
        dec = decode_block(blk_sh, pd);
        valid_sh = (blk_sh == 2'b01) || (blk_sh == 2'b10);
        lock_old = lock;
        x_d = dec.d; x_c = dec.c; x_os = (dec.note == 2'd3);
        blk_done = 1; blk_locked = lock_old; blk_kind = kind_of(blk_sh, pd);
        if (lock_old) begin
          x_v = 1; ev_sh_err = (dec.note == 2'd1); ev_type_err = (dec.note == 2'd2); ev_os = (dec.note == 2'd3);
        end
        if (settle > 0) begin
          settle = 0;
        end else if (!valid_sh && (!lock || inv_cnt == 15)) begin
          ev_loss = lock; lock = 0; slip_n = 1; ev_slip = 1; settle = 1; sh_cnt = 0; inv_cnt = 0;
        end else if (sh_cnt == 63) begin
          if (!lock && inv_cnt == 0) begin lock = 1; ev_lock = 1; end
          sh_cnt = 0; inv_cnt = 0;
        end else begin
          sh_cnt++;
          if (!valid_sh) inv_cnt++;
        end
      end
      // stage A: merge the word, apply the registered slip, extract at most one block
      m = acc | ({72'd0, word} << cnt);
      k = cnt + 64;
      if (slip_r) begin m = m >> 1; k -= 1; end
      nblk = 0; nsh = m[1:0]; np = m[65:2];
      if (k >= 66) begin nblk = 1; m = m >> 66; k -= 66; end
      acc = m; cnt = k;
      have_blk = nblk; blk_sh = nsh; blk_p = np;
      slip_r = slip_n;
    endfunction
  endclass

  // ---------------------------------------------------------------------------------------------------- receive MAC
  typedef struct { bq_t bytes; bit fcs_ok; int len; bit aborted; bit s4; int tlane; } rx_frame_t;
  typedef rx_frame_t rx_frameq_t [$];

  // what mac64_rx reports: a frame at its terminate (all data bytes, FCS included, the CRC verdict), or an abort for a frame cut by an error or
  // control word, a second start, a start with no data, or a lock loss. Frames start in lane 0 or lane 4; the 7 preamble bytes are skipped.
  class ref_mac_rx;
    typedef enum { R_IDLE, R_FRAME, R_FLUSH } st_e;
    st_e st; bq_t fbytes; int skip; bit s4;
    rx_frame_t done [$];
    rx_frame_t pend_f; int pend_n;      // a frame whose terminate has been seen, reported by mac64_rx 2 clocks later (3 after a flush); a reset in between loses it
    int n_abort, n_frames, last_tl;
    function new(); reset(); endfunction
    function void reset(); last_tl = 0; st = R_IDLE; fbytes.delete(); skip = 0; s4 = 0; done.delete(); n_abort = 0; n_frames = 0; pend_n = 0; endfunction
    function void abort_frame();
      rx_frame_t f; f.aborted = 1; f.fcs_ok = 0; f.len = 0; f.s4 = s4; f.tlane = 0; done.push_back(f); n_abort++; st = R_IDLE; fbytes.delete(); pend_n = 0;
    endfunction
    // the frame is complete: judge it now, report it after the pipeline delay
    function void finish_frame(input int delay);
      rx_frame_t f; bq_t data; bit [31:0] want;
      f.bytes = fbytes; f.len = fbytes.size(); f.aborted = 0; f.fcs_ok = 0; f.s4 = s4; f.tlane = last_tl;
      if (fbytes.size() >= 4) begin
        for (int i = 0; i < fbytes.size() - 4; i++) data.push_back(fbytes[i]);
        want = {fbytes[fbytes.size()-1], fbytes[fbytes.size()-2], fbytes[fbytes.size()-3], fbytes[fbytes.size()-4]};
        f.fcs_ok = (crc32(data) == want);
      end
      pend_f = f; pend_n = delay; fbytes.delete();
    endfunction
    function automatic int term_lane_of(input bit [63:0] d, input bit [7:0] c);   // -1 when none
      for (int k = 0; k < 8; k++) if (c == (8'hFF << k) && lane(d, k) == TERM) return k;
      return -1;
    endfunction
    function void step(input bit lock, input bit x_v, input bit [63:0] d, input bit [7:0] c);
      int tl; bit is_start0, is_start4;
      if (pend_n > 0) begin
        pend_n--;
        if (pend_n == 0) begin done.push_back(pend_f); n_frames++; end
      end
      if (st == R_FLUSH) begin
        if (!lock) abort_frame(); else st = R_IDLE;
        return;
      end
      if (!lock && st != R_IDLE) begin abort_frame(); return; end
      if (!x_v) return;
      tl = term_lane_of(d, c);
      is_start0 = (c == 8'h01) && (lane(d, 0) == START);
      is_start4 = (c == 8'h1F) && (lane(d, 4) == START);
      case (st)
        R_IDLE: if (is_start0 || is_start4) begin
          st = R_FRAME; fbytes.delete(); s4 = is_start4; skip = is_start4 ? 4 : 0;
        end
        R_FRAME: begin
          if (c == 8'h00) begin
            for (int i = 0; i < 8; i++) if (skip > 0) skip--; else fbytes.push_back(lane(d, i));
          end else if (tl >= 0) begin
            if (skip > 0) abort_frame();                       // a lane-4 frame that ends before any data
            else begin
              for (int i = 0; i < tl; i++) fbytes.push_back(lane(d, i));
              last_tl = tl;
              // a lane-4 frame whose terminate is in lanes 5-7 takes one more clock (the flush word), during which a lock loss aborts it
              if (s4 && tl > 4) begin finish_frame(3); st = R_FLUSH; end
              else begin finish_frame(2); st = R_IDLE; end
            end
          end else abort_frame();
        end
        default: ;
      endcase
    endfunction
  endclass
endpackage
