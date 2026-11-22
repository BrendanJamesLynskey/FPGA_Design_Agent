// itch_scoreboard.sv: the scoreboard of the ITCH/OUCH UVM bench (brief 170). Every observation arrives with its clock number; the scoreboard merges the three streams in clock order
// (received frames, configuration/command/reset events, order frames seen on the transmit side), runs the reference model over the inputs, and checks:
//   ORDERS  every order frame that leaves with a good FCS is byte-exact against the model's frame (UserRefNum, symbol, price, quantity, OUCH fields, ClOrdID, appendage, the Ethernet/IP/TCP
//           headers, the TCP sequence number counted over the good frames since the last TCP_LOAD), is in order, and is classed MUST or MAY; no good frame exists for a MUST NOT order; every MUST
//           order appears. A frame with a bad FCS is no order: the receiver's MAC drops it.
//   COUNTERS, US, FLAGS  at a status checkpoint (the quiet clocks before a stat read), every counter and flag the model predicts equals the design's STAT2 word (timing-dependent counters left out).
//   ORDERCNT the design's own order counters (sent, poisoned) against the frames the monitor counted.
`uvm_analysis_imp_decl(_in)
`uvm_analysis_imp_decl(_out)
`uvm_analysis_imp_decl(_cfg)
`uvm_analysis_imp_decl(_stat)

