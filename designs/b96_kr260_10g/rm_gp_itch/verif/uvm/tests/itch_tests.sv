// itch_tests.sv: the UVM tests of the ITCH/OUCH bench (brief 170). A test picks one virtual sequence; the regression runs them by +UVM_TESTNAME with several seeds.
class itch_base_test extends uvm_test;
  `uvm_component_utils(itch_base_test)
  itch_env env;
  int unsigned seed = 0;
  function new(string name, uvm_component parent); super.new(name, parent); endfunction
  function void build_phase(uvm_phase phase);
    env = itch_env::type_id::create("env", this);
    void'($value$plusargs("SEED=%d", seed));
  endfunction
  virtual function vseq_base make_vseq(); return vseq_smoke::type_id::create("vs"); endfunction
  task run_phase(uvm_phase phase);
    vseq_base vs;
    phase.raise_objection(this);
    fork begin #20ms; `uvm_fatal("WATCHDOG", "the test ran 20 ms of simulated time") end join_none
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

`define ITCH_TEST(NAME, SEQ) \
class NAME extends itch_base_test; \
  `uvm_component_utils(NAME) \
  function new(string name, uvm_component parent); super.new(name, parent); endfunction \
  virtual function vseq_base make_vseq(); return SEQ::type_id::create("vs"); endfunction \
endclass
`ITCH_TEST(t_smoke, vseq_smoke)
`ITCH_TEST(t_mix, vseq_mix)
`ITCH_TEST(t_mold, vseq_mold)
`ITCH_TEST(t_tail, vseq_tail)
`ITCH_TEST(t_badfcs, vseq_badfcs)
`ITCH_TEST(t_bp, vseq_bp)
`ITCH_TEST(t_book, vseq_book)
`ITCH_TEST(t_risk, vseq_risk)
`ITCH_TEST(t_hdr, vseq_hdr)
`ITCH_TEST(t_rand, vseq_rand)
