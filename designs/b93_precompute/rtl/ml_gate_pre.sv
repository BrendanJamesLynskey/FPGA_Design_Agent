// ml_gate_pre.sv: the model's verdict behind the 58A rule table, for a class that is computed EARLY (ml_feat_pre).
//
// en = 0: every rule decision passes through unchanged in the same clock (the 58A path, no added clock).
// en = 1, tracked message (trk, set by trk_v when the tracked instrument's message began, cleared by the next
//         msg_inst_v or when its decision is taken):
//   - the class has already arrived (cls_ok, or cls_v in this very clock): the decision is released in the SAME clock
//     with its order kept only if the class agrees with the order's side: no added clock;
//   - the class has not arrived: the decision is held until cls_v, as ml_gate.sv does (added clocks = the wait).
// The veto counter, last class and agreement rule are ml_gate.sv's (buy needs "up" = 2, sell needs "down" = 0).
// A decision for another message (trk = 0) passes through unchanged in the same clock.
// The class of one message is cleared by the next message's msg_inst_v, so a class is never used for another message.

module ml_gate_pre #(
    parameter int FW = 150
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          en,
    input  logic          inst_v,      // msg_inst_v: a new message begins
    input  logic          trk_v,       // the new message is the tracked instrument's (the clock after inst_v)
    input  logic          fire_v,
    input  logic          fire_order,
    input  logic          fire_side,
    input  logic [FW-1:0] fire_rest,
    input  logic          cls_v,
    input  logic [1:0]    cls,
    output logic          o_fire_v,
    output logic          o_fire_order,
    output logic          o_fire_side,
    output logic [FW-1:0] o_fire_rest,
    output logic [31:0]   vetoes,
    output logic [1:0]    last_cls
);
    logic          trk, cls_ok, held, h_order, h_side;
    logic [1:0]    cls_r;
    logic [FW-1:0] h_rest;
    logic          take, have, imm, hold_take, rel;
    logic [1:0]    cls_eff;
    function automatic logic agrees(input logic side, input logic [1:0] c);
        agrees = side ? (c == 2'd0) : (c == 2'd2);
    endfunction
    assign take      = fire_v && en && trk;
    assign have      = cls_ok || cls_v;
    assign cls_eff   = cls_v ? cls : cls_r;
    assign imm       = take && have;
    assign hold_take = take && !have;
    assign rel       = held && cls_v;
    always_ff @(posedge clk) begin
        if (rst) begin
            trk <= 1'b0; cls_ok <= 1'b0; held <= 1'b0; vetoes <= '0; last_cls <= 2'd1;
        end else begin
            if (take) trk <= 1'b0;
            if (inst_v) begin trk <= 1'b0; cls_ok <= 1'b0; end
            if (trk_v) trk <= 1'b1;
            if (cls_v) begin cls_ok <= 1'b1; last_cls <= cls; end
            if (hold_take) held <= 1'b1;
            else if (rel) held <= 1'b0;
            if (rel && h_order && !agrees(h_side, cls) && vetoes != '1) vetoes <= vetoes + 1;
            if (imm && fire_order && !agrees(fire_side, cls_eff) && vetoes != '1) vetoes <= vetoes + 1;
        end
        if (cls_v) cls_r <= cls;
        if (hold_take) begin h_order <= fire_order; h_side <= fire_side; h_rest <= fire_rest; end
    end
    always_comb begin
        if (rel) begin
            o_fire_v = 1'b1; o_fire_order = h_order && agrees(h_side, cls); o_fire_side = h_side; o_fire_rest = h_rest;
        end else if (imm) begin
            o_fire_v = 1'b1; o_fire_order = fire_order && agrees(fire_side, cls_eff); o_fire_side = fire_side;
            o_fire_rest = fire_rest;
        end else begin
            o_fire_v = fire_v && !hold_take; o_fire_order = fire_order; o_fire_side = fire_side; o_fire_rest = fire_rest;
        end
    end
endmodule
