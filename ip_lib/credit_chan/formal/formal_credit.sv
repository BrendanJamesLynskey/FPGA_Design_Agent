// formal_credit.sv: drives rtl/credit_chan.sv freely after one reset clock: the source numbers its beats 0, 1, 2 ...
// in the data word (W bits, wrapping), offers a beat again if it was not accepted (AXI-Stream), and the sink is free.
// The conservation, bound and order properties are in the RTL's `ifdef FORMAL block; this wrapper adds the output rules.
module formal_credit #(
    parameter int W       = 4,
    parameter int CREDITS = 2,
    parameter int LF      = 1,
    parameter int LB      = 1
) (
    input  logic clk,
    input  logic s_valid,
    input  logic m_ready
);
    logic f_past = 1'b0;
    always_ff @(posedge clk) f_past <= 1'b1;
    wire rst = !f_past;
    logic [W-1:0] in_cnt, out_cnt;
    wire  [W-1:0] s_data = in_cnt;
    logic s_ready, m_valid;
    logic [W-1:0] m_data;
    logic f_init = 1'b1, f_stall = 1'b0, f_src_stall = 1'b0;
    always_ff @(posedge clk) f_init <= rst;
    wire src_valid = s_valid && !rst && !f_init;      // AXI4-Stream 2.8: tvalid is not raised until a clock after reset is released
    logic m_last;
    logic [0:0] m_user;
    logic [(W/8 > 0 ? W/8 : 1)-1:0] m_keep;
    credit_chan #(.W(W), .CREDITS(CREDITS), .LF(LF), .LB(LB)) dut (.aclk(clk), .aresetn(!rst), .s_axis_tvalid(src_valid),
        .s_axis_tready(s_ready), .s_axis_tdata(s_data), .s_axis_tlast(1'b0), .s_axis_tkeep('0), .s_axis_tuser(1'b0),
        .m_axis_tvalid(m_valid), .m_axis_tready(m_ready), .m_axis_tdata(m_data), .m_axis_tlast(m_last), .m_axis_tkeep(m_keep),
        .m_axis_tuser(m_user), .f_in_o(in_cnt), .f_out_o(out_cnt));
`ifdef SVA
    axis_sva #(.DW(W), .KW(1), .UW(1)) chk_s (.aclk(clk), .aresetn(!rst), .tvalid(src_valid), .tready(s_ready), .tdata(s_data), .tlast(1'b0), .tkeep(1'b0), .tuser(1'b0));
    axis_sva #(.DW(W), .KW(1), .UW(1)) chk_m (.aclk(clk), .aresetn(!rst), .tvalid(m_valid), .tready(m_ready), .tdata(m_data), .tlast(m_last), .tkeep(1'b0), .tuser(1'b0));
`endif
    logic [W-1:0] f_data_q;
    always_ff @(posedge clk) begin
        f_stall     <= m_valid && !m_ready && !rst;
        f_src_stall <= src_valid && !s_ready && !rst;
        f_data_q    <= m_data;
    end
    always_ff @(posedge clk) if (!f_init && !rst) assume (!f_src_stall || s_valid);
    always_ff @(posedge clk) if (!f_init && !rst) begin
        if (m_valid && m_ready) h_order: assert (m_data == out_cnt);
        if (f_stall) begin
            h_stall_valid: assert (m_valid);
            h_stall_data: assert (m_data == f_data_q);
        end
        h_order__ante: cover (m_valid && m_ready);
        h_stall__ante: cover (f_stall);
    end
    always_ff @(posedge clk) if (!f_init && !rst) c_through: cover (m_valid && m_ready && out_cnt == W'(3));
endmodule
