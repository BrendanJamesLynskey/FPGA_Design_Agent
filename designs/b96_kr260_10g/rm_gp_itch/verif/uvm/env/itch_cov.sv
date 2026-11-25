// itch_cov.sv: functional coverage of the ITCH/OUCH bench (brief 170). The bins are named counters (the Basic tier's xcrg refuses to merge covergroup databases, so the merge is done
// on counts that every run prints: "COV <bin> <hits>"); the closure report lists every bin of the plan and the holes. A bin is hit by what the model SAW on the wires (its events),
// by what the monitors saw, or by a cross of the two, never by what a sequence intended.
class itch_cov extends uvm_component;
  `uvm_component_utils(itch_cov)
  int unsigned hits [string];
  string plan [$];
  function new(string name, uvm_component parent);
    super.new(name, parent);
    add_plan();
  endfunction
  function void add(string names);                // space separated
    string tok; int st; st = 0;
    for (int i = 0; i <= names.len(); i++) begin
      if (i == names.len() || names[i] == " ") begin
        if (i > st) begin tok = names.substr(st, i - 1); plan.push_back(tok); hits[tok] = 0; end
        st = i + 1;
      end
    end
  endfunction
  function void add_plan();
    add("msg_S msg_R msg_A msg_F msg_E msg_C msg_X msg_D msg_U m_skip m_badlen m_bad add_buy add_sell");
    add("mpp_1 mpp_3 mpp_6 mpp_other");
    add("gap overlap dup heartbeat eos sess short trunc badlen");
    add("drop_off drop_mac drop_type drop_frag drop_proto drop_dip drop_port drop_len drop_ipck");
    add("odup oovf lvovf oover omiss unwatch");
    add("fire_strict fire_cut fire_spec rej_arm rej_kill rej_gap rej_stale rej_size rej_pos rej_band rej_nobid");
    add("bad_fcs bad_fcs_with_order tail_near_strict tail_far_strict tail_edge_strict tail_near_cut tail_far_cut tail_edge_cut burst_3");
    add("cmd_clr_cnt cmd_clr_flags cmd_clr_book cmd_clr_pos cmd_clr_ref cmd_tcp_load reset");
    add("in_bubbles out_pause_in_frame obs_good obs_poisoned obs_must_present obs_mustnot_absent obs_may_present obs_may_absent");
    for (int k = 0; k < 8; k++) begin add($sformatf("align_%0d_l0", k)); add($sformatf("align_%0d_l4", k)); end
    add("order_lane0_only xtalk_strict_bad_none seq_after_poison");
  endfunction
  function void hit(string b);
    if (!hits.exists(b)) begin plan.push_back(b); hits[b] = 0; end
    hits[b]++;
  endfunction
  function void report_phase(uvm_phase phase);
    foreach (plan[i]) `uvm_info("COV", $sformatf("COV %s %0d", plan[i], hits[plan[i]]), UVM_NONE)
  endfunction
endclass
