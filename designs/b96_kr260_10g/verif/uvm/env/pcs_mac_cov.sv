// pcs_mac_cov.sv: functional coverage of the b96 PCS and MAC UVM bench (brief 112).
//
// The covergroups are ordinary SystemVerilog covergroups over enum-typed sample variables. Vivado 2026.1 Basic refuses xcrg (the coverage report and
// merge tool: "license tier BASIC does not meet the requirement", results/112_uvm_pcs_mac/xcrg_refusal.txt), so the bins cannot be read back from xsim's
// own database. Every sample therefore also increments a mirror counter keyed by point and bin name (class cov_db), written to a text file at the
// end of the run; verif/uvm/scripts/cov_merge.py merges the files of all seeds and lists the holes. The covergroups' own percentages
// (get_inst_coverage) are printed too, as a cross-check of the mirror.

typedef enum { LEN_60, LEN_61_64, LEN_65_127, LEN_128_255, LEN_256_511, LEN_512_1023, LEN_1024_1500, LEN_JUMBO } len_cls_e;
typedef enum { GAP_0, GAP_1_3, GAP_4_15, GAP_16_63, GAP_64_255, GAP_256P } gap_cls_e;
typedef enum { IFG_12, IFG_13_15, IFG_16_23, IFG_24_63, IFG_64_511, IFG_512P } ifg_cls_e;
typedef enum { FS_GOOD, FS_BAD } fcs_e;
typedef enum { SL_0, SL_4 } slane_e;
typedef enum { OC_GOOD, OC_BAD_FCS, OC_ABORT } outcome_e;
typedef enum { BL_HUNTING, BL_LOCKED } blklock_e;
typedef enum { EK_SH_ERR, EK_TYPE_ERR, EK_ORDERED_SET, EK_BAD_FCS_TX, EK_ABORT, EK_BIT_FLIP, EK_HDR_BURST, EK_SLIP_INS, EK_SLIP_DEL, EK_ERR_CHAR_XGMII, EK_RX_RESET } err_kind_e;
typedef enum { LK_ACQUIRE, LK_LOSS_IDLE, LK_LOSS_IN_FRAME, LK_SLIP_HUNT, LK_RELOCK } lock_ev_e;
typedef enum { HS_0, HS_1_3, HS_4_10, HS_11P } hunt_e;
typedef enum { LT_HUNT_TO_LOCK, LT_LOCK_TO_HUNT, LT_HUNT_TO_HUNT } lock_tr_e;

class cov_db;
  int unsigned hits [string];
  function void declare(string pt, string bin); string k; k = {pt, "|", bin}; if (!hits.exists(k)) hits[k] = 0; endfunction
  function void hit(string pt, string bin);
    string k; k = {pt, "|", bin};
    if (!hits.exists(k)) `uvm_error("COVDB", $sformatf("sample of undeclared bin %s", k))
    hits[k]++;
  endfunction
endclass

`define DECL_ENUM(DB, PT, TYPE) begin TYPE e_; e_ = e_.first(); forever begin DB.declare(PT, e_.name()); if (e_ == e_.last()) break; e_ = e_.next(); end end

