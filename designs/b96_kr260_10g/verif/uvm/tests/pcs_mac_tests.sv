// pcs_mac_tests.sv: the UVM tests of the b96 PCS and MAC bench (brief 112). Each test picks the mode (loopback through the real transmit chain, or the
// line agent driving the receiver), the initial bit offset and one virtual sequence. The regression runs them by +UVM_TESTNAME with several seeds.

class pcs_mac_base_test extends uvm_test;
  `uvm_component_utils(pcs_mac_base_test)
  pcs_mac_env env;
  virtual sys_if svif;
  bit          line_mode = 0;
  int unsigned init_off = 0;
  int unsigned seed = 0;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    env = pcs_mac_env::type_id::create("env", this);
    if (!uvm_config_db#(virtual sys_if)::get(this, "", "sys_vif", svif)) `uvm_fatal("NOVIF", "sys_vif not set")
    void'($value$plusargs("SEED=%d", seed));
  endfunction
  virtual function vseq_base make_vseq(); return vseq_smoke::type_id::create("vs"); endfunction
  task run_phase(uvm_phase phase);
    vseq_base vs;
    phase.raise_objection(this);
    fork begin #6ms; `uvm_fatal("WATCHDOG", "the test ran 6 ms of simulated time") end join_none
    svif.apply_reset(line_mode, init_off);
    vs = make_vseq();
    vs.start(env.vsqr);
    phase.drop_objection(this);
  endtask
  function void report_phase(uvm_phase phase);
    uvm_report_server rs; int unsigned errs;
    rs = uvm_report_server::get_server();
    errs = rs.get_severity_count(UVM_ERROR) + rs.get_severity_count(UVM_FATAL);
    `uvm_info("RESULT", $sformatf("%s test=%s seed=%0d errors=%0d", (errs == 0) ? "PASS" : "FAIL", get_type_name(), seed, errs), UVM_NONE)
  endfunction
endclass

class t_smoke extends pcs_mac_base_test;
  `uvm_component_utils(t_smoke)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_smoke::type_id::create("vs"); endfunction
endclass
class t_lens extends pcs_mac_base_test;
  `uvm_component_utils(t_lens)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_lens::type_id::create("vs"); endfunction
endclass
class t_gaps extends pcs_mac_base_test;
  `uvm_component_utils(t_gaps)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_gaps::type_id::create("vs"); endfunction
endclass
class t_badfcs extends pcs_mac_base_test;
  `uvm_component_utils(t_badfcs)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_badfcs::type_id::create("vs"); endfunction
endclass
class t_xg extends pcs_mac_base_test;
  `uvm_component_utils(t_xg)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_xg::type_id::create("vs"); endfunction
endclass
class t_line_blocks extends pcs_mac_base_test;
  `uvm_component_utils(t_line_blocks)
  function new(string name, uvm_component parent); super.new(name, parent); line_mode = 1; endfunction
  virtual function vseq_base make_vseq(); return vseq_line_blocks::type_id::create("vs"); endfunction
endclass
class t_hdr extends pcs_mac_base_test;
  `uvm_component_utils(t_hdr)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_hdr::type_id::create("vs"); endfunction
endclass
class t_slip extends pcs_mac_base_test;
  `uvm_component_utils(t_slip)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_slip::type_id::create("vs"); endfunction
endclass
class t_ber extends pcs_mac_base_test;
  `uvm_component_utils(t_ber)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_ber::type_id::create("vs"); endfunction
endclass
class t_rxreset extends pcs_mac_base_test;
  `uvm_component_utils(t_rxreset)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_rxreset::type_id::create("vs"); endfunction
endclass
class t_offsets extends pcs_mac_base_test;
  `uvm_component_utils(t_offsets)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  virtual function vseq_base make_vseq(); return vseq_offsets::type_id::create("vs"); endfunction
endclass
class t_rand extends pcs_mac_base_test;
  `uvm_component_utils(t_rand)
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    init_off = $urandom_range(131);
  endfunction
  virtual function vseq_base make_vseq(); return vseq_rand::type_id::create("vs"); endfunction
endclass
class t_rand_line extends pcs_mac_base_test;
  `uvm_component_utils(t_rand_line)
  function new(string name, uvm_component parent); super.new(name, parent); line_mode = 1; endfunction
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    init_off = $urandom_range(131);
  endfunction
  virtual function vseq_base make_vseq(); vseq_rand v; v = vseq_rand::type_id::create("vs"); v.line_mode = 1; return v; endfunction
endclass