class itch_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(itch_scoreboard)
  uvm_analysis_imp_in   #(in_frame_t,  itch_scoreboard) in_imp;
  uvm_analysis_imp_out  #(out_frame_t, itch_scoreboard) out_imp;
  uvm_analysis_imp_cfg  #(cfg_evt_t,   itch_scoreboard) cfg_imp;
  uvm_analysis_imp_stat #(stat_evt_t,  itch_scoreboard) stat_imp;
  in_frame_t  in_q [$];
  out_frame_t out_q [$];
  cfg_evt_t   cfg_q [$];
  itch_model  m;
  itch_cov    cov;
  int unsigned cmp [string];
  int unsigned mis [string];
  bit [31:0]   tcp_base;
  int unsigned tcp_k, obs_good, obs_bad, last_num;
  bit          seen [exp_order];
  int unsigned n_checkpoints = 0;
  int unsigned pz_since_load = 0, seq_resyncs = 0;
  bit          seq_strict = 0;           // +SEQ_STRICT: a good order whose TCP sequence number is not exactly 59 more than the previous good one is an error (the datasheet's rule)
  localparam int S_ITCH_BASE = 0, S_US_BASE = 45;

  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    in_imp = new("in_imp", this); out_imp = new("out_imp", this); cfg_imp = new("cfg_imp", this); stat_imp = new("stat_imp", this);
    m = new();
    seq_strict = $test$plusargs("SEQ_STRICT");
  endfunction

  function void write_in(in_frame_t f);   in_q.push_back(f); endfunction
  function void write_out(out_frame_t f); out_q.push_back(f); endfunction
  function void write_cfg(cfg_evt_t e);   cfg_q.push_back(e); endfunction

  function void chk(string name, bit ok, string msg);
    if (!cmp.exists(name)) begin cmp[name] = 0; mis[name] = 0; end
    cmp[name]++;
    if (!ok) begin mis[name]++; `uvm_error("SB", $sformatf("[%s] %s", name, msg)) end
  endfunction

  function void drain_ev();
    foreach (m.ev_q[i]) cov.hit(m.ev_q[i]);
    m.ev_q.delete();
  endfunction

  // ---- one order frame seen on the transmit side
  function void observe_out(out_frame_t o);
    string nm; exp_order e; bit found; int unsigned num; bq_t want; int bad_at;
    chk("ORDERS", !o.malformed, $sformatf("a malformed frame on the transmit side (terminate lane %0d)", o.term_lane));
    chk("ORDERS", o.data.size() == 113, $sformatf("an order frame of %0d bytes, expected 113 (before the FCS)", o.data.size()));
    if (o.data.size() != 113) return;
    cov.hit("order_lane0_only");
    if (!o.fcs_ok) begin obs_bad++; pz_since_load++; cov.hit("obs_poisoned"); return; end
    obs_good++; cov.hit("obs_good");
    num = be32(o.data, 58);
    found = 0;
    foreach (m.exp_q[i]) if (m.exp_q[i].num == num && !seen.exists(m.exp_q[i])) begin e = m.exp_q[i]; found = 1; break; end
    chk("ORDERS", found, $sformatf("an order with a good FCS and UserRefNum %0d that the model did not expect (or a second copy)", num));
    if (!found) begin tcp_k++; return; end
    seen[e] = 1;
    chk("ORDERS", e.klass != K_MUSTNOT, $sformatf("an order (UserRefNum %0d) left with a good FCS but must not: %s", num, e.why));
    chk("ORDERS", num > last_num, $sformatf("orders out of order: UserRefNum %0d after %0d", num, last_num));
    last_num = num;
    want = m.order_frame(e, tcp_base + 59 * tcp_k);
    bad_at = -1;
    for (int i = 0; i < 113; i++) if ((i < 38 || i > 41) && want[i] != o.data[i]) begin bad_at = i; break; end
    chk("ORDERS", bad_at < 0, (bad_at < 0) ? "" : $sformatf("order %0d differs at byte %0d: expected %02x, got %02x (frame byte 0 = destination MAC)", num, bad_at, want[bad_at], o.data[bad_at]));
    // the TCP sequence number: 59 more for every segment that left with a good FCS (docs/itch_integration.md sections 4 and 5: a poisoned frame consumes none)
    begin
      bit [31:0] got, exp_s; int j; bit ok_rtl;
      got = be32(o.data, 38); exp_s = tcp_base + 59 * tcp_k;
      if (got == exp_s) chk("SEQ", 1, "");
      else begin
        ok_rtl = 0;
        if (!seq_strict) for (j = 1; j <= pz_since_load; j++) if (got == exp_s + 59 * j) ok_rtl = 1;
        if (ok_rtl) begin
          // KNOWN RTL BUG (README, "Finding"): the order frame builder advances its sequence number for a frame that the multiplexer later poisons (bad FCS of the trigger frame, or STRICT
          // with the verdict still missing); the waiver lets the rest of the regression run and counts every occurrence.
          cov.hit("seq_consumed_by_poison"); seq_resyncs++;
          tcp_base = got - 59 * tcp_k;
        end else chk("SEQ", 0, $sformatf("order %0d: TCP sequence number %0d, expected %0d (%0d good segments since TCP_LOAD, %0d poisoned frames seen)", num, got, exp_s, tcp_k, pz_since_load));
      end
    end
    tcp_k++;
  endfunction

  // ---- end of an observation window: unmatched expectations
  function void finalize_orders();
    foreach (m.exp_q[i]) begin
      exp_order e = m.exp_q[i];
      bit s = seen.exists(e);
      if (e.klass == K_MUST) begin
        chk("ORDERS", s, $sformatf("missing order: UserRefNum %0d (%s) never left with a good FCS", e.num, e.why));
        if (s) cov.hit("obs_must_present");
      end else if (e.klass == K_MAY) begin
        cov.hit(s ? "obs_may_present" : "obs_may_absent");
      end else if (!s) begin
        cov.hit("obs_mustnot_absent");
        if (e.why == "bad FCS, STRICT") cov.hit("xtalk_strict_bad_none");
      end
    end
    m.exp_q.delete(); seen.delete();
  endfunction

  function void apply_cmd(cfg_evt_t e);
    m.cmd(e.cmd_bits);
    if (e.cmd_bits[0]) begin obs_good = 0; obs_bad = 0; cov.hit("cmd_clr_cnt"); end
    if (e.cmd_bits[1]) cov.hit("cmd_clr_flags");
    if (e.cmd_bits[2]) cov.hit("cmd_clr_book");
    if (e.cmd_bits[3]) cov.hit("cmd_clr_pos");
    if (e.cmd_bits[4]) begin last_num = 0; cov.hit("cmd_clr_ref"); end
    if (e.cmd_bits[6]) begin tcp_base = m.cfg.tcp_seq0; tcp_k = 0; pz_since_load = 0; cov.hit("cmd_tcp_load"); end
  endfunction

  // ---- a status checkpoint: process everything up to its clock, finalize the orders, compare the counters
  function void write_stat(stat_evt_t s);
    int unsigned names_n;
    // merge the streams in clock order
    forever begin
      longint unsigned tf, tc, to_; int pick;
      tf = (in_q.size()  > 0 && in_q[0].c_start <= s.cyc) ? in_q[0].c_start : '1;
      tc = (cfg_q.size() > 0 && cfg_q[0].cyc <= s.cyc)    ? cfg_q[0].cyc : '1;
      to_ = (out_q.size() > 0 && out_q[0].c_start <= s.cyc) ? out_q[0].c_start : '1;
      if (tf == '1 && tc == '1 && to_ == '1) break;
      // on a tie the configuration event comes first, then frames, then order frames
      if (tc <= tf && tc <= to_) pick = 1; else if (tf <= to_) pick = 0; else pick = 2;
      case (pick)
        0: begin
          in_frame_t f; f = in_q.pop_front();
          cov.hit($sformatf("align_%0d_l%0d", (f.data.size() + 4) % 8, f.lane4 ? 4 : 0));
          m.frame(f); drain_ev();
        end
        1: begin
          cfg_evt_t e; e = cfg_q.pop_front();
          case (e.kind)
            0: m.cfg = e.c.clone();
            1: apply_cmd(e);
            2: begin finalize_orders(); m.do_reset(); obs_good = 0; obs_bad = 0; tcp_base = 0; tcp_k = 0; pz_since_load = 0; last_num = 0; cov.hit("reset"); end
          endcase
          drain_ev();
        end
        default: begin
          out_frame_t o; o = out_q.pop_front();
          observe_out(o);
        end
      endcase
    end
    finalize_orders();
    compare(s);
    n_checkpoints++;
  endfunction

  function void compare(stat_evt_t s);
    for (int i = 0; i < NC; i++) if (!m.timing_dependent(i)) begin
      bit ok = (m.cnt[i] == s.w[S_ITCH_BASE + i]);
      chk("COUNTERS", ok, $sformatf("counter %0d (%s): model %0d, design %0d", i, cname(i), m.cnt[i], s.w[S_ITCH_BASE + i]));
    end
    for (int i = 0; i < 12; i++) begin
      bit ok = (m.us[i] == s.w[S_US_BASE + i]);
      chk("US", ok, $sformatf("udp_strip counter %0d (%s): model %0d, design %0d", i, uname(i), m.us[i], s.w[S_US_BASE + i]));
    end
    begin
      bit [31:0] fl = s.w[88];
      chk("FLAGS", fl[0] == m.gap_flag, $sformatf("gap flag: model %0d, design %0d", m.gap_flag, fl[0]));
      chk("FLAGS", fl[1] == m.untrusted, $sformatf("untrusted flag: model %0d, design %0d", m.untrusted, fl[1]));
      chk("FLAGS", fl[2] == m.eos_seen, $sformatf("end-of-session flag: model %0d, design %0d", m.eos_seen, fl[2]));
      chk("FLAGS", fl[3] == m.sess_lock, $sformatf("session lock flag: model %0d, design %0d", m.sess_lock, fl[3]));
      for (int i = 0; i < NINST; i++) chk("FLAGS", fl[8 + i] == m.inexact[i], $sformatf("inexact flag %0d: model %0d, design %0d", i, m.inexact[i], fl[8 + i]));
    end
    chk("ORDERCNT", s.w[60] == obs_good, $sformatf("orders sent (counter %0d) vs good order frames seen on the wire (%0d)", s.w[60], obs_good));
    chk("ORDERCNT", (s.w[61] + s.w[62] + s.w[63] + s.w[67]) == obs_bad, $sformatf("poisoned orders (counters %0d) vs bad-FCS order frames seen (%0d)", s.w[61] + s.w[62] + s.w[63] + s.w[67], obs_bad));
  endfunction

  function string cname(int i);
    string n [NC] = '{"pkt","msg","gap","missing","dup","ovlp","sess","hb","eos","short","trunc","badlen","pkt_err","m_a","m_f","m_e","m_c","m_x","m_d","m_u","m_s","m_r","m_skip","m_bad",
      "unwatch","omiss","odup","oovf","lvovf","lvmiss","oover","evdrop","cand","fire","rej_arm","rej_kill","rej_gap","rej_stale","rej_size","rej_pos","rej_band","rej_busy","abort","late_abort","spec"};
    return n[i];
  endfunction
  function string uname(int i);
    string n [12] = '{"frames","fwd","drop_off","drop_mac","drop_type","drop_frag","drop_proto","drop_dip","drop_port","drop_len","drop_ipck","bad_fcs"};
    return n[i];
  endfunction

  function void report_phase(uvm_phase phase);
    foreach (cmp[k]) `uvm_info("SB_SUMMARY", $sformatf("check=%s compared=%0d mismatches=%0d", k, cmp[k], mis[k]), UVM_NONE)
    `uvm_info("SB_SUMMARY", $sformatf("check=SEQ_WAIVED compared=%0d mismatches=0", seq_resyncs), UVM_NONE)
    `uvm_info("SB_SUMMARY", $sformatf("check=CHECKPOINTS compared=%0d mismatches=0", n_checkpoints), UVM_NONE)
    if (in_q.size() > 0 || out_q.size() > 0) `uvm_info("SB_SUMMARY", $sformatf("unprocessed after the last checkpoint: %0d frames in, %0d frames out", in_q.size(), out_q.size()), UVM_NONE)
  endfunction
endclass
