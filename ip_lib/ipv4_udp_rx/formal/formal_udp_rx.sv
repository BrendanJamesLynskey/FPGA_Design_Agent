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
    // clocks since the last input beat was offered (saturating). The RTL ends a frame in five phases (fin_phase 0..4) after tlast and then puts the held-back last
    // payload byte out, so a beat can leave 7 clocks after the last input beat: "a beat leaves only in the clock after an input beat" (the first form of this property)
    // was false at depth 50, which the old bmc depth of 30 never reached (brief 143c).
    logic [3:0] f_since;
    always_ff @(posedge clk) f_since <= (rst || s_axis_tvalid) ? 4'd0 : (f_since == 4'hF ? 4'hF : f_since + 4'd1);
    // Every assertion is labelled (a_*) and paired with a cover of its own antecedent (a_*__ante; brief 143c, flow/formal_rigour.py).
    always_ff @(posedge clk) if (f_past && !rst) begin
        a_axis_rules: assert (viol[2:0] == 3'b000);
        if (f_last_in) a_no_input_after_last: assert (!s_axis_tready);
        if (m_axis_tvalid && !$past(m_axis_tvalid)) a_output_follows_input: assert (f_since <= 4'd8);     // nothing leaves without input: within 8 clocks of an input beat
    end
    // antecedents (same guard)
    always_ff @(posedge clk) if (f_past && !rst) begin
        a_axis_rules__ante: cover (m_axis_tvalid && m_axis_tready);
        a_no_input_after_last__ante: cover (f_last_in);
        a_output_follows_input__ante: cover (m_axis_tvalid && !$past(m_axis_tvalid));
        c_late_final_beat: cover (m_axis_tvalid && !$past(m_axis_tvalid) && f_since >= 4'd5);   // the delayed final beat is reached: the bound of 8 is not trivially met
        c_datagram_out: cover (m_axis_tvalid && m_axis_tready && m_axis_tlast && !m_axis_tuser);
    end
endmodule
