// Fixture for the contract-test generator (brief 27B P0): an AXI4-Stream register slice, latency 1, back-pressure.
// MUT selects a deliberate contract violation (0 = correct): 1 drops beats while stalled, 2 changes tdata while
// stalled, 3 raises tvalid during reset.
module fx_axis_slice #(
    parameter int W   = 16,
    parameter int MUT = 0
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_axis_tvalid,
    output logic         s_axis_tready,
    input  logic [W-1:0] s_axis_tdata,
    input  logic         s_axis_tlast,
    output logic         m_axis_tvalid,
    input  logic         m_axis_tready,
    output logic [W-1:0] m_axis_tdata,
    output logic         m_axis_tlast
);
    assign s_axis_tready = (MUT == 1) ? 1'b1 : (!m_axis_tvalid || m_axis_tready);
    always_ff @(posedge clk) begin
        if (rst) begin
            m_axis_tvalid <= (MUT == 3);
            m_axis_tdata  <= '0;
            m_axis_tlast  <= 1'b0;
        end else if (s_axis_tready) begin
            m_axis_tvalid <= s_axis_tvalid;
            m_axis_tdata  <= s_axis_tdata;
            m_axis_tlast  <= s_axis_tlast;
        end else if (MUT == 2) begin
            m_axis_tdata  <= m_axis_tdata ^ 1;
        end
    end
endmodule
