// axis_demo_fifo: a 16-deep AXI4-Stream FIFO, the brief 59A stream demonstration target, with seeded bugs selected at
// run time. TDATA, TKEEP, TSTRB and TLAST travel together; the output is the head entry (stable until popped).
// bug_sel (0: none):
//   1 LOSE_LAST  a beat accepted while the output is stalled loses its TLAST   -> no rule; the sink's TLAST check catches it
//   2 KEEP_WIRE  output TKEEP wired from the input port (a wiring slip)        -> stream rule 0 (HOLD) under back-pressure
module axis_demo_fifo #(
    parameter int DATA_W = 32
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic [1:0]          bug_sel,
    input  logic [DATA_W-1:0]   s_tdata,
    input  logic [DATA_W/8-1:0] s_tkeep,
    input  logic [DATA_W/8-1:0] s_tstrb,
    input  logic                s_tlast,
    input  logic                s_tvalid,
    output logic                s_tready,
    output logic [DATA_W-1:0]   m_tdata,
    output logic [DATA_W/8-1:0] m_tkeep,
    output logic [DATA_W/8-1:0] m_tstrb,
    output logic                m_tlast,
    output logic                m_tvalid,
    input  logic                m_tready
);
    localparam int KW = DATA_W / 8;
    localparam int EW = DATA_W + 2 * KW + 1;
    logic [EW-1:0] mem [16];
    logic [3:0]    wp = '0, rp = '0;
    logic [4:0]    n = '0;
    initial for (int i = 0; i < 16; i++) mem[i] = '0;
    assign s_tready = (n != 5'd16);
    assign m_tvalid = (n != 5'd0);
    wire [EW-1:0] h = mem[rp];
    assign m_tdata = h[EW-1 -: DATA_W];
    assign m_tkeep = (bug_sel == 2'd2) ? s_tkeep : h[2*KW : KW+1];
    assign m_tstrb = (bug_sel == 2'd2) ? s_tstrb : h[KW : 1];
    assign m_tlast = h[0];
    wire push = s_tvalid && s_tready, pop = m_tvalid && m_tready;
    wire lose = (bug_sel == 2'd1) && m_tvalid && !m_tready;
    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            wp <= '0; rp <= '0; n <= '0;
        end else begin
            if (push) begin mem[wp] <= {s_tdata, s_tkeep, s_tstrb, s_tlast && !lose}; wp <= wp + 1'b1; end
            if (pop) rp <= rp + 1'b1;
            n <= n + (push ? 5'd1 : 5'd0) - (pop ? 5'd1 : 5'd0);
        end
    end
endmodule