class pcs_mac_cov extends uvm_component;
  `uvm_component_utils(pcs_mac_cov)
  cov_db db;
  // sample variables
  len_cls_e len_cls; bit [2:0] mod8; fcs_e fcs; pat_e pat; gap_cls_e gap_cls;
  ifg_cls_e ifg_cls; bit [2:0] tlane_mac;
  slane_e slane; bit [2:0] tlane_rx; outcome_e outcome;
  pcs_ref_pkg::blk_kind_e blkk; blklock_e blkl;
  err_kind_e errk;
  lock_ev_e lockk; hunt_e hunt; lock_tr_e lock_tr;

  covergroup cg_frame;
    cp_len:  coverpoint len_cls;
    cp_mod8: coverpoint mod8;
    cp_fcs:  coverpoint fcs;
    cp_pat:  coverpoint pat;
    cp_gap:  coverpoint gap_cls;
    x_len_fcs: cross cp_len, cp_fcs;
    x_len_gap: cross cp_len, cp_gap;
  endgroup
  covergroup cg_ifg;
    cp_ifg:   coverpoint ifg_cls;
    cp_tlane: coverpoint tlane_mac;
  endgroup
  covergroup cg_rxf;
    cp_slane:   coverpoint slane;
    cp_tlane:   coverpoint tlane_rx iff (outcome != OC_ABORT);
    cp_outcome: coverpoint outcome;
    x_slane_tlane: cross cp_slane, cp_tlane;
    x_outcome_slane: cross cp_outcome, cp_slane;
  endgroup
  covergroup cg_blk;
    cp_blk: coverpoint blkk;
    cp_bl:  coverpoint blkl;
    x_blk_lock: cross cp_blk, cp_bl;
  endgroup
  covergroup cg_err;
    cp_err: coverpoint errk;
  endgroup
  covergroup cg_lock;
    cp_lock: coverpoint lockk;
    cp_hunt: coverpoint hunt;
    cp_tr:   coverpoint lock_tr;
  endgroup

  function new(string name, uvm_component parent);
    super.new(name, parent);
    db = new();
    cg_frame = new(); cg_ifg = new(); cg_rxf = new(); cg_blk = new(); cg_err = new(); cg_lock = new();
    `DECL_ENUM(db, "frame.len", len_cls_e) `DECL_ENUM(db, "frame.fcs", fcs_e) `DECL_ENUM(db, "frame.pat", pat_e) `DECL_ENUM(db, "frame.gap", gap_cls_e)
    for (int i = 0; i < 8; i++) begin db.declare("frame.mod8", $sformatf("%0d", i)); db.declare("ifg.tlane", $sformatf("%0d", i)); db.declare("rxf.tlane", $sformatf("%0d", i)); end
    begin len_cls_e l; fcs_e f; l = l.first(); forever begin f = f.first(); forever begin db.declare("frame.len x fcs", {l.name(), ",", f.name()}); if (f == f.last()) break; f = f.next(); end if (l == l.last()) break; l = l.next(); end end
    `DECL_ENUM(db, "ifg.bytes", ifg_cls_e)
    `DECL_ENUM(db, "rxf.slane", slane_e) `DECL_ENUM(db, "rxf.outcome", outcome_e)
    begin len_cls_e l; gap_cls_e g; l = l.first(); forever begin g = g.first(); forever begin db.declare("frame.len x gap", {l.name(), ",", g.name()}); if (g == g.last()) break; g = g.next(); end if (l == l.last()) break; l = l.next(); end end
    begin outcome_e oc; oc = oc.first(); forever begin db.declare("rxf.outcome x slane", {oc.name(), ",SL_0"}); db.declare("rxf.outcome x slane", {oc.name(), ",SL_4"}); if (oc == oc.last()) break; oc = oc.next(); end end
    begin pcs_ref_pkg::blk_kind_e k; k = k.first(); forever begin db.declare("block.kind x lock", {k.name(), ",BL_HUNTING"}); db.declare("block.kind x lock", {k.name(), ",BL_LOCKED"}); if (k == k.last()) break; k = k.next(); end end
    for (int s = 0; s < 2; s++) for (int i = 0; i < 8; i++) db.declare("rxf.slane x tlane", $sformatf("%s,%0d", (s == 0) ? "SL_0" : "SL_4", i));
    `DECL_ENUM(db, "block.kind", pcs_ref_pkg::blk_kind_e)
    `DECL_ENUM(db, "error.kind", err_kind_e)
    `DECL_ENUM(db, "lock.event", lock_ev_e) `DECL_ENUM(db, "lock.hunt_slips_before_first_lock", hunt_e) `DECL_ENUM(db, "lock.transition", lock_tr_e)
  endfunction

  static function len_cls_e classify_len(int unsigned n);
    if (n <= 60) return LEN_60; if (n <= 64) return LEN_61_64; if (n <= 127) return LEN_65_127; if (n <= 255) return LEN_128_255;
    if (n <= 511) return LEN_256_511; if (n <= 1023) return LEN_512_1023; if (n <= 1500) return LEN_1024_1500; return LEN_JUMBO;
  endfunction
  static function gap_cls_e classify_gap(int unsigned n);
    if (n == 0) return GAP_0; if (n <= 3) return GAP_1_3; if (n <= 15) return GAP_4_15; if (n <= 63) return GAP_16_63; if (n <= 255) return GAP_64_255; return GAP_256P;
  endfunction
  static function ifg_cls_e classify_ifg(int unsigned n);
    if (n <= 12) return IFG_12; if (n <= 15) return IFG_13_15; if (n <= 23) return IFG_16_23; if (n <= 63) return IFG_24_63; if (n <= 511) return IFG_64_511; return IFG_512P;
  endfunction

  // the payload pattern, recovered from the bytes the monitor saw (the monitor does not know the sequence's choice)
  static function pat_e classify_pat(frame_item f);
    bit z = 1, o = 1, c = 1, a = 1;
    foreach (f.payload[i]) begin
      if (f.payload[i] != 8'h00) z = 0;
      if (f.payload[i] != 8'hFF) o = 0;
      if (f.payload[i] != 8'(i)) c = 0;
      if (f.payload[i] != ((i % 2) ? 8'h55 : 8'hAA)) a = 0;
    end
    if (z) return PAT_ZEROS; if (o) return PAT_ONES; if (c) return PAT_COUNT; if (a) return PAT_ALT; return PAT_RANDOM;
  endfunction
  function void sample_frame(frame_item f);
    len_cls = classify_len(f.len); mod8 = 3'(f.len % 8); fcs = f.poison ? FS_BAD : FS_GOOD; pat = classify_pat(f); gap_cls = classify_gap(f.gap);
    cg_frame.sample();
    db.hit("frame.len", len_cls.name()); db.hit("frame.mod8", $sformatf("%0d", mod8)); db.hit("frame.fcs", fcs.name()); db.hit("frame.pat", pat.name());
    db.hit("frame.gap", gap_cls.name()); db.hit("frame.len x fcs", {len_cls.name(), ",", fcs.name()}); db.hit("frame.len x gap", {len_cls.name(), ",", gap_cls.name()});
    if (f.poison) sample_err(EK_BAD_FCS_TX);
  endfunction
  function void sample_ifg(int unsigned bytes, int tlane);
    ifg_cls = classify_ifg(bytes); tlane_mac = 3'(tlane);
    cg_ifg.sample();
    db.hit("ifg.bytes", ifg_cls.name()); db.hit("ifg.tlane", $sformatf("%0d", tlane));
  endfunction
  function void sample_rxf(bit lane4, int tlane, bit fcs_ok, bit aborted);
    slane = lane4 ? SL_4 : SL_0; tlane_rx = 3'(tlane); outcome = aborted ? OC_ABORT : (fcs_ok ? OC_GOOD : OC_BAD_FCS);
    cg_rxf.sample();
    db.hit("rxf.outcome", outcome.name()); db.hit("rxf.slane", slane.name()); db.hit("rxf.outcome x slane", {outcome.name(), ",", slane.name()});
    if (!aborted) begin
      db.hit("rxf.tlane", $sformatf("%0d", tlane)); db.hit("rxf.slane x tlane", $sformatf("%s,%0d", slane.name(), tlane));
    end else sample_err(EK_ABORT);
  endfunction
  // a block the receive PCS decoded, with the lock state it was decoded in (hunting blocks are not delivered; only locked ones raise error events)
  function void sample_blk(pcs_ref_pkg::blk_kind_e k, bit locked);
    blkk = k; blkl = locked ? BL_LOCKED : BL_HUNTING; cg_blk.sample();
    db.hit("block.kind", k.name()); db.hit("block.kind x lock", {k.name(), ",", blkl.name()});
    if (!locked) return;
    if (k == pcs_ref_pkg::BK_BADSH) sample_err(EK_SH_ERR);
    if (k == pcs_ref_pkg::BK_BADTYPE) sample_err(EK_TYPE_ERR);
    if (k == pcs_ref_pkg::BK_OS) sample_err(EK_ORDERED_SET);
  endfunction
  function void sample_err(err_kind_e k);
    errk = k; cg_err.sample(); db.hit("error.kind", k.name());
  endfunction
  function void sample_lock(lock_ev_e k, int slips_before = 0);
    lockk = k; hunt = (slips_before == 0) ? HS_0 : (slips_before <= 3) ? HS_1_3 : (slips_before <= 10) ? HS_4_10 : HS_11P;
    lock_tr = (k == LK_ACQUIRE || k == LK_RELOCK) ? LT_HUNT_TO_LOCK : (k == LK_SLIP_HUNT) ? LT_HUNT_TO_HUNT : LT_LOCK_TO_HUNT;
    cg_lock.sample();
    db.hit("lock.event", k.name()); db.hit("lock.transition", lock_tr.name());
    if (k == LK_ACQUIRE) db.hit("lock.hunt_slips_before_first_lock", hunt.name());
  endfunction

  function void report_phase(uvm_phase phase);
    string path; int fd; int unsigned tot = 0, hit = 0;
    `uvm_info("COV", $sformatf("native covergroup coverage: frame %0.1f%% ifg %0.1f%% rxf %0.1f%% block %0.1f%% error %0.1f%% lock %0.1f%%",
              cg_frame.get_inst_coverage(), cg_ifg.get_inst_coverage(), cg_rxf.get_inst_coverage(), cg_blk.get_inst_coverage(),
              cg_err.get_inst_coverage(), cg_lock.get_inst_coverage()), UVM_LOW)
    foreach (db.hits[k]) begin tot++; if (db.hits[k] > 0) hit++; end
    `uvm_info("COV", $sformatf("mirror bins hit %0d of %0d (%0.1f%%)", hit, tot, 100.0 * hit / tot), UVM_LOW)
    if ($value$plusargs("COV_OUT=%s", path)) begin
      fd = $fopen(path, "w");
      foreach (db.hits[k]) $fdisplay(fd, "%s|%0d", k, db.hits[k]);
      $fclose(fd);
    end
  endfunction
endclass
