// itch_seqs.sv: the virtual sequences of the ITCH/OUCH UVM bench (brief 170). vseq_base holds the helpers (frames, Mold packets, ITCH messages, configuration, checkpoints); the others are the
// scenarios. A checkpoint is a stretch of idle clocks followed by a read of the status vector, at which the scoreboard compares everything the model has seen so far.
typedef struct { longint unsigned r; int inst; byte unsigned side; int unsigned sh; int unsigned px; } wo_t;

class vseq_base extends uvm_sequence;
  `uvm_object_utils(vseq_base)
  `uvm_declare_p_sequencer(itch_vsqr)
  itch_cfg c;
  string sess = "SESSION001";
  longint unsigned seq = 1;
  longint unsigned nref = 1000;
  int gap = 64;                 // idle words after each frame (64 keeps order frames apart; small values stress the queue)
  int bubble = 0;
  wo_t live [$];
  function new(string name = "vseq_base"); super.new(name); c = new(); c.defaults(); endfunction

  // ---- helpers
  function string sname(int i);
    string s; s = "";
    for (int k = 7; k >= 0; k--) s = {s, $sformatf("%c", c.watch[i][8*k +: 8])};
    return s;
  endfunction
  task idle(int n);
    in_item it; it = in_item::type_id::create("idle");
    it.kind = IN_IDLE; it.idle_n = n;
    start_item(it, -1, p_sequencer.in_s); finish_item(it);
  endtask
  task cf(cf_kind_e k, int bits = 0);
    cfg_item ci; ci = cfg_item::type_id::create("ci");
    ci.kind = k; ci.cmd_bits = bits; ci.c = c.clone();
    start_item(ci, -1, p_sequencer.cfg_s); finish_item(ci);
  endtask
  task set_cfg(); cf(CF_SET); endtask
  task cmd(int bits); cf(CF_CMD, bits); endtask
  task checkpoint(); idle(200); cf(CF_STATS); endtask
  task setup(bit restart = 1);
    if (restart) begin cf(CF_RESET); idle(2); end
    set_cfg(); cf(CF_READY); cmd(64); idle(8);
    live.delete(); seq = 1;
  endtask
  task send_bytes(bq_t f, bit bad = 0, bit l4 = 0, int g = -1, int bub = -1);
    in_item it; it = in_item::type_id::create("f");
    it.kind = IN_FRAME; it.data = f; it.bad_fcs = bad; it.lane4 = l4;
    it.gap_after = (g < 0) ? gap : g; it.bubble_pct = (bub < 0) ? bubble : bub;
    start_item(it, -1, p_sequencer.in_s); finish_item(it);
  endtask
  task send_pay(bq_t pay, bit bad = 0, bit l4 = 0, int g = -1);
    send_bytes(itch_gen::eth_frame(pay, c, itch_gen::no_opts()), bad, l4, g);
  endtask
  task send_msgs(bq_t msgs[$], bit bad = 0, bit l4 = 0, int g = -1);
    send_pay(itch_gen::mold(sess, seq, msgs), bad, l4, g);
    seq += msgs.size();
  endtask
  task one(bq_t m, bit bad = 0, bit l4 = 0); bq_t q [$]; q.push_back(m); send_msgs(q, bad, l4); endtask

  // messages for instrument i (locate 100 + i)
  function bq_t mA(int i, longint unsigned r, byte unsigned side, int unsigned sh, int unsigned px, bit mp = 0);
    return itch_gen::msg_A(100 + i, r, side, sh, sname(i), px, mp);
  endfunction
  function bq_t mE(int i, longint unsigned r, int unsigned sh, bit wp = 0, int unsigned px = 0); return itch_gen::msg_E(100 + i, r, sh, wp, px); endfunction
  function bq_t mX(int i, longint unsigned r, int unsigned sh); return itch_gen::msg_X(100 + i, r, sh); endfunction
  function bq_t mD(int i, longint unsigned r); return itch_gen::msg_D(100 + i, r); endfunction
  function bq_t mU(int i, longint unsigned r, longint unsigned nr, int unsigned sh, int unsigned px); return itch_gen::msg_U(100 + i, r, nr, sh, px); endfunction
  task directory(int n = 4);
    bq_t q [$];
    q.push_back(itch_gen::msg_S("O"));
    for (int i = 0; i < n; i++) q.push_back(itch_gen::msg_R(100 + i, sname(i)));
    send_msgs(q);
  endtask
  function bit rl4(); return bit'($urandom_range(1)); endfunction

  // a random plausible message from the world (live orders); k picks the kind
  function bq_t rand_msg();
    int k, i; wo_t w; bq_t m;
    k = $urandom_range(99);
    if (live.size() == 0 && k >= 35) k = 0;
    if (k < 35) begin             // add
      bit sell; int unsigned px;
      sell = $urandom_range(1);
      i = $urandom_range(3);
      px = sell ? (990000 + 2000 * $urandom_range(6)) : (990000 + 1000 * $urandom_range(6));
      w.r = nref++; w.inst = i; w.side = sell ? "S" : "B"; w.sh = 100 * (1 + $urandom_range(9)); w.px = px;
      live.push_back(w);
      return mA(i, w.r, w.side, w.sh, px, $urandom_range(9) == 0);
    end else if (k < 50) begin    // execute (partial)
      i = $urandom_range(live.size() - 1); w = live[i];
      if (w.sh > 1) begin int unsigned s; s = 1 + $urandom_range(w.sh - 1); live[i].sh -= s; return mE(w.inst, w.r, s, $urandom_range(1), w.px + $urandom_range(2)); end
      live.delete(i); return mE(w.inst, w.r, w.sh);
    end else if (k < 62) begin    // cancel (partial)
      i = $urandom_range(live.size() - 1); w = live[i];
      if (w.sh > 1) begin live[i].sh -= 1; return mX(w.inst, w.r, 1); end
      live.delete(i); return mX(w.inst, w.r, w.sh);
    end else if (k < 75) begin    // delete
      i = $urandom_range(live.size() - 1); w = live[i]; live.delete(i); return mD(w.inst, w.r);
    end else if (k < 88) begin    // replace
      longint unsigned nr; int unsigned px;
      i = $urandom_range(live.size() - 1); w = live[i]; nr = nref++;
      px = (w.side == "S") ? (990000 + 2000 * $urandom_range(6)) : (990000 + 1000 * $urandom_range(6));
      live[i].r = nr; live[i].px = px; live[i].sh = 200;
      return mU(w.inst, w.r, nr, 200, px);
    end else if (k < 93) return itch_gen::msg_S("Q");
    else if (k < 97) return itch_gen::msg_other("H", 25);
    else return itch_gen::msg_other("L", 26);
  endfunction

  virtual task body(); endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- smoke
