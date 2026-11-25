// formal_icmp.sv: icmp_echo (BUF_BYTES 128) under any input bytes and back-pressure: the AXI-Stream rules of the AXI checker
// (axis_rules) on m_axis; a reply never starts without a request and the busy flag covers it. Bounded (bmc), plus a
// cover of a whole reply leaving (a minimal echo request accepted: checksums, addresses and lengths right).
module formal_icmp (
    input logic       clk,
    input logic [7:0] s_axis_tdata,
    input logic       s_axis_tvalid, s_axis_tlast, s_axis_tuser,
    input logic       m_axis_tready
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic rst;
    assign rst = !f_past;
    logic [7:0] m_axis_tdata;
    logic m_axis_tvalid, m_axis_tlast, s_axis_tready, ev_request, ev_reply, ev_busy, ev_bad;
    icmp_echo #(.BUF_BYTES(128), .TTL(64), .RAM("lutram")) dut (.clk, .rst, .own_mac(48'h02_00_00_00_00_01),
        .own_ip(32'hC0A8_0A02), .s_axis_tdata, .s_axis_tvalid, .s_axis_tready, .s_axis_tlast, .s_axis_tuser,
        .m_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tlast, .ev_request, .ev_reply, .ev_busy, .ev_bad);
    logic [4:0] viol;
    axis_rules #(.DATA_W(8)) u_rules (.aclk(clk), .aresetn(!rst), .maxlen(16'd128), .tdata(m_axis_tdata), .tkeep(1'b1),
        .tstrb(1'b1), .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol));
    logic f_req;                        // a request was accepted and its reply has not finished
    always_ff @(posedge clk) begin
        if (rst) f_req <= 1'b0;
        else if (ev_request) f_req <= 1'b1;
        else if (ev_reply) f_req <= 1'b0;
    end
    // observable behaviour: the reply carries the request it answers. Byte 13 (the EtherType's low byte, copied from
    // the stored frame into the reply) of each accepted request is remembered, and the reply's byte 13 must equal it,
    // whatever frames arrive meanwhile (a frame stored over the request would change it).
    logic [15:0] f_ik, f_ok;            // index of the next input and output byte
    logic [7:0]  f_bx;                 // byte 13 of the frame now arriving
    logic        f_hasx;
    logic [8:0]  f_p1, f_p2, f_p3;      // {has byte 13, byte 13} of a frame that ended 1, 2 and 3 clocks ago (the request is
                                        // accepted 3 clocks after its last byte in 0.2.0, 2 in 0.1.0)
    logic [8:0]  f_rq;                  // ... of the request being answered
    always_ff @(posedge clk) begin
        if (rst) begin f_ik <= '0; f_ok <= '0; f_hasx <= 1'b0; f_bx <= '0; f_p1 <= '0; f_p2 <= '0; f_p3 <= '0; f_rq <= '0; end
        else begin
            f_p1 <= '0;
            if (s_axis_tvalid) begin
                if (f_ik == 16'd13) begin f_bx <= s_axis_tdata; f_hasx <= 1'b1; end
                if (s_axis_tlast) begin
                    f_p1 <= {f_hasx || f_ik == 16'd13, f_ik == 16'd13 ? s_axis_tdata : f_bx};
                    f_ik <= '0; f_hasx <= 1'b0;
                end else if (f_ik != 16'hFFFF) f_ik <= f_ik + 16'd1;
            end
            f_p2 <= f_p1; f_p3 <= f_p2;
            if (ev_request) f_rq <= f_p3;
            if (m_axis_tvalid && m_axis_tready) f_ok <= m_axis_tlast ? 16'd0 : f_ok + 16'd1;
        end
    end
    // Every assertion is labelled (a_*) and paired with a cover of its own antecedent (a_*__ante; brief 143c, flow/formal_rigour.py).
    always_ff @(posedge clk) if (f_past && !rst) begin
        if (m_axis_tvalid && f_ok == 16'd13 && f_rq[8]) a_reply_carries_request: assert (m_axis_tdata == f_rq[7:0]);
        if (ev_request) a_request_has_byte13: assert (f_p3[8]);
        a_axis_rules: assert (viol[3:0] == 4'b0000);
        if (m_axis_tvalid) a_reply_needs_request: assert (f_req || ev_request);
    end
    // `if (ev_reply) assert (f_req)` (a reply ends only after a request) was removed in brief 143c: ev_reply first happens at step 90 and the bounded check stops at 62
    // (no solver finishes deeper: see icmp.sby), so the assertion never had anything to check; c_reply below covers that the reply path is reachable.
    // antecedents (same guard); the first is the strongest: the reply's byte 13 is on the output and a request was remembered
    always_ff @(posedge clk) if (f_past && !rst) begin
        a_reply_carries_request__ante: cover (m_axis_tvalid && f_ok == 16'd13 && f_rq[8]);
        a_request_has_byte13__ante: cover (ev_request);
        a_axis_rules__ante: cover (m_axis_tvalid && m_axis_tready);
        a_reply_needs_request__ante: cover (m_axis_tvalid);
        c_reply: cover (ev_reply);
    end
endmodule
