// pcs_mac_agents.sv: the four agents of the b96 PCS and MAC UVM bench (brief 112).
//   usr_agent   active: frames into mac64_tx's source interface; monitor: the frames the MAC accepted
//   xg_agent    active: XGMII words injected straight into pcs_tx (lane-4 frames, error characters, malformed words); monitors: the MAC's output and pcs_tx's input
//   line_agent  active: the GT side. In loopback mode it injects faults into the channel; in line mode it also drives a 66B stream of its own
//               (raw blocks: any block type, any sync header). Monitors: TXDATA and RXDATA.
//   rx_agent    passive: pcs_rx's outputs every clock and mac64_rx's frames

// ------------------------------------------------------------------------------------------------------ usr agent
typedef uvm_sequencer #(frame_item) usr_sqr_t;

class usr_driver extends uvm_driver #(frame_item);
  `uvm_component_utils(usr_driver)
  virtual usr_if vif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual usr_if)::get(this, "", "usr_vif", vif)) `uvm_fatal("NOVIF", "usr_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    vif.cb.s_valid <= 0; vif.cb.s_last <= 0; vif.cb.s_data <= '0; vif.cb.s_nb1 <= '0; vif.cb.s_poison <= 0;
    forever begin
      seq_item_port.get_next_item(req);
      drive_frame(req);
      seq_item_port.item_done();
    end
  endtask
  task drive_frame(frame_item f);
    int unsigned nw; bit last; bit [63:0] w;
    repeat (f.gap) begin
      vif.cb.s_valid <= 0; vif.cb.s_last <= 0; vif.cb.s_poison <= 0;
      @(vif.cb);
    end
    nw = (f.len + 7) / 8;
    for (int unsigned i = 0; i < nw; i++) begin
      last = (i == nw - 1);
      w = '0;
      for (int b = 0; b < 8; b++) if (i * 8 + b < f.len) w[8*b +: 8] = f.payload[i * 8 + b];
      vif.cb.s_valid <= 1; vif.cb.s_data <= w; vif.cb.s_last <= last;
      vif.cb.s_nb1 <= last ? 3'(f.len - i * 8 - 1) : 3'd7;
      vif.cb.s_poison <= last ? f.poison : (f.noise_poison ? 1'($urandom()) : 1'b0);
      do @(vif.cb); while (!vif.cb.s_ready);       // the word is taken at the edge where s_ready (sampled before it) was high
    end
    vif.cb.s_valid <= 0; vif.cb.s_last <= 0; vif.cb.s_poison <= 0;
  endtask
endclass

class usr_monitor extends uvm_monitor;
  `uvm_component_utils(usr_monitor)
  virtual usr_if vif;
  uvm_analysis_port #(frame_item) ap;        // one item per frame whose last word the MAC took
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap = new("ap", this);
    if (!uvm_config_db#(virtual usr_if)::get(this, "", "usr_vif", vif)) `uvm_fatal("NOVIF", "usr_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    bit [7:0] bytes [$]; int unsigned idle = 0; frame_item f; bit in_frame = 0; int unsigned gap = 0;
    forever begin
      @(vif.cb);
      if (vif.cb.s_valid === 1'b1 && vif.cb.s_ready === 1'b1) begin
        if (!in_frame) begin in_frame = 1; gap = idle; end
        for (int b = 0; b < ((vif.cb.s_last) ? int'(vif.cb.s_nb1) + 1 : 8); b++) bytes.push_back(vif.cb.s_data[8*b +: 8]);
        if (vif.cb.s_last) begin
          f = frame_item::type_id::create("seen");
          f.len = bytes.size(); f.payload = new[bytes.size()]; foreach (bytes[i]) f.payload[i] = bytes[i];
          f.poison = vif.cb.s_poison; f.gap = gap;
          ap.write(f);
          bytes.delete(); in_frame = 0; idle = 0;
        end
      end else if (!in_frame && vif.cb.s_valid !== 1'b1) idle++;
    end
  endtask
endclass

class usr_agent extends uvm_agent;
  `uvm_component_utils(usr_agent)
  usr_sqr_t sqr; usr_driver drv; usr_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = usr_monitor::type_id::create("mon", this);
    sqr = usr_sqr_t::type_id::create("sqr", this);
    drv = usr_driver::type_id::create("drv", this);
  endfunction
  function void connect_phase(uvm_phase phase); drv.seq_item_port.connect(sqr.seq_item_export); endfunction
endclass

// ------------------------------------------------------------------------------------------------------ xg agent
typedef uvm_sequencer #(xg_item) xg_sqr_t;

class xg_driver extends uvm_driver #(xg_item);
  `uvm_component_utils(xg_driver)
  virtual xg_if vif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual xg_if)::get(this, "", "xg_vif", vif)) `uvm_fatal("NOVIF", "xg_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    vif.cb.direct <= 0;
    forever begin
      seq_item_port.get_next_item(req);
      foreach (req.words[i]) begin
        vif.cb.direct <= 1; vif.cb.dx_d <= req.words[i].d; vif.cb.dx_c <= req.words[i].c;
        do @(vif.cb); while (vif.cb.adv !== 1'b1);   // pcs_tx takes the word at the edge where adv (sampled before it) was high
      end
      vif.cb.direct <= 0;
      seq_item_port.item_done();
    end
  endtask
endclass

class xg_monitor extends uvm_monitor;
  `uvm_component_utils(xg_monitor)
  virtual xg_if vif;
  uvm_analysis_port #(smp_txn) ap_mac;       // every clock: the MAC's output word and adv (a word counts when adv is high)
  uvm_analysis_port #(smp_txn) ap_pin;       // every clock: the word at pcs_tx's input and adv
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap_mac = new("ap_mac", this); ap_pin = new("ap_pin", this);
    if (!uvm_config_db#(virtual xg_if)::get(this, "", "xg_vif", vif)) `uvm_fatal("NOVIF", "xg_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    longint unsigned cyc = 0; smp_txn a, b;
    forever begin
      @(vif.cb);
      a = new("mac"); a.cyc = cyc; a.rst = (vif.cb.rst_tx !== 1'b0); a.adv = (vif.cb.adv === 1'b1); a.d = vif.cb.xm_d; a.c = vif.cb.xm_c;
      b = new("pin"); b.cyc = cyc; b.rst = a.rst; b.adv = a.adv; b.d = vif.cb.p_d; b.c = vif.cb.p_c;
      ap_mac.write(a); ap_pin.write(b);
      cyc++;
    end
  endtask
endclass

class xg_agent extends uvm_agent;
  `uvm_component_utils(xg_agent)
  xg_sqr_t sqr; xg_driver drv; xg_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = xg_monitor::type_id::create("mon", this);
    sqr = xg_sqr_t::type_id::create("sqr", this);
    drv = xg_driver::type_id::create("drv", this);
  endfunction
  function void connect_phase(uvm_phase phase); drv.seq_item_port.connect(sqr.seq_item_export); endfunction
endclass

// ------------------------------------------------------------------------------------------------------ line agent
typedef uvm_sequencer #(line_item) line_sqr_t;

class line_driver extends uvm_driver #(line_item);
  `uvm_component_utils(line_driver)
  virtual line_if vif;
  virtual sys_if  svif;
  pcs_ref_pkg::ref_scr scr;
  pcs_ref_pkg::blk_t   blkq [$];             // blocks waiting to be put on the line
  bit [319:0]          acc; int fill;
  bit                  started;
  // one-shot and level controls written by the item thread, applied by the stream loop
  bit [63:0]   pend_flip; int pend_hdr, pend_skip; bit pend_ins, pend_del; int pend_rst; int ber_ppm;
  // statistics for the report
  int unsigned n_flips, n_hdr, n_ins, n_del, n_rst, n_blocks;
  pcs_mac_cov cov;                           // set by the env: stimulus kinds are sampled here
  function new(string name, uvm_component parent); super.new(name, parent); scr = new(); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual line_if)::get(this, "", "line_vif", vif)) `uvm_fatal("NOVIF", "line_vif not set")
    if (!uvm_config_db#(virtual sys_if)::get(this, "", "sys_vif", svif)) `uvm_fatal("NOVIF", "sys_vif not set")
  endfunction

  task run_phase(uvm_phase phase);
    fork stream_loop(); item_loop(); join
  endtask

  // the item thread: blocks go to the queue (throttled), the others take effect once the queued blocks have gone out
  task item_loop();
    forever begin
      seq_item_port.get_next_item(req);
      case (req.kind)
        L_BLOCKS: begin
          if (!svif.line_mode) `uvm_error("LINEDRV", "L_BLOCKS item in loopback mode")
          foreach (req.blks[i]) begin
            while (blkq.size() >= 4) @(vif.cb);
            blkq.push_back(req.blks[i]); n_blocks++;
          end
        end
        L_FLIP:     begin drain(); pend_flip = req.mask; n_flips++; if (cov != null) cov.sample_err(EK_BIT_FLIP); end
        L_HDR:      begin drain(); pend_hdr = int'(req.n); pend_skip = int'(req.skip); n_hdr++; if (cov != null) cov.sample_err(EK_HDR_BURST); end
        L_SLIP_INS: begin drain(); pend_ins = 1; n_ins++; if (cov != null) cov.sample_err(EK_SLIP_INS); end
        L_SLIP_DEL: begin drain(); pend_del = 1; n_del++; if (cov != null) cov.sample_err(EK_SLIP_DEL); end
        L_WAIT:     begin drain(); repeat (req.n) @(vif.cb); end
        L_RXRESET:  begin drain(); pend_rst = int'(req.n); n_rst++; if (cov != null) cov.sample_err(EK_RX_RESET); repeat (req.n + 2) @(vif.cb); end
        L_BER:      begin drain(); ber_ppm = int'(req.n); end
      endcase
      seq_item_port.item_done();
    end
  endtask
  task drain(); while (blkq.size() > 0) @(vif.cb); endtask

  // the stream loop: one clock at a time
  task stream_loop();
    bit [63:0] flip; bit first; pcs_ref_pkg::blk_t b; bit [65:0] bits; pcs_ref_pkg::xw_t iw;
    iw = pcs_ref_pkg::idle_word();
    forever begin
      @(vif.cb);
      flip = pend_flip; pend_flip = '0;
      if (ber_ppm > 0 && $urandom_range(999999) < ber_ppm * 64) begin flip[$urandom_range(63)] ^= 1'b1; n_flips++; if (cov != null) cov.sample_err(EK_BIT_FLIP); end
      vif.cb.flip_mask <= flip;
      vif.cb.hdr_load <= (pend_hdr > 0); vif.cb.hdr_cnt <= 16'(pend_hdr); vif.cb.hdr_skip <= 8'(pend_skip); pend_hdr = 0;
      vif.cb.slip_ins <= pend_ins; vif.cb.slip_del <= pend_del; pend_ins = 0; pend_del = 0;
      vif.cb.rst_rx_req <= (pend_rst > 0); if (pend_rst > 0) pend_rst--;
      if (!svif.line_mode || svif.rst_tx) begin
        vif.cb.drv_valid <= 0; vif.cb.drv_first <= 0; vif.cb.drv_word <= '0;
        started = 0; fill = 0; acc = '0; scr.reset();
        if (svif.rst_tx) blkq.delete();
      end else begin
        first = !started; started = 1;
        while (fill < 190 && blkq.size() > 0) begin
          b = blkq.pop_front(); bits = {scr.scramble_word(b.p), b.sh};
          acc |= 320'(bits) << fill; fill += 66;
        end
        while (fill < 64) begin
          b = pcs_ref_pkg::encode_block(iw.d, iw.c); bits = {scr.scramble_word(b.p), b.sh};
          acc |= 320'(bits) << fill; fill += 66;
        end
        vif.cb.drv_valid <= 1; vif.cb.drv_first <= first; vif.cb.drv_word <= acc[63:0];
        acc = acc >> 64; fill -= 64;
      end
    end
  endtask
endclass

class line_monitor extends uvm_monitor;
  `uvm_component_utils(line_monitor)
  virtual line_if vif;
  virtual sys_if  svif;
  uvm_analysis_port #(smp_txn) ap_tx;        // every clock: TXDATA of pcs_tx
  uvm_analysis_port #(smp_txn) ap_rx;        // every clock: RXDATA, the word pcs_rx captures
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap_tx = new("ap_tx", this); ap_rx = new("ap_rx", this);
    if (!uvm_config_db#(virtual line_if)::get(this, "", "line_vif", vif)) `uvm_fatal("NOVIF", "line_vif not set")
    if (!uvm_config_db#(virtual sys_if)::get(this, "", "sys_vif", svif)) `uvm_fatal("NOVIF", "sys_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    longint unsigned cyc = 0; smp_txn t, r;
    forever begin
      @(vif.cb);
      t = new("tx"); t.cyc = cyc; t.rst = (svif.rst_tx !== 1'b0); t.d = vif.cb.gt_tx_d;
      r = new("rx"); r.cyc = cyc; r.rst = (vif.cb.rst_rx !== 1'b0); r.d = vif.cb.gt_rx_d;
      ap_tx.write(t); ap_rx.write(r);
      cyc++;
    end
  endtask
endclass

class line_agent extends uvm_agent;
  `uvm_component_utils(line_agent)
  line_sqr_t sqr; line_driver drv; line_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = line_monitor::type_id::create("mon", this);
    sqr = line_sqr_t::type_id::create("sqr", this);
    drv = line_driver::type_id::create("drv", this);
  endfunction
  function void connect_phase(uvm_phase phase); drv.seq_item_port.connect(sqr.seq_item_export); endfunction
endclass

// ------------------------------------------------------------------------------------------------------ rx agent (passive)
class rx_monitor extends uvm_monitor;
  `uvm_component_utils(rx_monitor)
  virtual rx_if vif;
  uvm_analysis_port #(rxo_txn) ap_pcs;       // every clock: the receive PCS's registered outputs
  uvm_analysis_port #(rxf_txn) ap_frame;     // one per frame outcome of mac64_rx (frame at m_end, abort at m_err)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap_pcs = new("ap_pcs", this); ap_frame = new("ap_frame", this);
    if (!uvm_config_db#(virtual rx_if)::get(this, "", "rx_vif", vif)) `uvm_fatal("NOVIF", "rx_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    longint unsigned cyc = 0; rxo_txn o; rxf_txn f;
    rxf_txn accs [$]; rxf_txn cur = null;
    forever begin
      @(vif.cb);
      o = new("rxo"); o.cyc = cyc; o.rst = (vif.cb.rst_rx !== 1'b0);
      o.lock = vif.cb.lock; o.x_v = vif.cb.x_v; o.x_os = vif.cb.x_os; o.x_d = vif.cb.x_d; o.x_c = vif.cb.x_c;
      o.ev_sh_err = vif.cb.ev_sh_err; o.ev_type_err = vif.cb.ev_type_err; o.ev_os = vif.cb.ev_os;
      o.ev_slip = vif.cb.ev_slip; o.ev_loss = vif.cb.ev_loss; o.ev_lock = vif.cb.ev_lock;
      ap_pcs.write(o);
      begin
        // the sample is the state after the previous edge, so a reset asserted at this edge does not hide it; the accumulators are cleared after it
        // frames: rx_sop opens one, m_v words extend the newest, m_err abandons the newest, m_end closes the oldest (it can arrive after the next sop)
        if (vif.cb.rx_sop === 1'b1) begin cur = new("acc"); accs.push_back(cur); end
        if (vif.cb.m_v === 1'b1) begin
          if (cur == null) begin cur = new("acc"); accs.push_back(cur); end
          for (int b = 0; b < int'(vif.cb.m_nb); b++) cur.bytes.push_back(vif.cb.m_d[8*b +: 8]);
        end
        if (vif.cb.m_err === 1'b1) begin
          if (accs.size() > 0) void'(accs.pop_back());
          cur = null;
          f = new("abort"); f.cyc = cyc; f.aborted = 1; ap_frame.write(f);
        end
        if (vif.cb.m_end === 1'b1) begin
          if (accs.size() > 0) f = accs.pop_front(); else f = new("orphan");
          if (accs.size() == 0) cur = null;
          f.cyc = cyc; f.aborted = 0; f.fcs_ok = vif.cb.m_fcs_ok; f.len = int'(vif.cb.m_len);
          ap_frame.write(f);
        end
      end
      if (o.rst) begin accs.delete(); cur = null; end
      cyc++;
    end
  endtask
endclass

class rx_agent extends uvm_agent;
  `uvm_component_utils(rx_agent)
  rx_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase); mon = rx_monitor::type_id::create("mon", this); endfunction
endclass