class vseq_smoke extends vseq_base;
  `uvm_object_utils(vseq_smoke)
  function new(string name = "vseq_smoke"); super.new(name); endfunction
  task body();
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    one(mA(0, nref++, "S", 100, 990000));            // a candidate: sell at or below the threshold
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- message mix, 1, 3 and 6 messages a packet
class vseq_mix extends vseq_base;
  `uvm_object_utils(vseq_mix)
  int rounds = 30;
  function new(string name = "vseq_mix"); super.new(name); endfunction
  task body();
    int sizes [3] = '{1, 3, 6};
    void'($value$plusargs("ROUNDS=%d", rounds));
    setup(); directory();
    for (int i = 0; i < 4; i++) one(mA(i, nref++, "B", 1000, 994000));        // a bid in every book
    checkpoint();
    for (int r = 0; r < rounds; r++) begin
      bq_t q [$]; int n; n = sizes[$urandom_range(2)];
      repeat (n) q.push_back(rand_msg());
      bubble = ($urandom_range(3) == 0) ? 20 : 0;
      send_msgs(q, 0, rl4());
      if (r % 5 == 4) checkpoint();
    end
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- MoldUDP64: gaps, duplicates, overlaps, heartbeats, end of session, other session, short and broken packets
class vseq_mold extends vseq_base;
  `uvm_object_utils(vseq_mold)
  function new(string name = "vseq_mold"); super.new(name); endfunction
  task body();
    bq_t q [$];
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    one(mA(0, nref++, "S", 100, 990000));
    // a gap (halt on gap off: counted only), then the packet is still delivered
    seq += 5; one(mA(0, nref++, "S", 100, 991000));
    checkpoint();
    // a duplicate packet (already seen) and an overlapping packet
    send_pay(itch_gen::mold(sess, seq - 1, '{mA(1, nref++, "B", 10, 100000)}));              // sequence below the expected number: dup
    q.delete(); q.push_back(mA(0, nref++, "S", 100, 992000)); q.push_back(mA(0, nref++, "S", 100, 993000)); q.push_back(mA(0, nref++, "S", 100, 994000));
    send_pay(itch_gen::mold(sess, seq - 1, q)); seq += 2;                                      // starts one message early: overlap of one
    checkpoint();
    // heartbeat (next expected number), another session, short payload, end of session
    send_pay(itch_gen::mold_hb(sess, seq));
    send_pay(itch_gen::mold_hb(sess, seq - 3));                                                // heartbeat below the expected number: dup
    send_pay(itch_gen::mold("OTHERSESS1", 1, '{mA(0, nref++, "S", 100, 990000)}));
    begin bq_t sh; for (int i = 0; i < 12; i++) sh.push_back(8'(i)); send_pay(sh); end         // 12-byte payload: short
    checkpoint();
    // truncated packets: a count that promises more blocks than the packet has; a block longer than the packet; a block under 12 bytes
    q.delete(); q.push_back(mA(0, nref++, "S", 100, 990500)); q.push_back(mA(0, nref++, "B", 100, 996000));
    send_pay(itch_gen::mold(sess, seq, q, 4)); seq += 4;
    begin
      bq_t p; p = itch_gen::mold(sess, seq, '{mD(0, 1)}, 2); put_be(p, 200, 2); p.push_back(8'h41); p.push_back(8'h00);     // a second block claims 200 bytes, the packet ends
      send_pay(p); seq += 2;
    end
    begin
      bq_t p; p = itch_gen::mold(sess, seq, '{mD(0, 1)}, 3); put_be(p, 5, 2); for (int i = 0; i < 5; i++) p.push_back(8'h00); p = itch_gen::mold(sess, seq, '{mD(0, 2)}, 1);
      send_pay(p); seq += 1;
    end
    begin
      bq_t p; p = itch_gen::mold(sess, seq, '{}, 3); put_be(p, 5, 2); for (int i = 0; i < 5; i++) p.push_back(8'h00);                // first block is 5 bytes: bad length, rest dropped
      send_pay(p); seq += 3;
    end
    checkpoint();
    // a gap with halt-on-gap set: the candidates after it are refused until clr_flags
    c.halt = 1; set_cfg(); idle(10);
    seq += 3; one(mA(0, nref++, "S", 100, 991000));
    one(mA(0, nref++, "S", 100, 991100));
    checkpoint();
    cmd(2); idle(10);                                                                          // clr_flags: gap flag, session lock and the expected number are cleared
    sess = "SESSION002"; seq = 7000;
    one(mA(0, nref++, "S", 100, 991200));
    send_pay(itch_gen::mold_hb(sess, seq, 1));                                                 // end of session
    checkpoint();
    // the stock directory again, with another locate for an instrument already mapped, then orders under the new locate are unwatched under the old one
    q.delete(); q.push_back(itch_gen::msg_R(555, sname(2))); send_msgs(q);
    one(itch_gen::msg_A(555, nref++, "B", 100, sname(2), 990000));
    one(itch_gen::msg_A(102, nref++, "B", 100, sname(2), 990000));
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- candidates at every distance from the end of the packet, STRICT and cut-through, with and without speculation
class vseq_tail extends vseq_base;
  `uvm_object_utils(vseq_tail)
  function new(string name = "vseq_tail"); super.new(name); endfunction
  task one_mode(bit strict, bit spec);
    c.strict = strict; c.spec = spec; set_cfg(); idle(10);
    for (int n = 0; n <= 10; n++) begin
      bq_t q [$];
      q.push_back(mA(0, nref++, "S", 100, 990000 + 10 * (n % 4)));       // the candidate (four distinct prices at most: the ladder holds eight)
      for (int k = 0; k < n; k++) q.push_back(mD(2, 9999 + k));           // n filler messages after it (D, 21 bytes each on the wire): unmatched deletes of an unwatched-order table entry
      send_msgs(q, 0, rl4());
    end
    checkpoint();
  endtask
  task body();
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    for (int s = 0; s < 2; s++) for (int sp = 0; sp < 2; sp++) one_mode(s, sp);
    // 1, 3 and 6 messages a packet with the candidate first, middle and last
    c.strict = 1; c.spec = 0; set_cfg(); idle(10);
    for (int cnt = 1; cnt <= 6; cnt += (cnt == 1 ? 2 : 3)) for (int pos = 0; pos < cnt; pos++) begin
      bq_t q [$];
      for (int k = 0; k < cnt; k++) q.push_back((k == pos) ? mA(0, nref++, "S", 100, 990000 + k) : mD(2, 20000 + k));
      send_msgs(q, 0, rl4());
    end
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- bad frame check sequence
class vseq_badfcs extends vseq_base;
  `uvm_object_utils(vseq_badfcs)
  function new(string name = "vseq_badfcs"); super.new(name); endfunction
  task body();
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    one(mA(0, nref++, "S", 100, 990000));                                  // a good order first
    checkpoint();
    // STRICT: a candidate in a bad frame (1, 3 and 6 messages) produces no order with a good FCS
    one(mA(0, nref++, "S", 100, 990100), 1);
    begin bq_t q [$]; repeat (3) q.push_back(mA(0, nref++, "S", 100, 990200)); send_msgs(q, 1, 1); end
    begin bq_t q [$]; repeat (6) q.push_back(mA(0, nref++, "S", 100, 990300)); send_msgs(q, 1, 0); end
    checkpoint();
    // after a bad frame the flag `untrusted` is set: the next candidates are refused until clr_flags
    one(mA(0, nref++, "S", 100, 990400));
    checkpoint();
    cmd(2); idle(10); seq = 5000;
    one(mA(0, nref++, "S", 100, 990500));
    checkpoint();
    // cut-through mode: the order of a bad frame leaves unless the verdict is known by its last word
    c.strict = 0; set_cfg(); idle(10);
    cmd(2); idle(10); seq = 6000;
    one(mA(0, nref++, "S", 100, 990600), 1);
    cmd(2); idle(10); seq = 6100;
    begin bq_t q [$]; q.push_back(mA(0, nref++, "S", 100, 990700)); for (int k = 0; k < 9; k++) q.push_back(mD(2, 30000 + k)); send_msgs(q, 1); end
    cmd(2); idle(10); seq = 6200;
    begin bq_t q [$]; q.push_back(mA(0, nref++, "S", 100, 990800)); for (int k = 0; k < 3; k++) q.push_back(mD(2, 30100 + k)); send_msgs(q, 1, 1); end
    checkpoint();
    // a bad frame by itself, then good traffic after clr_flags; the bad frame still shows in the book and the counters
    c.strict = 1; set_cfg(); cmd(2); idle(10); seq = 7000;
    one(mA(1, nref++, "B", 10, 991000), 1);
    cmd(2); idle(10); seq = 7100;
    one(mA(1, nref++, "S", 100, 990000));
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- backpressure and bursts: bubbles in the receive words, closely spaced frames, bursts of orders
class vseq_bp extends vseq_base;
  `uvm_object_utils(vseq_bp)
  function new(string name = "vseq_bp"); super.new(name); endfunction
  task body();
    setup(); directory();
    for (int i = 0; i < 4; i++) one(mA(i, nref++, "B", 1000, 994000));
    c.max_pos = 1000000; set_cfg(); idle(10);
    for (int b = 0; b < 4; b++) begin
      int pcts [4] = '{0, 10, 30, 60};
      bubble = pcts[b];
      for (int k = 0; k < 4; k++) begin bq_t q [$]; repeat (1 + k) q.push_back((k % 2 == 0) ? mA(k % 4, nref++, "S", 100, 990000 + k) : mD(2, 40000 + k)); send_msgs(q, 0, rl4()); end
      checkpoint();
    end
    // bursts: several candidates in one packet, and packets that follow each other closely (the order queue holds four behind the frame in flight)
    bubble = 0; gap = 2;
    for (int rep = 0; rep < 4; rep++) begin
      bq_t q [$];
      for (int k = 0; k < 5; k++) q.push_back(mA(k % 4, nref++, "S", 100, 990000 + 10 * k));
      send_msgs(q, 0, rl4(), 120);
    end
    checkpoint();
    gap = 64; c.spec = 1; set_cfg(); idle(10);
    for (int rep = 0; rep < 4; rep++) begin
      bq_t q [$];
      for (int k = 0; k < 4; k++) q.push_back(mA(k % 4, nref++, "S", 100, 990000 + 10 * k));
      send_msgs(q, 0, rl4(), 100);
    end
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- book edge cases
class vseq_book extends vseq_base;
  `uvm_object_utils(vseq_book)
  function new(string name = "vseq_book"); super.new(name); endfunction
  task body();
    longint unsigned r;
    setup(); directory();
    // empty book: a candidate with no bid is refused (band check)
    one(mA(0, nref++, "S", 100, 990000));
    checkpoint();
    one(mA(0, nref++, "B", 500, 995000));
    // an order cancelled, executed in parts, executed with price, deleted, replaced
    r = nref++; one(mA(1, r, "B", 1000, 995000));
    one(mX(1, r, 100)); one(mE(1, r, 300)); one(mE(1, r, 100, 1, 995500)); one(mD(1, r));
    r = nref++; one(mA(1, r, "B", 1000, 996000)); one(mU(1, r, nref, 400, 997000)); r = nref++; one(mD(1, r));
    // more than the remaining shares executed: oover; unknown references: omiss for E, X, D and U
    r = nref++; one(mA(1, r, "S", 100, 1100000)); one(mE(1, r, 500));
    one(mE(1, 777777, 5)); one(mX(1, 777778, 5)); one(mD(1, 777779)); one(mU(1, 777780, 777781, 5, 5));
    // duplicate add (odup) and a table collision: two references with the same low eight bits (oovf), after which orders for the instrument are refused (rej_stale)
    r = nref++; one(mA(2, r, "B", 100, 990000)); one(mA(2, r, "B", 100, 990000));
    one(mA(2, r + 256, "B", 100, 991000));
    one(mA(2, nref++, "S", 100, 990000));
    checkpoint();
    cmd(4); idle(400); cf(CF_READY);                                                           // clr_book: every instrument empty and exact, the directory forgotten
    directory(); one(mA(3, nref++, "B", 500, 995000));
    // ladder overflow: nine distinct ask prices (eight levels per side): lvovf, inexact, refusals
    for (int k = 0; k < 9; k++) one(mA(3, nref++, "S", 100, 1010000 + 1000 * k));
    one(mA(3, nref++, "S", 100, 990000));
    checkpoint();
    // unwatched locate, and a stock directory for a stock not on the watch list
    one(itch_gen::msg_A(999, nref++, "B", 100, "ZZZZ    ", 990000));
    one(itch_gen::msg_R(321, "ZZZZ    "));
    one(itch_gen::msg_A(321, nref++, "S", 100, "ZZZZ    ", 990000));
    // known types with wrong lengths, other types, a zero-share add, a bad side letter
    one(itch_gen::resize(mA(0, nref++, "S", 100, 990000), 30));
    one(itch_gen::resize(mD(0, 1), 25));
    one(itch_gen::msg_other("P", 44)); one(itch_gen::msg_other("Q", 40)); one(itch_gen::msg_other("H", 25));
    one(mA(0, nref++, "S", 0, 990000));
    one(mA(0, nref++, "X", 100, 990000));
    one(mE(0, 1, 0));
    // price zero is never a candidate; a price just at the threshold is
    one(mA(0, nref++, "S", 100, 0)); one(mA(0, nref++, "S", 100, c.thr)); one(mA(0, nref++, "S", 100, c.thr + 1));
    // a bid that moves the best bid: the band follows the book as it is after every earlier message
    r = nref++; one(mA(0, r, "B", 100, 980000)); one(mA(0, nref++, "S", 100, 990000));
    one(mD(0, 1000)); 
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- risk refusals
class vseq_risk extends vseq_base;
  `uvm_object_utils(vseq_risk)
  function new(string name = "vseq_risk"); super.new(name); endfunction
  task cand(int inst = 0, int unsigned px = 990000); one(mA(inst, nref++, "S", 100, px)); endtask
  task body();
    setup(); directory();
    for (int i = 0; i < 4; i++) one(mA(i, nref++, "B", 1000, 995000));
    cand();                                                    // passes
    c.arm = 0; set_cfg(); idle(10); cand(); c.arm = 1;         // not armed
    c.kill = 1; set_cfg(); idle(10); cand(); c.kill = 0;       // kill switch
    c.qty = 0; set_cfg(); idle(10); cand();                    // quantity zero
    c.qty = 2000; set_cfg(); idle(10); cand();                 // above max_qty
    c.qty = 1000; c.max_qty = 5000000; set_cfg(); idle(10); cand();     // passes: 1000
    c.qty = 1000000; c.max_qty = 5000000; set_cfg(); idle(10); cand();  // 1,000,000 or more: refused by the OUCH limit
    c.qty = 999999; c.max_qty = 5000000; c.max_pos = 3000000; set_cfg(); idle(10); cand(); cand(1);   // the largest legal quantity
    cmd(8); idle(5);                                           // clr_pos
    c.qty = 100; c.max_qty = 1000; c.max_pos = 250; set_cfg(); idle(10);
    cand(); cand(); cand(); cand(1); cand(1); cand(1);         // position limit per instrument: two orders each pass, the third is refused
    cmd(8); idle(5);
    c.max_pos = 100000; c.band = 1000; set_cfg(); idle(10);
    cand(0, 996000); cand(0, 995000); cand(0, 996001);         // band: best bid 995000 plus 1000
    c.px_off = 3000; c.band = 5000; set_cfg(); idle(10);
    cand(0, 990000); cand(0, 997001);                          // the order price is price + px_off: 993000 passes; 1000001 is above bid + band
    c.px_off = 0; c.thr = 990000; set_cfg(); idle(10);
    cand(0, 990000); cand(0, 990001);                          // threshold: at it passes, above it is no candidate
    cmd(16); idle(5);                                          // clr_ref: order numbers start again at 1
    c.thr = 1000000; c.halt = 1; set_cfg(); idle(10);
    cand();
    seq += 4; cand();                                          // a gap with halt on: refused
    cand();                                                    // still refused until clr_flags
    cmd(2); idle(10); seq = 9000; cand();
    c.tif = "0"; c.display = "N"; c.capacity = "A"; c.ise = "Y"; c.cross_t = "O"; c.custtype = "Y"; c.minqty = 200; c.tcp_ack = 77777; set_cfg(); idle(10); cand();   // every OUCH field comes from the configuration
    checkpoint();
    cmd(1); idle(5);                                           // clr_cnt
    cand();
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- Ethernet / IP / UDP header checks
class vseq_hdr extends vseq_base;
  `uvm_object_utils(vseq_hdr)
  function new(string name = "vseq_hdr"); super.new(name); endfunction
  task hf(fopts_t o, bit l4 = 0);
    bq_t pay; pay = itch_gen::mold(sess, seq, '{mA(0, nref++, "S", 100, 990000)});
    send_bytes(itch_gen::eth_frame(pay, c, o), 0, l4);
    // dropped frames do not advance the sequence number the design sees: the good packet after them carries the same one
  endtask
  task body();
    fopts_t o;
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    o = itch_gen::no_opts(); o.use_dst_mac = 1; o.dst_mac = 48'h6B_0000_0000_09; hf(o);           // another unicast address
    o = itch_gen::no_opts(); o.ethertype = 16'h86DD; hf(o);                                           // IPv6
    o = itch_gen::no_opts(); o.ethertype = 16'h8100; hf(o);                                           // VLAN tag
    o = itch_gen::no_opts(); o.ver_ihl = 8'h46; hf(o);                                                // IP options (header length 6)
    o = itch_gen::no_opts(); o.ver_ihl = 8'h65; hf(o);                                                // version 6 nibble
    o = itch_gen::no_opts(); o.flags_frag = 16'h6000; hf(o);                                          // more fragments
    o = itch_gen::no_opts(); o.flags_frag = 16'h0010; hf(o);                                          // fragment offset
    o = itch_gen::no_opts(); o.proto = 6; hf(o);                                                      // TCP
    o = itch_gen::no_opts(); o.dst_ip = 32'hC0A8_3A63; hf(o);                                         // another address
    o = itch_gen::no_opts(); o.dst_port = 5811; hf(o);                                                // another port
    o = itch_gen::no_opts(); o.udp_len_delta = 3; hf(o);                                              // UDP length disagrees with the IP length
    o = itch_gen::no_opts(); o.udp_len_delta = -8; hf(o);
    o = itch_gen::no_opts(); o.bad_ip_ck = 1; hf(o);                                                  // header checksum
    checkpoint();
    // the group's multicast MAC is accepted when the feed address is a multicast address
    c.feed_ip = 32'hEF01_0203; set_cfg(); idle(10);
    o = itch_gen::no_opts(); o.dst_ip = 32'hEF01_0203; o.use_dst_mac = 1; o.dst_mac = 48'h03_0201_5E00_01; hf(o);
    o = itch_gen::no_opts(); o.dst_ip = 32'hEF01_0203; hf(o);                                         // our unicast address, multicast group
    c.feed_ip = 32'hC0A8_3A0A; set_cfg(); idle(10);
    checkpoint();
    // a frame that is accepted: every start lane, every length remainder; EN = 0 drops everything
    for (int n = 1; n <= 9; n++) begin bq_t q [$]; for (int k = 0; k < n; k++) q.push_back(mD(2, 50000 + k)); send_msgs(q, 0, n % 2); end
    c.en = 0; set_cfg(); idle(10);
    one(mA(0, nref++, "S", 100, 990000));
    c.en = 1; set_cfg(); idle(10);
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- constrained random: a long mixed stream with anomalies, bad frames, commands and configuration changes
class vseq_rand extends vseq_base;
  `uvm_object_utils(vseq_rand)
  int rounds = 40;
  function new(string name = "vseq_rand"); super.new(name); endfunction
  task body();
    void'($value$plusargs("ROUNDS=%d", rounds));
    setup(); directory();
    for (int i = 0; i < 4; i++) one(mA(i, nref++, "B", 1000, 994000 + 1000 * $urandom_range(2)));
    gap = 70;
    for (int r = 0; r < rounds; r++) begin
      int k; k = $urandom_range(99);
      if (k < 62) begin                                          // ordinary packet
        bq_t q [$]; int n; int szs [5] = '{1, 1, 3, 3, 6}; n = szs[$urandom_range(4)];
        repeat (n) q.push_back(rand_msg());
        bubble = ($urandom_range(3) == 0) ? 1 + $urandom_range(40) : 0;
        send_msgs(q, 0, rl4());
      end else if (k < 68) begin                                 // a gap
        seq += 1 + $urandom_range(4); one(rand_msg());
      end else if (k < 72) begin                                 // a duplicate or an overlap
        bq_t q [$]; q.push_back(rand_msg());
        if (seq > 3) send_pay(itch_gen::mold(sess, seq - 1 - $urandom_range(1), q));
      end else if (k < 77) begin                                 // a bad frame
        one(mD($urandom_range(3), 70000 + r), 1, rl4()); cmd(2); idle(10);    // no candidate in the LAST message of a bad frame: whether the late verdict reaches the risk check first depends on the start lane (README, finding 2)
      end else if (k < 81) begin send_pay(itch_gen::mold_hb(sess, seq));
      end else if (k < 85) begin                                 // a risk or mode change
        case ($urandom_range(6))
          0: c.arm = !c.arm;  1: c.kill = !c.kill;  2: c.halt = !c.halt;  3: c.strict = !c.strict;  4: c.spec = !c.spec;
          5: begin int qs [6] = '{1, 100, 999, 1000, 0, 2000}; c.qty = qs[$urandom_range(5)]; end
          default: begin int os [4] = '{0, 100, 3000, 20000}; c.px_off = os[$urandom_range(3)]; end
        endcase
        set_cfg(); idle(10);
      end else if (k < 88) begin                                 // a command
        case ($urandom_range(3)) 0: cmd(2); 1: cmd(8); 2: cmd(16); default: cmd(1); endcase
        idle(8);
      end else begin                                             // a header fault
        fopts_t o; bq_t pay; o = itch_gen::no_opts();
        case ($urandom_range(3)) 0: o.proto = 6; 1: o.dst_port = 1; 2: o.bad_ip_ck = 1; default: o.ethertype = 16'h86DD; endcase
        pay = itch_gen::mold(sess, seq, '{rand_msg()});
        send_bytes(itch_gen::eth_frame(pay, c, o), 0, rl4());
      end
      if (r % 6 == 5) checkpoint();
    end
    checkpoint();
  endtask
endclass

// ---------------------------------------------------------------------------------------------------------------- the minimal failing test of the finding (README, "Finding"): the TCP sequence number after a poisoned order frame
class vseq_seq_poison extends vseq_base;
  `uvm_object_utils(vseq_seq_poison)
  function new(string name = "vseq_seq_poison"); super.new(name); endfunction
  task body();
    setup(); directory();
    one(mA(0, nref++, "B", 500, 995000));
    one(mA(0, nref++, "S", 100, 990000));                    // order 1: leaves, TCP sequence number 1000
    one(mA(0, nref++, "S", 100, 990100), 1);                 // order 2: in a frame with a bad FCS, STRICT: poisoned, must consume no sequence number
    cmd(2); idle(10); seq = 5000;                            // clr_flags: the bad frame set `untrusted`
    one(mA(0, nref++, "S", 100, 990200));                    // order 3: datasheet says sequence number 1059, the design sends 1118
    checkpoint();
  endtask
endclass
