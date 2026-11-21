// pcs_mac_scoreboard.sv: the scoreboard of the b96 PCS and MAC UVM bench (brief 112). Five independent checks, each against a reference
// model written in pcs_ref_pkg (not against the RTL's own functions):
//   TXMAC   frames the user offered -> the MAC's XGMII words, word for word (preamble, data, FCS or poisoned FCS, terminate, idles) and the
//           interframe gap (at least 12 byte times, the terminate counted)
//   TXPCS   pcs_tx's TXDATA, clock for clock, against ref_tx_pcs fed the words pcs_tx was offered; adv (the one-in-33 pause) too
//   RXPCS   pcs_rx's registered outputs, clock for clock, against ref_rx_pcs fed the words pcs_rx captured: lock, decoded words, six event pulses
//   RXMAC   mac64_rx's frame outcomes (bytes, length, FCS verdict) in order against ref_mac_rx fed the reference PCS's outputs; abort counts
//   E2E     (clean channel only) the frames received equal the frames sent, with the FCS verdict equal to "not poisoned"
// Streams are paired by clock number: a DUT output sampled at clock n+1 is the result of the inputs sampled at clock n.
`uvm_analysis_imp_decl(_usr)
`uvm_analysis_imp_decl(_macw)
`uvm_analysis_imp_decl(_pin)
`uvm_analysis_imp_decl(_gtx)
`uvm_analysis_imp_decl(_grx)
`uvm_analysis_imp_decl(_rxo)
`uvm_analysis_imp_decl(_rxf)

class pcs_mac_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(pcs_mac_scoreboard)
  uvm_analysis_imp_usr  #(frame_item, pcs_mac_scoreboard) usr_imp;
  uvm_analysis_imp_macw #(smp_txn,    pcs_mac_scoreboard) macw_imp;
  uvm_analysis_imp_pin  #(smp_txn,    pcs_mac_scoreboard) pin_imp;
  uvm_analysis_imp_gtx  #(smp_txn,    pcs_mac_scoreboard) gtx_imp;
  uvm_analysis_imp_grx  #(smp_txn,    pcs_mac_scoreboard) grx_imp;
  uvm_analysis_imp_rxo  #(rxo_txn,    pcs_mac_scoreboard) rxo_imp;
  uvm_analysis_imp_rxf  #(rxf_txn,    pcs_mac_scoreboard) rxf_imp;
  pcs_mac_cov cov;
  bit e2e_en;                           // set by tests that run on a clean channel
  uvm_event ev_locked;                  // triggered when the reference receiver first holds lock

  pcs_ref_pkg::ref_tx_pcs  rtx;
  pcs_ref_pkg::ref_rx_pcs  rrx;
  pcs_ref_pkg::ref_mac_rx  rmac;
  int unsigned compared [string];
  int unsigned mismatch [string];
  int unsigned max_msgs = 8;

  // TXMAC
  frame_item sent_q [$];
  pcs_ref_pkg::xwq_t obs_q [$];
  pcs_ref_pkg::xwq_t cur_words; bit in_frame; int gap_bytes; bit have_prev_frame;
  // TXPCS
  bit [63:0] exp_tx [longint unsigned];
  bit [63:0] dut_tx [longint unsigned];
  // RXPCS
  rxo_txn exp_rx [longint unsigned];
  rxo_txn dut_rx [longint unsigned];
  // RXMAC / E2E
  rxf_txn exp_frames [$];
  rxf_txn dut_frames [$];
  frame_item e2e_q [$];
  int unsigned abort_ref, abort_dut;
  // lock tracking for coverage
  bit had_lock; int slips_since_reset;
  bit frame_open_ref;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    usr_imp = new("usr_imp", this); macw_imp = new("macw_imp", this); pin_imp = new("pin_imp", this); gtx_imp = new("gtx_imp", this);
    grx_imp = new("grx_imp", this); rxo_imp = new("rxo_imp", this); rxf_imp = new("rxf_imp", this);
    rtx = new(); rrx = new(); rmac = new();
    ev_locked = new("ev_locked");
    foreach (CHECKS[i]) begin compared[CHECKS[i]] = 0; mismatch[CHECKS[i]] = 0; end
    `uvm_info("SB", $sformatf("checks: %0d", compared.size()), UVM_HIGH)
  endfunction
  localparam string CHECKS [6] = '{"TXMAC", "TXMAC_IFG", "TXPCS", "RXPCS", "RXMAC", "E2E"};

  function void fail(string chk, string msg);
    mismatch[chk]++;
    if (mismatch[chk] <= max_msgs) `uvm_error("SB", $sformatf("%s: %s", chk, msg))
  endfunction
  function void ok(string chk); compared[chk]++; endfunction

  // ------------------------------------------------------------------------------------------------ TXMAC
  function void write_usr(frame_item f);
    sent_q.push_back(f);
    if (cov != null) cov.sample_frame(f);
    if (e2e_en) e2e_q.push_back(f);
    cmp_txmac();
  endfunction

  function bit is_idle_word(pcs_ref_pkg::xw_t w); return (w.c == 8'hFF) && (w.d == pcs_ref_pkg::IDLE_D); endfunction

  function void write_macw(smp_txn t);
    pcs_ref_pkg::xw_t w;
    if (t.rst) begin in_frame = 0; cur_words.delete(); have_prev_frame = 0; gap_bytes = 0; return; end
    if (!t.adv) return;                                      // the PCS does not take the word on a pause clock
    w.d = t.d; w.c = t.c;
    if (!in_frame) begin
      if (is_idle_word(w)) begin gap_bytes += 8; end
      else if (w.c == 8'h01 && pcs_ref_pkg::lane(w.d, 0) == pcs_ref_pkg::START) begin
        in_frame = 1; cur_words.delete(); cur_words.push_back(w);
        if (have_prev_frame) begin
          ok("TXMAC_IFG");
          if (gap_bytes < 12) fail("TXMAC_IFG", $sformatf("interframe gap %0d byte times, less than 12", gap_bytes));
          if (cov != null) cov.sample_ifg(gap_bytes, last_tl_mac);
        end
      end else fail("TXMAC", $sformatf("neither idle nor a start between frames: d=%h c=%h", w.d, w.c));
    end else begin
      cur_words.push_back(w);
      for (int k = 0; k < 8; k++) if (w.c == (8'hFF << k) && pcs_ref_pkg::lane(w.d, k) == pcs_ref_pkg::TERM) begin
        in_frame = 0; have_prev_frame = 1; gap_bytes = 8 - k; last_tl_mac = k;
        obs_q.push_back(cur_words); cur_words.delete();
        break;
      end
    end
    cmp_txmac();
  endfunction
  int last_tl_mac;

  function void cmp_txmac();
    while (sent_q.size() > 0 && obs_q.size() > 0) begin
      frame_item f; pcs_ref_pkg::xwq_t got, want; bit same;
      f = sent_q.pop_front(); got = obs_q.pop_front();
      want = pcs_ref_pkg::frame_words(f.as_queue(), 1'b0, f.poison);
      same = (got.size() == want.size());
      if (same) foreach (got[i]) if (got[i].d !== want[i].d || got[i].c !== want[i].c) same = 0;
      ok("TXMAC");
      if (!same) fail("TXMAC", $sformatf("frame of %0d bytes (poison=%0b): %0d words out, %0d expected, first difference at word %0d",
                                        f.len, f.poison, got.size(), want.size(), first_diff(got, want)));
    end
  endfunction
  function int first_diff(pcs_ref_pkg::xwq_t a, pcs_ref_pkg::xwq_t b);
    for (int i = 0; i < a.size() && i < b.size(); i++) if (a[i].d !== b[i].d || a[i].c !== b[i].c) return i;
    return -1;
  endfunction

  // ------------------------------------------------------------------------------------------------ TXPCS
  function void write_pin(smp_txn t);
    bit [63:0] o;
    if (t.rst) begin rtx.reset(); o = '0; end
    else begin
      if (rtx.adv() !== t.adv) fail("TXPCS", $sformatf("adv at clock %0d: DUT %0b, model %0b", t.cyc, t.adv, rtx.adv()));
      o = rtx.step(t.d, t.c);
    end
    if (cov != null && !t.rst && t.adv) for (int i = 0; i < 8; i++) if (t.c[i] && pcs_ref_pkg::lane(t.d, i) == pcs_ref_pkg::ERRC) begin cov.sample_err(EK_ERR_CHAR_XGMII); break; end
    exp_tx[t.cyc] = o;
    cmp_tx(t.cyc + 1);
  endfunction
  function void write_gtx(smp_txn t);
    if (t.cyc == 0) return;
    dut_tx[t.cyc] = t.d;
    cmp_tx(t.cyc);
  endfunction
  function void cmp_tx(longint unsigned m);
    if (m > 0 && exp_tx.exists(m - 1) && dut_tx.exists(m)) begin
      ok("TXPCS");
      if (exp_tx[m - 1] !== dut_tx[m]) fail("TXPCS", $sformatf("TXDATA at clock %0d: DUT %h, model %h", m, dut_tx[m], exp_tx[m - 1]));
      exp_tx.delete(m - 1); dut_tx.delete(m);
    end
  endfunction

  // ------------------------------------------------------------------------------------------------ RXPCS + RXMAC
  function void write_grx(smp_txn t);
    rxo_txn e; int nd;
    if (t.rst) begin rrx.reset(); rmac.reset(); had_lock = 0; slips_since_reset = 0; end
    else begin
      rmac.step(rrx.lock, rrx.x_v, rrx.x_d, rrx.x_c);
      frame_open_ref = (rmac.st != pcs_ref_pkg::ref_mac_rx::R_IDLE);
      rrx.step(t.d);
      while (rmac.done.size() > 0) begin
        pcs_ref_pkg::rx_frame_t rf; rxf_txn x;
        rf = rmac.done.pop_front();
        x = new("exp"); x.aborted = rf.aborted; x.fcs_ok = rf.fcs_ok; x.len = rf.len; x.bytes = rf.bytes;
        if (rf.aborted) abort_ref++; else exp_frames.push_back(x);
        if (cov != null) cov.sample_rxf(rf.s4, rf.tlane, rf.fcs_ok, rf.aborted);
      end
      if (cov != null) begin
        if (rrx.blk_done) cov.sample_blk(rrx.blk_kind, rrx.blk_locked);
        if (rrx.ev_lock) begin cov.sample_lock(had_lock ? LK_RELOCK : LK_ACQUIRE, slips_since_reset); had_lock = 1; ev_locked.trigger(); end
        if (rrx.ev_loss) cov.sample_lock(frame_open_ref ? LK_LOSS_IN_FRAME : LK_LOSS_IDLE);
        if (rrx.ev_slip && !rrx.ev_loss) cov.sample_lock(LK_SLIP_HUNT);
      end
      if (rrx.ev_slip) slips_since_reset++;
    end
    e = new("exp");
    e.lock = rrx.lock; e.x_v = rrx.x_v; e.x_d = rrx.x_d; e.x_c = rrx.x_c; e.x_os = rrx.x_os;
    e.ev_sh_err = rrx.ev_sh_err; e.ev_type_err = rrx.ev_type_err; e.ev_os = rrx.ev_os; e.ev_slip = rrx.ev_slip; e.ev_loss = rrx.ev_loss; e.ev_lock = rrx.ev_lock;
    exp_rx[t.cyc] = e;
    cmp_rx(t.cyc + 1);
    cmp_frames();
  endfunction
  function void write_rxo(rxo_txn o);
    if (o.cyc == 0) return;
    dut_rx[o.cyc] = o;
    cmp_rx(o.cyc);
  endfunction
  function void cmp_rx(longint unsigned m);
    if (m > 0 && exp_rx.exists(m - 1) && dut_rx.exists(m)) begin
      rxo_txn e, d; bit bad;
      e = exp_rx[m - 1]; d = dut_rx[m];
      bad = (e.lock !== d.lock) || (e.x_v !== d.x_v) || (e.x_os !== d.x_os) || (e.events() !== d.events()) || (e.x_v && (e.x_d !== d.x_d || e.x_c !== d.x_c));
      ok("RXPCS");
      if (bad) fail("RXPCS", $sformatf("clock %0d: DUT lock=%0b v=%0b os=%0b ev=%b d=%h c=%h; model lock=%0b v=%0b os=%0b ev=%b d=%h c=%h",
                                       m, d.lock, d.x_v, d.x_os, d.events(), d.x_d, d.x_c, e.lock, e.x_v, e.x_os, e.events(), e.x_d, e.x_c));
      exp_rx.delete(m - 1); dut_rx.delete(m);
    end
  endfunction

  function void write_rxf(rxf_txn f);
    if (f.aborted) begin abort_dut++; if (e2e_en) fail("E2E", "mac64_rx aborted a frame on a clean channel"); return; end
    dut_frames.push_back(f);
    cmp_frames();
  endfunction
  function void cmp_frames();
    while (exp_frames.size() > 0 && dut_frames.size() > 0) begin
      rxf_txn e, d; bit same;
      e = exp_frames.pop_front(); d = dut_frames.pop_front();
      same = (e.len == d.len) && (e.fcs_ok === d.fcs_ok) && (e.bytes.size() == d.bytes.size());
      if (same) foreach (e.bytes[i]) if (e.bytes[i] !== d.bytes[i]) same = 0;
      ok("RXMAC");
      if (!same) fail("RXMAC", $sformatf("frame: DUT len=%0d fcs_ok=%0b bytes=%0d; model len=%0d fcs_ok=%0b bytes=%0d", d.len, d.fcs_ok, d.bytes.size(), e.len, e.fcs_ok, e.bytes.size()));
      if (e2e_en) begin
        frame_item s;
        if (e2e_q.size() == 0) fail("E2E", "frame received that was never sent");
        else begin
          pcs_ref_pkg::bq_t want, fcs;
          s = e2e_q.pop_front(); want = s.as_queue(); fcs = pcs_ref_pkg::fcs_bytes(want, s.poison);
          foreach (fcs[i]) want.push_back(fcs[i]);
          same = (d.bytes.size() == want.size()) && (d.len == int'(want.size())) && (d.fcs_ok === !s.poison);
          if (same) foreach (want[i]) if (want[i] !== d.bytes[i]) same = 0;
          ok("E2E");
          if (!same) fail("E2E", $sformatf("sent %0d bytes poison=%0b; received len=%0d fcs_ok=%0b", s.len, s.poison, d.len, d.fcs_ok));
        end
      end
    end
  endfunction

  // ------------------------------------------------------------------------------------------------ end of test
  function void check_phase(uvm_phase phase);
    if (sent_q.size() != 0) fail("TXMAC", $sformatf("%0d frames offered but never seen on the MAC's output", sent_q.size()));
    if (obs_q.size() != 0) fail("TXMAC", $sformatf("%0d frames on the MAC's output that were not offered", obs_q.size()));
    if (in_frame) fail("TXMAC", "the test ended inside a frame on the MAC's output");
    if (exp_frames.size() != 0) fail("RXMAC", $sformatf("%0d frames the reference receiver found were not reported by mac64_rx", exp_frames.size()));
    if (dut_frames.size() != 0) fail("RXMAC", $sformatf("%0d frames reported by mac64_rx that the reference receiver did not find", dut_frames.size()));
    ok("RXMAC");
    if (abort_ref != abort_dut) fail("RXMAC", $sformatf("aborted frames: DUT %0d, model %0d", abort_dut, abort_ref));
    if (e2e_en && e2e_q.size() != 0) fail("E2E", $sformatf("%0d frames sent were never received", e2e_q.size()));
  endfunction

  function void report_phase(uvm_phase phase);
    foreach (compared[k]) `uvm_info("SB_SUMMARY", $sformatf("check=%s compared=%0d mismatches=%0d", k, compared[k], mismatch[k]), UVM_NONE)
    `uvm_info("SB_SUMMARY", $sformatf("aborts model=%0d dut=%0d frames_model_total=%0d", abort_ref, abort_dut, rmac.n_frames), UVM_NONE)
  endfunction
endclass
