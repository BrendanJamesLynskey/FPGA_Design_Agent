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
    logic [8:0]  f_p1, f_p2;            // {has byte 13, byte 13} of a frame that ended 1 and 2 clocks ago
    logic [8:0]  f_rq;                  // ... of the request being answered
    always_ff @(posedge clk) begin
        if (rst) begin f_ik <= '0; f_ok <= '0; f_hasx <= 1'b0; f_bx <= '0; f_p1 <= '0; f_p2 <= '0; f_rq <= '0; end
        else begin
            f_p1 <= '0;
            if (s_axis_tvalid) begin
                if (f_ik == 16'd13) begin f_bx <= s_axis_tdata; f_hasx <= 1'b1; end
                if (s_axis_tlast) begin
                    f_p1 <= {f_hasx || f_ik == 16'd13, f_ik == 16'd13 ? s_axis_tdata : f_bx};
                    f_ik <= '0; f_hasx <= 1'b0;
                end else if (f_ik != 16'hFFFF) f_ik <= f_ik + 16'd1;
            end
            f_p2 <= f_p1;
            if (ev_request) f_rq <= f_p2;
            if (m_axis_tvalid && m_axis_tready) f_ok <= m_axis_tlast ? 16'd0 : f_ok + 16'd1;
        end
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        if (m_axis_tvalid && f_ok == 16'd13 && f_rq[8]) assert (m_axis_tdata == f_rq[7:0]);
        if (ev_request) assert (f_p2[8]);
        assert (viol[3:0] == 4'b0000);
        if (m_axis_tvalid) assert (f_req || ev_request);
        if (ev_reply) assert (f_req);
        cover (ev_reply);
    end
endmodule
