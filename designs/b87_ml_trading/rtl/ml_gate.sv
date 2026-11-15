// ml_gate.sv: the model's verdict behind the 58A rule table, selectable at run time.
//
// en = 0: every rule decision passes through unchanged in the same clock (the 58A path, no added clock).
// en = 1: a rule decision for the tracked instrument is held until the model's class for the same message arrives
//         (cls_v), then released; its order is kept only if the class agrees with the order's side (buy needs "up",
//         sell needs "down"); otherwise the decision goes on with fire_order = 0 (vetoed: the rule's pin and log
//         actions still happen) and the veto counter counts it. A decision for another instrument (track = 0)
//         passes through unchanged in the same clock. Added clocks with en = 1: the arm's LATENCY plus 0 (the
//         features are registered in the same clock as the rule's own fire register).
// One decision at a time: the next message's decision point is at least 16 clocks later (one Bench Feed message is
// 16 bytes), so the hold register cannot be overwritten while LATENCY < 16; trigger_core allows at most 8 (see docs/arms.md).
// Changing en while a decision is held: the held decision is still released by its class.

module ml_gate #(
    parameter int FW = 150          // width of the packed rule-decision fields
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          en,
    input  logic          track,     // this decision's message is the tracked instrument (registered with fire_v)
    input  logic          fire_v,
    input  logic          fire_order,
    input  logic          fire_side, // 0 buy, 1 sell
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
    logic          held;
    logic          h_order, h_side;
    logic [FW-1:0] h_rest;
    logic          take, rel, agree;
    assign take  = fire_v && en && track;
    assign rel   = held && cls_v;
    assign agree = h_side ? (cls == 2'd0) : (cls == 2'd2);
    always_ff @(posedge clk) begin
        if (rst) begin
            held <= 1'b0;
            vetoes <= '0;
            last_cls <= 2'd1;
        end else begin
            if (take) held <= 1'b1;
            else if (rel) held <= 1'b0;
            if (rel && h_order && !agree && vetoes != '1) vetoes <= vetoes + 1;
            if (cls_v) last_cls <= cls;
        end
        if (take) begin
            h_order <= fire_order;
            h_side  <= fire_side;
            h_rest  <= fire_rest;
        end
    end
    always_comb begin
        if (rel) begin
            o_fire_v = 1'b1; o_fire_order = h_order && agree; o_fire_side = h_side; o_fire_rest = h_rest;
        end else begin
            o_fire_v = fire_v && !take; o_fire_order = fire_order; o_fire_side = fire_side; o_fire_rest = fire_rest;
        end
    end
endmodule
