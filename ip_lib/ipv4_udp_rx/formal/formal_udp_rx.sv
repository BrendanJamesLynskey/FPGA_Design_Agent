// formal_udp_rx.sv: ipv4_udp_rx under any input bytes, gaps and back-pressure: the AXI-Stream rules of brief 59
// (axis_rules) on m_axis with tuser, tdest and the header fields held steady with the data; the input is not taken
// in the clock after a frame's last byte; nothing leaves without input. Bounded (bmc), plus a cover of a payload's
// last byte leaving (a whole UDP datagram parsed).
module formal_udp_rx (
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
    logic [2:0] m_axis_tdest;
    logic [31:0] m_src_ip, m_dst_ip;
    logic [15:0] m_src_port, m_dst_port, m_len;
    logic m_axis_tvalid, m_axis_tlast, m_axis_tuser, s_axis_tready;
    logic ev_ok, ev_bad_ip, ev_bad_udp, ev_no_port, ev_frag, ev_empty;
    ipv4_udp_rx #(.N_PORTS(2), .CHECK_UDP(1)) dut (.clk, .rst, .own_ip(32'hC0A8_0A02), .ports({16'd5000, 16'd7}),
        .port_en(2'b11), .s_axis_tdata, .s_axis_tvalid, .s_axis_tready, .s_axis_tlast, .s_axis_tuser, .m_axis_tdata,
        .m_axis_tvalid, .m_axis_tready, .m_axis_tlast, .m_axis_tuser, .m_axis_tdest, .m_src_ip, .m_dst_ip, .m_src_port,
        .m_dst_port, .m_len, .ev_ok, .ev_bad_ip, .ev_bad_udp, .ev_no_port, .ev_frag, .ev_empty);
    logic [4:0] viol;
    axis_rules #(.DATA_W(128)) u_rules (.aclk(clk), .aresetn(!rst), .maxlen(16'd0),
        .tdata({m_axis_tdata, 4'd0, m_axis_tuser, m_axis_tdest, m_src_ip, m_dst_ip, m_src_port, m_dst_port, m_len}),
        .tkeep(16'hFFFF), .tstrb(16'hFFFF), .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol));
    logic f_last_in;
    always_ff @(posedge clk) f_last_in <= !rst && s_axis_tvalid && s_axis_tready && s_axis_tlast;
    always_ff @(posedge clk) if (f_past && !rst) begin
        assert (viol[2:0] == 3'b000);
        if (f_last_in) assert (!s_axis_tready);
        if (m_axis_tvalid && !$past(m_axis_tvalid)) assert ($past(s_axis_tvalid) || $past(f_last_in));
        cover (m_axis_tvalid && m_axis_tready && m_axis_tlast && !m_axis_tuser);
    end
endmodule
