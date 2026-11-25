// itch_agents.sv: the agents of the ITCH/OUCH UVM bench (brief 170).
//   in_agent   active: Ethernet frames as XGMII words into the receive MAC (lane-0 or lane-4 starts, any length, optional bubbles); monitor: the frames the wire carries, with the bench's own CRC verdict
//   out_agent  passive: the XGMII words the transmit MAC hands to the PCS (only clocks where adv is high), assembled into frames with the bench's own CRC verdict
//   cfg_agent  active: reset, configuration words, command pulses, status read-back; monitor: decodes the configuration and command words off the wires

typedef uvm_sequencer #(in_item)  in_sqr_t;
typedef uvm_sequencer #(cfg_item) cfg_sqr_t;

// ------------------------------------------------------------------------------------------------------ in agent
class in_driver extends uvm_driver #(in_item);
  `uvm_component_utils(in_driver)
  virtual itch_in_if vif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual itch_in_if)::get(this, "", "in_vif", vif)) `uvm_fatal("NOVIF", "in_vif not set")
  endfunction
  task drive_idle_word();
    vif.cb.x_v <= 1'b1; vif.cb.x_d <= {8{8'h07}}; vif.cb.x_c <= 8'hFF;
    @(vif.cb);
  endtask
  task run_phase(uvm_phase phase);
    in_item it;
    vif.cb.x_v <= 1'b1; vif.cb.x_d <= {8{8'h07}}; vif.cb.x_c <= 8'hFF;
    forever begin
      seq_item_port.try_next_item(it);
      if (it == null) begin drive_idle_word(); end
      else begin
        if (it.kind == IN_IDLE) repeat (it.idle_n) drive_idle_word();
        else send_frame(it);
        seq_item_port.item_done();
      end
    end
  endtask
  task send_frame(in_item it);
    bit [7:0] bq [$]; bit cq [$];
    bq_t body;
    bit [31:0] fcs;
    body = it.data;
    fcs = crc32(body);
    if (it.bad_fcs) fcs = fcs ^ 32'h0000_0100;
    if (it.lane4) repeat (4) begin bq.push_back(8'h07); cq.push_back(1); end
    bq.push_back(8'hFB); cq.push_back(1);
    repeat (6) begin bq.push_back(8'h55); cq.push_back(0); end
    bq.push_back(8'hD5); cq.push_back(0);
    foreach (body[i]) begin bq.push_back(body[i]); cq.push_back(0); end
    for (int i = 0; i < 4; i++) begin bq.push_back(fcs[8*i +: 8]); cq.push_back(0); end
    bq.push_back(8'hFD); cq.push_back(1);
    while (bq.size() % 8 != 0) begin bq.push_back(8'h07); cq.push_back(1); end
    for (int w = 0; w < bq.size() / 8; w++) begin
      bit [63:0] d; bit [7:0] c;
      for (int l = 0; l < 8; l++) begin d[8*l +: 8] = bq[8*w + l]; c[l] = cq[8*w + l]; end
      if (it.bubble_pct > 0 && w > 0) while ($urandom_range(99) < it.bubble_pct) begin vif.cb.x_v <= 1'b0; @(vif.cb); end
      vif.cb.x_v <= 1'b1; vif.cb.x_d <= d; vif.cb.x_c <= c;
      @(vif.cb);
    end
    repeat (it.gap_after) drive_idle_word();
  endtask
endclass

class in_monitor extends uvm_monitor;
  `uvm_component_utils(in_monitor)
  virtual itch_in_if vif;
  uvm_analysis_port #(in_frame_t) ap;
  xgmii_parser p;
  int unsigned n_bubbles_in_frame = 0;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap = new("ap", this); p = new();
    if (!uvm_config_db#(virtual itch_in_if)::get(this, "", "in_vif", vif)) `uvm_fatal("NOVIF", "in_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    forever begin
      @(vif.cb);
      if (vif.cb.x_v === 1'b1) begin
        for (int l = 0; l < 8; l++) begin
          if (p.push(vif.cb.x_c[l], vif.cb.x_d[8*l +: 8], l, vif.cyc)) begin
            if (!p.last_malformed) ap.write(p.last);
            else `uvm_error("IN_MON", "the bench drove a malformed frame")
          end
        end
      end else if (p.st == 2) n_bubbles_in_frame++;
    end
  endtask
endclass

class in_agent extends uvm_agent;
  `uvm_component_utils(in_agent)
  in_sqr_t sqr; in_driver drv; in_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = in_monitor::type_id::create("mon", this);
    sqr = in_sqr_t::type_id::create("sqr", this);
    drv = in_driver::type_id::create("drv", this);
  endfunction
  function void connect_phase(uvm_phase phase);
    drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass

// ------------------------------------------------------------------------------------------------------ out agent (passive)
class out_monitor extends uvm_monitor;
  `uvm_component_utils(out_monitor)
  virtual itch_out_if vif;
  uvm_analysis_port #(out_frame_t) ap;
  xgmii_parser p;
  int unsigned n_pause_in_frame = 0;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap = new("ap", this); p = new();
    if (!uvm_config_db#(virtual itch_out_if)::get(this, "", "out_vif", vif)) `uvm_fatal("NOVIF", "out_vif not set")
  endfunction
  task run_phase(uvm_phase phase);
    forever begin
      @(vif.cb);
      if (vif.cb.adv === 1'b1) begin
        for (int l = 0; l < 8; l++) begin
          if (p.push(vif.cb.t_c[l], vif.cb.t_d[8*l +: 8], l, vif.cyc)) begin
            out_frame_t o = new();
            o.data = p.last.data; o.fcs_ok = p.last.fcs_ok; o.malformed = p.last_malformed; o.term_lane = p.term_lane; o.c_start = p.last.c_start; o.c_end = p.last.c_end;
            ap.write(o);
          end
        end
      end else if (p.st == 2) n_pause_in_frame++;
    end
  endtask
endclass

// ------------------------------------------------------------------------------------------------------ cfg agent
class cfg_driver extends uvm_driver #(cfg_item);
  `uvm_component_utils(cfg_driver)
  virtual itch_cfg_if vif;
  uvm_analysis_port #(stat_evt_t) ap_stat;
  bit [1023:0] cw_vec;
  bit [7:0]    cmd_seq = 0;
  itch_cfg     cur;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap_stat = new("ap_stat", this);
    if (!uvm_config_db#(virtual itch_cfg_if)::get(this, "", "cfg_vif", vif)) `uvm_fatal("NOVIF", "cfg_vif not set")
  endfunction
  function void set_word(int i, bit [31:0] v); cw_vec[32*i +: 32] = v; endfunction
  function void encode(itch_cfg c);
    set_word(0, {26'd0, c.strict, c.halt, c.spec, c.kill, c.arm, c.en});
    set_word(1, c.thr); set_word(2, c.qty); set_word(3, c.max_qty); set_word(4, c.max_pos); set_word(5, c.band); set_word(6, c.px_off); set_word(7, c.minqty);
    set_word(8, {c.ise, c.capacity, c.display, c.tif});
    set_word(9, {16'd0, c.custtype, c.cross_t});
    for (int i = 0; i < 4; i++) begin set_word(10 + 2*i, c.watch[i][31:0]); set_word(11 + 2*i, c.watch[i][63:32]); end
    set_word(18, c.feed_ip); set_word(19, {16'd0, c.feed_port});
    set_word(20, c.tcp_seq0); set_word(21, c.tcp_ack);
  endfunction
  task apply();
    @(vif.cb);
    vif.cb.cfg <= cur.pack_cfg();
    vif.cb.cfg2 <= cw_vec;
  endtask
  task run_phase(uvm_phase phase);
    vif.cb.rst <= 1'b1; vif.cb.cfg <= '0; vif.cb.cfg2 <= '0;
    cur = new(); cur.defaults();
    forever begin
      seq_item_port.get_next_item(req);
      case (req.kind)
        CF_SET: begin cur = req.c.clone(); encode(cur); apply(); repeat (4) @(vif.cb); end
        CF_CMD: begin
          cmd_seq++;
          set_word(22, {8'd0, cmd_seq, req.cmd_bits[15:0]});
          apply(); repeat (6) @(vif.cb);
        end
        CF_RESET: begin
          @(vif.cb); vif.cb.rst <= 1'b1; repeat (6) @(vif.cb); vif.cb.rst <= 1'b0; repeat (4) @(vif.cb);
        end
        CF_STATS: begin
          stat_evt_t s = new();
          repeat (2) @(vif.cb);
          s.cyc = vif.cyc;
          for (int i = 0; i < 96; i++) s.w[i] = vif.cb.stat2[32*i +: 32];
          ap_stat.write(s);
        end
        CF_READY: begin
          int t = 0;
          while (!(vif.cb.stat2[32*88 + 4] === 1'b1) && t < 4000) begin @(vif.cb); t++; end
          if (t >= 4000) `uvm_error("CFG", "the book did not become ready")
        end
      endcase
      seq_item_port.item_done();
    end
  endtask
endclass

class cfg_monitor extends uvm_monitor;
  `uvm_component_utils(cfg_monitor)
  virtual itch_cfg_if vif;
  uvm_analysis_port #(cfg_evt_t) ap;
  bit [1023:0] last_cw; bit [420:0] last_cfg; bit last_rst; bit have;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    ap = new("ap", this);
    if (!uvm_config_db#(virtual itch_cfg_if)::get(this, "", "cfg_vif", vif)) `uvm_fatal("NOVIF", "cfg_vif not set")
  endfunction
  function bit [31:0] cwd(bit [1023:0] v, int i); return v[32*i +: 32]; endfunction
  // decode the configuration off the wires: the register map of itch_pkg2 / docs/register_map.md
  function itch_cfg decode(bit [1023:0] v, bit [420:0] cf);
    itch_cfg c = new();
    c.my_mac = cf[47:0]; c.venue_mac = cf[95:48]; c.my_ip = cf[127:96]; c.venue_ip = cf[159:128]; c.sport = cf[175:160]; c.port_order = cf[207:192];
    {c.strict, c.halt, c.spec, c.kill, c.arm, c.en} = cwd(v, 0)[5:0];
    c.thr = cwd(v, 1); c.qty = cwd(v, 2); c.max_qty = cwd(v, 3); c.max_pos = cwd(v, 4); c.band = cwd(v, 5); c.px_off = cwd(v, 6); c.minqty = cwd(v, 7);
    {c.ise, c.capacity, c.display, c.tif} = cwd(v, 8);
    {c.custtype, c.cross_t} = cwd(v, 9)[15:0];
    for (int i = 0; i < 4; i++) c.watch[i] = {cwd(v, 11 + 2*i), cwd(v, 10 + 2*i)};
    c.feed_ip = cwd(v, 18); c.feed_port = cwd(v, 19)[15:0]; c.tcp_seq0 = cwd(v, 20); c.tcp_ack = cwd(v, 21);
    return c;
  endfunction
  task run_phase(uvm_phase phase);
    forever begin
      cfg_evt_t e;
      @(vif.cb);
      if (vif.rst === 1'b1 && last_rst !== 1'b1) begin
        e = new(); e.cyc = vif.cyc; e.kind = 2; ap.write(e);
      end
      last_rst = vif.rst;
      if (!have || vif.cfg2[32*22 - 1:0] !== last_cw[32*22 - 1:0] || vif.cfg !== last_cfg) begin
        e = new(); e.cyc = vif.cyc; e.kind = 0; e.c = decode(vif.cfg2, vif.cfg); ap.write(e);
      end
      if (have && vif.cfg2[32*22 + 23 : 32*22 + 16] !== last_cw[32*22 + 23 : 32*22 + 16]) begin
        e = new(); e.cyc = vif.cyc; e.kind = 1; e.cmd_bits = vif.cfg2[32*22 +: 16]; ap.write(e);
      end
      last_cw = vif.cfg2; last_cfg = vif.cfg; have = 1;
    end
  endtask
endclass

class cfg_agent extends uvm_agent;
  `uvm_component_utils(cfg_agent)
  cfg_sqr_t sqr; cfg_driver drv; cfg_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = cfg_monitor::type_id::create("mon", this);
    sqr = cfg_sqr_t::type_id::create("sqr", this);
    drv = cfg_driver::type_id::create("drv", this);
  endfunction
  function void connect_phase(uvm_phase phase);
    drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass

class out_agent extends uvm_agent;
  `uvm_component_utils(out_agent)
  out_monitor mon;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    mon = out_monitor::type_id::create("mon", this);
  endfunction
endclass
