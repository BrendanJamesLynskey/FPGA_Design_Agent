// formal_udp_tx.sv: ipv4_udp_tx (MAX_PAYLOAD 4) under any payload stream and back-pressure: the AXI-Stream rules of
// brief 59 (axis_rules) on m_axis; every frame sent is 42 header bytes plus the stored payload; the input is not taken
// while a frame is being prepared or sent. Bounded (bmc), plus a cover of a two-byte datagram leaving.
module formal_udp_tx (
    input logic        clk,
    input logic [7:0]  s_axis_tdata,
    input logic        s_axis_tvalid, s_axis_tlast,
    input logic [47:0] s_dst_mac,
    input logic [31:0] s_dst_ip,
    input logic [15:0] s_src_port, s_dst_port,
    input logic        m_axis_tready
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    logic rst;
    assign rst = !f_past;
    logic [7:0] m_axis_tdata;
    logic m_axis_tvalid, m_axis_tlast, s_axis_tready, ev_sent, ev_too_long;
    ipv4_udp_tx #(.MAX_PAYLOAD(4), .CSUM(1), .TTL(64), .RAM("lutram")) dut (.clk, .rst, .own_mac(48'h02_00_00_00_00_01),
        .own_ip(32'hC0A8_0A02), .s_axis_tdata, .s_axis_tvalid, .s_axis_tready, .s_axis_tlast, .s_dst_mac, .s_dst_ip,
        .s_src_port, .s_dst_port, .m_axis_tdata, .m_axis_tvalid, .m_axis_tready, .m_axis_tlast, .ev_sent, .ev_too_long);
    logic [4:0] viol;
    axis_rules #(.DATA_W(8)) u_rules (.aclk(clk), .aresetn(!rst), .maxlen(16'd46), .tdata(m_axis_tdata), .tkeep(1'b1),
        .tstrb(1'b1), .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .viol(viol));
    logic [3:0] f_in;                   // payload bytes taken for the datagram being stored
    logic [3:0] f_n;                    // payload bytes of the datagram being sent
    logic [6:0] f_out;                  // bytes of the current frame already sent
    logic       f_tx;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_n <= '0; f_out <= '0; f_tx <= 1'b0; end
        else begin
            if (s_axis_tvalid && s_axis_tready) begin
                if (s_axis_tlast) begin
                    if (f_in < 4'd4) begin f_n <= f_in + 4'd1; f_tx <= 1'b1; end
                    f_in <= '0;
                end else if (f_in != 4'hF) f_in <= f_in + 4'd1;
            end
            if (m_axis_tvalid && m_axis_tready) begin
                f_out <= m_axis_tlast ? 7'd0 : f_out + 7'd1;
                if (m_axis_tlast) f_tx <= 1'b0;
            end
        end
    end
    always_ff @(posedge clk) if (f_past && !rst) begin
        assert (viol[3:0] == 4'b0000);
        if (m_axis_tvalid) assert (f_tx);
        if (m_axis_tvalid && m_axis_tlast) assert (f_out == 7'd41 + {3'd0, f_n});
        if (m_axis_tvalid && !m_axis_tlast) assert (f_out < 7'd41 + {3'd0, f_n});
        if (f_tx) assert (!s_axis_tready);
        cover (ev_sent && f_n == 4'd2);
    end
endmodule
