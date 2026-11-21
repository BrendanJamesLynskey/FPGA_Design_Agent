// pcs_mac_seqs.sv: the virtual sequences of the b96 PCS and MAC UVM bench (brief 112). A virtual sequence runs on pcs_mac_vsqr and starts items on
// the usr, xg and line sequencers. vseq_base holds the helpers; the others are the directed scenarios and the constrained-random mix.

class vseq_base extends uvm_sequence;
  `uvm_object_utils(vseq_base)
  `uvm_declare_p_sequencer(pcs_mac_vsqr)
  function new(string name = "vseq_base"); super.new(name); endfunction

  task clks(int n); repeat (n) @(posedge p_sequencer.svif.clk); endtask
  // wait for the reference receiver's lock (the DUT's is checked clock for clock by the scoreboard), then a few clocks more
  task wait_lock(int timeout = 30000, int extra = 20);
    int t; t = 0;
    while (!p_sequencer.sb.rrx.lock && t < timeout) begin clks(1); t++; end
    if (t >= timeout) `uvm_error("SEQ", "the receiver did not lock")
    clks(extra);
  endtask
  task e2e(bit on); p_sequencer.sb.e2e_en = on; if (!on) p_sequencer.sb.e2e_q.delete(); endtask
  task drain(int n = 400); clks(n); endtask

  // user-side frame
  task frame(int unsigned l, bit p = 0, int unsigned g = 0, pat_e pt = PAT_RANDOM, bit noise = 0);
    frame_item f; f = frame_item::type_id::create("f");
    start_item(f, -1, p_sequencer.usr);
    if (!f.randomize() with { len == l; poison == p; gap == g; pat == pt; noise_poison == noise; }) `uvm_fatal("SEQ", "frame randomize failed")
    finish_item(f);
  endtask
  task rand_frame(int unsigned lo, int unsigned hi, int unsigned glo = 0, int unsigned ghi = 40, int poison_pct = 10);
    frame_item f; f = frame_item::type_id::create("f");
    start_item(f, -1, p_sequencer.usr);
    if (!f.randomize() with { len inside {[lo:hi]}; gap inside {[glo:ghi]}; poison dist { 1 := poison_pct, 0 := 100 - poison_pct }; })
      `uvm_fatal("SEQ", "frame randomize failed")
    finish_item(f);
  endtask

  // XGMII words straight into pcs_tx
  task xg(pcs_ref_pkg::xwq_t w, string tag = "");
    xg_item x; x = xg_item::type_id::create("x");
    start_item(x, -1, p_sequencer.xg);
    x.words = w; x.tag = tag;
    finish_item(x);
  endtask

  // line agent items
  task line(line_kind_e k, int unsigned n = 0, bit [63:0] mask = '0, int unsigned skip = 0);
    line_item li; li = line_item::type_id::create("li");
    start_item(li, -1, p_sequencer.line);
    li.kind = k; li.n = n; li.mask = mask; li.skip = skip;
    finish_item(li);
  endtask
  task line_blocks(pcs_ref_pkg::blkq_t q);
    line_item li; li = line_item::type_id::create("li");
    start_item(li, -1, p_sequencer.line);
    li.kind = L_BLOCKS; li.blks = q;
    finish_item(li);
  endtask

  function pcs_ref_pkg::bq_t rbytes(int n);
    pcs_ref_pkg::bq_t q; repeat (n) q.push_back(8'($urandom())); return q;
  endfunction
  function pcs_ref_pkg::blkq_t blocks_of(pcs_ref_pkg::xwq_t w);
    pcs_ref_pkg::blk_t q [$];
    foreach (w[i]) q.push_back(pcs_ref_pkg::encode_block(w[i].d, w[i].c, 1'b1));
    return q;
  endfunction
  function pcs_ref_pkg::blkq_t idle_blocks(int n);
    pcs_ref_pkg::blk_t q [$]; pcs_ref_pkg::xw_t iw; iw = pcs_ref_pkg::idle_word();
    repeat (n) q.push_back(pcs_ref_pkg::encode_block(iw.d, iw.c));
    return q;
  endfunction
  function pcs_ref_pkg::blk_t raw(bit [1:0] sh, bit [7:0] typ);   // a raw block: the type byte and random bits above it
    pcs_ref_pkg::blk_t b; b.sh = sh; b.p = {56'($urandom()), typ}; b.p[63:32] = $urandom(); return b;
  endfunction
  function pcs_ref_pkg::blk_t os_block(int j); return raw(2'b10, pcs_ref_pkg::T_OS[j]); endfunction
  function pcs_ref_pkg::blk_t bad_type_block();
    bit [7:0] t [10] = '{8'h00, 8'h01, 8'h10, 8'h20, 8'h40, 8'h80, 8'hF0, 8'hC3, 8'h5A, 8'hA5};
    return raw(2'b10, t[$urandom_range(9)]);
  endfunction
  function pcs_ref_pkg::blk_t bad_sh_block(); return raw($urandom_range(1) ? 2'b00 : 2'b11, 8'($urandom())); endfunction
endclass

// ------------------------------------------------------------------------------------------------------ loopback, user-side frames
class vseq_smoke extends vseq_base;
  `uvm_object_utils(vseq_smoke)
  function new(string name = "vseq_smoke"); super.new(name); endfunction
  task body();
    wait_lock(); e2e(1);
    frame(60); frame(64); frame(1514, 0, 0); frame(61, 0, 5); frame(100, 1, 0); frame(60, 0, 0); frame(1514, 0, 0);
    drain(); e2e(0);
  endtask
