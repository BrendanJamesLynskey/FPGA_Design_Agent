// tb_feat_pre.sv: ml_feat_pre against the 87 ml_feat in lockstep on random book and message streams.
//   iverilog -g2012 -o sim tb_feat_pre.sv ../rtl/ml_feat_pre.sv ../../b87_ml_trading/rtl/ml_feat.sv ; vvp sim +N=<messages>
// A message: msg_inst_v at clock c; the book entry (random, edge-heavy: sizes above 255, crossed and equal prices, empty
// sides) is on bk_* from c+1 until the next message; msg_px_v at c+4 with type and side. A fraction of messages never
// reaches msg_px_v (a cut-off frame: not possible on the wire because FCS bytes complete the price field, but the unit
// must not commit state for them); the reference unit never sees those messages. Every vector the early unit computes
// for a message that does reach its price field must equal the reference's vector for it, and the early unit's state
// must be unchanged by the partial ones (the following message proves it). Prints "feat_pre: ... mismatches 0" on success.
`timescale 1ns/1ps
module tb_feat_pre;
    logic clk = 0, rst = 1;
    always #1 clk = ~clk;
    logic [15:0] ml_inst = 16'd3;
    // shared stimulus
    logic        inst_v = 0, px_v = 0;
    logic [7:0]  m_type = 0;
    logic        m_side = 0;
    logic [15:0] m_inst = 0;
    logic        bk_valid = 1;
    logic [31:0] bpx, bsz, apx, asz;
    // dut
    logic trk_v, fv_p; logic [37:0] f_p;
    ml_feat_pre dut (.clk, .rst, .ml_inst, .inst_v, .msg_px_v(px_v), .msg_type(m_type), .msg_side(m_side), .msg_inst(m_inst),
                     .bk_valid, .bk_bid_px(bpx), .bk_bid_sz(bsz), .bk_ask_px(apx), .bk_ask_sz(asz), .trk_v, .feat_v(fv_p), .feat(f_p));
    // reference sees only messages that reach the price field, with its px_v
    logic px_ref = 0;
    logic fv_r; logic [37:0] f_r;
    ml_feat ref_u (.clk, .rst, .ml_inst, .msg_px_v(px_ref), .msg_type(m_type), .msg_side(m_side), .msg_inst(m_inst),
                   .bk_valid, .bk_bid_px(bpx), .bk_bid_sz(bsz), .bk_ask_px(apx), .bk_ask_sz(asz), .feat_v(fv_r), .feat(f_r));
    int n, mism = 0, tracked_done = 0, partial = 0, tracked_partial = 0;
    logic [37:0] pre_hold;
    logic        pre_seen;
    logic [31:0] r = 32'h1234567;
    function automatic int rnd(input int m);
        r = r * 1664525 + 1013904223;
        return int'(r[27:16]) % m;
    endfunction
    function automatic logic [31:0] pick_px();
        case (rnd(8))
            0: return 32'd0; 1: return 32'd10000; 2: return 32'd10001; 3: return 32'd9999;
            4: return 32'd10000 + rnd(40); 5: return 32'd10000 - rnd(40); 6: return 32'd10000 + rnd(3); default: return 32'd9990 + rnd(20);
        endcase
    endfunction
    function automatic logic [31:0] pick_sz();
        case (rnd(6))
            0: return 32'd0; 1: return 32'd1 + rnd(8); 2: return 32'd255; 3: return 32'd256 + rnd(300); 4: return 32'd70000; default: return 32'd1 + rnd(200);
        endcase
    endfunction
    initial begin
        if (!$value$plusargs("N=%d", n)) n = 20000;
        repeat (4) @(posedge clk);
        rst <= 0;
        repeat (3) @(posedge clk);
        for (int i = 0; i < n; i++) begin
            bit complete, tracked;
            complete = (rnd(100) >= 25);
            tracked = (rnd(100) >= 25);
            if (!complete) partial = partial + 1;
            // c: inst_v with msg_inst
            m_inst <= tracked ? 16'd3 : 16'd7; inst_v <= 1;
            @(posedge clk);
            inst_v <= 0;
            // c+1: the book entry for this message is on bk_*
            bpx <= pick_px(); bsz <= pick_sz(); apx <= pick_px(); asz <= pick_sz();
            repeat (2) @(posedge clk);   // c+2, c+3
            // c+4: price field complete
            m_type <= 8'(1 + rnd(4)); m_side <= 1'(rnd(2));
            if (complete) begin px_v <= 1; px_ref <= 1; end
            @(posedge clk);
            px_v <= 0; px_ref <= 0;
            repeat (11 + rnd(3)) @(posedge clk);   // the next message is 16 bytes later
        end
        repeat (8) @(posedge clk);
        $display("feat_pre: n %0d tracked_complete %0d partial %0d mismatches %0d", n, tracked_done, partial, mism);
        $finish;
    end
    // capture the early vector (feat_v) and compare to the reference's vector when the reference produces one
    always @(posedge clk) begin
        if (fv_p) begin pre_hold <= f_p; pre_seen <= 1; end
        if (fv_r) begin
            tracked_done <= tracked_done + 1;
            if (!pre_seen || pre_hold !== f_r) begin
                if (mism < 5) $display("mismatch: pre %h ref %h seen %b", pre_hold, f_r, pre_seen);
                mism <= mism + 1;
            end
            pre_seen <= 0;
        end
        if (inst_v) pre_seen <= 0;
    end
endmodule
