// Static branch predictor: purely combinational, no clock, no reset, no state.
module static_branch_predict (
  input  logic [31:0] fetch_rdata_i,
  input  logic [31:0] fetch_pc_i,
  input  logic [31:0] register_addr_i,
  input  logic        fetch_valid_i,

  output logic        predict_branch_taken_o,
  output logic [31:0] predict_branch_pc_o,
  output logic [7:0]  predict_confidence_o,
  output logic        predict_exception_o,
  output logic [2:0]  predict_branch_type_o,
  output logic [31:0] predict_branch_offset_o
);
  localparam logic [6:0] OPCODE_BRANCH = 7'h63;
  localparam logic [6:0] OPCODE_JAL    = 7'h6F;
  localparam logic [6:0] OPCODE_JALR   = 7'h67;

  logic [31:0] instr;
  logic [31:0] imm_jal_type, imm_jalr_type, imm_b_type, imm_cj_type, imm_cb_type;
  logic [31:0] branch_imm;
  logic instr_jal, instr_jalr, instr_b, instr_cj, instr_cb;

  assign instr = fetch_rdata_i;

  assign imm_jal_type  = {{12{instr[31]}}, instr[19:12], instr[20], instr[30:21], 1'b0};
  assign imm_jalr_type = {{20{instr[31]}}, instr[31:20]} + register_addr_i;
  assign imm_b_type    = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
  assign imm_cj_type   = {{20{instr[12]}}, instr[12], instr[8], instr[10:9], instr[6], instr[7],
                          instr[2], instr[11], instr[5:3], 1'b0};
  assign imm_cb_type   = {{23{instr[12]}}, instr[12], instr[6:5], instr[2], instr[11:10],
                          instr[4:3], 1'b0};

  assign instr_b    = instr[6:0] == OPCODE_BRANCH;
  assign instr_jal  = instr[6:0] == OPCODE_JAL;
  assign instr_jalr = instr[6:0] == OPCODE_JALR;
  assign instr_cb   = (instr[1:0] == 2'b01) & ((instr[15:13] == 3'b110) | (instr[15:13] == 3'b111));
  assign instr_cj   = (instr[1:0] == 2'b01) & ((instr[15:13] == 3'b101) | (instr[15:13] == 3'b001));

  always_comb begin
    branch_imm            = imm_b_type;
    predict_branch_type_o = 3'b000;
    unique case (1'b1)
      instr_jal:  begin branch_imm = imm_jal_type;  predict_branch_type_o = 3'b001; end
      instr_jalr: begin branch_imm = imm_jalr_type; predict_branch_type_o = 3'b010; end
      instr_b:    begin branch_imm = imm_b_type;    predict_branch_type_o = 3'b011; end
      instr_cj:   begin branch_imm = imm_cj_type;   predict_branch_type_o = 3'b100; end
      instr_cb:   begin branch_imm = imm_cb_type;   predict_branch_type_o = 3'b101; end
      default: ;
    endcase
  end

  always_comb begin
    predict_confidence_o = 8'd0;
    if (fetch_valid_i) begin
      if (predict_branch_type_o == 3'b011 || predict_branch_type_o == 3'b101)
        predict_confidence_o = branch_imm[31] ? 8'd90 : 8'd50;
      else if (predict_branch_type_o != 3'b000)
        predict_confidence_o = 8'd100;
    end
  end

  assign predict_branch_taken_o  = predict_confidence_o > 8'd50;
  assign predict_branch_offset_o = branch_imm;
  assign predict_branch_pc_o     = fetch_pc_i + branch_imm;
  assign predict_exception_o     = (fetch_pc_i[1:0] != 2'b00);
endmodule