endclass

class vseq_lens extends vseq_base;
  `uvm_object_utils(vseq_lens)
  function new(string name = "vseq_lens"); super.new(name); endfunction
  task body();
    int unsigned big [] = '{127, 128, 129, 255, 256, 511, 512, 1023, 1024, 1500, 1514, 1600, 4000, 9000};
    wait_lock(); e2e(1);
    for (int l = 60; l < 100; l++) frame(l, 0, l % 3);
    foreach (big[i]) frame(big[i], 0, i % 4);
    for (int l = 60; l < 76; l++) frame(l, 0, 0);
    drain(); e2e(0);
  endtask
endclass

class vseq_gaps extends vseq_base;
  `uvm_object_utils(vseq_gaps)
  function new(string name = "vseq_gaps"); super.new(name); endfunction
  task body();
    int unsigned g [] = '{0, 0, 1, 2, 3, 4, 5, 8, 12, 16, 17, 32, 33, 34, 64, 100, 300, 520};
    wait_lock(); e2e(1);
    foreach (g[i]) frame(60 + (i * 7) % 90, 0, g[i]);
    for (int i = 0; i < 30; i++) rand_frame(60, 300, 0, 3, 0);
    frame(60, 0, 300); frame(61, 0, 300); frame(9000, 0, 300); frame(9000, 0, 2);    // the long gap after a minimum frame and after a jumbo
    drain(); e2e(0);
  endtask
endclass

