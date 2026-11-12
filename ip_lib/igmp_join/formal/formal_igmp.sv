// formal_igmp.sv: igmp_join's transmit side under free inputs (any received frames, joins and leaves at any time,
// back-pressure): the AXI-Stream rules of brief 59 (axis_rules) on m_axis and every frame exactly 46 bytes. Bounded
// (bmc), plus a cover of a report and a leave leaving.
module formal_igmp (
    input logic       clk,
    input logic [7:0] s_axis_tdata,
    input logic       s_axis_tvalid, s_axis_tlast, s_axis_tuser,
    input logic       m_axis_tready,
    input logic [1:0] group_en
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic rst;
    assign rst = !f_past;
    logic [7:0] m_axis_tdata;
    logic m_axis_tvalid, m_axis_tlast, s_axis_tready, ev_query, ev_report, ev_leave, ev_suppressed;
    igmp_join #(.N_GROUPS(2), .TICK_CLKS(2), .UNSOL_TICKS(2)) dut (.clk, .rst, .own_mac(48'h02_00_00_00_00_01),
        .own_ip(32'hC0A8_0A02), .groups({32'hEF02_0202, 32'hEF01_0101}), .group_en, .s_axis_tdata, .s_axis_tvalid,
        .s_axis_tready, .s_axis_tlast, .s_axis_tuser, .m_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tlast,
        .ev_query, .ev_report, .ev_leave, .ev_suppressed);
    logic [4:0] viol;
    axis_rules #(.DATA_W(8)) u_rules (.aclk(clk), .aresetn(!rst), .maxlen(16'd46), .tdata(m_axis_tdata), .tkeep(1'b1),
        .tstrb(1'b1), .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol));
    logic [6:0] beats;
    always_ff @(posedge clk) begin
        if (rst) beats <= '0;
        else if (m_axis_tvalid && m_axis_tready) beats <= m_axis_tlast ? 7'd0 : beats + 7'd1;
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        assert (viol[3:0] == 4'b0000);
        if (m_axis_tvalid && m_axis_tlast) assert (beats == 7'd45);
        if (m_axis_tvalid && !m_axis_tlast) assert (beats < 7'd45);
        cover (ev_report);
        cover (ev_leave);
    end
endmodule
