// pcs_mac_env.sv: the environment: four agents, the virtual sequencer, the reference-model scoreboard and the coverage collector (brief 112).

class pcs_mac_vsqr extends uvm_sequencer;
  `uvm_component_utils(pcs_mac_vsqr)
  usr_sqr_t  usr;
  xg_sqr_t   xg;
  line_sqr_t line;
  pcs_mac_scoreboard sb;
  virtual sys_if svif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
endclass

class pcs_mac_env extends uvm_env;
  `uvm_component_utils(pcs_mac_env)
  usr_agent  ua;
  xg_agent   xa;
  line_agent la;
  rx_agent   ra;
  pcs_mac_vsqr vsqr;
  pcs_mac_scoreboard sb;
  pcs_mac_cov cov;
  virtual sys_if svif;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    if (!uvm_config_db#(virtual sys_if)::get(this, "", "sys_vif", svif)) `uvm_fatal("NOVIF", "sys_vif not set")
    ua = usr_agent::type_id::create("ua", this);
    xa = xg_agent::type_id::create("xa", this);
    la = line_agent::type_id::create("la", this);
    ra = rx_agent::type_id::create("ra", this);
    vsqr = pcs_mac_vsqr::type_id::create("vsqr", this);
    sb = pcs_mac_scoreboard::type_id::create("sb", this);
    cov = pcs_mac_cov::type_id::create("cov", this);
  endfunction
  function void connect_phase(uvm_phase phase);
    ua.mon.ap.connect(sb.usr_imp);
    xa.mon.ap_mac.connect(sb.macw_imp);
    xa.mon.ap_pin.connect(sb.pin_imp);
    la.mon.ap_tx.connect(sb.gtx_imp);
    la.mon.ap_rx.connect(sb.grx_imp);
    ra.mon.ap_pcs.connect(sb.rxo_imp);
    ra.mon.ap_frame.connect(sb.rxf_imp);
    sb.cov = cov; la.drv.cov = cov;
    vsqr.usr = ua.sqr; vsqr.xg = xa.sqr; vsqr.line = la.sqr; vsqr.sb = sb; vsqr.svif = svif;
  endfunction
endclass