class vseq_badfcs extends vseq_base;
  `uvm_object_utils(vseq_badfcs)
  function new(string name = "vseq_badfcs"); super.new(name); endfunction
  task body();
    wait_lock(); e2e(1);
    for (int i = 0; i < 48; i++) frame(60 + (i * 13) % 200, (i % 3) == 0, i % 4, pat_e'(i % 5), 1);
    frame(1514, 1, 0, PAT_ONES, 1); frame(60, 1, 0, PAT_ZEROS, 1); frame(60, 0, 0);
    drain(); e2e(0);
  endtask
endclass

// ------------------------------------------------------------------------------------------------------ loopback, XGMII injection
class vseq_xg extends vseq_base;
  `uvm_object_utils(vseq_xg)
  function new(string name = "vseq_xg"); super.new(name); endfunction
  localparam bit [31:0] RES_MASK [32] = '{32'hDB710641, 32'h6D930AC3, 32'hDB261586, 32'h6D3D2D4D, 32'hDA7A5A9A, 32'h6F85B375, 32'hDF0B66EA, 32'h6567CB95,
    32'hCACF972A, 32'h4EEE2815, 32'h9DDC502A, 32'hE0C9A615, 32'h1AE24A6B, 32'h35C494D6, 32'h6B8929AC, 32'hD7125358, 32'h7555A0F1, 32'hEAAB41E2, 32'h0E278585,
    32'h1C4F0B0A, 32'h389E1614, 32'h713C2C28, 32'hE2785850, 32'h1F81B6E1, 32'h3F036DC2, 32'h7E06DB84, 32'hFC0DB708, 32'h236A6851, 32'h46D4D0A2, 32'h8DA9A144,
    32'hC02244C9, 32'h5B358FD3};
  function pcs_ref_pkg::xwq_t put_err(pcs_ref_pkg::xwq_t w, int wi, int ln);   // an error character in lane ln of word wi
    w[wi].d[8*ln +: 8] = pcs_ref_pkg::ERRC; w[wi].c[ln] = 1'b1; return w;
  endfunction
  task body();
    pcs_ref_pkg::xwq_t w, v; pcs_ref_pkg::xw_t iw;
    iw = pcs_ref_pkg::idle_word();
    wait_lock();
    // clean frames, start in lane 0 and in lane 4, every terminate lane (lengths 60..75 cover every residue mod 8)
    for (int l = 60; l < 76; l++) begin
      xg(pcs_ref_pkg::frame_words(rbytes(l), 0, 0), $sformatf("l0 len %0d", l));
      xg(pcs_ref_pkg::frame_words(rbytes(l), 1, 0), $sformatf("l4 len %0d", l));
    end
    xg(pcs_ref_pkg::frame_words(rbytes(300), 1, 1), "l4 bad fcs");
    xg(pcs_ref_pkg::frame_words(rbytes(1000), 0, 1), "l0 bad fcs");
    // error characters inside a frame, in the preamble word, in the terminate word
    for (int k = 0; k < 6; k++) begin
      w = pcs_ref_pkg::frame_words(rbytes(80 + 3 * k), k % 2, 0);
      w = put_err(w, 1 + (k % 4), k % 8);
      xg(w, "error character in data");
    end
    // a frame cut short: idles where data should be; a second start inside a frame; a terminate without a start
    w = pcs_ref_pkg::frame_words(rbytes(100), 0, 0); v = w[0:3]; xg(v, "cut: idles follow");
    w = pcs_ref_pkg::frame_words(rbytes(100), 0, 0); v = w[0:4]; v.push_back(w[0]); v = {v, pcs_ref_pkg::frame_words(rbytes(70), 0, 0)}; xg(v, "second start inside a frame");
    for (int k = 0; k < 8; k++) begin pcs_ref_pkg::xw_t t; t.d = pcs_ref_pkg::IDLE_D; t.d[8*k +: 8] = pcs_ref_pkg::TERM; t.c = 8'hFF; xg('{t}, $sformatf("lone terminate lane %0d", k)); end
    // start followed at once by a terminate, in lane 0 and lane 4 (a frame with no data)
    for (int k = 0; k < 8; k++) begin
      pcs_ref_pkg::xw_t s, t;
      s.d = {8'hD5, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, pcs_ref_pkg::START}; s.c = 8'h01;
      t.d = pcs_ref_pkg::IDLE_D; t.d[8*k +: 8] = pcs_ref_pkg::TERM; t.c = 8'hFF << k;
      xg('{s, t}, $sformatf("start then terminate lane %0d", k));
      s.d = {8'hD5, 8'h55, 8'h55, 8'h55, pcs_ref_pkg::START, {4{pcs_ref_pkg::IDLE}}}; s.c = 8'h1F;
      xg('{s, t}, $sformatf("lane-4 start then terminate lane %0d", k));
    end
    // ordered sets, local-fault sequences, start in another lane, malformed control vectors, bad data words: pcs_tx must turn them into error blocks
    for (int i = 0; i < 12; i++) begin
      pcs_ref_pkg::xw_t o; o.d = {8'h00, 8'h00, 8'h01, 8'h9C, {4{pcs_ref_pkg::IDLE}}}; o.c = 8'h01 << (i % 2);
      if (i >= 4) begin o.d = $urandom(); o.d[63:32] = $urandom(); o.c = 8'($urandom()); if (o.c == 8'h00 || o.c == 8'hFF) o.c = 8'h5A; end
      xg('{o}, "ordered set or malformed word");
    end
    // FCS errors that move the CRC residue in exactly one bit position b (the mask is the solution of a linear system over GF(2): flipping FCS bits
    // changes the final register by a fixed vector whatever the data; checked against a bitwise CRC when the masks were made). A receiver whose FCS
    // compare ignores one residue bit, which no random error or full poisoning shows, fails the frame of that bit.
    foreach (RES_MASK[b]) xg(pcs_ref_pkg::frame_words(rbytes(64 + b % 8), 0, 0, RES_MASK[b]), $sformatf("residue bit %0d only", b));
    // frames after all that: the receiver must still be locked and framing
    for (int l = 60; l < 70; l++) xg(pcs_ref_pkg::frame_words(rbytes(l), l % 2, 0), "recovery frame");
    drain();
  endtask
endclass

// ------------------------------------------------------------------------------------------------------ line mode: the line agent's own block stream
class vseq_line_blocks extends vseq_base;
  `uvm_object_utils(vseq_line_blocks)
  function new(string name = "vseq_line_blocks"); super.new(name); endfunction
  task body();
    pcs_ref_pkg::blk_t q [$];
    wait_lock();
    // frames from raw blocks, lane 0 and lane 4, every terminate lane
    for (int l = 60; l < 84; l++) begin
      line_blocks(blocks_of(pcs_ref_pkg::frame_words(rbytes(l), 0, (l % 5) == 0)));
      line_blocks(idle_blocks(1 + l % 3));
      line_blocks(blocks_of(pcs_ref_pkg::frame_words(rbytes(l), 1, (l % 7) == 0)));
      line_blocks(idle_blocks(1 + l % 2));
    end
    // ordered sets of all four types, between frames and inside one
    for (int j = 0; j < 4; j++) begin q = {}; q.push_back(os_block(j)); q = {q, idle_blocks(2)}; line_blocks(q); end
    q = blocks_of(pcs_ref_pkg::frame_words(rbytes(200), 0, 0)); q.insert(5, os_block(1)); line_blocks(q);
    line_blocks(idle_blocks(3));
    // all-error control blocks, unknown block types, a single bad sync header (lock holds), data blocks outside a frame
    for (int i = 0; i < 4; i++) begin q = {}; q.push_back(pcs_ref_pkg::err_block()); q.push_back(bad_type_block()); q.push_back(bad_sh_block()); line_blocks(q); line_blocks(idle_blocks(2)); end
    q = {}; repeat (4) begin pcs_ref_pkg::blk_t d; d.sh = 2'b01; d.p = {$urandom(), $urandom()}; q.push_back(d); end line_blocks(q);
    // terminate blocks of every lane with no start, start blocks of both kinds back to back, a bad type inside a frame
    for (int k = 0; k < 8; k++) begin
      pcs_ref_pkg::xw_t t; t.d = pcs_ref_pkg::IDLE_D; t.c = 8'hFF << k; t.d[8*k +: 8] = pcs_ref_pkg::TERM;
      for (int i = 0; i < k; i++) t.d[8*i +: 8] = 8'($urandom());
      q = {}; q.push_back(pcs_ref_pkg::encode_block(t.d, t.c)); line_blocks(q);
    end
    q = blocks_of(pcs_ref_pkg::frame_words(rbytes(90), 0, 0)); q.insert(4, bad_type_block()); line_blocks(q);
    q = blocks_of(pcs_ref_pkg::frame_words(rbytes(90), 1, 0)); q.insert(3, bad_sh_block()); line_blocks(q);
    q = blocks_of(pcs_ref_pkg::frame_words(rbytes(90), 0, 0)); q = {q[0:2], q}; line_blocks(q);              // a second start inside the frame
    for (int l = 60; l < 70; l++) line_blocks(blocks_of(pcs_ref_pkg::frame_words(rbytes(l), l % 2, 0)));
    line_blocks(idle_blocks(40));
    // lock lost while a frame is in progress: 15 bad headers spread over 30 blocks, then a frame with the 16th bad header either in its 5th block (even
    // phases) or straight after its terminate block (odd phases: a lane-4 frame with the terminate in lane 5, 6 or 7, so mac64_rx is in its flush
    // state when the lock drops: the one place where its lock-loss branch is not made redundant by the error word the bad header delivers).
    // The 64-block window of the lock FSM has an unknown phase, so the pattern is tried at 12 phases
    for (int ph = 0; ph < 12; ph++) begin
      line_blocks(idle_blocks(3 + 5 * ph));
      q = {};
      repeat (15) begin q.push_back(bad_sh_block()); q.push_back(pcs_ref_pkg::encode_block(pcs_ref_pkg::IDLE_D, 8'hFF)); end
      line_blocks(q);
      if ((ph % 2) == 0) begin
        q = blocks_of(pcs_ref_pkg::frame_words(rbytes(100), 0, 0)); q.insert(5, bad_sh_block());
      end else begin
        q = blocks_of(pcs_ref_pkg::frame_words(rbytes(61 + (ph / 2) % 3 + 8 * (ph / 6)), 1, 0)); q.push_back(bad_sh_block());
      end
      line_blocks(q);
      line_blocks(idle_blocks(20));
      wait_lock(60000);
    end
    drain();
  endtask
endclass

// ------------------------------------------------------------------------------------------------------ loopback faults and lock
class vseq_hdr extends vseq_base;
  `uvm_object_utils(vseq_hdr)
  function new(string name = "vseq_hdr"); super.new(name); endfunction
  task body();
    wait_lock(); e2e(1);
    for (int i = 0; i < 6; i++) frame(60 + 20 * i);
    e2e(0);
    // isolated header errors: counted, lock holds
    for (int i = 0; i < 3; i++) begin
      fork frame(300, 0, 0); begin clks(25); line(L_HDR, 1 + i); end join
      drain(60);
    end
    // 15 inside the window: the limit; 16 and more: the lock is lost (in a frame, then idle), the receiver hunts and locks again
    foreach (HB[i]) begin
      fork begin frame(1514, 0, 0); frame(200, 0, 0); end begin clks(HD[i]); line(L_HDR, HB[i]); end join
      drain(100);
      wait_lock();
    end
    // sparse corruption: every (skip+1)th header bad, 16 of them: the lock is lost while a frame is in progress when a frame started after the 15th
    for (int sk = 3; sk <= 14; sk++) begin
      fork
        for (int i = 0; i < 40; i++) frame(60, 0, 0);
        begin clks(40); line(L_HDR, 16, '0, sk); end
      join
      drain(100);
      wait_lock();
    end
    e2e(1);
    for (int i = 0; i < 8; i++) frame(70 + i);
    drain(); e2e(0);
  endtask
  int unsigned HB [] = '{15, 16, 17, 30, 70};
  int unsigned HD [] = '{40, 30, 60, 100, 20};
endclass

class vseq_slip extends vseq_base;
  `uvm_object_utils(vseq_slip)
  function new(string name = "vseq_slip"); super.new(name); endfunction
  task body();
    wait_lock();
    for (int r = 0; r < 4; r++) begin
      fork
        for (int i = 0; i < 6; i++) frame(100 + 50 * i, 0, 2);
        begin clks(60 + 30 * r); line((r % 2) ? L_SLIP_DEL : L_SLIP_INS); if (r >= 2) begin clks(40); line(L_SLIP_INS); end end
      join
      drain(100);
      wait_lock(60000);                       // hunting: one slip per 64 blocks until the alignment is found again
    end
    e2e(1);
    for (int i = 0; i < 6; i++) frame(64 + i);
    drain(); e2e(0);
  endtask
endclass

class vseq_ber extends vseq_base;
  `uvm_object_utils(vseq_ber)
  int unsigned ppm_list [] = '{0, 20, 300, 2000, 30000};
  function new(string name = "vseq_ber"); super.new(name); endfunction
  task body();
    wait_lock();
    foreach (ppm_list[i]) begin
      line(L_BER, ppm_list[i]);
      for (int k = 0; k < 14; k++) rand_frame(60, 700, 0, 6, 0);
      drain(100);
      line(L_BER, 0);
      drain(100);
      wait_lock(60000);
    end
    e2e(1);
    for (int i = 0; i < 6; i++) frame(66 + i);
    drain(); e2e(0);
  endtask
endclass

class vseq_rxreset extends vseq_base;
  `uvm_object_utils(vseq_rxreset)
  function new(string name = "vseq_rxreset"); super.new(name); endfunction
  task body();
    wait_lock();
    for (int r = 0; r < 3; r++) begin
      fork
        for (int i = 0; i < 6; i++) frame(300 + 100 * i, 0, 1);
        begin clks(50 + 70 * r); line(L_RXRESET, 1 + 2 * r); end
      join
      drain(100);
      wait_lock(60000);
    end
    e2e(1);
    for (int i = 0; i < 6; i++) frame(62 + i);
    drain(); e2e(0);
  endtask
endclass

// a clean frame burst after resetting with each initial bit offset: lock acquisition from every alignment class
class vseq_offsets extends vseq_base;
  `uvm_object_utils(vseq_offsets)
  function new(string name = "vseq_offsets"); super.new(name); endfunction
  task body();
    int unsigned offs [] = '{0, 1, 2, 5, 17, 33, 50, 60, 62, 64, 65, 66, 100, 131, 132};
    foreach (offs[i]) begin
      p_sequencer.svif.apply_reset(1'b0, offs[i]);
      wait_lock(60000); e2e(1);
      for (int k = 0; k < 4; k++) frame(60 + (offs[i] + k) % 40, 0, k);
      drain(300); e2e(0);
    end
  endtask
endclass

// ------------------------------------------------------------------------------------------------------ constrained random
class vseq_rand extends vseq_base;
  `uvm_object_utils(vseq_rand)
  int unsigned n_actions = 60;
  bit          line_mode = 0;
  function new(string name = "vseq_rand"); super.new(name); endfunction
  task body();
    int r; int unsigned bers [] = '{0, 0, 50, 300, 1000};
    void'($value$plusargs("NACT=%d", n_actions));
    wait_lock(60000);
    for (int a = 0; a < n_actions; a++) begin
      r = $urandom_range(99);
      if (r < 45) begin
        int nf; nf = $urandom_range(1, 4);
        repeat (nf) begin
          int c; c = $urandom_range(99);
          if (line_mode) line_blocks(blocks_of(pcs_ref_pkg::frame_words(rbytes((c < 60) ? $urandom_range(60, 90) : $urandom_range(91, 400)), $urandom_range(1), $urandom_range(9) == 0)));
          else if (c < 50) rand_frame(60, 90); else if (c < 80) rand_frame(91, 300); else if (c < 97) rand_frame(301, 1514); else rand_frame(1515, 6000, 0, 4, 5);
        end
      end else if (r < 55) begin
        if (line_mode) line_blocks(idle_blocks($urandom_range(1, 30))); else clks($urandom_range(1, 200));
      end else if (r < 65) line(L_FLIP, 0, 64'd1 << $urandom_range(63));
      else if (r < 70) begin int unsigned hb [] = '{1, 3, 8, 15, 16, 17, 25}; line(L_HDR, hb[$urandom_range(6)]); end
      else if (r < 73) line($urandom_range(1) ? L_SLIP_INS : L_SLIP_DEL);
      else if (r < 77 && !line_mode) begin
        pcs_ref_pkg::xwq_t w; w = pcs_ref_pkg::frame_words(rbytes($urandom_range(60, 120)), $urandom_range(1), $urandom_range(5) == 0);
        if ($urandom_range(2) == 0) begin int wi, ln; wi = $urandom_range(w.size() - 1); ln = $urandom_range(7); w[wi].d[8*ln +: 8] = pcs_ref_pkg::ERRC; w[wi].c[ln] = 1'b1; end
        xg(w, "random xg");
      end else if (r < 80) line(L_RXRESET, $urandom_range(1, 4));
      else if (r < 82 && line_mode) begin
        pcs_ref_pkg::blk_t q [$]; q.push_back(os_block($urandom_range(3))); q.push_back(bad_type_block()); q.push_back(pcs_ref_pkg::err_block()); line_blocks(q);
      end else if (r < 90) line(L_BER, bers[$urandom_range(4)]);
      else clks($urandom_range(1, 50));
      if ((a % 15) == 14) begin line(L_BER, 0); drain(300); end
    end
    line(L_BER, 0); drain(600);
  endtask
endclass
