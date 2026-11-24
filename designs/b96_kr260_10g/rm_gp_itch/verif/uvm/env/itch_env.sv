// itch_env.sv: the environment of the ITCH/OUCH UVM bench (brief 170): the three agents, the virtual sequencer, the scoreboard and the coverage collector.
class itch_vsqr extends uvm_sequencer;
  `uvm_component_utils(itch_vsqr)
  in_sqr_t  in_s;
  cfg_sqr_t cfg_s;
  itch_scoreboard sb;
  virtual itch_cfg_if cvif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
endclass

class itch_env extends uvm_env;
  `uvm_component_utils(itch_env)
  in_agent  ia;
  out_agent oa;
  cfg_agent ca;
  itch_vsqr vsqr;
  itch_scoreboard sb;
  itch_cov cov;
  virtual itch_cfg_if cvif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual itch_cfg_if)::get(this, "", "cfg_vif", cvif)) `uvm_fatal("NOVIF", "cfg_vif not set")
    ia = in_agent::type_id::create("ia", this);
    oa = out_agent::type_id::create("oa", this);
    ca = cfg_agent::type_id::create("ca", this);
    vsqr = itch_vsqr::type_id::create("vsqr", this);
    sb = itch_scoreboard::type_id::create("sb", this);
    cov = itch_cov::type_id::create("cov", this);
  endfunction
  function void connect_phase(uvm_phase phase);
    ia.mon.ap.connect(sb.in_imp);
    oa.mon.ap.connect(sb.out_imp);
    ca.mon.ap.connect(sb.cfg_imp);
    ca.drv.ap_stat.connect(sb.stat_imp);
    sb.cov = cov;
    vsqr.in_s = ia.sqr; vsqr.cfg_s = ca.sqr; vsqr.sb = sb; vsqr.cvif = cvif;
  endfunction
  function void extract_phase(uvm_phase phase);
    if (ia.mon.n_bubbles_in_frame > 0) cov.hit("in_bubbles");
    if (oa.mon.n_pause_in_frame > 0) cov.hit("out_pause_in_frame");
  endfunction
endclass
