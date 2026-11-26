// Static branch predictor: purely combinational, RISC-V JAL/JALR/B/CJ/CB.
module static_branch_predict (
  input  logic [31:0] fetch_rdata_i,
  input  logic [31:0] fetch_pc_i,
  input  logic [31:0] register_addr_i,
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic        fetch_valid_i,
  /* verilator lint_on UNUSEDSIGNAL */
  output logic        predict_branch_taken_o,
  output logic [31:0] predict_branch_pc_o
);

  logic [31:0] instr;
  assign instr = fetch_rdata_i;

  logic instr_jal, instr_jalr, instr_b, instr_cj, instr_cb, instr_b_taken;
  assign instr_jal  = (instr[6:0] == 7'h6F);
  assign instr_jalr = (instr[6:0] == 7'h67);
  assign instr_b    = (instr[6:0] == 7'h63);
  assign instr_cj   = (instr[1:0] == 2'b01) && (instr[15:13] == 3'b101);
  assign instr_cb   = (instr[1:0] == 2'b01) && (instr[15:14] == 2'b11);

  logic [31:0] imm_jal_type, imm_jalr_type, imm_b_type, imm_cj_type, imm_cb_type;
  assign imm_jal_type  = {{12{instr[31]}}, instr[19:12], instr[20], instr[30:21], 1'b0};
  assign imm_jalr_type = {{20{instr[31]}}, instr[31:20]} + register_addr_i;
  assign imm_b_type    = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
  assign imm_cj_type   = {{20{instr[12]}}, instr[12], instr[8], instr[10:9], instr[6], instr[7],
                          instr[2], instr[11], instr[5:3], 1'b0};
  assign imm_cb_type   = {{23{instr[12]}}, instr[12], instr[6:5], instr[2], instr[11:10],
                          instr[4:3], 1'b0};

  logic [31:0] branch_imm;
  always_comb begin
    branch_imm = imm_b_type;
    if (instr_jal)  branch_imm = imm_jal_type;
    if (instr_jalr) branch_imm = imm_jalr_type;
    if (instr_b)    branch_imm = imm_b_type;
    if (instr_cj)   branch_imm = imm_cj_type;
    if (instr_cb)   branch_imm = imm_cb_type;
  end

  assign instr_b_taken = (instr_b && imm_b_type[31]) || (instr_cb && imm_cb_type[31]);
  assign predict_branch_taken_o = instr_jal || instr_jalr || instr_cj || instr_b_taken;
  assign predict_branch_pc_o    = fetch_pc_i + branch_imm;

endmodule
