// formal_pipe.sv: drives rtl/pipe_reg.sv freely after one reset clock. The source numbers its beats 0, 1, 2 ... in
// the data word (W bits, wrapping), so a beat's data is its place in the stream; the sink is free (any m_ready).
// Proved with the slices' invariants: no beat lost, repeated or reordered (what leaves carries the next number), the
// output holds while stalled (AXI-Stream), the chain never holds more beats than it accepted.
module formal_pipe #(
    parameter int W    = 4,
    parameter int N    = 2,
    parameter int MODE = 1
) (
    input  logic         clk,
    input  logic         s_valid,
    input  logic         m_ready
);
    logic f_past = 1'b0;
    logic f_init = 1'b1;                      // high in the reset clock and in the clock after it
    always_ff @(posedge clk) f_past <= 1'b1;
    wire rst = !f_past;
    always_ff @(posedge clk) f_init <= rst;
    wire src_valid = s_valid && !rst && !f_init;      // AXI4-Stream 2.8: tvalid is not raised until a clock after reset is released
    logic [W-1:0] in_cnt, out_cnt;             // the DUT's own ghost counters: beats accepted at its input, delivered at its output
    wire  [W-1:0] s_data = in_cnt;
    logic s_ready, m_valid;
    logic [W-1:0] m_data;
    logic m_last;
    logic [(W/8 > 0 ? W/8 : 1)-1:0] m_keep;
    logic [0:0] m_user;
    pipe_reg #(.W(W), .N(N), .MODE(MODE)) dut (.aclk(clk), .aresetn(!rst), .s_axis_tvalid(src_valid), .s_axis_tready(s_ready),
        .s_axis_tdata(s_data), .s_axis_tlast(1'b0), .s_axis_tkeep('0), .s_axis_tuser(1'b0), .m_axis_tvalid(m_valid),
        .m_axis_tready(m_ready), .m_axis_tdata(m_data), .m_axis_tlast(m_last), .m_axis_tkeep(m_keep), .m_axis_tuser(m_user),
        .f_in_o(in_cnt), .f_out_o(out_cnt));
    // the protocol rules as assertions on both ports (tb/axis_sva.sv); needs the slang front end
`ifdef SVA
    axis_sva #(.DW(W), .KW(1), .UW(1)) chk_s (.aclk(clk), .aresetn(!rst), .tvalid(src_valid), .tready(s_ready), .tdata(s_data), .tlast(1'b0), .tkeep(1'b0), .tuser(1'b0));
    axis_sva #(.DW(W), .KW(1), .UW(1)) chk_m (.aclk(clk), .aresetn(!rst), .tvalid(m_valid), .tready(m_ready), .tdata(m_data), .tlast(m_last), .tkeep(1'b0), .tuser(1'b0));
`endif

    logic f_stall = 1'b0;
    logic f_src_stall = 1'b0;
    logic [W-1:0] f_data_q;
    always_ff @(posedge clk) begin
        f_stall <= m_valid && !m_ready && !rst;
        f_src_stall <= s_valid && !s_ready && !rst;
        f_data_q <= m_data;
    end
    // the source obeys AXI-Stream: a beat that was offered and not accepted is offered again
    always_ff @(posedge clk) if (!f_init && !rst) assume (!f_src_stall || s_valid);
    always_ff @(posedge clk) if (!f_init && !rst) begin
        // order and loss: what leaves is the next beat in the stream
        if (m_valid && m_ready) h_order: assert (m_data == out_cnt);
        // nothing leaves that was not accepted, and the chain's holding is the difference (N = 0 passes the beat straight through)
        if (N == 0) begin
            if (m_valid && m_ready) h_wire: assert (s_valid && s_ready);
            h_wire__ante: cover (m_valid && m_ready);
        end else begin
            h_bound: assert (W'(in_cnt - out_cnt) <= W'(2 * N));
            h_bound__ante: cover (W'(in_cnt - out_cnt) >= W'(N));
        end
        // AXI-Stream: a stalled output stays valid with the same data
        if (f_stall) begin
            h_stall_valid: assert (m_valid);
            h_stall_data: assert (m_data == f_data_q);
        end
        h_order__ante: cover (m_valid && m_ready);
        h_stall__ante: cover (f_stall);
    end
    // reachability: every mode can pass a beat all the way through
    always_ff @(posedge clk) if (!f_init && !rst) c_through: cover (m_valid && m_ready && out_cnt == W'(3));
endmodule
