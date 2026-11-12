// formal_arp.sv: arp_responder's transmit side under free inputs (any frames, lookups, flushes, back-pressure):
// the AXI-Stream rules of brief 59 (axis_rules: hold, reset) on m_axis, every frame exactly 42 bytes, and no lookup
// answer without a lookup. Bounded (bmc), plus covers of a reply and a request leaving.
module formal_arp (
    input logic        clk,
    input logic [7:0]  s_axis_tdata,
    input logic        s_axis_tvalid, s_axis_tlast, s_axis_tuser,
    input logic        m_axis_tready,
    input logic        lk_valid, flush,
    input logic [31:0] lk_ip
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic rst;
    assign rst = !f_past;
    logic [7:0] m_axis_tdata;
    logic m_axis_tvalid, m_axis_tlast, s_axis_tready, lk_ready, lk_done, lk_hit;
    logic [47:0] lk_mac;
    logic ev_rx_request, ev_rx_reply, ev_tx_reply, ev_tx_request, ev_learn, ev_drop;
    arp_responder #(.CACHE_N(2), .HOLDOFF(3)) dut (.clk, .rst, .own_mac(48'h02_00_00_00_00_01), .own_ip(32'hC0A8_0A02),
        .s_axis_tdata, .s_axis_tvalid, .s_axis_tready, .s_axis_tlast, .s_axis_tuser, .m_axis_tdata, .m_axis_tvalid,
        .m_axis_tready, .m_axis_tlast, .lk_valid, .lk_ip, .lk_ready, .lk_done, .lk_hit, .lk_mac, .flush, .ev_rx_request,
        .ev_rx_reply, .ev_tx_reply, .ev_tx_request, .ev_learn, .ev_drop);
    logic [4:0] viol;
    axis_rules #(.DATA_W(8)) u_rules (.aclk(clk), .aresetn(!rst), .maxlen(16'd42), .tdata(m_axis_tdata), .tkeep(1'b1),
        .tstrb(1'b1), .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol));
    logic [6:0] beats;
    always_ff @(posedge clk) begin
        if (rst) beats <= '0;
        else if (m_axis_tvalid && m_axis_tready) beats <= m_axis_tlast ? 7'd0 : beats + 7'd1;
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        assert (viol[2:0] == 3'b000 && !viol[3]);
        if (m_axis_tvalid && m_axis_tlast) assert (beats == 7'd41);
        if (m_axis_tvalid && !m_axis_tlast) assert (beats < 7'd41);
        assert (s_axis_tready && lk_ready);
        if (lk_done) assert ($past(lk_valid));
        cover (ev_tx_reply);
        cover (ev_tx_request);
    end
endmodule
