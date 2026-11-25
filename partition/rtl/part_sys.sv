// part_sys.sv: the synthetic "large system" generator of brief 151, as a parameterised module. NM sub-modules (part_stage, logic
// depth D) in a chain, with a boundary before the first, between each pair and after the last (NM + 1 boundaries). A boundary is
// chosen by HS and STAGES:
//   HS 0 FWD, 1 SKID, 2 FULL, 3 HALF, 4 COMB: pipe_reg MODE 0..4 with N = STAGES slices (valid/ready, AXI4-Stream)
//   HS 5 PLAIN: STAGES plain registers on data and valid, no ready (the sink must always be ready; the cheapest boundary)
//   HS 6 CREDIT: credit_chan with LF = LB = STAGES, CREDITS = 2 * STAGES + 2 (full rate), STAGES >= 1
// STAGES = 0 puts a wire at every boundary: no registers in the system at all (the unpartitioned extreme).
// KEEP 1 puts (* keep_hierarchy = "yes" *) on every sub-module, so synthesis cannot optimise across its boundary; 0 leaves it free.
// Latency, throughput and data are checked in tests/test_partition_sim.py; area from Yosys and timing from Vivado are in
// partition/README.md (Vivado runs are queued, not run).
module part_sys #(
    parameter int W      = 64,
    parameter int NM     = 8,
    parameter int D      = 2,
    parameter int HS     = 1,
    parameter int STAGES = 1,
    parameter int KEEP   = 0
) (
    input  logic         aclk,
    input  logic         aresetn,
    input  logic         s_axis_tvalid,
    output logic         s_axis_tready,
    input  logic [W-1:0] s_axis_tdata,
    output logic         m_axis_tvalid,
    input  logic         m_axis_tready,
    output logic [W-1:0] m_axis_tdata
);
    // link i is the boundary before stage i (i = 0..NM); the stage i sits between link i and link i+1
    logic [NM:0]   bv_in, br_in;                 // into boundary i
    logic [NM:0]   bv_out, br_out;               // out of boundary i
    logic [W-1:0]  bd_in  [0:NM];
    logic [W-1:0]  bd_out [0:NM];
    assign bv_in[0]  = s_axis_tvalid;
    assign bd_in[0]  = s_axis_tdata;
    assign s_axis_tready = br_in[0];
    assign m_axis_tvalid = bv_out[NM];
    assign m_axis_tdata  = bd_out[NM];
    assign br_out[NM]    = m_axis_tready;
    genvar i;
    generate
        for (i = 0; i <= NM; i++) begin : g_b
            if (STAGES == 0) begin : g_wire
                assign bv_out[i] = bv_in[i];
                assign bd_out[i] = bd_in[i];
                assign br_in[i]  = br_out[i];
            end else if (HS <= 4) begin : g_pipe
                pipe_reg #(.W(W), .N(STAGES), .MODE(HS)) u (.aclk, .aresetn, .s_axis_tvalid(bv_in[i]), .s_axis_tready(br_in[i]),
                    .s_axis_tdata(bd_in[i]), .s_axis_tlast(1'b0), .s_axis_tkeep('0), .s_axis_tuser(1'b0), .m_axis_tvalid(bv_out[i]),
                    .m_axis_tready(br_out[i]), .m_axis_tdata(bd_out[i]), .m_axis_tlast(), .m_axis_tkeep(), .m_axis_tuser());
            end else if (HS == 5) begin : g_plain
                logic [STAGES-1:0] v;
                logic [W-1:0]      d [0:STAGES-1];
                always_ff @(posedge aclk) begin
                    v[0] <= aresetn && bv_in[i];
                    d[0] <= bd_in[i];
                end
                for (genvar k = 1; k < STAGES; k++) begin : g_s
                    always_ff @(posedge aclk) begin
                        v[k] <= aresetn && v[k-1];
                        d[k] <= d[k-1];
                    end
                end
                assign bv_out[i] = v[STAGES-1];
                assign bd_out[i] = d[STAGES-1];
                assign br_in[i]  = 1'b1;
            end else begin : g_credit
                credit_chan #(.W(W), .CREDITS(2 * STAGES + 2), .LF(STAGES), .LB(STAGES)) u (.aclk, .aresetn, .s_axis_tvalid(bv_in[i]),
                    .s_axis_tready(br_in[i]), .s_axis_tdata(bd_in[i]), .s_axis_tlast(1'b0), .s_axis_tkeep('0), .s_axis_tuser(1'b0),
                    .m_axis_tvalid(bv_out[i]), .m_axis_tready(br_out[i]), .m_axis_tdata(bd_out[i]), .m_axis_tlast(), .m_axis_tkeep(),
                    .m_axis_tuser());
            end
        end
        for (i = 0; i < NM; i++) begin : g_m
            // the sub-module takes its input from boundary i's output and feeds boundary i+1's input
            assign bv_in[i+1] = bv_out[i];
            assign br_out[i]  = br_in[i+1];
            if (KEEP != 0) begin : g_keep
                (* keep_hierarchy = "yes" *) part_stage #(.W(W), .D(D), .ID(i)) u (.x(bd_out[i]), .y(bd_in[i+1]));
            end else begin : g_free
                part_stage #(.W(W), .D(D), .ID(i)) u (.x(bd_out[i]), .y(bd_in[i+1]));
            end
        end
    endgenerate
endmodule
